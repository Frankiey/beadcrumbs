# Repeatable integration example

From the repository root, run the full integration scenario.

```sh
python3 integration/run.py
```

The script uses the public CLI in separate processes and checks dependency readiness, blocked explanations, claim conflicts, release and reclaim, stale-token rejection, notes, completion, validation, and repeat initialization. It leaves two completed issues and one ready follow-up for exploration. Failure returns exit 1 and records the error.

To create a starting workspace for manual experimentation, run the setup mode.

```sh
python3 integration/run.py --setup-only
```

Setup mode verifies a ready prerequisite and a blocked dependent, then leaves both open.

Every invocation creates a fresh directory under `integration/.runs/`. Each run contains `workspace/` with the example store and brief, `commands.jsonl` with CLI arguments and outputs, and `summary.json` with the result and issue IDs. The console prints the exact workspace path. Previous runs remain available.

Inspect a workspace by copying its printed path into the command below.

```sh
python3 beadcrumbs.py --workspace "/path/printed/by/the/script/workspace" --list
```

The script and this guide belong in Git. The generated `.runs/` directory is ignored. Remove individual run directories when finished with them.

This persistent example complements the temporary-workspace suite in `tests/`. It requires only Python 3.10+ and uses local files.

Both modes also generate workspace/board.md for a readable overview.

## All-client compatibility matrix

Build the clients using the guides under implementations/, then run `python3 integration/test_clients.py`. Use `--clients python typescript` for a subset. The runner requires existing local build outputs and does not install dependencies or build packages. It saves per-client and per-pair logs plus summary.json in a new ignored .runs/clients-* directory. Test stores are temporary and cleaned up automatically. Use run.py above when you want a persistent example store to inspect.
