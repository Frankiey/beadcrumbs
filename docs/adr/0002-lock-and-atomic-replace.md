# 0002 Serialize operations and publish one record at a time

**Status** Proposed

## Context

A claim depends on the state of multiple issues. Two clients can see the same ready result. A write can also stop before it finishes.

## Decision

Acquire a store-wide lock using exclusive directory creation. Recheck eligibility under that lock. Publish each issue mutation through same-directory atomic replacement. Readers use the same lock for a coherent view of the dependency graph.

## Consequences

Clients need only two filesystem primitives for coordination and publication. Contention makes readers and writers retry, and process termination can require manual unlock. Per-issue locking would add ordering and snapshot rules to the protocol. The v1 guarantee covers process interruption on supported local filesystems. Power-loss durability is outside that guarantee.
