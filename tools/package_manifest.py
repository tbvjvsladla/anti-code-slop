#!/usr/bin/env python3
"""Write or check PACKAGE_MANIFEST.json: the packaged files with size and mode.

The check compares the file list and sizes; the recorded mode is informational, since
some file systems cannot hold the executable bit.

The manifest says which files make up the package. It holds no digests: whether an
installed copy is intact is checked with git, or by comparing bytes with the tagged
blobs directly.

  python3 -B tools/package_manifest.py           # write
  python3 -B tools/package_manifest.py --check   # exit 0 when the tree has the listed files and sizes
  python3 -B tools/package_manifest.py --check --root <installed skill folder>
  python3 -B tools/package_manifest.py --check --root <installed skill folder> --against <repository> --ref <tag>
      # also compare every installed file byte for byte with the tag's blob in the repository
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "PACKAGE_MANIFEST.json"
SKIP_DIRS = {".git", "__pycache__", ".cache"}
EXCLUDES = [MANIFEST_NAME, *sorted(SKIP_DIRS)]


def package_version(root: Path) -> str:
    match = re.search(r'^\s*version:\s*"([^"]+)"', (root / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit("SKILL.md has no metadata.version")
    return match.group(1)


def walk(root: Path) -> list[str]:
    """Every file under root, relative and sorted, without git data and bytecode."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name not in SKIP_DIRS and not name.endswith(".pyc"):
                found.append((Path(dirpath) / name).relative_to(root).as_posix())
    return sorted(found)


def inventory(root: Path) -> list[dict]:
    files = []
    for rel in walk(root):
        if rel == MANIFEST_NAME:
            continue
        path = root / rel
        files.append({"path": rel, "bytes": path.stat().st_size,
                      "mode": "0755" if os.access(path, os.X_OK) else "0644"})
    return files


def build(root: Path) -> dict:
    files = inventory(root)
    return {"manifest_version": "2.0.0", "package": "anti-code-slop", "version": package_version(root),
            "inventory_excludes": EXCLUDES, "file_count": len(files), "files": files}


def git(repo: Path, *args: str) -> bytes:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.decode("utf-8", "replace").strip() or f"git {' '.join(args)} failed")
    return done.stdout


def against_ref(root: Path, repo: Path, ref: str) -> list[str]:
    """Compare the installed files with the blobs of ref, byte for byte."""
    names = [os.fsdecode(n) for n in git(repo, "ls-tree", "-r", "-z", "--name-only", ref).split(b"\0") if n]
    installed = set(walk(root))
    problems = [f"missing against {ref}: {n}" for n in names if n not in installed]
    problems += [f"not in {ref}: {n}" for n in sorted(installed - set(names))]
    problems += [f"differs from {ref}: {n}" for n in names
                 if n in installed and (root / n).read_bytes() != git(repo, "show", f"{ref}:{n}")]
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=str(PACKAGE_ROOT))
    parser.add_argument("--against", help="git repository holding the release tag")
    parser.add_argument("--ref", help="release tag or commit in --against")
    args = parser.parse_args()
    if bool(args.against) != bool(args.ref):
        parser.error("--against and --ref go together")
    if args.against and not args.check:
        parser.error("--against compares an installed copy; it needs --check")
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
    problems += [f"differs: {p} (bytes {want[p]['bytes']} listed, {have[p]['bytes']} found)"
                 for p in sorted(set(want) & set(have)) if want[p]["bytes"] != have[p]["bytes"]]
    if recorded.get("version") != current["version"]:
        problems.append(f"version: manifest {recorded.get('version')} vs SKILL.md {current['version']}")
    if args.against:
        try:
            problems += against_ref(root, Path(args.against).resolve(), args.ref)
        except (OSError, RuntimeError) as exc:
            problems.append(f"cannot compare with {args.ref} in {args.against}: {exc}")
    for line in problems:
        print(line)
    same = f", same bytes as {args.ref}" if args.against and not problems else ""
    print(f"MANIFEST {'OK' if not problems else 'FAIL'} ({len(have)} files{same})")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
