# Implementation progress

Updated 19 November 2026. Reference client 0.1.0 implements core contract v1 draft 1, including issue types, priority, epics, and labels.

Read this file and AGENTS.md when continuing in another chat. Keep completed work, evidence, and outstanding verification current here.

| Step | Status | Evidence |
| --- | --- | --- |
| Contract review | Complete for first implementation | Explicit handling of extra store entries, error precedence, text input, and interrupted output. |
| Schemas and shared fixtures | Complete initial set | schemas/v1 and tests/fixtures/cases.json. Semantic restrictions are documented in docs/conformance.md. |
| Initialization, validation, and reads | Implemented | Init, validate, show, list, ready, blocked. |
| Atomic mutations and lifecycle | Implemented | Create, claim, note, release, close. One lock and replacement path. |
| Concurrency and interruption tests | Passing locally | Competing claims, simultaneous init, concurrent notes, process death before/after replace, fsync/replace failures. |
| Offline lifecycle | Passing locally | Full dependency lifecycle under an audit hook rejecting network and subprocess calls. |

## Verification

Run `python3 -m unittest discover -s tests -v` from the repository root. The default Python discovery currently has 33 test methods, with 29 active and four pair tests skipped unless a peer is configured, including parameterized cases and seventeen shared fixture scenarios. It passed on macOS with Python 3.15.2. Tests use temporary stores outside Git and require no external packages.

The black-box CLI suite supports BEADCRUMBS_COMMAND as a JSON argv array for all clients. Reference-only fault injection stays in test_storage.py. Documentation links and JSON artifacts are checked during this implementation handoff.

## Decisions made during implementation

- Human-readable output uses indented, escaped JSON. Machine mode returns compact JSON with the same semantic values.
- Extra entries in an initialized store are preserved and ignored unless they occupy a protocol path or end in .json directly inside issues/.
- JSON Schemas describe structure. The standard-library runtime additionally checks duplicate keys, Unicode scalar values, integer lexical forms, graph integrity, and filename matching.
- The protocol remains draft 1. Earlier hand-authored records missing task-content fields require the documented explicit conversion.

## Remaining verification and next work

- Test Python 3.10 and supported Linux/Windows local filesystems, including Windows reparse-point rejection and replacement behavior.
- Run the schemas through a full draft-2020-12 validator with format assertions. The dependency-free suite parses them but does not implement a general schema engine.
- Extend the five-client conformance matrix as new corner cases are found. Current covered scenarios pass across all ten pairs.
- Expand fixtures when bugs or new protocol cases are found.
- Freeze v1 only after the compatibility and platform checks above.
- Next/Later features in docs/features.md remain deferred.

The current implementation uses explicit claim recovery and has no request deduplication or power-loss durability guarantee. These are documented contract boundaries.

## Persistent integration example

Added integration/run.py and integration/README.md. Run the script for a full checked lifecycle or pass --setup-only to leave a ready prerequisite and blocked dependent. Each invocation creates a fresh workspace and command transcript under integration/.runs/. Both modes passed on 14 November 2026. Git ignore verification confirms generated results and stores are ignored while the script and guide remain visible to Git.

## Markdown board

Implemented --board on 14 November 2026. It writes workspace-level board.md with a timestamp and four status sections using atomic publication under the existing lock. The JSON result schema, CLI contract, concurrency notes, and integration scenarios include it. Added four tests for empty/explicit workspaces, grouping and escaping, refresh behavior, preservation on failure, and symlink rejection. All 23 tests pass locally. JSON/YAML rationale is recorded in ADR 0001.

## Replaceable serialization and rendering

Added JsonIssueCodec with accepts, filename, decode, and encode operations. Store reads and lifecycle writes now use the codec boundary. Shared field validation operates on logical records, and Markdown rendering is a pure function. The manifest and CLI retain their explicit JSON contracts.

A test-only alternate byte format and suffix passed the create/ready/claim/note/close/read/render workflow. All 25 tests passed locally. This proves internal substitution, while YAML and other production formats still require versioned protocols and migration.

