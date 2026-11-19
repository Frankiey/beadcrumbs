"""Cross-client tests. Set BEADCRUMBS_PEER_COMMAND to a JSON argv array."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = json.loads(
    os.environ.get("BEADCRUMBS_PRIMARY_COMMAND", json.dumps([sys.executable, str(ROOT / "beadcrumbs.py")]))
)
PEER = json.loads(os.environ.get("BEADCRUMBS_PEER_COMMAND", "null"))


@unittest.skipUnless(PEER, "Set BEADCRUMBS_PEER_COMMAND to exercise a second implementation")
class InteroperabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)

    def call(self, client, *args, code=0):
        result = subprocess.run(
            client + list(args) + ["--json"], cwd=self.workspace, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, code, result.stderr)
        if code:
            self.assertEqual(result.stdout, "")
            return None
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_bidirectional_lifecycle_and_board(self):
        self.call(PRIMARY, "--init")
        first = self.call(PRIMARY, "--create", "Python created", "--description", "λ\nUnicode")
        second = self.call(PEER, "--create", "Peer created", "--depends-on", first["id"])
        self.assertEqual(self.call(PEER, "--ready"), [first])
        claim = self.call(PEER, "--claim", first["id"], "--agent", "peer")
        self.call(PRIMARY, "--note", first["id"], "--agent", "python", "--text", "Reviewed")
        self.call(PRIMARY, "--close", first["id"], "--token", claim["claim"]["token"])
        self.assertEqual(self.call(PEER, "--ready"), [second])
        claim = self.call(PRIMARY, "--claim", second["id"], "--agent", "python")
        self.call(PEER, "--release", second["id"], "--token", claim["claim"]["token"])
        fresh = self.call(PEER, "--claim", second["id"], "--agent", "peer")
        self.call(PRIMARY, "--close", second["id"], "--token", claim["claim"]["token"], code=4)
        self.call(PRIMARY, "--close", second["id"], "--token", fresh["claim"]["token"])
        self.assertEqual(self.call(PRIMARY, "--list"), self.call(PEER, "--list"))
        self.call(PEER, "--board")
        first_board = (self.workspace / "board.md").read_text(encoding="utf-8").splitlines()
        self.call(PRIMARY, "--board")
        second_board = (self.workspace / "board.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [line for line in first_board if not line.startswith("Generated at ")],
            [line for line in second_board if not line.startswith("Generated at ")],
        )
        self.assertEqual(self.call(PEER, "--validate")["issue_count"], 2)

    def test_epics_types_priorities_and_labels_across_clients(self):
        self.call(PRIMARY, "--init")
        self.call(PEER, "--create-epic", "shared", "--title", "Shared epic", "--description", "λ")
        self.call(PRIMARY, "--create-epic", "shared", "--title", "Again", code=4)
        low = self.call(PRIMARY, "--create", "Low", "--priority", "4", "--type", "chore")
        bug = self.call(
            PEER,
            "--create",
            "Bug",
            "--priority",
            "0",
            "--type",
            "bug",
            "--epic",
            "shared",
            "--label",
            "ui",
            "--label",
            "api",
        )
        self.assertEqual(bug["labels"], ["api", "ui"])
        self.assertEqual(self.call(PRIMARY, "--ready"), [bug, low])
        bug = self.call(PRIMARY, "--relabel", bug["id"], "--add", "backend", "--remove", "ui")
        self.assertEqual(bug["labels"], ["api", "backend"])
        self.call(PEER, "--relabel", bug["id"], "--add", "api", code=4)
        self.assertEqual(self.call(PEER, "--list", "--label", "backend", "--label", "api"), [bug])
        moved = self.call(PRIMARY, "--set-epic", low["id"], "--epic", "shared")
        self.assertEqual(self.call(PEER, "--show", low["id"]), moved)
        edited = self.call(PRIMARY, "--edit-epic", "shared", "--description", "Updated")
        self.assertEqual(self.call(PEER, "--epics"), [edited])
        self.assertEqual(self.call(PEER, "--show-epic", "shared"), self.call(PRIMARY, "--show-epic", "shared"))
        self.assertEqual(self.call(PEER, "--ready", "--type", "bug", "--epic", "shared"), [bug])
        self.call(PEER, "--board")
        first_board = (self.workspace / "board.md").read_text(encoding="utf-8").splitlines()
        self.call(PRIMARY, "--board")
        second_board = (self.workspace / "board.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [line for line in first_board if not line.startswith("Generated at ")],
            [line for line in second_board if not line.startswith("Generated at ")],
        )

    def test_mixed_client_claim_race(self):
        self.call(PEER, "--init")
        issue = self.call(PEER, "--create", "Shared race")
        processes = [
            subprocess.Popen(
                client + ["--claim", issue["id"], "--agent", f"worker-{index}", "--json"],
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for index, client in enumerate([PRIMARY, PEER] * 4)
        ]
        winners = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertIn(process.returncode, (0, 4, 5), stderr)
            if process.returncode == 0:
                winners.append(json.loads(stdout))
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.call(PRIMARY, "--show", issue["id"]), winners[0])
        self.assertEqual(self.call(PEER, "--show", issue["id"]), winners[0])

    def test_both_clients_respect_existing_lock_and_newer_version(self):
        self.call(PEER, "--init")
        store = self.workspace / ".beadcrumbs"
        lock = store / ".writer.lock"
        lock.mkdir()
        for client in (PRIMARY, PEER):
            self.call(client, "--ready", code=5)
        (store / "store.json").write_text('{"format":"beadcrumbs","version":2}')
        for client in (PRIMARY, PEER):
            self.call(client, "--ready", code=1)
        self.assertTrue(lock.is_dir())
