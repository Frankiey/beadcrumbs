# 0001 Make the filesystem the shared interface

**Status** Proposed

## Context

Beadcrumbs must be deployable by copying a single Python file into a restricted environment. Independent clients need a common interface without relying on the Python runtime or a running service.

## Decision

Use a versioned JSON manifest and one JSON record per issue. Store notes in the issue record and derive ready work from a directory scan. Ship the first client as a standard-library-only Python script. Leave Git usage to the workspace owner.

## Consequences

Files are easy to inspect and changes to different issues can be reviewed separately. Full scans and rewriting the notes array limit the useful store size. A single JSONL log would require replay and recovery rules for partial appends. Revisit it if change history becomes a core requirement.

## JSON and YAML

Python ships a JSON parser in its standard library. Reading YAML would require an external dependency or a custom parser. YAML supports convenient multiline text and comments, along with additional syntax, tags, aliases, and scalar-resolution rules. Keeping JSON lets the single-file reference client use a standard parser and gives independent clients a smaller parsing contract. Human browsing is supported through the generated Markdown board. [Python JSON documentation](https://docs.python.org/3/library/json.html), [YAML specification](https://yaml.org/spec/1.2.2/)
