# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems.

Report them privately through GitHub's [private vulnerability reporting](https://github.com/Frankiey/beadcrumbs/security/advisories/new) for this repository. Include:

- the affected client(s) and version (`--version`), OS, and filesystem
- the commands or store contents that trigger the problem
- what an attacker can achieve, and under which access assumptions

You should get an acknowledgement within a week. Once a fix is ready, we'll coordinate a disclosure date with you and credit you in the advisory unless you'd rather stay anonymous.

## Supported versions

Beadcrumbs is pre-release (protocol v1 draft 1, clients 0.1.x). Only the latest commit on `main` receives fixes.

## Scope

Beadcrumbs trusts the workspace it runs in. Read the [threat model](docs/security.md) before reporting. In short:

**In scope:**

- path traversal or escaping the workspace through crafted IDs, symlinks, reparse points, or special files
- a client accepting a record that the [protocol](docs/protocol.md) says is invalid, or publishing a partial or corrupt record
- terminal escape or control-sequence injection through issue text in human-readable output
- any network access, subprocess execution, or telemetry by a client
- a stale claim token closing or releasing a newer claim

**Out of scope (documented limits):**

- a process with write access to the workspace tampering with records, locks, or claim tokens
- agent labels being unauthenticated
- claim tokens being readable by anyone who can read the store
- resource exhaustion by a writer that creates very large records
- loss of durability on power failure, and stores on network shares or synced folders
