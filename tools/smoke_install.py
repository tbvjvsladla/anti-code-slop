#!/usr/bin/env python3
"""Install the package into a fresh project and drive one full gate round.

For each install location (Claude Code `.claude/skills/`, Codex `.agents/skills/`):
copy the package in, audit the whole project root (default scope), remove a block of
commented-out code, write the reviews and the report, expect `verify` COMPLETE with
the run folder outside the project, then `restore` and expect the original file back.
Prints SMOKE-PASS on the last line when every step holds. Nothing outside a temporary
folder is written (XDG_STATE_HOME points inside it).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".cache")
LOCATIONS = {"claude-code": Path(".claude/skills/anti-code-slop"), "codex": Path(".agents/skills/anti-code-slop")}

ORIGINAL = '''def add(a, b):
    # old = a - b
    # return old
    return a + b
'''
FIXED = '''def add(a, b):
    return a + b
'''
CHECK = "python3 -B -c \"import sys; sys.path.insert(0, 'src'); import calc; assert calc.add(1, 2) == 3\""


class SmokeFailure(Exception):
    pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)
    print(f"  ok  {message}")


def run_gate(gate: Path, env: dict, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(gate), *map(str, args)], capture_output=True, text=True, env=env)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def round_for(location: str, root: Path) -> None:
    print(f"[{location}]")
    project = root / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "calc.py").write_text(ORIGINAL, encoding="utf-8")
    skill = project / LOCATIONS[location]
    shutil.copytree(PACKAGE_ROOT, skill, ignore=COPY_IGNORE)
    gate = skill / "scripts" / "slop_gate.py"
    state = root / "state"
    env = dict(os.environ, XDG_STATE_HOME=str(state), PYTHONDONTWRITEBYTECODE="1")
    env.pop("ANTI_CODE_SLOP_RUNS", None)

    manifest = subprocess.run([sys.executable, "-B", str(skill / "tools" / "package_manifest.py"), "--check",
                               "--root", str(skill)], capture_output=True, text=True)
    expect(manifest.returncode == 0, "installed copy matches PACKAGE_MANIFEST.json")

    scan_out = root / "scan.json"
    proc = run_gate(gate, env, "scan", "--target", project, "--out", scan_out)
    expect(proc.returncode == 0, "scan of the whole project exits 0")
    scan = json.loads(scan_out.read_text())
    found = [(s["file"], s["rule"]) for s in scan["signals"]]
    expect(found == [("src/calc.py", "PY-COMMENTED-CODE")], f"only the project's slop is found ({found})")
    own = {rel for rel, why in scan["files"]["excluded"].items() if why == "anti_code_slop_skill"}
    expect(own and all(rel.startswith(LOCATIONS[location].as_posix() + "/") for rel in own),
           f"the installed skill folder is excluded from the scan ({len(own)} files)")

    proc = run_gate(gate, env, "snapshot", "--target", project, "--allowed", "src",
                    "--fix-types", "commented-code", "--check", CHECK, "--executor", "smoke_install")
    expect(proc.returncode == 0, f"snapshot exits 0 {proc.stderr.strip()}")
    run_dir = Path(json.loads(proc.stdout)["run_dir"])
    expect(run_dir.parent == (state / "anti-code-slop" / "runs").resolve(), "default run folder is the state folder")
    expect(project.resolve() not in run_dir.parents, "run folder is outside the project")

    (project / "src" / "calc.py").write_text(FIXED, encoding="utf-8")
    for role in ("comment", "structure", "diff"):
        write_json(run_dir / "reviews" / f"{role}.json", {"role": role, "independent": False, "items": []})
    write_json(run_dir / "report.json", {
        "executor": "smoke_install",
        "reviewers": [{"role": r, "independent": False} for r in ("comment", "structure", "diff")],
        "verdicts": [], "dispositions": [], "proposals": [], "open_constraints": [], "findings": [], "deleted_files": [],
    })
    proc = run_gate(gate, env, "verify", "--run-dir", run_dir, "--executor", "smoke_install")
    verdict = json.loads(sorted(run_dir.glob("verdict-*.json"))[-1].read_text())
    expect(proc.returncode == 0 and verdict.get("result") == "COMPLETE",
           f"verify COMPLETE (exit {proc.returncode}, {verdict.get('result')})")

    proc = run_gate(gate, env, "restore", "--run-dir", run_dir)
    expect(proc.returncode == 0, f"restore exits 0 {proc.stderr.strip()}")
    expect((project / "src" / "calc.py").read_text(encoding="utf-8") == ORIGINAL, "restore brings the original back")


def main() -> int:
    try:
        for location in LOCATIONS:
            with tempfile.TemporaryDirectory(prefix=f"slop-smoke-{location}-") as tmp:
                round_for(location, Path(tmp))
    except SmokeFailure as failure:
        print(f"  FAIL {failure}")
        print("SMOKE-FAIL")
        return 1
    print("SMOKE-PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
