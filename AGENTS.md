# Working on Beadcrumbs

- Keep `beadcrumbs.py` runnable as a single file on Python 3.10 or later using only the standard library. The tracker must operate offline with a local filesystem and no Git dependency.
- Read [PROGRESS.md](PROGRESS.md) at the start of work. Update it with completed steps, verification evidence, and remaining work before handing off to another chat.
- Use [the CLI spec](docs/cli.md) for public commands, JSON output, and exit codes. Use [the protocol spec](docs/protocol.md) and [the concurrency spec](docs/concurrency.md) for on-disk compatibility.
- For changes to store records, issue state, locking, or publication, follow the [Beadcrumbs protocol skill](.agents/skills/beadcrumbs-protocol/SKILL.md).
- Verify CLI changes from the repository root with `python3 -m unittest discover -s tests -v`, and run `make check` (or the relevant `make` targets) before opening a pull request; CI runs the same targets. Use temporary workspaces for tests that create tracker data.

- Across all language implementations, follow [implementation boundaries](docs/implementation-boundaries.md). Keep issue serialization behind a codec, logical validation and lifecycle independent of encoding, filesystem publication centralized, and presentation separate from persistence.
