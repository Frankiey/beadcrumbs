# Command-line interface

The v1 draft 1 [core contract](core-contract.md) reference interface uses one action flag per invocation. Options may appear before or after the action. Long option names must be spelled in full. Examples use Python. Future clients can expose the same interface under their own executable name.

| Action | Result |
| --- | --- |
| `--init` | Create an empty store in the selected workspace. Succeed without changing an already initialized, valid v1 store. |
| `--create TITLE [--depends-on ID ...]` | Create an open issue and return it. Repeat `--depends-on` for each dependency. |
| `--show ID` | Return the issue. |
| `--list [--state STATE]` | Return all issues, optionally filtered by open, claimed, or closed. |
| `--blocked` | Return blocked open issues with their unresolved direct dependencies. |
| `--validate` | Validate the entire store and return a success result. |
| `--board` | Write board.md in the selected workspace and return snapshot metadata. |
| `--ready` | Return the ordered list of ready issues. |
| `--claim ID --agent LABEL` | Claim a ready issue and return its new record, including the claim token. |
| `--note ID --agent LABEL --text TEXT` | Append a note to an existing issue and return its new record. |
| `--release ID --token TOKEN` | Clear a matching claim, return the issue to open, and return its new record. |
| `--close ID --token TOKEN` | Clear a matching claim, close the issue, and return its new record. |
| `--help`, `--version` | Print usage or client release version, respectively. These actions stand alone and do not access the workspace. |

`--workspace PATH` selects an existing directory and defaults to the current directory. `--json` selects machine-readable output for any store action. Repeat only `--depends-on`. Reject duplicate dependency IDs. Options apply only to the action that declares them. Reject unknown, repeated, or inapplicable options before accessing the store. Supply option values that begin with a dash using `--option=value`.

## Output

With `--json`, a successful store action writes exactly one UTF-8 JSON value followed by LF to stdout. `--init` returns the manifest. `--ready` returns an array of full issue records, possibly `[]`. `--list` returns an array of full issue records. List, ready, and blocked sort by creation timestamp and then issue ID, both ascending. `--blocked` returns the shape below, with blockers in the issue’s dependency-array order. `--validate` returns exactly `{"valid": true, "issue_count": N}`, where N is the number of issue records. `--board` returns exactly `{"path": "/resolved/workspace/board.md", "issue_count": N, "generated_at": "YYYY-MM-DDTHH:MM:SSZ"}`. Other actions return one full issue record. JSON object field order and whitespace are unspecified.

Human-readable output is the default and uses indented JSON in the Python client. IDs, titles, complete records, and claim tokens remain visible. Machine mode emits compact JSON. Both modes escape non-ASCII characters and controls with JSON escapes. Decoding preserves original text. Human-readable formatting may change. See [terminal handling](security.md#untrusted-text).

For failures detected before output begins, stdout is empty and stderr contains a diagnostic. Output failures may leave a partial stdout value, which callers must discard. The exit code is the machine-readable error contract. An output failure or an interrupted process can leave a mutation committed even if the caller saw no successful response. After an ambiguous result, inspect the store before retrying. Create and note retries can otherwise produce duplicates.

| Exit | Meaning |
| --- | --- |
| 0 | Success, including an empty ready list. |
| 1 | I/O failure, missing or invalid store, unsupported version, or exhausted revision. |
| 2 | Invalid invocation, including malformed arguments and missing required options. |
| 3 | Issue not found, including a dependency supplied to create. |
| 4 | Issue state conflict or claim token mismatch. |
| 5 | Writer lock is busy. A later invocation may retry. |

## Workflow

```sh
python3 beadcrumbs.py --init
python3 beadcrumbs.py --create "Document the offline setup"
python3 beadcrumbs.py --ready --json
python3 beadcrumbs.py --claim "$issue_id" --agent worker-01 --json
python3 beadcrumbs.py --note "$issue_id" --agent worker-01 --text "Verified offline."
python3 beadcrumbs.py --close "$issue_id" --token "$claim_token"
```

Set `issue_id` from the ready result and `claim_token` from the successful claim. The Python reference client implements this workflow.

## Create text input

Create accepts optional `--description TEXT` and `--acceptance-criteria TEXT`. Either defaults to an empty string. `--description-file PATH` supplies the description instead, and is mutually exclusive with `--description`. A path of `-` reads stdin. Decode file/stdin bytes as strict UTF-8 without a BOM, preserving line endings and trailing newlines. An unreadable file is exit 1 and invalid encoding is exit 2. Read input before acquiring the store lock. Relative input paths resolve against the invocation's current directory, even when `--workspace` selects another directory.

## Blocked JSON shape

Each array item contains exactly `issue` (a full issue record) and `blockers` (an array of objects containing exactly `id` and `state`). Blocker states are open or claimed. For example, an issue B that depends on A appears once with A in its blockers array. Closed and claimed issues never appear as blocked rows.

## Validation and error precedence

Validate acquires and releases the ordinary store lock, performs no repairs, and reports the first validation failure on stderr with exit 1. Failure ordering among multiple corrupt records is unspecified. Busy returns exit 5. The transient lock is the only filesystem mutation made by a successful validation.

Validate command syntax and scalar argument formats first. Then check workspace and manifest, acquire the lock, validate the store, resolve requested IDs, and check state/token preconditions, in that order. A well-formed ID absent from a valid store is exit 3. A broken reference already in a store is exit 1. All pre-publication command failures preserve authoritative records.

## Markdown board

Run `python3 beadcrumbs.py --board` to replace board.md in the selected workspace with a UTF-8 Markdown snapshot. The workspace must have an initialized valid store. Existing regular board.md files are replaced, including manual edits. Linked files and non-file destinations fail with exit 1.

The board contains Ready, Blocked, Claimed, and Closed sections in that order, each with a count. Rows use the same creation-time/ID ordering as list. Columns show full issue ID, title, current agent, and unresolved direct blocker IDs with states. Empty sections are explicit. Titles are escaped for Markdown tables and HTML, and line breaks become spaces. Claim tokens and detailed notes are omitted.

Generation validates and holds the store lock through atomic board publication. Successful generation preserves issue records and revisions. Normal issue operations do not refresh the board. The generated UTC timestamp identifies the snapshot. A failure before replacement preserves an existing board. An interrupted output response can follow successful publication, and regenerating is safe.
