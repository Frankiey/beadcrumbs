package tracker

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStrictJSON(t *testing.T) {
	for _, value := range []string{`{"x":1,"x":2}`, `{"x":1.0}`, `{"x":1e0}`, `{"x":"\ud800"}`, `{"x":NaN}`, `{"x":9007199254740992}`} {
		if _, err := strictJSON([]byte(value)); err == nil {
			t.Errorf("accepted %s", value)
		}
	}
	if _, err := strictJSON([]byte(`{"text":"\ud83d\ude00","number":1}`)); err != nil {
		t.Fatal(err)
	}
}

type exampleCodec struct{ JSONCodec }

func (exampleCodec) Accepts(name string) bool           { return strings.HasSuffix(name, ".example") }
func (exampleCodec) Filename(id string) (string, error) { return id + ".example", nil }
func (c exampleCodec) Encode(issue *Issue) ([]byte, error) {
	data, err := c.JSONCodec.Encode(issue)
	return append([]byte("example\n"), data...), err
}
func (c exampleCodec) Decode(data []byte) (*Issue, error) {
	return c.JSONCodec.Decode(bytes.TrimPrefix(data, []byte("example\n")))
}

func TestAlternateCodecLifecycle(t *testing.T) {
	root := filepath.Join(t.TempDir(), ".beadcrumbs")
	codec := exampleCodec{}
	_, err := locked(root, true, func() (any, error) {
		if err := initialize(root); err != nil {
			return nil, err
		}
		execute := func(argv ...string) (any, error) {
			args, err := parse(argv)
			if err != nil {
				return nil, err
			}
			issues, err := load(root, codec)
			if err != nil {
				return nil, err
			}
			return run(args, root, issues, codec)
		}
		result, err := execute("--create", "Alternate")
		if err != nil {
			return nil, err
		}
		issue := result.(*Issue)
		result, err = execute("--claim", issue.ID, "--agent", "worker")
		if err != nil {
			return nil, err
		}
		claim := result.(*Issue).Claim.Token
		if _, err = execute("--note", issue.ID, "--agent", "worker", "--text", "Done"); err != nil {
			return nil, err
		}
		result, err = execute("--close", issue.ID, "--token", claim)
		if err != nil {
			return nil, err
		}
		closed := result.(*Issue)
		if closed.State != "closed" || closed.Revision != 4 {
			t.Fatal("invalid lifecycle result")
		}
		data, err := os.ReadFile(filepath.Join(root, "issues", issue.ID+".example"))
		if err != nil {
			return nil, err
		}
		if !bytes.HasPrefix(data, []byte("example\n")) {
			t.Fatal("codec was bypassed")
		}
		return nil, nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
func TestFailedPublicationCleansScratch(t *testing.T) {
	root := t.TempDir()
	destination := filepath.Join(root, "directory")
	if err := os.Mkdir(destination, 0700); err != nil {
		t.Fatal(err)
	}
	if err := publish(destination, []byte("payload")); err == nil {
		t.Fatal("replacement should fail")
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].Name() != "directory" {
		t.Fatal("scratch file remains")
	}
}
