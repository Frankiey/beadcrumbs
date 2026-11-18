#!/usr/bin/env python3
"""Run the shared suite for each built client and every pair of implementations."""

import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clients",
        nargs="+",
        choices=["python", "typescript", "go", "rust", "dotnet"],
        default=["python", "typescript", "go", "rust", "dotnet"],
    )
    args = parser.parse_args()
    suffix = ".exe" if os.name == "nt" else ""
    commands = {
        "python": [sys.executable, str(ROOT / "beadcrumbs.py")],
        "typescript": ["node", str(ROOT / "implementations/javascript/dist/cli.js")],
        "go": [str(ROOT / ("implementations/go/bin/beadcrumbs" + suffix))],
        "rust": [str(ROOT / ("implementations/rust/target/debug/beadcrumbs" + suffix))],
        "dotnet": [
            "dotnet",
            str(ROOT / "implementations/dotnet/src/Beadcrumbs.Cli/bin/Debug/net11.0/Beadcrumbs.Cli.dll"),
        ],
    }
    clients = list(dict.fromkeys(args.clients))
    for client in clients:
        command = commands[client]
        if not shutil.which(command[0]) or (len(command) > 1 and not Path(command[1]).is_file()):
            parser.error(f"Build {client} first using implementations/README.md")
    runs = ROOT / "integration/.runs"
    runs.mkdir(exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime("clients-%Y%m%dT%H%M%SZ-")
    output = Path(tempfile.mkdtemp(prefix=prefix, dir=runs))
    checks = []
    cases = [(name, "test_cli.py", {"BEADCRUMBS_COMMAND": json.dumps(commands[name])}) for name in clients]
    cases += [
        (
            f"{first}-{second}",
            "test_interop.py",
            {
                "BEADCRUMBS_PRIMARY_COMMAND": json.dumps(commands[first]),
                "BEADCRUMBS_PEER_COMMAND": json.dumps(commands[second]),
            },
        )
        for first, second in itertools.combinations(clients, 2)
    ]
    for name, suite, settings in cases:
        env = dict(os.environ)
        for key in ("BEADCRUMBS_COMMAND", "BEADCRUMBS_PRIMARY_COMMAND", "BEADCRUMBS_PEER_COMMAND"):
            env.pop(key, None)
        env.update(settings)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", suite, "-v"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            code, log = result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            code, log = 1, "Suite exceeded 180 seconds."
        (output / (name + ".log")).write_text(log, encoding="utf-8")
        checks.append({"name": name, "suite": suite, "exit": code})
        print(f"{name}: {'passed' if code == 0 else 'FAILED'}", flush=True)
        if code:
            failing = [line for line in log.splitlines() if not line.endswith("... ok")]
            print("\n".join(f"    {line}" for line in failing[-60:]), flush=True)
    summary = {
        "status": "passed" if all(item["exit"] == 0 for item in checks) else "failed",
        "clients": clients,
        "checks": checks,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {output}")
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
