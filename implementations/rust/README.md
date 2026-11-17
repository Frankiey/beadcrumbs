# Rust client

The Codec trait isolates encoding from logical validation and lifecycle. Store code owns locking and atomic publication. Board rendering works on logical records. The executable does not invoke Python.

From the repository root with Rust 1.85+ and locked crates cached locally

```sh
cargo test --offline --locked --manifest-path implementations/rust/Cargo.toml
cargo build --offline --locked --manifest-path implementations/rust/Cargo.toml
implementations/rust/target/debug/beadcrumbs --help
```

Cargo.lock is checked in. serde and serde_json provide JSON primitives and getrandom supplies operating-system randomness. Strict decoding rejects duplicate keys and non-integer numeric spellings before logical validation. Native tests exercise strict decoding and a substituted codec through the lifecycle. target/ is ignored and Cargo publishing is disabled.

Verified locally with Rust 1.94.1 on macOS. The minimum toolchain and other operating systems still need verification. For a fresh air-gapped build, provision the locked crates separately before entering the isolated environment.