Documented planned Go, Rust, .NET, and JavaScript directories under implementations/. Python remains at the root. Shared specs and conformance fixtures remain at the root. AGENTS.md and the core contract require these boundaries for future implementations.

## Five-client implementation pass

Implemented independent TypeScript/npm, Go, Rust, and .NET clients on 14 November 2026. All core commands, including --board, use the v1 store and lock protocol. Each port has a codec boundary, logical validation, centralized publication, and pure board rendering. TypeScript is the primary npm source language and ships compiled JavaScript. Python remains the reference client; the shared contract and fixtures define parity.

Added package-local build metadata, lockfiles where needed, ignores, native tests, and build guides. No runtime network access or Python subprocess delegation is used by the ports. Build prerequisites were available locally; no dependency downloads or publication were performed.

The matrix in integration/test_clients.py passed all 130 test executions, comprising 20 CLI tests for each client and three tests for each of ten client pairs. Evidence is in ignored integration/.runs/clients-20261114T165428Z-rleeu8az/summary.json and adjacent logs. Native suites passed separately for all four ports. The TypeScript suite includes process interruption around replacement. Other native suite limitations are recorded in docs/conformance.md.

Verified toolchains are Python 3.15.2, Node 26.13.1, TypeScript 5.9.3, Go 1.27.4, Rust 1.94.1, and .NET SDK 11.0.100 on macOS. Minimum-version and Linux/Windows verification remains outstanding. .NET currently targets net11.0 and uses a private runtime shim for Unix file-type checks, which requires review when retargeting. Rust and TypeScript air-gapped builds need their locked dependencies provisioned locally. Published packages and signed releases remain future work. All source changes remain uncommitted on main, with no remote configured.

## Documentation overhaul

Rewrote README.md on 14 November 2026 with badges, feature summary, quick start, exit-code table, comparison, roadmap checklist, and five Mermaid diagrams (architecture, lifecycle, competing-claim sequence, dependency example, client/spec relationship). Added docs/README.md (index and glossary), docs/getting-started.md (tutorial), docs/agent-guide.md (worker loop, AGENTS.md snippet, retry wrappers, ambiguous-result recovery), docs/faq.md, and CONTRIBUTING.md. Added non-normative diagrams to architecture.md, concurrency.md, and protocol.md without changing spec text.

Verification: all relative links and heading anchors resolve; all 16 Mermaid blocks parse and render with Mermaid 11.4.1; tutorial commands and outputs (exit 4 on second claim, revision 4 after close, repeat close exit 4) were replayed against the reference client; the unittest suite passes (29 tests, 3 skipped). The project is now licensed under Apache-2.0: LICENSE contains the unmodified canonical text, beadcrumbs.py carries an SPDX header, the npm, Cargo, and .NET CLI manifests declare Apache-2.0, and the README and CONTRIBUTING describe the license.

## Pre-publication fixes

Prepared for publication at https://github.com/Frankiey/beadcrumbs on 17 November 2026. The research doc's links to a local Beads checkout now point at upstream gastownhall/beads pinned to commit d76ade2. The review was performed on a fork commit, 53cc7d8, whose 19 additional commits change none of the 21 cited files, so the upstream links show identical content. The clone URL and copyright holder are filled in. SECURITY.md defines private reporting through GitHub advisories and the in-scope and out-of-scope boundary from docs/security.md; GitHub private vulnerability reporting must be enabled in the repository settings after the first push. The README comparison table now links upstream gastownhall/beads, and every Beads cell was checked against the reviewed checkout. Relative links and anchors resolve and the unittest suite passes.

Still open before announcing: CI across Linux, macOS, and Windows; minimum-toolchain verification; community templates; a CHANGELOG and v0.1.0 tag; repository metadata. On 20 November 2026 the CHANGELOG, issue and PR templates, repository topics, and a required "CI passed" status check on the `main` rule set were added; the v0.1.0 tag follows the merge of that change.

