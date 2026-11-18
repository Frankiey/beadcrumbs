# Proposed Beadcrumbs feature set

This proposal follows the [Beads source review](research/beads-feature-extraction.md). The [core contract](core-contract.md) adopts task briefs, acceptance criteria, list, blocked explanations, and validation into v1 draft 1. Features marked Next or Later remain proposals. The Python implementation now covers core draft 1. See [progress](../PROGRESS.md) for verification evidence.

| Scope | Feature | Acceptance criteria | Effect on current draft |
| --- | --- | --- | --- |
| Foundation | Offline initialization and explicit workspace | Initialize in a temporary directory outside Git with networking unavailable. A second init preserves existing valid data. | Already specified. |
| Foundation | Create and show | Full issue records round-trip through JSON and survive a new client process. Invalid stores fail visibly. | Already specified. |
| Foundation | Blocking dependencies and ready | A dependent stays absent until every blocker closes. Ready ordering is deterministic. | Already specified. |
| Foundation | Claim, note, release, close | Two competing workers produce one successful claim. An old claim token cannot release a newer claim. Notes persist across sessions. | Already specified. |
| Foundation | Atomic publication and recovery | Interrupt before and after replacement. Readers see complete old or new records. Document manual lock recovery. | Already specified. |
| Core draft 1 | Task brief and acceptance criteria | Create/show preserve multiline text and Unicode. An agent can retrieve enough context to perform and verify the task. | Required description and acceptance_criteria strings, empty at creation when omitted. Explicit conversion of earlier draft records. |
| Core draft 1 | List and blocked explanations | List includes open, claimed, and closed issues under explicit filters. Blocked output names the unresolved dependency IDs and their states. | Specified in the CLI contract. |
| Core draft 1 | Issue types, priority, and epics | Ready work is ordered by priority (0–4, default 2), then age. Each issue has a fixed type (`task`, `bug`, `chore`, `docs`, `spike`). Epics are separate records with a fixed key and title and an editable description. Issues move between epics with `--set-epic`. Lists filter by type and epic, and the board groups by epic. | Adopted into v1 without a version bump, since nothing had been released. New `epics/` directory and three issue fields. |
| Core draft 1 | Local store validation | Report malformed records, unsupported versions, missing dependencies, and cycles. A healthy store returns success. Validation performs no repairs. | Specified shared validator and transient locking. |
| Next | Claim next ready issue | Selection and claim happen under one lock, using the same eligibility and ordering as ready. Empty work has a defined success result. | New CLI action. Define retry behavior after ambiguous output. |
| Next | Editable task content | Edits preserve unrelated fields and reject an outdated expected revision. | New update command, revision guard, and explicit mutable fields. |
| Next | Offline workflow context | Print supported commands and a bounded summary from the local store for a new agent session. | Read-only command with an output budget. |
| Later | Labels, nested grouping, search | Demonstrated need for finding or grouping work beyond type, epic, status, and dependencies. | Specify field semantics and query rules first. |
| Later | Import from Beads | Preview supported mappings and report every dropped field or relationship. Preserve originals and validate the complete resulting graph. | Dedicated migration design and fixtures pinned to export versions. |

The adopted first release additions are small enough to retain full directory scans, one issue JSON file per task, and a single shared lock. A task description and acceptance criteria can live in the same record as its notes. List, blocked explanations, and validation can reuse the existing read and validation path.

Automatic lease expiry, replication, workflow templates, messaging, remote tracker integrations, semantic summarization, and server/UI modes are deferred. Each adds execution or coordination behavior beyond the initial local tracker. Independent Go, Rust, .NET, and Node.js clients become useful after the format and interoperability fixtures stabilize.

## Decisions needed before the protocol freezes

1. Review the adopted task content and input rules against real agent workflows.
2. Priority and type are fixed at creation, and only an issue's epic can change. Decide whether re-prioritizing needs its own command before the protocol freezes.
3. Keep dependencies immutable and closed issues terminal for the first release. Any future editing or reopening proposal must define how already claimed dependents behave.
4. Decide how retryable mutations identify an earlier successful request. The initial release can retain the documented inspect-before-retry procedure, while stronger idempotency requires additional protocol state.

## Delivery sequence

Implement and test the existing foundation first, including process contention and interruption. Implement the adopted draft 1 additions using the protocol and CLI contracts. Then freeze v1 with valid and invalid store fixtures and cross-process tests. Add a second implementation only once it can be checked against those same fixtures.

A release demonstration should create a brief, create a dependent task, show why it is blocked, claim and finish the prerequisite, discover the newly ready task, and recover an interrupted worker. Run this demonstration in a plain local directory with networking unavailable.
