#!/usr/bin/env python3
"""Write or check PACKAGE_MANIFEST.json: every packaged file with size, mode and SHA-256.

  python3 -B tools/package_manifest.py           # write
  python3 -B tools/package_manifest.py --check   # exit 0 when the tree matches, 1 otherwise
  python3 -B tools/package_manifest.py --check --root <installed skill folder>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "PACKAGE_MANIFEST.json"
EXCLUDES = [MANIFEST_NAME, ".git", "__pycache__", ".cache"]


def package_version(root: Path) -> str:
    match = re.search(r'^\s*version:\s*"([^"]+)"', (root / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit("SKILL.md has no metadata.version")
    return match.group(1)


def inventory(root: Path) -> list[dict]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDES)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if rel in EXCLUDES or name.endswith(".pyc"):
                continue
            data = path.read_bytes()
            files.append({"path": rel, "bytes": len(data), "mode": "0755" if os.access(path, os.X_OK) else "0644",
                          "sha256": hashlib.sha256(data).hexdigest()})
    return sorted(files, key=lambda f: f["path"])


def build(root: Path) -> dict:
    files = inventory(root)
    return {"manifest_version": "1.0.0", "package": "anti-code-slop", "version": package_version(root),
            "inventory_excludes": EXCLUDES, "file_count": len(files), "files": files}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=str(PACKAGE_ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    current = build(root)
    path = root / MANIFEST_NAME
    if not args.check:
        path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"MANIFEST WRITTEN ({current['file_count']} files)")
        return 0
    if not path.is_file():
        print(f"MANIFEST FAIL: {MANIFEST_NAME} missing")
        return 1
    recorded = json.loads(path.read_text(encoding="utf-8"))
    want = {f["path"]: f for f in recorded.get("files", [])}
    have = {f["path"]: f for f in current["files"]}
    problems = [f"missing: {p}" for p in sorted(set(want) - set(have))]
    problems += [f"unexpected: {p}" for p in sorted(set(have) - set(want))]
    problems += [f"differs: {p}" for p in sorted(set(want) & set(have))
                 if (want[p]["sha256"], want[p]["bytes"]) != (have[p]["sha256"], have[p]["bytes"])]
    if recorded.get("version") != current["version"]:
        problems.append(f"version: manifest {recorded.get('version')} vs SKILL.md {current['version']}")
    for line in problems:
        print(line)
    print(f"MANIFEST {'OK' if not problems else 'FAIL'} ({len(have)} files)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
