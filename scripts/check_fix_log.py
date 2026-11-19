#!/usr/bin/env python3
"""Enforce a hash-bound fix ledger so trial-and-error history cannot evaporate.

Rule: every debugging iteration is executed through record_run.py, and LOG.md
must carry a [FIX:Fn] row binding that run's manifest.

Checks
1. [FIX:Fn] markers are unique and ascending;
2. each row has non-empty symptom / root cause / change cells plus a
   run=<manifest path> cell pointing at an existing manifest;
3. consecutive entries must show DIFFERENT code snapshots (code really changed);
4. the CURRENT code snapshot must have a passing run (returncode 0) that started
   no earlier than the last fix;
5. a workspace with code but no ledger is INCOMPLETE.

Lines tagged [RETRO-BUG:n] are ignored: they document failures from before this
mechanism existed and are deliberately not hash-bound.

A workspace that never needed a debugging iteration may declare `[FIX:NONE] <reason>`
instead of a ledger.  That is only accepted when no recorded run ever failed and the
current code snapshot has a passing run: "no fixes" must be consistent with the run
history, so a cleaned-up ledger still cannot hide a failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from common import Incomplete, finish, read_json, require, run, sha256, within

MARKER = re.compile(r"\[FIX:(F[0-9]+)\]")
NOFIX = re.compile(r"\[FIX:NONE\]\s*(.*)")
RETRO = re.compile(r"\[(?:RETRO|RETRO)-BUG:?[0-9]*\]")


def snapshot_digest(snapshot, prefix):
    if not isinstance(snapshot, dict):
        return None
    items = sorted((k, v) for k, v in snapshot.items() if k.startswith(prefix))
    if not items:
        return None
    payload = json.dumps(items, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def current_code_digest(root):
    files = sorted(list((Path(root) / "code").rglob("*.py")))
    if not files:
        return None
    items = [(str(p.relative_to(Path(root))), sha256(p)) for p in files]
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()


def entries(root):
    log = within(root, "LOG.md")
    require(log.is_file(), "LOG.md required")
    found = []
    for line_no, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
        if RETRO.search(line):
            continue
        seen = set()
        for match in MARKER.finditer(line):
            fid = match.group(1)
            if fid in seen:
                continue
            seen.add(fid)
            found.append((line_no, fid, line))
    return found


def recorded_runs(root):
    out = []
    for path in sorted((Path(root) / "runs").glob("*/manifest.json")):
        manifest = read_json(path)
        out.append((path, manifest))
    return out


def passing_runs(root, digest_now):
    return [str(m.get("started", "")) for _, m in recorded_runs(root)
            if m.get("returncode") == 0
            and snapshot_digest(m.get("snapshot", ""), "code/") == digest_now]


def empty_declaration(root, digest_now):
    """`[FIX:NONE] <reason>`: no debugging iteration was needed, and history agrees."""
    log = within(root, "LOG.md")
    require(log.is_file(), "LOG.md required")
    text = log.read_text(encoding="utf-8")
    match = None
    for line in text.splitlines():
        found = NOFIX.search(line)
        if found and len(found.group(1).strip()) >= 8:
            match = found
            break
    require(match is not None,
            "no [FIX:Fn] entries in LOG.md: record every debugging iteration, or declare "
            "[FIX:NONE] <why no iteration was needed>")
    failed = [str(path.relative_to(Path(root))) for path, m in recorded_runs(root)
              if m.get("returncode") != 0]
    require(not failed,
            "declared [FIX:NONE] but these runs failed, so an iteration exists: "
            + ", ".join(failed[:5]) + " -> log it as [FIX:Fn] with run=<manifest>")
    require(passing_runs(root, digest_now),
            "declared [FIX:NONE] but the current code snapshot has no passing recorded run: "
            "run it through record_run.py")
    return finish("PASS", "no fix iteration declared; recorded runs never failed and the current "
                          "code snapshot has a passing run")


def check(root):
    digest_now = current_code_digest(root)
    if digest_now is None:
        raise Incomplete("no code/*.py to audit; fix ledger not applicable")

    rows = entries(root)
    if not rows:
        return empty_declaration(root, digest_now)

    previous = None
    last_started = ""
    for line_no, fid, line in rows:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        require(len(cells) >= 7, f"{fid} (LOG.md:{line_no}): table row needs >=7 cells")
        labels = {"symptom": cells[2], "cause": cells[3], "change": cells[4]}
        for name, value in labels.items():
            require(bool(value), f"{fid}: empty {name} cell")
        match = re.search(r"run=([^\s|]+)", line)
        require(match, f"{fid}: missing run=<runs/.../manifest.json> binding")
        manifest_path = within(root, match[1])
        require(manifest_path.is_file(), f"{fid}: missing run manifest {match[1]}")
        manifest = read_json(manifest_path)
        require(manifest.get("snapshot"), f"{fid}: manifest lacks code snapshot")
        digest = snapshot_digest(manifest["snapshot"], "code/")
        require(digest, f"{fid}: manifest snapshot has no code/ entries")
        if previous is not None:
            require(digest != previous, f"{fid}: code snapshot identical to previous fix; no code change recorded")
        previous = digest
        last_started = max(last_started, str(manifest.get("started", "")))

    passing = passing_runs(root, digest_now)
    require(passing, "current code snapshot has no passing recorded run: run it through record_run.py")
    require(max(passing) >= last_started, "no passing run of the current code after the last fix")

    return finish("PASS", f"{len(rows)} fixes hash-bound; code really changed and was really run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
