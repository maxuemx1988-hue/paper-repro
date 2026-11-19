#!/usr/bin/env python3
"""Append one produced artifact to artifacts.jsonl (hash-deduped, append-only).

Mira's more useful habit is not the fancy event log -- it is that the second
session "pinned" intermediate products as it went (`rgf_ucf.py -> run_sweep.py ->
aggregate.py -> fig3_data.csv -> plot_fig3.py -> fig3_reproduction.png`) instead of
picking five files out of 184 at the very end.  A human reviewing a reproduction
needs that timeline; without it the packet shows a conclusion with no visible
route to it.

Design rules learned from the same session:

  * dedupe by sha256, never by filename -- Mira listed the same PNG twice under
    the task root and under delivery/ and counted it twice;
  * append-only: never rewrite history, `--supersede` records a replacement edge;
  * the ledger is machine-checked (`make_review.py` renders it; `check_review.py`
    requires every file cited in REPORT.md to have been registered).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from common import finish, require, run, sha256, within

KINDS = ("figure", "table", "code", "log", "data", "report", "delivery")
LEDGER = "artifacts.jsonl"


def read_ledger(root):
    path = Path(root) / LEDGER
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def add(root, name, kind, target, note, supersede):
    root = Path(root).resolve()
    require(kind in KINDS, f"kind must be one of {KINDS}")
    path = within(root, name)
    require(path.is_file(), f"missing artifact: {name}")
    digest = sha256(path)
    rows = read_ledger(root)
    if any(row.get("sha256") == digest for row in rows):
        prior = next(row for row in rows if row.get("sha256") == digest)
        return finish("NOT_APPLICABLE",
                      f"already registered as {prior.get('path')} (same sha256); dedupe by content, not filename")
    if supersede:
        patched = [row["path"] for row in rows if row.get("superseded") is None and row.get("path") != name]
        require(supersede in patched, f"--supersede {supersede} is not a registered artifact")
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "path": str(path.relative_to(root)), "sha256": digest, "size": path.stat().st_size,
           "kind": kind, "target": target, "note": note or "",
           "supersedes": supersede}
    with (root / LEDGER).open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[ARTIFACT] {row['path']} ({kind}, sha256 {digest[:12]})")
    return finish("PASS", f"registered {row['path']}")


def listing(root):
    rows = read_ledger(root)
    if not rows:
        return finish("NOT_APPLICABLE", "no artifacts registered yet")
    for row in rows:
        edge = f"  <- {row['supersedes']}" if row.get("supersedes") else ""
        print(f"  {row.get('ts', '?')}  {row.get('kind', '?'):9s} {row.get('path')}{edge}")
    return finish("PASS", f"{len(rows)} artifacts registered (append-only ledger {LEDGER})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    parser.add_argument("path", nargs="?", help="artifact path relative to the project root")
    parser.add_argument("--kind", choices=KINDS, default="figure")
    parser.add_argument("--target", default=None, help="复现目标 id（如 fig3）")
    parser.add_argument("--note", default=None, help="一句话说明这份产物证明了什么")
    parser.add_argument("--supersede", default=None, help="被这份产物取代的旧产物路径")
    parser.add_argument("--list", action="store_true", help="打印时间线")
    args = parser.parse_args()
    if args.list or not args.path:
        raise SystemExit(run(lambda: listing(args.root)))
    raise SystemExit(run(lambda: add(args.root, args.path, args.kind, args.target, args.note, args.supersede)))
