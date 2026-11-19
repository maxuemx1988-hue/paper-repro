#!/usr/bin/env python3
"""Audit the compute budget: estimate before running, throughput from real runs.

Two failure modes this blocks, both observed in the wild:

  * a scan that silently becomes a 300 CPU-hour job because nobody did the
    arithmetic first (Mira's Fig.8 session opened with exactly that estimate and
    then cut L=20 -> L=15);
  * an ETA inherited from a *tool error message* rather than from measured wall
    time ("after 1200 seconds" while the process was killed at 645 s).

So: `spec/budget.json` must state an estimate with a basis, the alternatives that
were considered when the estimate is over the local limit, the chosen mitigation,
and at least one measured chunk bound to `runs/*/manifest.json`.  Every ETA must
be consistent with the measured throughput; every scale reduction must be
explained by a decision entry (`{budget_amendment: true}`).

No budget file (or `not_applicable`) -> NOT_APPLICABLE, so pre-v3 workspaces
stay green.
"""
import argparse
import json
from pathlib import Path

from common import finish, number, read_json, require, run, sha256, within

HARD_LIMIT_HOURS = 2.0      # above this, alternatives must be on the record
ETA_BAND = 2.0              # measured-vs-declared ETA may differ by at most this factor


def amendments(root):
    path = Path(root) / "spec/decisions.json"
    if not path.is_file():
        return []
    try:
        items = read_json(path).get("items") or []
    except ValueError:
        return []
    return [i for i in items if isinstance(i, dict) and i.get("budget_amendment") is True]


def measured_rate(entries, root):
    """Seconds per unit of work, from manifests only. Returns (rate, total_done)."""
    done = 0
    seconds = 0.0
    for entry in entries:
        require(isinstance(entry, dict), "measured entry must be an object")
        count = number(entry.get("done"), "measured.done", 0)
        require(count > 0, "measured.done must be positive")
        entry = dict(entry)
        run_ref = entry.get("run")
        if isinstance(run_ref, dict):
            path = within(root, run_ref.get("file"))
            require(path.is_file(), f"measured run manifest missing: {run_ref.get('file')}")
            require(run_ref.get("sha256") == sha256(path),
                    f"measured run hash mismatch: {run_ref.get('file')}")
            manifest = json.loads(path.read_text(encoding="utf-8"))
            require(bool(manifest.get("id")), "bound run manifest is not a record_run.py manifest")
            if entry.get("seconds") is None:
                started, finished = manifest.get("started"), manifest.get("finished")
                require(started and finished,
                        "manifest lacks started/finished; pass measured.seconds explicitly")
                entry["seconds"] = _span(started, finished)
        seconds += number(entry.get("seconds"), "measured.seconds", 0)
        done += int(count)
    require(seconds > 0, "measured chunks must sum to positive seconds")
    return seconds / done, done


def _span(started, finished):
    from datetime import datetime
    parse = lambda v: datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return (parse(finished) - parse(started)).total_seconds()


def check(root):
    path = Path(root) / "spec/budget.json"
    if not path.is_file():
        return finish("NOT_APPLICABLE", "no spec/budget.json (pre-v3 workspace); budget tracking is optional")
    doc = read_json(path)
    require(isinstance(doc, dict), "budget.json must be an object")
    if doc.get("not_applicable"):
        reason = doc["not_applicable"]
        require(isinstance(reason, str) and reason.strip(),
                "not_applicable must be a non-empty reason")
        project_doc = read_json(within(root, "spec/project.json"))
        if str(reason).startswith("TEMPLATE:"):
            require(project_doc.get("stage") != "final",
                    "spec/budget.json is still the scaffold template: either fill estimate/chosen/"
                    "measured or replace not_applicable with the real reason (no TEMPLATE: prefix)")
            print("  [DISCLOSURE] budget is still the scaffold template; long scans need an estimate")
        return finish("NOT_APPLICABLE", reason)

    estimate = doc.get("estimate")
    require(isinstance(estimate, dict), "estimate required (flops/cpu_hours + basis)")
    hours = number(estimate.get("cpu_hours"), "estimate.cpu_hours", 0)
    require(hours >= 0, "estimate.cpu_hours must be >= 0")
    require(bool(str(estimate.get("basis") or "").strip()),
            "estimate.basis required: show the arithmetic, not just a number")

    paths = doc.get("paths_considered")
    require(isinstance(paths, list), "paths_considered must be a list (may be empty under the limit)")
    require(all(isinstance(p, str) and p.strip() for p in paths), "paths_considered entries must be non-empty strings")
    if hours > HARD_LIMIT_HOURS:
        require(len(paths) >= 2,
                f"estimate {hours}h > {HARD_LIMIT_HOURS}h: at least two alternatives must be on the record")

    chosen = doc.get("chosen")
    require(isinstance(chosen, dict), "chosen required")
    chunk = chosen.get("chunk_size")
    require(type(chunk) is int and chunk >= 1, "chosen.chunk_size must be a positive integer")
    require(isinstance(chosen.get("resume"), bool), "chosen.resume must be boolean")
    configs = chosen.get("configs")

    measured = doc.get("measured")
    require(isinstance(measured, list) and measured,
            "measured must contain at least one chunk bound to runs/*/manifest.json")
    rate, done = measured_rate(measured, root)
    measured_hours = (configs * rate / 3600) if isinstance(configs, int) and configs > 0 else None
    print(f"  measured {rate:.3f} s/unit over {done} units"
          + (f"; {configs} units -> {measured_hours:.2f} h" if measured_hours else ""))

    eta = doc.get("eta_hours")
    if eta is not None:
        eta = number(eta, "eta_hours", 0)
        require(bool(str(doc.get("eta_basis") or "").strip()),
                "eta_hours requires eta_basis citing measured throughput, not a tool error message")
        require("measured" in str(doc.get("eta_basis")) or "manifest" in str(doc.get("eta_basis")),
                "eta_basis must cite measured throughput (mention 'measured' or 'manifest'), "
                "not the seconds printed in a timeout message")
        if measured_hours:
            ratio = eta / measured_hours
            if not (1 / ETA_BAND <= ratio <= ETA_BAND):
                require(bool(amendments(root)),
                        f"eta_hours {eta} is {ratio:.1f}x the measured projection {measured_hours:.2f}h; "
                        "recompute it or record a {budget_amendment: true} decision")

    planned = estimate.get("planned_configs")
    if isinstance(planned, int) and isinstance(configs, int) and configs < planned:
        require(bool(amendments(root)),
                f"chosen.configs {configs} < planned {planned}: a scale reduction needs a "
                "{budget_amendment: true} decision citing measured throughput")
        print(f"  [DISCLOSURE] scale reduced {planned} -> {configs}")

    churn = doc.get("churn_count")
    if churn is not None:
        require(type(churn) is int and churn >= 0, "churn_count must be a non-negative integer")
        if churn:
            print(f"  [DISCLOSURE] budget revised {churn} time(s); disclose it in REPORT.md §3")

    return finish("PASS", f"budget estimated, chosen mitigation chunked ({chunk}) and measured")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
