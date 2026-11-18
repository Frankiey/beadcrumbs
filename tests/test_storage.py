"""Reference-client fault injection, independent of the portable CLI suite."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("beadcrumbs", ROOT / "beadcrumbs.py")
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class PublicationTests(unittest.TestCase):
    def test_failed_flush_or_replace_preserves_old_record(self):
        for failure in ("fsync", "replace"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "record.json"
                path.write_text('{"old":true}\n')
                with patch.object(client.os, failure, side_effect=OSError("injected")), self.assertRaises(OSError):
                    client.publish(path, {"new": True})
                self.assertEqual(json.loads(path.read_text()), {"old": True})
                self.assertEqual([p.name for p in path.parent.iterdir()], ["record.json"])

    def test_process_death_at_publication_boundary(self):
        script = """
import os, runpy, sys
module = runpy.run_path(sys.argv[1])
real_replace = os.replace
def interrupted_replace(source, destination):
    if sys.argv[2] == "after":
        real_replace(source, destination)
    os._exit(77)
os.replace = interrupted_replace
module["main"](["--claim", sys.argv[3], "--agent", "worker", "--json"])
"""
        for phase in ("before", "after"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(ROOT / "beadcrumbs.py")]
                subprocess.run(command + ["--init"], cwd=folder, check=True, capture_output=True)
                created = subprocess.run(
                    command + ["--create", "Task", "--json"], cwd=folder, check=True, capture_output=True, text=True
                )
                issue = json.loads(created.stdout)
                result = subprocess.run(
                    [sys.executable, "-c", script, str(ROOT / "beadcrumbs.py"), phase, issue["id"]],
                    cwd=folder,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 77, result.stderr)
                store = Path(folder) / ".beadcrumbs"
                record = json.loads((store / "issues" / (issue["id"] + ".json")).read_text())
                self.assertEqual(record["state"], "open" if phase == "before" else "claimed")
                self.assertEqual(record["revision"], 1 if phase == "before" else 2)
                self.assertTrue((store / ".writer.lock").is_dir())
                (store / ".writer.lock").rmdir()
                validated = subprocess.run(command + ["--validate"], cwd=folder, capture_output=True)
                self.assertEqual(validated.returncode, 0, validated.stderr)

    def test_offline_lifecycle_without_subprocess_or_network(self):
        script = """
import contextlib, io, json, runpy, sys
module = runpy.run_path(sys.argv[1])
def audit(event, args):
    if event.startswith(("socket.", "subprocess.")) or event in ("os.system", "os.posix_spawn"):
        raise RuntimeError("Forbidden external activity: " + event)
sys.addaudithook(audit)
def call(args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert module["main"](args + ["--json"]) == 0
    return json.loads(output.getvalue())
call(["--init"])
a = call(["--create", "Prerequisite"])
b = call(["--create", "Dependent", "--depends-on", a["id"]])
assert call(["--blocked"])[0]["issue"]["id"] == b["id"]
claim = call(["--claim", a["id"], "--agent", "worker"])
call(["--note", a["id"], "--agent", "worker", "--text", "Done"])
call(["--close", a["id"], "--token", claim["claim"]["token"]])
assert call(["--ready"])[0]["id"] == b["id"]
assert call(["--validate"])["issue_count"] == 2
"""
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-c", script, str(ROOT / "beadcrumbs.py")], cwd=folder, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_schema_examples_and_lexical_integer_rules(self):
        # Schema documents are offline artifacts. Runtime validation additionally
        # checks graph relationships, JSON lexemes and Unicode scalar values.
        for path in (ROOT / "schemas/v1").glob("*.json"):
            schema = json.loads(path.read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "store.json"
            for value in ("1.0", "1e0", "true"):
                path.write_text('{"format":"beadcrumbs","version":' + value + "}")
                with self.assertRaises(client.Failure):
                    client.read_manifest(root)


class LockTests(unittest.TestCase):
    def test_lock_removed_after_failed_creation_is_busy(self):
        # Another process can release the lock between our failed mkdir and the follow-up inspection.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / ".beadcrumbs"
            root.mkdir()
            with client.store_lock(root, True):
                client.initialize_store(root)
            with (
                patch.object(Path, "mkdir", side_effect=FileExistsError),
                self.assertRaises(client.Failure) as caught,
                client.store_lock(root, False),
            ):
                self.fail("lock acquired")
            self.assertEqual(caught.exception.code, 5)
            self.assertFalse((root / ".writer.lock").exists())


class CodecBoundaryTests(unittest.TestCase):
    def test_alternate_codec_runs_existing_lifecycle(self):
        class ExampleCodec:
            def accepts(self, filename):
                return filename.endswith(".example")

            def filename(self, issue_id):
                return issue_id + ".example"

            def encode(self, issue):
                return b"example-v1\n" + client.encode_json(issue)

            def decode(self, payload):
                if not payload.startswith(b"example-v1\n"):
                    raise client.Failure("Invalid example format")
                return client.decode_json(payload.split(b"\n", 1)[1])

        codec = ExampleCodec()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / ".beadcrumbs"
            with client.store_lock(root, True):
                client.initialize_store(root)

                def execute(*args):
                    parsed = client.parse_args(list(args))
                    return client.run_action(parsed, root, client.load_issues(root, codec), codec)

                issue = execute("--create", "Alternate format", "--description", "λ\ntext")
                path = root / "issues" / codec.filename(issue["id"])
                self.assertTrue(path.read_bytes().startswith(b"example-v1\n"))
                self.assertEqual(execute("--ready"), [issue])
                claim = execute("--claim", issue["id"], "--agent", "worker")
                execute("--note", issue["id"], "--agent", "worker", "--text", "Done")
                closed = execute("--close", issue["id"], "--token", claim["claim"]["token"])
                self.assertEqual(closed["state"], "closed")
                self.assertEqual(closed["revision"], 4)
                self.assertEqual(execute("--show", issue["id"])["description"], "λ\ntext")
                snapshot = client.load_issues(root, codec)
                before = json.dumps(snapshot, sort_keys=True)
                rendered = client.render_board(list(snapshot.values()), snapshot, "2026-11-14T00:00:00Z")
                self.assertIn("## Closed (1)", rendered)
                self.assertEqual(json.dumps(snapshot, sort_keys=True), before)
                self.assertEqual(sorted(p.suffix for p in (root / "issues").iterdir()), [".example"])

    def test_json_codec_roundtrip_and_strict_decode(self):
        codec = client.JsonIssueCodec()
        value = {"text": "Unicode λ\n", "number": 1, "empty": None}
        self.assertEqual(codec.decode(codec.encode(value)), value)
        for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff"):
            with self.subTest(payload=payload), self.assertRaises(client.Failure):
                codec.decode(payload)
        with self.assertRaises(client.Failure):
            codec.filename("../escape")
