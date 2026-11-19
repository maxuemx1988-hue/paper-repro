#!/usr/bin/env python3
"""Run an explicit command, retaining logs, config/code/input/output hashes and exit status."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid
from common import finish, number, require, run, sha256, within


def now():
    return datetime.now(timezone.utc).isoformat()


def record(root, command, inputs, outputs, timeout):
    root = Path(root).resolve()
    require(command, "command required after --command")
    require(number(timeout, "timeout", 0) > 0, "timeout must be positive")
    require(len(outputs) == len(set(outputs)), "duplicate output paths")
    for name in outputs:
        require(not within(root, name).exists(), f"output already exists: {name}; use a fresh run directory")
    before = {name: sha256(within(root, name)) for name in inputs}
    paths = sorted(list((root / "code").rglob("*.py")) + list((root / "spec").rglob("*.json")))
    snapshot = {str(p.relative_to(root)): sha256(p) for p in paths}
    rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    folder = root / "runs" / rid
    folder.mkdir(parents=True)
    versions = {}
    for name in ("numpy", "scipy", "kwant", "Pillow"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    try:
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        commit = git.stdout.strip() if git.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    manifest = {"id": rid, "started": now(), "command": command, "inputs": before,
                "snapshot": snapshot, "recorder_environment": {"python": platform.python_version(),
                "executable": sys.executable, "packages": versions},
                "commit": commit}
    with (folder / "output.log").open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code = 124
                log.write("\n[TIMEOUT] process group killed\n")
        except OSError as exc:
            code = 127
            log.write(f"[LAUNCH ERROR] {exc}\n")
    manifest.update(finished=now(), returncode=code, outputs={})
    for name in outputs:
        path = within(root, name)
        if path.is_file():
            manifest["outputs"][name] = sha256(path)
    manifest["log_sha256"] = sha256(folder / "output.log")
    manifest["inputs_unchanged"] = all(within(root, name).is_file() and sha256(within(root, name)) == digest for name, digest in before.items())
    manifest["snapshot_unchanged"] = all(within(root, name).is_file() and sha256(within(root, name)) == digest for name, digest in snapshot.items())
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[RECORDED] {folder / 'manifest.json'}; command exit={code}")
    complete = code == 0 and len(manifest["outputs"]) == len(outputs) and manifest["inputs_unchanged"] and manifest["snapshot_unchanged"]
    return finish("PASS" if complete else "FAIL", "command/evidence capture only, not a scientific verdict")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    raise SystemExit(run(lambda: record(args.root, args.command, args.input, args.output, args.timeout)))
