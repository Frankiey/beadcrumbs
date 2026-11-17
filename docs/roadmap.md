# Roadmap

Current execution status and handoff notes live in [PROGRESS.md](../PROGRESS.md).

The [proposed feature set](features.md) expands the scope discussion using the [Beads source review](research/beads-feature-extraction.md). The [core contract](core-contract.md) adopts the first-release additions into draft 1. Next and Later features remain proposals.

## 0. Design and scaffold

- Review workspace selection, the v1 record format, claim recovery, and error handling.
- Verify the single-file entry point and dependency-free test command.

## 1. Python reference implementation

- Build manifest initialization, protocol validation, locking, and atomic record replacement.
- Add create, show, and ready. Cover dependency validation, deterministic ordering, and machine-readable output.
- Add claim, note, release, and close. Exercise contention between independent processes, an outdated claim token, and interruption before and after publication.
- Verify offline operation and atomic replacement on the OS and local filesystem combinations the release will support. Publish that support list with the release.

## 2. Interoperable v1 release

- Freeze the on-disk rules, lock behavior, and CLI JSON contract together.
- Publish valid and invalid record fixtures, expected ready order, and expected exit codes. Include duplicate keys, malformed Unicode, unsupported versions, missing dependencies, and invalid paths.
- Use the same fixtures and cross-process tests for each independent client. Require bidirectional reads and writes against a shared store, including a race between different implementations for the same claim.
- Consider Go, Rust, .NET, or Node.js clients when there is a deployment need. Each implementation should run independently of the Python script.

Revisit indexes, split event logs, and synchronization when a concrete use case exceeds the draft's small local-store model.
