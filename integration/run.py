#!/usr/bin/env python3
"""Create a persistent example workspace and exercise the public CLI."""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "beadcrumbs.py"


def check(condition, message, **details):
    if not condition:
        shown = "; ".join(f"{key}={value!r}" for key, value in details.items())
        raise RuntimeError(f"{message} ({shown})" if shown else message)


def run_scenario(workspace, transcript, setup_only):
    def call(*args, expected=0):
        result = subprocess.run(
            [sys.executable, str(CLI), *args, "--json"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=20,
        )
        transcript.write(
            json.dumps(
                {
                    "args": list(args),
                    "expected_exit": expected,
                    "exit": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            + "\n"
        )
        transcript.flush()
        check(
            result.returncode == expected,
            f"{args[0]} returned {result.returncode}, expected {expected}: {result.stderr}",
        )
        if expected:
            check(not result.stdout, "Failed command emitted stdout")
            return None
        check(not result.stderr, "Successful command emitted stderr")
        return json.loads(result.stdout)

    call("--init")
    epic = call("--create-epic", "offline-docs", "--title", "Offline documentation")
    brief = workspace / "brief.md"
    # Write bytes so the brief has LF endings on every platform; write_text would use CRLF on Windows.
    brief_text = "Document the offline setup.\nVerify Unicode survives — café.\n"
    brief.write_bytes(brief_text.encode("utf-8"))
    first = call(
        "--create",
        "Document offline setup",
        "--description-file",
        str(brief),
        "--acceptance-criteria",
        "A new worker can run the documented steps.",
        "--type",
        "docs",
        "--priority",
        "1",
        "--epic",
        epic["key"],
        "--label",
        "onboarding",
    )
    second = call("--create", "Verify the setup guide", "--depends-on", first["id"], "--epic", epic["key"])
    check((first["type"], first["priority"], first["epic"]) == ("docs", 1, epic["key"]), "Unexpected fields")
    check(first["labels"] == ["onboarding"], "Unexpected labels", actual=first["labels"])
    check(call("--list", "--label", "onboarding") == [first], "Unexpected label filter")
    check(first["description"] == brief_text, "Brief changed", expected=brief_text, actual=first["description"])
    check(call("--ready") == [first], "Unexpected initial ready list")
    check(
        call("--blocked")
        == [
            {
                "issue": second,
                "blockers": [{"id": first["id"], "state": "open"}],
            }
        ],
        "Unexpected blocker explanation",
    )
    if setup_only:
        call("--board")
        return {"prerequisite": first["id"], "dependent": second["id"]}

    call("--claim", second["id"], "--agent", "reviewer", expected=4)
    claim = call("--claim", first["id"], "--agent", "writer")
    call("--claim", first["id"], "--agent", "other-worker", expected=4)
    old_token = claim["claim"]["token"]
    call("--release", first["id"], "--token", old_token)
    claim = call("--claim", first["id"], "--agent", "writer")
    check(claim["claim"]["token"] != old_token, "Reclaimed issue reused its token")
    call("--close", first["id"], "--token", old_token, expected=4)
    call("--note", first["id"], "--agent", "writer", "--text", "Offline guide completed.")
    call("--close", first["id"], "--token", claim["claim"]["token"])
    check(call("--ready") == [second], "Closing prerequisite did not unblock dependent")
    claim = call("--claim", second["id"], "--agent", "reviewer")
    call("--note", second["id"], "--agent", "reviewer", "--text", "Guide verified.")
    call("--close", second["id"], "--token", claim["claim"]["token"])
    check(len(call("--list", "--state", "closed")) == 2, "Expected two closed issues")
    progress = call("--show-epic", epic["key"])["counts"]
    check(progress == {"ready": 0, "blocked": 0, "claimed": 0, "closed": 2}, "Epic not complete", progress=progress)
    followup = call("--create", "Explore this example workspace", "--type", "chore")
    check(call("--ready") == [followup], "Expected ready follow-up")
    check(call("--blocked") == [], "Unexpected remaining blockers")
    check(call("--validate") == {"valid": True, "issue_count": 3, "epic_count": 1}, "Validation failed")
    call("--init")
    check(len(call("--list")) == 3, "Repeated initialization changed the store")
    call("--board")
    check((workspace / "board.md").is_file(), "Board was not generated")
    return {"prerequisite": first["id"], "dependent": second["id"], "followup": followup["id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="leave a ready prerequisite and blocked dependent for manual exploration",
    )
    args = parser.parse_args()
    runs = HERE / ".runs"
    runs.mkdir(exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
    run = Path(tempfile.mkdtemp(prefix=prefix, dir=runs))
    workspace = run / "workspace"
    workspace.mkdir()
    summary = {"status": "failed", "workspace": str(workspace), "mode": "setup" if args.setup_only else "integration"}
    try:
        with (run / "commands.jsonl").open("w", encoding="utf-8") as transcript:
            summary["issues"] = run_scenario(workspace, transcript, args.setup_only)
        summary["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        summary["error"] = str(error)
    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Command transcript: {run / 'commands.jsonl'}")
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
