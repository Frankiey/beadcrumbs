package tracker

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode/utf8"
)

type Failure struct {
	Message string
	Code    int
}

func (e *Failure) Error() string             { return e.Message }
func failure(code int, message string) error { return &Failure{message, code} }

var idRE = regexp.MustCompile("^bc-[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$")
var tokenRE = regexp.MustCompile("^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$")
var agentRE = regexp.MustCompile("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
var timeRE = regexp.MustCompile("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

const maxRevision = int64(9007199254740991)

type Claim struct {
	Agent string `json:"agent"`
	Token string `json:"token"`
}
type Note struct {
	At   string `json:"at"`
	By   string `json:"by"`
	Text string `json:"text"`
}
type Issue struct {
	ID           string   `json:"id"`
	Title        string   `json:"title"`
	Description  string   `json:"description"`
	Acceptance   string   `json:"acceptance_criteria"`
	State        string   `json:"state"`
	Dependencies []string `json:"depends_on"`
	Claim        *Claim   `json:"claim"`
	Notes        []Note   `json:"notes"`
	Created      string   `json:"created_at"`
	Updated      string   `json:"updated_at"`
	Revision     int64    `json:"revision"`
}
type Blocker struct {
	ID    string `json:"id"`
	State string `json:"state"`
}

// Check escaped Unicode before encoding/json replaces invalid surrogates.
func unicodeValid(data []byte) bool {
	if !utf8.Valid(data) {
		return false
	}
	for i := 0; i < len(data); i++ {
		if data[i] != '\\' {
			continue
		}
		i++
		if i >= len(data) || data[i] != 'u' {
			continue
		}
		if i+4 >= len(data) {
			return false
		}
		var value uint32
		if _, err := fmt.Sscanf(string(data[i+1:i+5]), "%04x", &value); err != nil {
			return false
		}
		i += 4
		if value >= 0xdc00 && value <= 0xdfff {
			return false
		}
		if value >= 0xd800 && value <= 0xdbff {
			if i+6 >= len(data) || string(data[i+1:i+3]) != "\\u" {
				return false
			}
			var low uint32
			if _, err := fmt.Sscanf(string(data[i+3:i+7]), "%04x", &low); err != nil || low < 0xdc00 || low > 0xdfff {
				return false
			}
			i += 6
		}
	}
	return true
}

// Strict token walking retains duplicate-key and integer-lexeme validation.
func readValue(decoder *json.Decoder) (any, error) {
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	switch value := token.(type) {
	case json.Delim:
		if value == '{' {
			object := map[string]any{}
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return nil, err
				}
				key, ok := keyToken.(string)
				if !ok {
					return nil, fmt.Errorf("invalid key")
				}
				if _, exists := object[key]; exists {
					return nil, fmt.Errorf("duplicate JSON key")
				}
				item, err := readValue(decoder)
				if err != nil {
					return nil, err
				}
				object[key] = item
			}
			_, err = decoder.Token()
			return object, err
		}
		if value == '[' {
			array := []any{}
			for decoder.More() {
				item, err := readValue(decoder)
				if err != nil {
					return nil, err
				}
				array = append(array, item)
			}
			_, err = decoder.Token()
			return array, err
		}
		return nil, fmt.Errorf("unexpected delimiter")
	case json.Number:
		if strings.ContainsAny(string(value), ".eE") {
			return nil, fmt.Errorf("integer lexical form required")
		}
		number, err := value.Int64()
		if err != nil || number > maxRevision || number < -maxRevision {
			return nil, fmt.Errorf("integer out of range")
		}
		return value, nil
	default:
		return value, nil
	}
}
func strictJSON(data []byte) (any, error) {
	if !unicodeValid(data) {
		return nil, fmt.Errorf("invalid Unicode")
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	value, err := readValue(decoder)
	if err != nil {
		return nil, err
	}
	if _, err = decoder.Token(); err != io.EOF {
		return nil, fmt.Errorf("trailing JSON content")
	}
	return value, nil
}
func exact(value any, fields ...string) bool {
	object, ok := value.(map[string]any)
	if !ok || len(object) != len(fields) {
		return false
	}
	for _, field := range fields {
		if _, ok := object[field]; !ok {
			return false
		}
	}
	return true
}
func validTime(value string) bool {
	parsed, err := time.Parse("2006-01-02T15:04:05Z", value)
	return err == nil && timeRE.MatchString(value) && parsed.Year() > 0
}
func validate(issue *Issue) error {
	if !idRE.MatchString(issue.ID) || issue.Title == "" ||
		(issue.State != "open" && issue.State != "claimed" && issue.State != "closed") ||
		issue.Dependencies == nil || issue.Notes == nil || !validTime(issue.Created) ||
		!validTime(issue.Updated) || issue.Revision < 1 || issue.Revision > maxRevision {
		return fmt.Errorf("invalid issue fields")
	}
	if issue.State == "claimed" {
		if issue.Claim == nil || !agentRE.MatchString(issue.Claim.Agent) || !tokenRE.MatchString(issue.Claim.Token) {
			return fmt.Errorf("invalid claim")
		}
	} else if issue.Claim != nil {
		return fmt.Errorf("unexpected claim")
	}
	seen := map[string]bool{}
	for _, dep := range issue.Dependencies {
		if !idRE.MatchString(dep) || seen[dep] {
			return fmt.Errorf("invalid dependency")
		}
		seen[dep] = true
	}
	for _, note := range issue.Notes {
		if !validTime(note.At) || !agentRE.MatchString(note.By) || note.Text == "" {
			return fmt.Errorf("invalid note")
		}
	}
	return nil
}

type Codec interface {
	Accepts(string) bool
	Filename(string) (string, error)
	Decode([]byte) (*Issue, error)
	Encode(*Issue) ([]byte, error)
}
type JSONCodec struct{}

func (JSONCodec) Accepts(name string) bool { return strings.HasSuffix(name, ".json") }
func (JSONCodec) Filename(id string) (string, error) {
	if !idRE.MatchString(id) {
		return "", fmt.Errorf("invalid ID")
	}
	return id + ".json", nil
}
func (JSONCodec) Encode(issue *Issue) ([]byte, error) { return encode(issue) }
func (JSONCodec) Decode(data []byte) (*Issue, error) {
	value, err := strictJSON(data)
	if err != nil {
		return nil, err
	}
	if !exact(value, "id", "title", "description", "acceptance_criteria", "state", "depends_on", "claim", "notes", "created_at", "updated_at", "revision") {
		return nil, fmt.Errorf("invalid issue fields")
	}
	object := value.(map[string]any)
	for _, key := range []string{"id", "title", "description", "acceptance_criteria", "state", "created_at", "updated_at"} {
		if _, ok := object[key].(string); !ok {
			return nil, fmt.Errorf("expected text")
		}
	}
	if object["claim"] != nil && !exact(object["claim"], "agent", "token") {
		return nil, fmt.Errorf("invalid claim fields")
	}
	notes, ok := object["notes"].([]any)
	if !ok {
		return nil, fmt.Errorf("invalid notes")
	}
	for _, note := range notes {
		if !exact(note, "at", "by", "text") {
			return nil, fmt.Errorf("invalid note fields")
		}
	}
	// Typed decoding supplies the remaining field-type checks.
	var issue Issue
	if err = json.Unmarshal(data, &issue); err != nil {
		return nil, err
	}
	if err = validate(&issue); err != nil {
		return nil, err
	}
	return &issue, nil
}
func encode(value any) ([]byte, error) {
	var out bytes.Buffer
	encoder := json.NewEncoder(&out)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	err := encoder.Encode(value)
	return out.Bytes(), err
}
func blockers(issue *Issue, issues map[string]*Issue) []Blocker {
	result := []Blocker{}
	for _, id := range issue.Dependencies {
		if issues[id].State != "closed" {
			result = append(result, Blocker{id, issues[id].State})
		}
	}
	return result
}
func ordered(issues map[string]*Issue) []*Issue {
	result := []*Issue{}
	for _, issue := range issues {
		result = append(result, issue)
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].Created != result[j].Created {
			return result[i].Created < result[j].Created
		}
		return result[i].ID < result[j].ID
	})
	return result
}
