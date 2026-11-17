# 0003 Use explicit claims with tokens

**Status** Proposed

## Context

Workers can share an agent label or resume after an interruption. An older worker could otherwise close an issue after another worker has claimed it.

## Decision

Issue a fresh token on each claim and require it on close and release. Keep claims active until an explicit state change. Dependency edges are fixed at creation and closed issues stay closed.

## Consequences

Workers can run for an arbitrary period without a heartbeat or a shared clock. The operator must recover claims abandoned by a worker. The token identifies an assignment and is visible to store readers. The OS access boundary governs who can operate on the store.
