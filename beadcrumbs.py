#!/usr/bin/env python3
# Copyright 2026 Frankiey
# SPDX-License-Identifier: Apache-2.0
"""Offline, filesystem-native issue tracking. Python 3.10+, standard library."""

import argparse
import json
import os
import re
import stat
import sys
import unicodedata
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
MANIFEST = {"format": "beadcrumbs", "version": 1}
TOKEN = r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}"
ID = "bc-" + TOKEN
AGENT = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
TIME = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
MAX_REVISION = 9007199254740991
FIELDS = {
    "id",
    "title",
    "description",
    "acceptance_criteria",
    "state",
    "depends_on",
    "claim",
    "notes",
    "created_at",
    "updated_at",
    "revision",
}


class Failure(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def require(condition, message):
    if not condition:
        raise Failure(message)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def text_value(value, nonempty=False):
    require(isinstance(value, str), "Expected text")
    require(not nonempty or bool(value), "Text must be nonempty")
    require(not any(0xD800 <= ord(char) <= 0xDFFF for char in value), "Unpaired Unicode surrogate")


def object_fields(value, fields):
    require(isinstance(value, dict) and set(value) == fields, "Invalid object fields")


def timestamp(value):
    require(matches(TIME, value), "Invalid timestamp format")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise Failure("Invalid calendar timestamp") from error


def path_kind(path, directory=False, optional=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if optional:
            return False
        raise Failure(f"Missing path: {path}") from None
    require(
        not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
        f"Linked protocol path: {path}",
    )
    predicate = stat.S_ISDIR if directory else stat.S_ISREG
    require(predicate(info.st_mode), f"Unexpected path type: {path}")
    return True


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        text_value(key)
        result[key] = value
    return result


def invalid_constant(value):
    raise Failure(f"Invalid JSON constant: {value}")


def decode_json(payload):
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as error:
        raise Failure(f"Invalid JSON: {error}") from error


def encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path):
    path_kind(path)
    return decode_json(path.read_bytes())


class JsonIssueCodec:
    """Pure v1 issue serialization and filename rules; no filesystem access."""

    def accepts(self, filename):
        return filename.endswith(".json")

    def filename(self, issue_id):
        require(matches(ID, issue_id), "Invalid issue ID")
        return issue_id + ".json"

    def decode(self, payload):
        return decode_json(payload)

    def encode(self, issue):
        return encode_json(issue)


ISSUE_CODEC = JsonIssueCodec()


def read_manifest(root):
    path = root / "store.json"
    if not path_kind(path, optional=True):
        return False
    value = read_json(path)
    require(isinstance(value, dict), "Invalid manifest")
    require(value.get("format") == "beadcrumbs", "Unsupported store format")
    require(type(value.get("version")) is int and value["version"] == 1, "Unsupported store version")
    object_fields(value, {"format", "version"})
    return True


def validate_issue(issue):
    object_fields(issue, FIELDS)
    require(matches(ID, issue["id"]), "Invalid issue ID")
    for field in ("title", "description", "acceptance_criteria"):
        text_value(issue[field], nonempty=field == "title")
    require(issue["state"] in ("open", "claimed", "closed"), "Invalid issue state")
    dependencies = issue["depends_on"]
    require(isinstance(dependencies, list) and all(matches(ID, dep) for dep in dependencies), "Invalid dependencies")
    require(len(set(dependencies)) == len(dependencies), "Duplicate dependency")
    if issue["state"] == "claimed":
        object_fields(issue["claim"], {"agent", "token"})
        require(matches(AGENT, issue["claim"]["agent"]), "Invalid agent")
        require(matches(TOKEN, issue["claim"]["token"]), "Invalid token")
    else:
        require(issue["claim"] is None, "Unclaimed issue has a claim")
    require(isinstance(issue["notes"], list), "Invalid notes")
    for note in issue["notes"]:
        object_fields(note, {"at", "by", "text"})
        timestamp(note["at"])
        require(matches(AGENT, note["by"]), "Invalid note author")
        text_value(note["text"], nonempty=True)
    timestamp(issue["created_at"])
    timestamp(issue["updated_at"])
    require(type(issue["revision"]) is int and 1 <= issue["revision"] <= MAX_REVISION, "Invalid revision")


def load_issues(root, codec=ISSUE_CODEC):
    directory = root / "issues"
    path_kind(directory, directory=True)
    issues = {}
    for path in sorted(directory.iterdir()):
        if codec.accepts(path.name):
            path_kind(path)
            issue = codec.decode(path.read_bytes())
            validate_issue(issue)
            require(path.name == codec.filename(issue["id"]), "Issue ID and filename must match")
            issues[issue["id"]] = issue
    indegree = {}
    dependents = {key: [] for key in issues}
    for key, issue in issues.items():
        indegree[key] = len(issue["depends_on"])
        for dep in issue["depends_on"]:
            require(dep in issues, f"Missing dependency: {dep}")
            require(
                issue["state"] == "open" or issues[dep]["state"] == "closed",
                "Claimed or closed issue has an unresolved dependency",
            )
            dependents[dep].append(key)
    queue = deque(key for key, count in indegree.items() if count == 0)
    visited = 0
    while queue:
        visited += 1
        for key in dependents[queue.popleft()]:
            indegree[key] -= 1
            if indegree[key] == 0:
                queue.append(key)
    require(visited == len(issues), "Dependency cycle")
    return issues


def publish(path, value):
    publish_bytes(path, encode_json(value))


def publish_bytes(path, payload):
    scratch = path.parent / (".tmp-" + uuid.uuid4().hex)
    descriptor = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
    finally:
        scratch.unlink(missing_ok=True)


def lock_pending_removal(lock):
    """Windows denies access to a directory while another process is still removing it."""
    if os.name != "nt":
        return False
    try:
        lock.lstat()
    except PermissionError:
        return True
    except FileNotFoundError:
        return False
    return True


@contextmanager
def store_lock(root, initialize):
    if initialize:
        root.mkdir(mode=0o700, exist_ok=True)
    path_kind(root, directory=True)
    manifest_exists = read_manifest(root)
    lock = root / ".writer.lock"
    if not manifest_exists and not initialize:
        try:
            locked = path_kind(lock, directory=True, optional=True)
        except PermissionError:
            if not lock_pending_removal(lock):
                raise
            locked = True
        if locked:
            raise Failure("Store is busy", 5)
        require(read_manifest(root), "Store is uninitialized")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        # The holder may remove the lock before we inspect it; that is still busy.
        try:
            path_kind(lock, directory=True, optional=True)
        except PermissionError:
            if not lock_pending_removal(lock):
                raise
        raise Failure("Store is busy", 5) from None
    except PermissionError:
        if not lock_pending_removal(lock):
            raise
        raise Failure("Store is busy", 5) from None
    try:
        yield
    finally:
        lock.rmdir()


def initialize_store(root):
    if read_manifest(root):
        return
    for path in root.iterdir():
        if path.name == ".writer.lock":
            continue
        if path.name == "issues":
            path_kind(path, directory=True)
            require(not any(path.iterdir()), "Uninitialized issues directory is not empty")
        elif matches(r"\.tmp-" + TOKEN, path.name):
            path_kind(path)
        else:
            raise Failure(f"Unexpected uninitialized content: {path.name}")
    (root / "issues").mkdir(mode=0o700, exist_ok=True)
    publish(root / "store.json", MANIFEST)


def blockers(issue, issues):
    return [
        {"id": dep, "state": issues[dep]["state"]} for dep in issue["depends_on"] if issues[dep]["state"] != "closed"
    ]


def markdown_cell(value):
    # Escape table separators and Markdown/HTML syntax in issue text.
    parts = []
    for char in value:
        if char in "\r\n":
            parts.append(" ")
        elif unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp"):
            parts.append(f"&#92;u{ord(char):04x}")
        elif char in "&<>|`[]*_\\":
            parts.append(f"&#{ord(char)};")
        else:
            parts.append(char)
    return "".join(parts)


def render_board(ordered, issues, generated):
    """Render a snapshot without accessing files or changing issue records."""
    sections = {name: [] for name in ("Ready", "Blocked", "Claimed", "Closed")}
    for issue in ordered:
        unresolved = blockers(issue, issues)
        section = issue["state"].title()
        if issue["state"] == "open":
            section = "Blocked" if unresolved else "Ready"
        owner = issue["claim"]["agent"] if issue["claim"] else "—"
        dependencies = ", ".join(item["id"] + " (" + item["state"] + ")" for item in unresolved) or "—"
        cells = (issue["id"], issue["title"], owner, dependencies)
        sections[section].append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")
    lines = [
        "# Beadcrumbs board",
        "",
        f"Generated at {generated}.",
        "",
        "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.",
        "",
    ]
    for name, rows in sections.items():
        lines.extend([f"## {name} ({len(rows)})", ""])
        if rows:
            lines.extend(["| ID | Title | Agent | Blockers |", "| --- | --- | --- | --- |", *rows, ""])
        else:
            lines.extend(["No issues.", ""])
    return "\n".join(lines)


def write_board(root, ordered, issues):
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = render_board(ordered, issues, generated).encode("utf-8")
    path = root.parent / "board.md"
    path_kind(path, optional=True)
    publish_bytes(path, payload)
    return {"path": str(path), "issue_count": len(issues), "generated_at": generated}


def run_action(args, root, issues, codec=ISSUE_CODEC):
    action = args.action
    ordered = sorted(issues.values(), key=lambda item: (item["created_at"], item["id"]))
    if action == "board":
        return write_board(root, ordered, issues)
    if action == "init":
        return MANIFEST
    if action == "validate":
        return {"valid": True, "issue_count": len(issues)}
    if action == "list":
        return [item for item in ordered if args.state is None or item["state"] == args.state]
    if action == "ready":
        return [item for item in ordered if item["state"] == "open" and not blockers(item, issues)]
    if action == "blocked":
        return [
            {"issue": item, "blockers": blockers(item, issues)}
            for item in ordered
            if item["state"] == "open" and blockers(item, issues)
        ]
    if action == "create":
        for dep in args.depends_on:
            if dep not in issues:
                raise Failure(f"Issue not found: {dep}", 3)
        key = "bc-" + uuid.uuid4().hex
        while key in issues:
            key = "bc-" + uuid.uuid4().hex
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        issue = dict(
            id=key,
            title=args.create,
            description=args.description,
            acceptance_criteria=args.acceptance_criteria,
            state="open",
            depends_on=args.depends_on,
            claim=None,
            notes=[],
            created_at=now,
            updated_at=now,
            revision=1,
        )
    else:
        key = getattr(args, action)
        if key not in issues:
            raise Failure(f"Issue not found: {key}", 3)
        issue = issues[key]
        if action == "show":
            return issue
        if action == "claim":
            if issue["state"] != "open" or blockers(issue, issues):
                raise Failure("Issue is not ready", 4)
        elif action in ("release", "close"):
            if issue["state"] != "claimed" or issue["claim"]["token"] != args.token:
                raise Failure("Claim state or token mismatch", 4)
        require(issue["revision"] < MAX_REVISION, "Revision exhausted")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if action == "claim":
            issue.update(state="claimed", claim={"agent": args.agent, "token": uuid.uuid4().hex})
        elif action == "note":
            issue["notes"].append({"at": now, "by": args.agent, "text": args.text})
        else:
            issue.update(state="closed" if action == "close" else "open", claim=None)
        issue["revision"] += 1
        issue["updated_at"] = now
    validate_issue(issue)
    publish_bytes(root / "issues" / codec.filename(key), codec.encode(issue))
    return issue


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(safe_text(message))


def parse_args(argv):
    parser = ArgumentParser(description=__doc__, allow_abbrev=False, add_help=False)
    actions = (
        "init",
        "create",
        "show",
        "list",
        "ready",
        "blocked",
        "validate",
        "claim",
        "note",
        "release",
        "close",
        "board",
        "help",
        "version",
    )
    values = {"create", "show", "claim", "note", "release", "close"}
    group = parser.add_mutually_exclusive_group(required=True)
    for action in actions:
        if action in values:
            group.add_argument("--" + action)
        else:
            group.add_argument("--" + action, action="store_true")
    for name in (
        "workspace",
        "state",
        "agent",
        "token",
        "text",
        "description",
        "description-file",
        "acceptance-criteria",
    ):
        parser.add_argument("--" + name)
    parser.add_argument("--depends-on", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    seen = set()
    for word in argv:
        if word.startswith("--"):
            option = word.split("=", 1)[0]
            if option in seen and option != "--depends-on":
                parser.error(f"Repeated option: {option}")
            seen.add(option)
    args = parser.parse_args(argv)
    args.action = next(name for name in actions if getattr(args, name) is not None and getattr(args, name) is not False)
    allowed = {"--" + args.action}
    if args.action not in ("help", "version"):
        allowed.update(("--workspace", "--json"))
    options = {
        "create": {"--depends-on", "--description", "--description-file", "--acceptance-criteria"},
        "list": {"--state"},
        "claim": {"--agent"},
        "note": {"--agent", "--text"},
        "release": {"--token"},
        "close": {"--token"},
    }
    if seen - allowed - options.get(args.action, set()):
        parser.error("Option does not apply to this action")
    if args.action == "help":
        parser.print_help()
        return args
    if args.action == "version":
        print(f"beadcrumbs {VERSION}")
        return args
    try:
        for name in ("show", "claim", "note", "release", "close"):
            value = getattr(args, name)
            if value is not None:
                require(matches(ID, value), "Invalid issue ID")
        for dep in args.depends_on:
            require(matches(ID, dep), "Invalid dependency ID")
        require(len(set(args.depends_on)) == len(args.depends_on), "Duplicate dependency")
        if args.action in ("claim", "note"):
            require(matches(AGENT, args.agent), "Valid --agent is required")
        if args.action in ("release", "close"):
            require(matches(TOKEN, args.token), "Valid --token is required")
        if args.action == "note":
            text_value(args.text, nonempty=True)
        if args.state is not None:
            require(args.state in ("open", "claimed", "closed"), "Invalid state")
        if args.action == "create":
            text_value(args.create, nonempty=True)
        require(
            args.description is None or args.description_file is None,
            "Description and description-file are mutually exclusive",
        )
        args.description = args.description or ""
        args.acceptance_criteria = args.acceptance_criteria or ""
        text_value(args.description)
        text_value(args.acceptance_criteria)
    except Failure as error:
        parser.error(str(error))
    if args.description_file is not None:
        data = sys.stdin.buffer.read() if args.description_file == "-" else Path(args.description_file).read_bytes()
        try:
            args.description = data.decode("utf-8")
            require(not args.description.startswith("\ufeff"), "Description BOM is invalid")
        except (UnicodeError, Failure) as error:
            raise Failure(f"Invalid description encoding: {error}", 2) from error
    return args


def safe_text(value):
    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def main(argv=None):
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        if args.action in ("help", "version"):
            return 0
        workspace = Path(args.workspace or ".").resolve(strict=True)
        require(workspace.is_dir(), "Workspace must be a directory")
        root = workspace / ".beadcrumbs"
        with store_lock(root, args.action == "init"):
            if args.action == "init":
                initialize_store(root)
            require(read_manifest(root), "Store is uninitialized")
            result = run_action(args, root, load_issues(root))
        # ASCII escaping is also valid UTF-8 JSON and prevents terminal controls.
        print(json.dumps(result, ensure_ascii=True, indent=None if args.json else 2))
        sys.stdout.flush()
        return 0
    except Failure as error:
        print("beadcrumbs: " + safe_text(error), file=sys.stderr)
        return error.code
    except BrokenPipeError:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - stays open to absorb writes during interpreter shutdown
        print("beadcrumbs: output pipe closed; inspect state before retrying", file=sys.stderr)
        return 1
    except (OSError, ValueError, MemoryError, RecursionError) as error:
        print("beadcrumbs: " + safe_text(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
