# Security and threat model

Beadcrumbs coordinates cooperating agents in a trusted local workspace. Offline operation means the client performs no network calls, telemetry, package downloads, subprocess execution, or Git operations. Air-gap enforcement belongs to the host environment.

## Workspace boundary

Choose a workspace whose writers you trust. OS accounts, directory permissions, and managed ACLs define the boundary. On POSIX, request owner-only permissions when creating tracker directories and files (`0700` and `0600`, subject to a stricter umask). On Windows, inherit the workspace ACL. Deployments that deliberately share the store across accounts must arrange equivalent access for all participants, including on replacement files. V1 does not change ACLs on existing paths.

Accept an explicitly selected workspace that resolves to a directory. Reject symlinks and, where applicable, reparse points at protocol paths within it, including the store root, manifest, issues directory, issue candidates, and lock. Require ordinary directories and files where specified. Construct issue paths from validated IDs. Create scratch files exclusively with unpredictable names. Atomic replacement avoids updating existing issue file contents in place.

These checks guard against accidental path traversal and misplaced files. Processes with write access to the workspace can race path checks or tamper with records and locks. v1 assumes the workspace and its parents stay under trusted control during execution.

## Identity and claims

Agent labels are caller-supplied attribution. Claim tokens detect stale assignments. Anyone who can read an issue can see the token, and anyone with store write access can modify records directly. The tracker provides neither authentication nor a tamper-evident audit trail.

## Untrusted text

Treat titles and notes as data. Never execute them or pass them through a shell. Escape terminal control characters, including ESC, C0/C1 controls, and bidirectional formatting controls, in human-readable output and diagnostics that include store content. JSON output preserves content after decoding. Agents should treat retrieved issue text as untrusted input and follow the authority and workspace rules of their host.

Malformed data stops store operations under the validation rules in the [protocol](protocol.md#validation-and-compatibility). Resource use grows with issue count and note history. A writer who can create arbitrarily large records can exhaust local resources.

## Local data and Git

Keep secrets and sensitive corporate data out of titles and notes unless the workspace and its backups are approved for that content. The default source-repository ignore rule excludes the entire local store. To version a store here, replace that rule with `/.beadcrumbs/.writer.lock/`, `/.beadcrumbs/.tmp-*`, and `/.beadcrumbs/issues/.tmp-*`, and `/.beadcrumbs/epics/.tmp-*`. Track the manifest, issue records, and epic records. Git does not track empty directories, so recreate an empty `issues/` or `epics/` directory offline before using a checked-out store. Reconcile divergent versions with all clients stopped. A Git commit or merge does not acquire the Beadcrumbs lock, and Git history can retain old task text and claim tokens.
