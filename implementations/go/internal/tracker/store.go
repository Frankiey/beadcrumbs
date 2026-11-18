package tracker

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func token() (string, error) {
	data := make([]byte, 16)
	if _, err := rand.Read(data); err != nil {
		return "", err
	}
	data[6] = (data[6] & 15) | 64
	data[8] = (data[8] & 63) | 128
	return hex.EncodeToString(data), nil
}
func pathKind(path string, directory, optional bool) (bool, error) {
	info, err := os.Lstat(path)
	if optional && os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if info.Mode()&os.ModeSymlink != 0 || (directory && !info.IsDir()) || (!directory && !info.Mode().IsRegular()) {
		return false, fmt.Errorf("unexpected path type: %s", path)
	}
	return true, nil
}
func manifestExists(root string) (bool, error) {
	path := filepath.Join(root, "store.json")
	exists, err := pathKind(path, false, true)
	if err != nil || !exists {
		return false, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return false, err
	}
	value, err := strictJSON(data)
	if err != nil {
		return false, err
	}
	object, ok := value.(map[string]any)
	if !ok || object["format"] != "beadcrumbs" || fmt.Sprint(object["version"]) != "1" || !exact(value, "format", "version") {
		return false, fmt.Errorf("unsupported or invalid manifest")
	}
	// A string "1" must not satisfy the numeric manifest version.
	if _, ok := object["version"].(interface{ Int64() (int64, error) }); !ok {
		return false, fmt.Errorf("invalid version")
	}
	return true, nil
}
func mkdir(path string) error {
	err := os.Mkdir(path, 0700)
	if err != nil && !os.IsExist(err) {
		return err
	}
	_, err = pathKind(path, true, false)
	return err
}
func locked(root string, initialize bool, action func() (any, error)) (result any, err error) {
	if initialize {
		if err = mkdir(root); err != nil {
			return nil, err
		}
	}
	if _, err = pathKind(root, true, false); err != nil {
		return nil, err
	}
	exists, err := manifestExists(root)
	if err != nil {
		return nil, err
	}
	lock := filepath.Join(root, ".writer.lock")
	if !exists && !initialize {
		busy, e := pathKind(lock, true, true)
		if e != nil {
			return nil, e
		}
		if busy {
			return nil, failure(5, "store busy")
		}
		exists, e = manifestExists(root)
		if e != nil {
			return nil, e
		}
		if !exists {
			return nil, fmt.Errorf("store uninitialized")
		}
	}
	if err = os.Mkdir(lock, 0700); err != nil {
		if !os.IsExist(err) {
			return nil, err
		}
		// The holder may remove the lock before we inspect it; that is still busy.
		if _, err = pathKind(lock, true, true); err != nil {
			return nil, err
		}
		return nil, failure(5, "store busy")
	}
	defer func() {
		if unlock := os.Remove(lock); unlock != nil {
			err = unlock
		}
	}()
	return action()
}
func publish(path string, payload []byte) (err error) {
	id, err := token()
	if err != nil {
		return err
	}
	scratch := filepath.Join(filepath.Dir(path), ".tmp-"+id)
	file, err := os.OpenFile(scratch, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer func() {
		if remove := os.Remove(scratch); remove != nil && !os.IsNotExist(remove) && err == nil {
			err = remove
		}
	}()
	if _, err = file.Write(payload); err != nil {
		file.Close()
		return err
	}
	if err = file.Sync(); err != nil {
		file.Close()
		return err
	}
	if err = file.Close(); err != nil {
		return err
	}
	return os.Rename(scratch, path)
}
func initialize(root string) error {
	exists, err := manifestExists(root)
	if err != nil || exists {
		return err
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		name := entry.Name()
		path := filepath.Join(root, name)
		if name == ".writer.lock" {
			continue
		}
		if name == "issues" || name == "epics" {
			if _, err = pathKind(path, true, false); err != nil {
				return err
			}
			children, e := os.ReadDir(path)
			if e != nil {
				return e
			}
			if len(children) > 0 {
				return fmt.Errorf("uninitialized %s not empty", name)
			}
		} else if strings.HasPrefix(name, ".tmp-") && tokenRE.MatchString(name[5:]) {
			if _, err = pathKind(path, false, false); err != nil {
				return err
			}
		} else {
			return fmt.Errorf("unexpected uninitialized content")
		}
	}
	if err = mkdir(filepath.Join(root, "issues")); err != nil {
		return err
	}
	if err = mkdir(filepath.Join(root, "epics")); err != nil {
		return err
	}
	data, _ := encode(map[string]any{"format": "beadcrumbs", "version": 1})
	return publish(filepath.Join(root, "store.json"), data)
}
func loadEpics(root string) (map[string]*Epic, error) {
	directory := filepath.Join(root, "epics")
	if _, err := pathKind(directory, true, false); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, err
	}
	epics := map[string]*Epic{}
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		if _, err = pathKind(path, false, false); err != nil {
			return nil, err
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		epic, err := decodeEpic(data)
		if err != nil {
			return nil, err
		}
		if entry.Name() != epic.Key+".json" {
			return nil, fmt.Errorf("epic filename mismatch")
		}
		epics[epic.Key] = epic
	}
	return epics, nil
}
func load(root string, codec Codec) (map[string]*Issue, map[string]*Epic, error) {
	epics, err := loadEpics(root)
	if err != nil {
		return nil, nil, err
	}
	issues, err := loadIssues(root, codec, epics)
	return issues, epics, err
}
func loadIssues(root string, codec Codec, epics map[string]*Epic) (map[string]*Issue, error) {
	directory := filepath.Join(root, "issues")
	if _, err := pathKind(directory, true, false); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, err
	}
	issues := map[string]*Issue{}
	for _, entry := range entries {
		if !codec.Accepts(entry.Name()) {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		if _, err = pathKind(path, false, false); err != nil {
			return nil, err
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		issue, err := codec.Decode(data)
		if err != nil {
			return nil, err
		}
		name, err := codec.Filename(issue.ID)
		if err != nil || name != entry.Name() {
			return nil, fmt.Errorf("filename mismatch")
		}
		if issue.Epic != nil && epics[*issue.Epic] == nil {
			return nil, fmt.Errorf("missing epic")
		}
		issues[issue.ID] = issue
	}
	counts := map[string]int{}
	dependents := map[string][]string{}
	queue := []string{}
	for id, issue := range issues {
		counts[id] = len(issue.Dependencies)
		if counts[id] == 0 {
			queue = append(queue, id)
		}
		for _, dep := range issue.Dependencies {
			target, ok := issues[dep]
			if !ok {
				return nil, fmt.Errorf("missing dependency")
			}
			if issue.State != "open" && target.State != "closed" {
				return nil, fmt.Errorf("unresolved dependency on active issue")
			}
			dependents[dep] = append(dependents[dep], id)
		}
	}
	for i := 0; i < len(queue); i++ {
		for _, id := range dependents[queue[i]] {
			counts[id]--
			if counts[id] == 0 {
				queue = append(queue, id)
			}
		}
	}
	if len(queue) != len(issues) {
		return nil, fmt.Errorf("dependency cycle")
	}
	return issues, nil
}
