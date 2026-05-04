#!/usr/bin/env python3
"""Scan the public repository for local paths and likely private strings."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DEFAULT_PATTERNS = [
    "/" + "Users/",
    r"\b" + "wchao" + r"\b",
    "Desk" + "top",
    "API" + r"[_ -]?KEY",
    "api" + r"[_ -]?key",
    "tok" + "en",
    "coo" + "kie",
    "sec" + "ret",
    "sk" + r"-[A-Za-z0-9]",
    r"AKIA[0-9A-Z]{16}",
]

SKIP_DIRS = {".git", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".md", ".json", ".py", ".txt", ".html", ".css", ".js", ".yml", ".yaml", ""}


def iter_files(root: Path):
    self_path = Path(__file__).resolve()
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() == self_path:
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan public benchmark files for local/private strings")
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    regexes = [re.compile(pattern) for pattern in DEFAULT_PATTERNS]
    findings: list[str] = []
    for path in iter_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for regex in regexes:
                if regex.search(line):
                    rel = path.relative_to(root).as_posix()
                    findings.append(f"{rel}:{lineno}: {regex.pattern}: {line[:180]}")
    if findings:
        print("Sanitize check failed:")
        print("\n".join(findings))
        return 1
    print("Sanitize check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
