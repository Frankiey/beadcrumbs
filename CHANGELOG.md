# Changelog

All notable changes to Beadcrumbs are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and client releases use [Semantic Versioning](https://semver.org/).

Client release versions are separate from the on-disk store version in `store.json`. Until the protocol freezes, the store format is **v1 draft 1** and may still change between releases.

## [Unreleased]

## [0.1.0] - 2026-11-20

First public release. The store format is v1 draft 1.

### Added

- Offline, filesystem-native issue store at `.beadcrumbs/`: one JSON file per issue, a versioned manifest, and no Git, network, or database dependency.
- Core lifecycle: `--init`, `--create`, `--show`, `--list`, `--ready`, `--blocked`, `--claim`, `--note`, `--release`, `--close`, and `--validate`.
- Dependencies with a derived ready/blocked view, and race-safe claims with fresh claim tokens under a single writer lock.
- Atomic publication: every mutation writes a complete record to a scratch file, syncs it, and renames it into place.
- Task briefs: description (inline, from a file, or from stdin) and acceptance criteria.
- Issue types (`task`, `bug`, `chore`, `docs`, `spike`) and priorities 0–4. Lists sort by priority, then age.
- Epics: separate records with a fixed key and title and an editable description. `--create-epic`, `--edit-epic`, `--show-epic`, `--epics`, and `--set-epic`.
- Free-form labels: up to 32 per issue, set with `--label` and changed with `--relabel`, with filters on `--list` and `--ready`.
- `--board`: a Markdown snapshot grouped by epic, with a per-epic status summary.
- Machine-readable `--json` output and a documented exit-code contract.
- Five independent clients sharing one protocol: Python (reference, single stdlib file), TypeScript, Go, Rust, and .NET.
- JSON schemas, shared fixtures, a black-box CLI suite, and a cross-client interoperability matrix.
- CI on Linux, macOS, and Windows, and a Makefile with the same targets.

[Unreleased]: https://github.com/Frankiey/beadcrumbs/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Frankiey/beadcrumbs/releases/tag/v0.1.0
