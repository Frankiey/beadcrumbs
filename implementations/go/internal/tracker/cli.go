package tracker

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

var actionNames = []string{"init", "create", "show", "list", "ready", "blocked", "validate", "claim", "note", "release", "close", "board", "help", "version"}

func contains(items []string, value string) bool {
	for _, item := range items {
		if item == value {
			return true
		}
	}
	return false
}

type Arguments struct {
	Action, Value string
	Options       map[string]string
	Dependencies  []string
	JSON          bool
}

func parse(argv []string) (Arguments, error) {
	args := Arguments{Options: map[string]string{}, Dependencies: []string{}}
	values := []string{"create", "show", "claim", "note", "release", "close", "workspace", "state", "agent", "token", "text", "description", "description-file", "acceptance-criteria", "depends-on"}
	for i := 0; i < len(argv); i++ {
		word := argv[i]
		if !strings.HasPrefix(word, "--") {
			return args, failure(2, "expected long option")
		}
		pair := strings.SplitN(word[2:], "=", 2)
		name := pair[0]
		value := ""
		if !contains(actionNames, name) && !contains(values, name) && name != "json" {
			return args, failure(2, "unknown option")
		}
		if _, exists := args.Options[name]; exists && name != "depends-on" {
			return args, failure(2, "repeated option")
		}
		if contains(values, name) {
			if len(pair) == 2 {
				value = pair[1]
			} else {
				i++
				if i >= len(argv) || strings.HasPrefix(argv[i], "--") {
					return args, failure(2, "missing option value")
				}
				value = argv[i]
			}
		} else if len(pair) > 1 {
			return args, failure(2, "flag takes no value")
		}
		if contains(actionNames, name) {
			if args.Action != "" {
				return args, failure(2, "one action required")
			}
			args.Action = name
			args.Value = value
		}
		args.Options[name] = value
		if name == "depends-on" {
			args.Dependencies = append(args.Dependencies, value)
		}
	}
	if args.Action == "" {
		return args, failure(2, "action required")
	}
	allowed := map[string][]string{
		"create": {"depends-on", "description", "description-file", "acceptance-criteria"},
		"list":   {"state"}, "claim": {"agent"}, "note": {"agent", "text"}, "release": {"token"}, "close": {"token"},
	}
	for key := range args.Options {
		if key == args.Action || contains(allowed[args.Action], key) {
			continue
		}
		if args.Action != "help" && args.Action != "version" && (key == "workspace" || key == "json") {
			continue
		}
		return args, failure(2, "option does not apply")
	}
	if contains([]string{"show", "claim", "note", "release", "close"}, args.Action) && !idRE.MatchString(args.Value) {
		return args, failure(2, "invalid ID")
	}
	if args.Action == "create" && args.Value == "" {
		return args, failure(2, "empty title")
	}
	if contains([]string{"claim", "note"}, args.Action) && !agentRE.MatchString(args.Options["agent"]) {
		return args, failure(2, "agent required")
	}
	if contains([]string{"release", "close"}, args.Action) && !tokenRE.MatchString(args.Options["token"]) {
		return args, failure(2, "token required")
	}
	if args.Action == "note" && args.Options["text"] == "" {
		return args, failure(2, "note text required")
	}
	if state, ok := args.Options["state"]; ok && !contains([]string{"open", "claimed", "closed"}, state) {
		return args, failure(2, "invalid state")
	}
	seen := map[string]bool{}
	for _, dep := range args.Dependencies {
		if !idRE.MatchString(dep) || seen[dep] {
			return args, failure(2, "invalid dependency")
		}
		seen[dep] = true
	}
	_, description := args.Options["description"]
	file, fromFile := args.Options["description-file"]
	if description && fromFile {
		return args, failure(2, "conflicting description inputs")
	}
	for _, value := range args.Options {
		if !utf8.ValidString(value) {
			return args, failure(2, "invalid Unicode")
		}
	}
	if fromFile {
		var data []byte
		var err error
		if file == "-" {
			data, err = io.ReadAll(os.Stdin)
		} else {
			data, err = os.ReadFile(file)
		}
		if err != nil {
			return args, err
		}
		if !utf8.Valid(data) || strings.HasPrefix(string(data), "\ufeff") {
			return args, failure(2, "invalid description encoding")
		}
		args.Options["description"] = string(data)
	}
	_, args.JSON = args.Options["json"]
	return args, nil
}
func cell(value string) string {
	var out strings.Builder
	for _, char := range value {
		switch {
		case char == '\r' || char == '\n':
			out.WriteByte(' ')
		case unicode.IsControl(char) || unicode.In(char, unicode.Cf, unicode.Zl, unicode.Zp):
			fmt.Fprintf(&out, "&#92;u%04x", char)
		case strings.ContainsRune("&<>|\x60[]*_\\", char):
			fmt.Fprintf(&out, "&#%d;", char)
		default:
			out.WriteRune(char)
		}
	}
	return out.String()
}
func renderBoard(issues map[string]*Issue, generated string) string {
	names := []string{"Ready", "Blocked", "Claimed", "Closed"}
	sections := map[string][]string{}
	for _, issue := range ordered(issues) {
		unresolved := blockers(issue, issues)
		section := "Closed"
		if issue.State == "claimed" {
			section = "Claimed"
		}
		if issue.State == "open" {
			section = "Ready"
			if len(unresolved) > 0 {
				section = "Blocked"
			}
		}
		owner := "—"
		if issue.Claim != nil {
			owner = issue.Claim.Agent
		}
		deps := []string{}
		for _, dep := range unresolved {
			deps = append(deps, dep.ID+" ("+dep.State+")")
		}
		text := "—"
		if len(deps) > 0 {
			text = strings.Join(deps, ", ")
		}
		sections[section] = append(sections[section], "| "+cell(issue.ID)+" | "+cell(issue.Title)+" | "+cell(owner)+" | "+cell(text)+" |")
	}
	lines := []string{"# Beadcrumbs board", "", "Generated at " + generated + ".", "", "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.", ""}
	for _, name := range names {
		rows := sections[name]
		lines = append(lines, fmt.Sprintf("## %s (%d)", name, len(rows)), "")
		if len(rows) == 0 {
			lines = append(lines, "No issues.", "")
		} else {
			lines = append(lines, "| ID | Title | Agent | Blockers |", "| --- | --- | --- | --- |")
			lines = append(lines, rows...)
			lines = append(lines, "")
		}
	}
	return strings.Join(lines, "\n")
}
func run(args Arguments, root string, issues map[string]*Issue, codec Codec) (any, error) {
	now := func() string { return time.Now().UTC().Format("2006-01-02T15:04:05Z") }
	switch args.Action {
	case "init":
		return map[string]any{"format": "beadcrumbs", "version": 1}, nil
	case "validate":
		return map[string]any{"valid": true, "issue_count": len(issues)}, nil
	case "list", "ready":
		result := []*Issue{}
		for _, issue := range ordered(issues) {
			state, filtered := args.Options["state"]
			if args.Action == "list" && (!filtered || state == issue.State) || args.Action == "ready" && issue.State == "open" && len(blockers(issue, issues)) == 0 {
				result = append(result, issue)
			}
		}
		return result, nil
	case "blocked":
		result := []any{}
		for _, issue := range ordered(issues) {
			deps := blockers(issue, issues)
			if issue.State == "open" && len(deps) > 0 {
				result = append(result, map[string]any{"issue": issue, "blockers": deps})
			}
		}
		return result, nil
	case "board":
		path := filepath.Join(filepath.Dir(root), "board.md")
		if _, err := pathKind(path, false, true); err != nil {
			return nil, err
		}
		generated := now()
		if err := publish(path, []byte(renderBoard(issues, generated))); err != nil {
			return nil, err
		}
		return map[string]any{"path": path, "issue_count": len(issues), "generated_at": generated}, nil
	}
	var issue *Issue
	if args.Action == "create" {
		for _, dep := range args.Dependencies {
			if issues[dep] == nil {
				return nil, failure(3, "issue not found")
			}
		}
		id, err := token()
		if err != nil {
			return nil, err
		}
		id = "bc-" + id
		for issues[id] != nil {
			id, err = token()
			if err != nil {
				return nil, err
			}
			id = "bc-" + id
		}
		created := now()
		issue = &Issue{ID: id, Title: args.Value, Description: args.Options["description"], Acceptance: args.Options["acceptance-criteria"], State: "open", Dependencies: args.Dependencies, Notes: []Note{}, Created: created, Updated: created, Revision: 1}
	} else {
		issue = issues[args.Value]
		if issue == nil {
			return nil, failure(3, "issue not found")
		}
		if args.Action == "show" {
			return issue, nil
		}
		if args.Action == "claim" {
			if issue.State != "open" || len(blockers(issue, issues)) > 0 {
				return nil, failure(4, "issue is not ready")
			}
		} else if args.Action == "close" || args.Action == "release" {
			if issue.State != "claimed" || issue.Claim.Token != args.Options["token"] {
				return nil, failure(4, "claim mismatch")
			}
		}
		if issue.Revision >= maxRevision {
			return nil, fmt.Errorf("revision exhausted")
		}
		updated := now()
		switch args.Action {
		case "claim":
			value, err := token()
			if err != nil {
				return nil, err
			}
			issue.State = "claimed"
			issue.Claim = &Claim{args.Options["agent"], value}
		case "note":
			issue.Notes = append(issue.Notes, Note{updated, args.Options["agent"], args.Options["text"]})
		case "release":
			issue.State = "open"
			issue.Claim = nil
		case "close":
			issue.State = "closed"
			issue.Claim = nil
		}
		issue.Updated = updated
		issue.Revision++
	}
	if err := validate(issue); err != nil {
		return nil, err
	}
	name, err := codec.Filename(issue.ID)
	if err != nil {
		return nil, err
	}
	data, err := codec.Encode(issue)
	if err != nil {
		return nil, err
	}
	if err = publish(filepath.Join(root, "issues", name), data); err != nil {
		return nil, err
	}
	return issue, nil
}
func Main(argv []string) int {
	result, compact, err := execute(argv)
	if err != nil {
		fmt.Fprintln(os.Stderr, "beadcrumbs: "+strconv.QuoteToASCII(err.Error()))
		if typed, ok := err.(*Failure); ok {
			return typed.Code
		}
		return 1
	}
	if result == nil {
		return 0
	}
	var data []byte
	if compact {
		data, err = json.Marshal(result)
	} else {
		data, err = json.MarshalIndent(result, "", "  ")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	// Escape Unicode, including bidi controls, for safe terminal output.
	var out strings.Builder
	for _, char := range string(data) {
		if char > 126 {
			if char <= 0xffff {
				fmt.Fprintf(&out, "\\u%04x", char)
			} else {
				r := char - 0x10000
				fmt.Fprintf(&out, "\\u%04x\\u%04x", 0xd800+(r>>10), 0xdc00+(r&1023))
			}
		} else {
			out.WriteRune(char)
		}
	}
	if _, err = fmt.Fprintln(os.Stdout, out.String()); err != nil {
		return 1
	}
	return 0
}
func execute(argv []string) (any, bool, error) {
	args, err := parse(argv)
	if err != nil {
		return nil, false, err
	}
	if args.Action == "help" {
		fmt.Println("Beadcrumbs offline issue tracker\n--" + strings.Join(actionNames, " --"))
		return nil, false, nil
	}
	if args.Action == "version" {
		fmt.Println("beadcrumbs 0.1.0")
		return nil, false, nil
	}
	workspace := args.Options["workspace"]
	if workspace == "" {
		workspace = "."
	}
	workspace, err = filepath.Abs(workspace)
	if err != nil {
		return nil, false, err
	}
	workspace, err = filepath.EvalSymlinks(workspace)
	if err != nil {
		return nil, false, err
	}
	if _, err = pathKind(workspace, true, false); err != nil {
		return nil, false, err
	}
	root := filepath.Join(workspace, ".beadcrumbs")
	codec := JSONCodec{}
	result, err := locked(root, args.Action == "init", func() (any, error) {
		if args.Action == "init" {
			if err := initialize(root); err != nil {
				return nil, err
			}
		}
		exists, err := manifestExists(root)
		if err != nil {
			return nil, err
		}
		if !exists {
			return nil, fmt.Errorf("store uninitialized")
		}
		issues, err := load(root, codec)
		if err != nil {
			return nil, err
		}
		return run(args, root, issues, codec)
	})
	return result, args.JSON, err
}
