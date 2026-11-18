# FAQ & troubleshooting

## General

### What is Beadcrumbs for?

Coordinating multiple coding agents, or agents and humans, working in the same local workspace. It answers three questions: *what can I work on now*, *is anyone else on it*, and *what happened so far*. It works without a network, a server, or Git.

### How is it different from Beads?

Beadcrumbs was shaped by a [review of Beads](research/beads-feature-extraction.md). Beads is a full-featured tracker with priorities, epics, workflow templates, history, and replication. Beadcrumbs deliberately keeps only the core loop (create, ready, claim, note, close) so the reference client fits in one standard-library Python file and the store is plain JSON any language can implement.

### Why JSON and not YAML or SQLite?

JSON parsing ships with Python's standard library and gives independent clients a small, strict parsing contract. YAML would need a dependency or a custom parser. SQLite would make the store opaque to `cat` and `grep`. For human browsing there's `--board`. See [ADR 0001](adr/0001-filesystem-as-interface.md).

### Does it need Git?

No. Git is optional. You can version the store if you want; see [Can I commit the store to Git?](#can-i-commit-the-store-to-git).

### Does it phone home?

No. The client makes no network calls, sends no telemetry, runs no subprocesses, and performs no Git operations. The test suite runs a full lifecycle under an audit hook that fails on any socket or subprocess use.

## Errors and recovery

### `beadcrumbs: Store is busy` (exit 5) on every command

Every command, including reads, holds `.beadcrumbs/.writer.lock/` briefly. Occasional exit 5 under contention is normal; retry with backoff ([wrapper](agent-guide.md#a-retry-wrapper)).

If it **never** clears, a process was probably killed while holding the lock:

1. Stop every client that uses this store.
2. Check that `.beadcrumbs/.writer.lock` is an **empty directory**.
3. Remove it: `rmdir .beadcrumbs/.writer.lock`
4. Run `python3 beadcrumbs.py --validate` before resuming.

There is intentionally no automatic stale-lock removal. A timestamp or PID cannot prove that nobody holds the lock. Details are in [concurrency](concurrency.md#recovering-an-abandoned-lock).

### A worker crashed while holding a claim

Claims never expire. Once you're sure the worker is gone, read the token from the record and release it:

```sh
python3 beadcrumbs.py --show "$ID" --json      # copy claim.token
python3 beadcrumbs.py --release "$ID" --token "$TOKEN"
```

### My command got killed: did it happen or not?

Maybe. The atomic rename may have committed before the output was printed. **Inspect before retrying** with `--show` or `--list`; `--create` and `--note` are not deduplicated. See [retrying safely](agent-guide.md#retrying-safely-after-an-ambiguous-result).

### Exit 1: "invalid store"

Something under `.beadcrumbs/` failed validation. Common causes:

- a hand-edited record with a typo, duplicate key, or unknown field
- a file ending in `.json` in `issues/` that isn't a valid issue (every `*.json` there is treated as one)
- a dependency pointing at a deleted issue file
- a symlink at a protocol path
- an issue file whose name doesn't match its `id`

Run `python3 beadcrumbs.py --validate`, fix or restore the reported file **with all clients stopped**, and validate again. Beadcrumbs never repairs a store automatically.

### Exit 4 when closing my own issue

Your token doesn't match the current claim. Someone probably released and re-claimed the issue after you, which is exactly what tokens are for. Re-read the issue with `--show`.

### Leftover `.tmp-*` files

These are scratch files from an interrupted write. Issue scans ignore them. Delete them during maintenance with all clients stopped.

## Usage

### How do I reopen a closed issue or change a title?

You can't in v1. Closed is terminal and titles, descriptions, and dependencies are immutable. Create a new issue, optionally depending on the old one, and add a note on the old one pointing at it. Editable content is on the [roadmap](features.md).

### How do I delete an issue?

There's no delete command. Deleting a file by hand would break any issue that depends on it, so the store would fail validation. Close it with a note explaining why.

### Is there priority ordering?

Yes. Create issues with `--priority 0` (most urgent) through `4`; the default is `2`. `--ready`, `--list`, and `--blocked` sort by priority, then creation time, then ID. Priority is fixed at creation.

### Are there epics, stories, or sub-tasks?

There's one kind of issue. Group related issues into an **epic**: a separate record with a key, a title, and an editable description. Create one with `--create-epic KEY --title TITLE`, assign issues with `--epic KEY` on create or `--set-epic ID --epic KEY` later, and see progress with `--show-epic KEY`. Epics have no state of their own and never block work; use `--depends-on` for ordering. Each issue also has a type (`task`, `bug`, `chore`, `docs`, or `spike`) for filtering.

### Can I use a store on a network share or Dropbox?

Not supported in v1. The lock relies on atomic exclusive `mkdir` and same-directory rename semantics, which sync tools and many network filesystems don't guarantee. Use one machine and a local filesystem.

### Can I commit the store to Git?

Yes. This repository ignores `/.beadcrumbs/` by default. To track a store, ignore only the transient files:

```gitignore
/.beadcrumbs/.writer.lock/
/.beadcrumbs/.tmp-*
/.beadcrumbs/issues/.tmp-*
```

Caveats: Git doesn't take the Beadcrumbs lock, history retains old task text **and claim tokens**, and an empty `issues/` directory isn't tracked. See [local data and Git](security.md#local-data-and-git).

### Is it secure for untrusted agents?

No. The workspace is a trust boundary. Anyone who can write to it can edit records directly, and agent labels aren't authenticated. Use OS permissions to control who can write. See the [threat model](security.md).

### How big can a store get?

Every command scans and validates the whole store, so it's designed for hundreds of issues rather than hundreds of thousands. Notes grow inside their issue file.

## Development

### How do I run the tests?

```sh
python3 -m unittest discover -s tests -v
```

### How do I test my own client implementation?

```sh
BEADCRUMBS_COMMAND='["/abs/path/to/client"]' python3 -m unittest discover -s tests -p test_cli.py -v
```

See [conformance](conformance.md) and [CONTRIBUTING](../CONTRIBUTING.md).
