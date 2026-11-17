---
name: beadcrumbs-protocol
description: Implement or review Beadcrumbs changes to JSON store records, issue state transitions, claim tokens, locking, or atomic publication. Use when a change can affect clients sharing an on-disk store.
---

# Beadcrumbs protocol changes

1. Read the repository's [protocol](../../../docs/protocol.md) and [concurrency](../../../docs/concurrency.md) specs. For CLI-facing changes, also check the [CLI contract](../../../docs/cli.md).
2. Check the behavior with an existing store and a second cooperating process. For mutations, verify that current state is checked under the shared lock, at most one authoritative record is published, and a failure before publication leaves the prior record intact.
3. Verify the affected behavior in a temporary workspace. For claim changes, check contention and an outdated token. For format changes, check that an unsupported store version is rejected before a lock or scratch file is created.
4. When a change alters the draft contract, update the affected spec and examples alongside the implementation. After v1 freezes, follow the protocol versioning rules.
