#!/usr/bin/env python3
"""Check that relative Markdown links and anchors resolve, and that JSON schemas and fixtures parse."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"```.*?```", re.S)
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#+ (.*)$", re.M)


def tracked(pattern):
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", pattern],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / line for line in output.splitlines() if line]


def slug(heading):
    """Approximate GitHub's anchor generation for headings."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def anchors(path):
    return {slug(h) for h in HEADING.findall(FENCE.sub("", path.read_text(encoding="utf-8")))}


def check_links(files):
    problems = []
    for path in files:
        text = FENCE.sub("", path.read_text(encoding="utf-8"))
        for target in LINK.findall(text):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):
                continue
            file_part, _, anchor = target.partition("#")
            destination = (path.parent / file_part).resolve() if file_part else path
            where = f"{path.relative_to(ROOT)}: {target}"
            if not destination.exists():
                problems.append(f"{where} (missing file)")
            elif anchor and destination.suffix == ".md" and anchor not in anchors(destination):
                problems.append(f"{where} (missing anchor)")
    return problems


def check_json(files):
    problems = []
    for path in files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            problems.append(f"{path.relative_to(ROOT)}: {error}")
    return problems


def main():
    markdown = tracked("*.md")
    data = tracked("schemas/*.json") + tracked("tests/fixtures/*.json")
    problems = check_links(markdown) + check_json(data)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"Checked {len(markdown)} Markdown files and {len(data)} JSON files: {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
