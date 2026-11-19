# Conformance and testing

Run the reference suite from the repository root with Python 3.10 or later.

```sh
python3 -m unittest discover -s tests -v
```

The CLI suite launches a separate process for each command. It uses temporary directories outside Git. To exercise another client, set BEADCRUMBS_COMMAND to a JSON array containing its executable and any fixed arguments, then run only test_cli.py.

```sh
BEADCRUMBS_COMMAND='["/absolute/path/beadcrumbs-go"]' python3 -m unittest discover -s tests -p test_cli.py -v
```

[Shared cases](../tests/fixtures/cases.json) define initial manifests and issues, argument arrays, expected exit codes, and exact semantic JSON results for deterministic read cases. A missing manifest property defaults to the v1 manifest. The runner appends --json. Mutation tests compare invariants and resulting records because IDs, claim tokens, and timestamps are generated at runtime.

[Manifest schema](../schemas/v1/manifest.schema.json), [issue schema](../schemas/v1/issue.schema.json), and [epic schema](../schemas/v1/epic.schema.json) describe JSON structure using draft 2020-12. [Result definitions](../schemas/v1/results.schema.json) expose named $defs for issues, blocked, validation, board, epics, and epic detail results. Init returns the manifest schema, individual issue commands return the issue schema, and create-epic and edit-epic return the epic schema. Fixture cases may also define `epics` records, or raw `epic_files` by filename. Resolve relative references locally. The schemas do not require network access.

A JSON Schema validator must enable format assertions for calendar timestamp checking. Structural schemas do not detect duplicate keys, unsorted labels, integer lexical forms, unpaired Unicode surrogates, filename/ID mismatches, graph cycles, missing dependency or epic targets, or command transitions. Those requirements belong to the protocol validator and conformance suite. The runtime uses its own standard-library validator. The suite parses schema documents but does not include a general JSON Schema engine.

Reference-only storage tests inject fsync and replacement failures and terminate subprocesses immediately before and after replacement. After confirming the process has exited, the tests remove the abandoned lock and validate the store. These tests exercise process-interruption atomicity. An offline lifecycle also runs under a Python audit hook that rejects socket and subprocess activity by the tracker.

## Multiple clients

Build each client following implementations/README.md and its linked package guides, then run

```sh
python3 integration/test_clients.py
```

The runner executes 22 CLI tests for each of five clients, followed by four interoperability tests for every unordered pair. All 150 test executions passed locally on 19 November 2026. Pair tests exercise bidirectional lifecycle operations, epics, types, priorities and labels, board agreement, mixed-process claim contention, stale tokens, and shared lock/version handling. POSIX CLI tests include rejecting FIFOs without blocking. Windows skips that case.

To run a subset, use `--clients python typescript`. To run one pair directly, set BEADCRUMBS_PRIMARY_COMMAND and BEADCRUMBS_PEER_COMMAND to JSON argv arrays and run unittest discovery with `-p test_interop.py`. Pair tests skip when no peer is configured. The default Python discovery runs 29 active tests and skips the four pair tests.

Each port also has native strict-decoding and codec-substitution tests. TypeScript additionally injects process interruption and fsync failure. Go and .NET test failed publication cleanup. Rust's native suite currently does not inject publication failures.

Verified on macOS with Python 3.15.2, Node 26.13.1, Go 1.27.4, Rust 1.94.1, and .NET SDK 11.0.100. Linux, Windows, minimum declared toolchains, complete JSON Schema validation, and real power-loss behavior remain unverified. Cross-client parity is demonstrated for the covered scenarios, not all possible inputs. The protocol remains a draft until broader conformance evidence exists.
