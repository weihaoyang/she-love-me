"""Scan a repository for personal data before publishing.

Checks phones, ID numbers, real-looking wxids, message IDs and long digit runs.
Placeholders such as ``wxid_xxx``, ``wxid_example_*`` and ``wxid_friend`` are allowed.

    python scripts/privacy_scan.py
    python scripts/privacy_scan.py --root . --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_EXCLUDES = {".git", "data", "reports", "vendor", "tmp", "__pycache__",
                    "node_modules", ".venv", "dist", "build"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".txt", ".yaml", ".yml", ".toml", ".cjs",
                 ".js", ".ts", ".ps1", ".sh", ".mdc", ".html", ".csv"}
ALLOWED_WXID = {"xxx", "example", "owner", "friend", "me", "a", "b", "x", "y"}
ALLOWED_PREFIXES = ("xxx", "yyy", "example", "demo", "owner", "friend", "other",
                    "test", "placeholder", "sample")
PATTERNS = [
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("wxid", re.compile(r"wxid_([0-9a-zA-Z]+)")),
    ("message_id", re.compile(r"msg_[0-9a-f]{20,}")),
    ("long_digits", re.compile(r"(?<!\d)\d{16,}(?!\d)")),
]


def scan(root, excludes):
    hits = []
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in excludes for part in rel.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            for kind, pattern in PATTERNS:
                for match in pattern.finditer(line):
                    if kind == "wxid":
                        tail = match.group(1).lower()
                        if tail in ALLOWED_WXID or tail.startswith(ALLOWED_PREFIXES):
                            continue
                    hits.append({"file": str(rel), "line": number, "kind": kind,
                                 "match": match.group(0)[:48]})
    return hits


def main():
    parser = argparse.ArgumentParser(description="发布前的隐私扫描")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    hits = scan(args.root, excludes)
    if args.json:
        print(json.dumps({"status": "ok" if not hits else "review", "hits": hits},
                         ensure_ascii=False, indent=1))
    else:
        for hit in hits:
            print(f"{hit['file']}:{hit['line']} [{hit['kind']}] {hit['match']}")
        print(f"\n{'通过：没有发现明显的个人信息。' if not hits else f'需要复核：{len(hits)} 处。'}")
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
