# Python client

The Python client lives at the repository root: [`beadcrumbs.py`](../../beadcrumbs.py). There is no code in this directory.

## Why it lives at the root

- **Copy-and-run.** The reference client is one standard-library file for Python 3.10+. Keeping it at the top level makes "copy `beadcrumbs.py` into your workspace and run it" as short as possible.
- **It's the reference implementation.** The shared CLI suite in [`tests/`](../../tests) runs against it by default, and the [integration example](../../integration/README.md) drives it. The other clients are checked against the same tests.
- **The specs still come first.** Python is the reference, but the [core contract](../../docs/core-contract.md), schemas, and fixtures define compatibility. It follows the same [implementation boundaries](../../docs/implementation-boundaries.md) as the other clients, implemented as functions and a small codec class inside the one file.

If the client ever outgrows a single file, for example to package it for `pip install`, it would move here and leave a thin entry point at the root.

## Run and test

From the repository root:

```sh
python3 beadcrumbs.py --help
python3 -m unittest discover -s tests -v
```

No build step or dependencies are needed. See [Getting started](../../docs/getting-started.md) for a full walkthrough.
