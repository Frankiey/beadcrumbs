# Language implementations

Five independent clients implement the shared v1 draft. Python remains a copy-and-run single file at the repository root. Each other client operates directly on the store without invoking Python.

| Client | Source | Build requirements | Runtime |
| --- | --- | --- | --- |
| Python | ../beadcrumbs.py | None | Python 3.10+ standard library |
| TypeScript/npm | javascript/src | Node 22+, npm, pinned TypeScript dev dependencies | Node 22+, no npm runtime dependencies |
| Go | go/cmd and go/internal | Go 1.22+ standard library | Native executable |
| Rust | rust/src | Rust 1.85+, Cargo, locked crates | Native executable |
| .NET | dotnet/src | .NET SDK 11, no NuGet packages | .NET 11 |

JavaScript ecosystem source is written in strict TypeScript and compiled to JavaScript for npm distribution. The directory is named javascript for the ecosystem. Native tests live beside each implementation. See each directory's README for build and test commands.

Build dependencies must already be available locally for an air-gapped build. The TypeScript and Rust lockfiles record dependencies, but do not bundle their archives. No client accesses the network at runtime. Packages remain unpublished and publishing is disabled for npm and Cargo.

All clients follow the shared [contract](../docs/core-contract.md) and [implementation boundaries](../docs/implementation-boundaries.md). The contract, schemas, shared fixtures, and behavioral tests define compatibility. Python is the reference implementation, not an executable dependency or the only specification.

After building, run `python3 integration/test_clients.py` from the repository root. It runs all five CLI suites and all ten client pairings. Generated output stays under ignored integration/.runs/. See [conformance](../docs/conformance.md) for coverage and platform limits.

Build products have package-local ignore rules. Release versions may differ, while store protocol versions determine compatibility. Future publication, signing, installers, and supported-platform certification remain separate work.
