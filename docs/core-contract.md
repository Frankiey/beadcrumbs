# Beadcrumbs core contract

Version 1, draft 1. This document defines the implementation target. The Python reference CLI implements this draft. Independent-client interoperability has yet to be verified.

The words MUST, MUST NOT, and SHOULD express requirements, prohibitions, and recommendations. The [protocol](protocol.md), [CLI](cli.md), [concurrency](concurrency.md), and [security](security.md) documents form the detailed contract. Any disagreement between them is a specification defect to resolve before shipping.

## Scope and environment

A conforming client MUST operate offline on a caller-selected local workspace. Tracker operations MUST use ordinary files without a database, daemon, network service, or Git dependency. The Python reference client MUST remain a single Python 3.10+ file using the standard library.

Draft v1 supports cooperating processes sharing one physical store on one machine. The filesystem MUST support exclusive directory creation and atomic same-directory file replacement. Store writers and their parent directories are trusted under the OS access boundary.

## Core capabilities

| Capability | Required behavior |
| --- | --- |
| Initialize | Create a versioned manifest and issue directory. Repeating initialization on a valid store preserves its data. |
| Create | Persist a title, description, acceptance criteria, and optional blocking dependencies. Return the full created issue. |
| Board | Generate a Markdown snapshot of all issues in workspace-level board.md. |
| Inspect | Show an issue, list issues, list ready work, and explain blocked open issues through unresolved dependency IDs and states. |
| Claim | Claim only ready work, with eligibility checked while holding the store lock. Return the newly assigned claim token. |
| Record progress | Append an attributed note in any state. |
| Release | Require the current claim token, clear the claim, and return the issue to open. |
| Close | Require the current claim token, clear the claim, and make the issue terminal. |
| Validate | Check the entire store using the same rules as normal operations. Return a successful validation result or a nonzero failure. |

Descriptions and acceptance criteria are adopted into this draft as immutable strings with empty defaults at creation. List, blocked, and validate are adopted as core commands. Priority, editable content, automatic claim-next, expiring claims, hierarchy, and import remain future proposals.

## Identity and state

Issue IDs MUST be full lowercase compact UUIDv4 values prefixed with `bc-`. Clients MUST validate supplied IDs before constructing a path. Prefix matching is outside v1.

An issue MUST have exactly one state from `open`, `claimed`, and `closed`. Ready and blocked are derived views of open issues. A ready issue has every direct dependency closed. A blocked issue has at least one direct dependency open or claimed. Missing dependencies invalidate the store.

Claim tokens identify assignments and MUST be freshly generated for each successful claim. Agent labels provide attribution. Workspace readers can see the tokens. Claims persist until explicitly released or closed.

| Action | Precondition | Record change |
| --- | --- | --- |
| Create | Every supplied dependency exists and IDs are distinct. | New open issue, null claim, empty notes, revision 1. |
| Claim | Issue is open and ready. | State claimed and new agent/token pair. |
| Note | Issue exists in any state. | Append one note. |
| Release | State claimed and token matches. | State open and null claim. |
| Close | State claimed and token matches. | State closed and null claim. |

Each successful mutation of an existing issue MUST increment revision once and update its mutation timestamp. A rejected mutation MUST preserve authoritative records. Repeating claim, release, or close after a state change is a conflict. Notes require attribution but no claim token.

## Coordination and failure

Every store command MUST acquire the shared lock and validate the store before acting, with the pre-lock manifest checks described in the concurrency specification. Validation and other reads create and remove only that transient lock. Initialization may create missing store structures.

All issue mutations MUST publish one complete issue record through atomic replacement. The replacement is the commit point. A successful response MUST describe the committed result. Clients MUST NOT infer assignment from a previous ready listing.

A process can stop after publication but before returning output. A caller receiving an interrupted or failed response MUST inspect the current state before retrying a mutation. V1 provides no request deduplication. Repeated create and note requests can create duplicates. Recover a lost claim response by showing the issue and checking its current assignment. A claim token can also be used for explicit operator recovery once the original worker has stopped.

An abandoned lock requires all clients to stop before manual removal. Process-interruption atomicity is required. Power-loss durability and coordinated writes across independent copies are outside the v1 guarantee.

## Compatibility

The manifest version governs record shape, validation, and coordination semantics. Unsupported versions MUST be rejected before creating a lock or scratch file. Unknown fields are invalid. Draft 1 adds description and acceptance criteria to the earlier unreleased draft. Earlier hand-authored records missing these fields fail validation and require an explicit offline edit adding empty strings after backing up the store and stopping clients. Clients MUST NOT silently rewrite them.

After v1 freezes, changing required or allowed fields or coordination rules requires a new protocol version. Conforming clients MUST agree on the semantic JSON results and exit codes. JSON whitespace, member order, and human-readable presentation may differ.

## Conformance scenarios

| Scenario | Required observation |
| --- | --- |
| Plain directory | Initialization and the complete issue lifecycle work outside a Git repository with networking unavailable. |
| Task content | Multiline Unicode descriptions and acceptance criteria survive create/show round trips. |
| Dependency chain | B depends on A. B is blocked until A closes, then becomes ready. |
| Competing claims | Two independent processes claim one issue. Exactly one succeeds. The other returns busy or conflict according to when it acquires the lock. |
| Stale assignment | Claim, release, and claim again. The original token cannot close or release the new assignment. |
| Publication interruption | Before replacement, the old record remains. After replacement, a complete new record is visible after lock recovery. |
| Invalid store | Duplicate JSON keys, invalid Unicode, cycles, missing dependencies, and unexpected protocol-path file types cause failure. |
| Unsupported version | Operations fail with no lock, scratch file, or record change. |
| Empty views | List, ready, and blocked return empty arrays when appropriate. Validation succeeds for an initialized empty store. |
| Independent client | Another implementation reads and mutates the same records with the same lifecycle and lock behavior. |

Verification coverage and remaining platform checks are recorded in [Conformance](conformance.md) and [implementation progress](../PROGRESS.md).

## Implementation requirement

Every client MUST isolate issue encoding/decoding and filename rules behind an explicit codec boundary. Logical issue validation and state transitions MUST operate on decoded records. Rendering MUST accept logical records independently of persistence. See [implementation boundaries](implementation-boundaries.md) for the interface and format evolution rules.
