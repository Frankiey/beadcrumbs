"""Black-box conformance tests. BEADCRUMBS_COMMAND is a JSON argv array."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND = json.loads(os.environ.get("BEADCRUMBS_COMMAND", json.dumps([sys.executable, str(ROOT / "beadcrumbs.py")])))
MISSING = "bc-00000000000040008000000000000009"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def call(self, *args, code=0, stdin=None):
        result = subprocess.run(
            COMMAND + list(args), cwd=self.workspace, input=stdin, capture_output=True, text=True, timeout=20
        )
        self.assertEqual(result.returncode, code, result.stderr)
        if code:
            self.assertEqual(result.stdout, "")
        else:
            self.assertEqual(result.stderr, "")
        return result

    def value(self, *args):
        return json.loads(self.call(*args, "--json").stdout)

    def init(self):
        self.value("--init")

    def test_help_version_and_invalid_invocations(self):
        self.assertIn("--ready", self.call("--help").stdout)
        self.assertIn("beadcrumbs", self.call("--version").stdout)
        for args in [
            [],
            ["--rea"],
            ["--ready", "--ready"],
            ["--help", "--json"],
            ["--ready", "--agent", "worker"],
            ["--show", "../escape"],
            ["--create", ""],
            ["--claim", MISSING],
            ["--ready", "--show", MISSING],
        ]:
            with self.subTest(args=args):
                self.call(*args, code=2)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_shared_fixtures(self):
        cases = json.loads((ROOT / "tests/fixtures/cases.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as folder:
                old = self.workspace
                self.workspace = Path(folder)
                try:
                    store = self.workspace / ".beadcrumbs"
                    (store / "issues").mkdir(parents=True)
                    (store / "store.json").write_text(
                        json.dumps(case.get("manifest", {"format": "beadcrumbs", "version": 1}))
                    )
                    for issue in case["issues"]:
                        (store / "issues" / (issue["id"] + ".json")).write_text(json.dumps(issue))
                    before = {str(p): p.read_bytes() for p in store.rglob("*") if p.is_file()}
                    for command in case["commands"]:
                        result = self.call(*command["args"], "--json", code=command["code"])
                        if command["code"] == 0:
                            self.assertEqual(json.loads(result.stdout), command["result"])
                    self.assertEqual(before, {str(p): p.read_bytes() for p in store.rglob("*") if p.is_file()})
                    self.assertFalse((store / ".writer.lock").exists())
                finally:
                    self.workspace = old

    def test_lifecycle(self):
        self.init()
        a = self.value(
            "--create", "Prerequisite", "--description", "Multiline\n日本語", "--acceptance-criteria", "Tests pass"
        )
        b = self.value("--create", "Dependent", "--depends-on", a["id"])
        self.assertEqual([a], self.value("--ready"))
        self.assertEqual(self.value("--blocked")[0]["blockers"], [{"id": a["id"], "state": "open"}])
        self.call("--claim", b["id"], "--agent", "worker", code=4)
        claim = self.value("--claim", a["id"], "--agent", "worker")
        token = claim["claim"]["token"]
        self.assertEqual(claim["revision"], 2)
        self.value("--note", a["id"], "--agent", "worker", "--text", "Progress")
        closed = self.value("--close", a["id"], "--token", token)
        self.assertEqual(closed["revision"], 4)
        self.assertEqual(closed["description"], a["description"])
        self.assertIsNone(closed["claim"])
        self.assertEqual(self.value("--ready"), [b])
        self.assertEqual(self.value("--list", "--state", "closed"), [closed])
        self.call("--close", a["id"], "--token", token, code=4)
        self.assertEqual(self.value("--validate")["issue_count"], 2)
        self.value("--note", a["id"], "--agent", "reviewer", "--text", "Verified")

    def test_release_stale_token_and_repeated_claim(self):
        self.init()
        issue = self.value("--create", "Task")["id"]
        first = self.value("--claim", issue, "--agent", "worker")["claim"]["token"]
        self.call("--claim", issue, "--agent", "worker", code=4)
        self.value("--release", issue, "--token", first)
        second = self.value("--claim", issue, "--agent", "worker")["claim"]["token"]
        self.assertNotEqual(first, second)
        self.call("--close", issue, "--token", first, code=4)
        self.call("--release", issue, "--token", first, code=4)
        self.value("--close", issue, "--token", second)

    def test_busy_and_manual_recovery(self):
        self.init()
        lock = self.workspace / ".beadcrumbs/.writer.lock"
        lock.mkdir()
        self.call("--ready", code=5)
        self.assertTrue(lock.exists())
        lock.rmdir()
        self.assertEqual(self.value("--ready"), [])

    def test_concurrent_claims(self):
        self.init()
        issue = self.value("--create", "Race")["id"]
        processes = [
            subprocess.Popen(
                COMMAND + ["--claim", issue, "--agent", f"worker-{n}", "--json"],
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for n in range(8)
        ]
        outputs = [p.communicate(timeout=20) for p in processes]
        winners = [json.loads(out[0]) for p, out in zip(processes, outputs, strict=True) if p.returncode == 0]
        self.assertEqual(len(winners), 1)
        self.assertTrue(all(p.returncode in (0, 4, 5) for p in processes))
        self.assertEqual(self.value("--show", issue), winners[0])

    def test_description_inputs_and_idempotent_init(self):
        self.init()
        text = "line one\r\nλ\n"
        file = self.workspace / "brief.txt"
        file.write_bytes(text.encode())
        issue = self.value("--create", "File", "--description-file", str(file))
        self.assertEqual(issue["description"], text)
        result = self.call("--create", "Stdin", "--description-file", "-", "--json", stdin="你好\n")
        self.assertEqual(json.loads(result.stdout)["description"], "你好\n")
        self.init()
        self.assertEqual(self.value("--show", issue["id"]), issue)
        file.write_bytes(b"\xef\xbb\xbfBOM")
        self.call("--create", "Invalid", "--description-file", str(file), code=2)

    def test_corruption_and_filename_validation(self):
        self.init()
        issue = self.value("--create", "Task")
        path = self.workspace / ".beadcrumbs/issues" / (issue["id"] + ".json")
        for payload in [
            '{"id":1,"id":2}',
            json.dumps(dict(issue, revision=1.0)),
            json.dumps(dict(issue, title="\ud800")),
            json.dumps(dict(issue, revision=True)),
            json.dumps(dict(issue, created_at="2026-02-30T00:00:00Z")),
            json.dumps(dict(issue, claim={"agent": "x", "token": "x"})),
        ]:
            with self.subTest(payload=payload):
                path.write_text(payload)
                self.call("--validate", code=1)
        path.write_text(json.dumps(issue))
        path.rename(path.with_name(MISSING + ".json"))
        self.call("--validate", code=1)

    def test_missing_ids_and_revision_overflow(self):
        self.init()
        self.call("--show", MISSING, code=3)
        self.call("--create", "Missing", "--depends-on", MISSING, code=3)
        issue = self.value("--create", "Task")
        path = self.workspace / ".beadcrumbs/issues" / (issue["id"] + ".json")
        issue["revision"] = 9007199254740991
        path.write_text(json.dumps(issue))
        before = path.read_bytes()
        self.call("--claim", issue["id"], "--agent", "worker", code=1)
        self.assertEqual(path.read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "POSIX symlink and mode test")
    def test_paths_permissions_and_terminal_escaping(self):
        self.init()
        issue = self.value("--create", "unsafe\x1b[31m\u202e")
        result = self.call("--show", issue["id"])
        self.assertNotIn("\x1b", result.stdout)
        self.assertNotIn("\u202e", result.stdout)
        path = self.workspace / ".beadcrumbs/issues" / (issue["id"] + ".json")
        self.assertEqual(path.stat().st_mode & 0o077, 0)
        target = self.workspace / "target"
        path.rename(target)
        path.symlink_to(target)
        self.call("--validate", code=1)

    def test_partial_init_and_unknown_content(self):
        store = self.workspace / ".beadcrumbs"
        (store / "issues").mkdir(parents=True)
        self.init()
        self.assertEqual(self.value("--validate")["issue_count"], 0)
        (store / "store.json").unlink()
        extra = store / "important.txt"
        extra.write_text("preserve")
        self.call("--init", code=1)
        self.assertEqual(extra.read_text(), "preserve")

    def test_simultaneous_initialization(self):
        processes = [
            subprocess.Popen(
                COMMAND + ["--init", "--json"], cwd=self.workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            for _ in range(8)
        ]
        for process in processes:
            _stdout, stderr = process.communicate(timeout=20)
            self.assertIn(process.returncode, (0, 5), stderr)
        self.assertEqual(self.value("--validate"), {"valid": True, "issue_count": 0})

    def test_concurrent_notes_preserve_successful_writes(self):
        self.init()
        issue = self.value("--create", "Notes")["id"]
        processes = [
            subprocess.Popen(
                COMMAND + ["--note", issue, "--agent", "worker", "--text", str(n), "--json"],
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for n in range(8)
        ]
        expected = []
        for n, process in enumerate(processes):
            _, stderr = process.communicate(timeout=20)
            self.assertIn(process.returncode, (0, 5), stderr)
            if process.returncode == 0:
                expected.append(str(n))
        actual = self.value("--show", issue)
        self.assertEqual(sorted(note["text"] for note in actual["notes"]), sorted(expected))
        self.assertEqual(actual["revision"], 1 + len(expected))

    def test_unsupported_version_does_not_touch_existing_lock(self):
        self.init()
        root = self.workspace / ".beadcrumbs"
        (root / "store.json").write_text('{"format":"beadcrumbs","version":2}')
        (root / ".writer.lock").mkdir()
        self.call("--ready", code=1)
        self.assertTrue((root / ".writer.lock").is_dir())

    def test_explicit_workspace_and_local_description_path(self):
        other = self.workspace / "other"
        other.mkdir()
        (self.workspace / "brief.txt").write_bytes(b"local\r\n")
        self.value("--workspace", str(other), "--init")
        issue = self.value("--workspace", str(other), "--create", "Task", "--description-file", "brief.txt")
        self.assertEqual(issue["description"], "local\r\n")
        self.assertFalse((self.workspace / ".beadcrumbs").exists())

    def test_board_empty_and_explicit_workspace(self):
        other = self.workspace / "other"
        other.mkdir()
        self.value("--init", "--workspace", str(other))
        result = self.value("--board", "--workspace", str(other))
        path = other / "board.md"
        self.assertEqual(result["path"], str(path.resolve()))
        self.assertEqual(result["issue_count"], 0)
        self.assertFalse((self.workspace / "board.md").exists())
        content = path.read_text()
        for section in ("Ready", "Blocked", "Claimed", "Closed"):
            self.assertIn(f"## {section} (0)", content)
        self.assertIn(result["generated_at"], content)

    def test_board_groups_escaping_and_refresh(self):
        self.init()
        first = self.value("--create", "Ready")
        dependent = self.value("--create", "Blocked", "--depends-on", first["id"])
        active = self.value("--create", "Unsafe | [link](https://example.test) <script>\nnext\u202e")
        claim = self.value("--claim", active["id"], "--agent", "worker")
        done = self.value("--create", "Done")
        token = self.value("--claim", done["id"], "--agent", "worker")["claim"]["token"]
        self.value("--close", done["id"], "--token", token)
        files = self.workspace / ".beadcrumbs/issues"
        before = {p.name: p.read_bytes() for p in files.iterdir()}
        self.value("--board")
        path = self.workspace / "board.md"
        content = path.read_text()
        for section in ("Ready", "Blocked", "Claimed", "Closed"):
            self.assertIn(f"## {section} (1)", content)
        self.assertIn("&#124;", content)
        self.assertNotIn("<script>", content)
        self.assertNotIn("\u202e", content)
        self.assertNotIn(claim["claim"]["token"], content)
        self.assertEqual(before, {p.name: p.read_bytes() for p in files.iterdir()})
        token = self.value("--claim", first["id"], "--agent", "worker")["claim"]["token"]
        self.value("--close", first["id"], "--token", token)
        self.assertEqual(path.read_text(), content)
        self.value("--board")
        self.assertIn("## Blocked (0)", path.read_text())
        self.assertIn(dependent["id"], self.value("--ready")[0]["id"])

    def test_board_failure_preserves_previous_snapshot(self):
        self.init()
        self.value("--board")
        board = self.workspace / "board.md"
        original = board.read_bytes()
        lock = self.workspace / ".beadcrumbs/.writer.lock"
        lock.mkdir()
        self.call("--board", code=5)
        lock.rmdir()
        (self.workspace / ".beadcrumbs/store.json").write_text("{}")
        self.call("--board", code=1)
        self.assertEqual(board.read_bytes(), original)

    @unittest.skipIf(os.name == "nt", "POSIX symlink test")
    def test_board_rejects_symlink(self):
        self.init()
        target = self.workspace / "personal.md"
        target.write_text("Keep me")
        (self.workspace / "board.md").symlink_to(target)
        self.call("--board", code=1)
        self.assertEqual(target.read_text(), "Keep me")

    @unittest.skipIf(os.name == "nt", "POSIX FIFO test")
    def test_fifo_issue_is_rejected_without_blocking(self):
        self.init()
        path = self.workspace / ".beadcrumbs/issues" / (MISSING + ".json")
        os.mkfifo(path)
        self.call("--validate", code=1)