## CI and local tooling

Added on 18 November 2026: a root Makefile with lint, format, test, build, matrix, and docs targets for all five clients; ruff.toml (Ruff 0.17.5, Python 3.10 target); tools/check_docs.py for links, anchors, and JSON parsing; and .github/workflows/ci.yml, which runs the same make targets on pull requests and main. Python tests run on Linux, macOS, and Windows with Python 3.10 and the latest 3.x. Go uses the go.mod minimum, Rust runs 1.85 and stable, and TypeScript runs Node 22 and the current LTS. .NET and the cross-client matrix run on Linux. A final "CI passed" job aggregates the results for branch protection.

First lint pass fixes: Ruff formatting across Python files, import sorting, an unused import, `raise ... from None` in two places, explicit `zip(strict=True)`, executable bits on scripts with shebangs, a clippy range check in Rust, and dotnet format whitespace. There are no behavior changes. Locally on macOS, `make check` and `make matrix` pass (5 client suites and 10 pairs).

## Issue types, priority, and epics

Added on 18 November 2026 and kept within store version 1, since nothing had been released or announced.

- Issue records gain `type` (`task`, `bug`, `chore`, `docs`, `spike`; default `task`), `priority` (0–4; default 2), and `epic` (an epic key or null). Type and priority are fixed at creation. The epic can change in any state through `--set-epic ID --epic KEY|none`, which needs no claim token and bumps the revision.
- Epics are separate records at `.beadcrumbs/epics/<key>.json` with an immutable key and title, an editable description (`--edit-epic`), timestamps, and a revision. Keys are lowercase slugs, and `none` plus Windows device names are reserved. Epics have no state; `--show-epic` derives ready, blocked, claimed, and closed counts. An issue pointing to a missing epic invalidates the store.
- Issue lists sort by priority, then `created_at`, then ID. `--list` and `--ready` filter by `--type` and `--epic KEY|none`. `--validate` and `--board` report `epic_count`. The board now opens with a per-epic status summary and has one table per epic plus "No epic", with Status, Type, and Priority columns.
- `--init` creates `epics/`. Stores made before this change need the offline conversion described in the core contract.
- Schemas: new `schemas/v1/epic.schema.json`; issue and result schemas updated. Shared fixtures add a combined epics/types/priority scenario and four invalid-store cases. New CLI and interop tests cover create, filter, set-epic, edit-epic, show-epic, conflicts, and board grouping across clients.
- All five clients implement the change. Locally on macOS: Python unittest (28 active, 4 skipped pair tests), each port's native tests, `make check`, and `make matrix` (21 CLI tests per client and 4 interop tests per pair, all 15 suites passing). The integration example now uses an epic, a type, and a priority; its temporary CI diagnostics were removed.
- Not yet verified: this branch's Linux and Windows CI runs.

## Labels

Added on 19 November 2026, also within store version 1.

- Issue records gain `labels`: an array of at most 32 distinct lowercase slugs (`^[a-z0-9][a-z0-9-]{0,63}$`), stored sorted ascending. Unsorted or duplicate arrays invalidate the store. There is no label registry.
- `--create` accepts repeatable `--label`. `--relabel ID [--add L ...] [--remove L ...]` changes labels in any state without a claim token and bumps the revision. It needs at least one `--add` or `--remove`, rejects a label in both (exit 2), and returns exit 4 when nothing changes or the result would exceed 32 labels.
- `--list` and `--ready` accept repeatable `--label`; an issue must have every given label. The board gains a Labels column between Title and Agent.
- Schemas, shared fixtures (one labels scenario and five invalid-store cases), a new CLI test, the cross-client epic/type/priority interop test, and the integration example cover labels.
- All five clients implement the change. Locally on macOS: Python unittest (29 active, 4 skipped pair tests), each port's native tests, `make check`, `make py-integration`, and `make matrix` (22 CLI tests per client and 4 interop tests per pair, all 15 suites passing).
- Not yet verified: this branch's Linux and Windows CI runs.
