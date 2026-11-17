# Implementation boundaries

All Beadcrumbs implementations must keep serialization, issue semantics, filesystem operations, and presentation independently replaceable. In the single-file Python reference, these boundaries are functions and a small codec class within beadcrumbs.py.

## Issue codec

Each issue codec provides four operations.

| Operation | Input | Result |
| --- | --- | --- |
| accepts | Candidate filename | Whether the filename belongs to this encoding. |
| filename | Valid issue ID | Canonical filename with the encoding's suffix. Reject invalid IDs. |
| decode | Raw bytes | Decoded record using the shared logical field representation. |
| encode | Valid logical issue | Complete encoded bytes ready for publication. |

Codecs perform encoding-specific checks, such as JSON duplicate keys and invalid byte sequences. They have no filesystem, clock, lock, or network responsibilities. Encoding must preserve every supported field and value.

The store reader enumerates candidates through the selected codec, checks path types, decodes records, validates logical fields, checks filename identity, and validates the graph. The command layer performs lifecycle changes on logical records. The publisher writes the codec's bytes through exclusive scratch creation, flush, and atomic replacement. This preserves the single-record commit boundary when an encoding changes.

JsonIssueCodec is the v1 implementation. load_issues and run_action accept a codec internally for testing and future format dispatch. A test-only encoding exercises creation, readiness, claiming, notes, closing, reading, and board rendering with a different suffix and byte prefix. This proves the interface can be substituted within the reference implementation.

## Presentation

The Markdown renderer accepts logical issue records and an explicit generation timestamp, then returns text. The caller handles locking, output paths, and publication. CLI JSON results retain their own output contract. A storage encoding change must preserve those result shapes unless the CLI contract explicitly changes too.

## Format evolution

V1 continues to use store.json and JSON issue files. A future YAML or custom encoding requires a new manifest version, matching filename rules, fixtures, and explicit migration. Clients select one encoding for the entire store from the supported manifest version before loading issue files. Unsupported versions fail before locking as specified today.

Changing a file extension or selecting an internal test codec does not constitute a supported migration. Future migration must preserve IDs, revisions, timestamps, claims, dependencies, and notes, with defined crash recovery and reader compatibility. Mixed-format stores require a separate protocol design.

The manifest remains the bootstrap document through which clients determine support. Its current JSON encoding can also change only through an explicit bootstrap/versioning design.

## Language implementations

Use idiomatic equivalents of these boundaries in each language. Go uses a Codec interface, Rust a Codec trait, .NET an IIssueCodec interface, and TypeScript an IssueCodec interface. Native tests substitute a test codec in every client. The shared semantics and conformance results govern compatibility. Runtime plugin loading is unnecessary for the current static v1 codec.
