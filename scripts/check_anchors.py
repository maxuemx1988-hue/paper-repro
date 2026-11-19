#!/usr/bin/env python3
"""Audit pre-registered paper anchors: declared before the first run, still hash-bound.

The point of `spec/anchors.json` is to make "we got 0.39 and the paper says 0.39"
falsifiable *in advance*.  A reproduction skill without pre-registration lets the
model quietly widen a tolerance after seeing its own number, which is the most
common way an automated reproduction turns into self-fulfilling arithmetic.

Enforced here (policy, never physics):

  * every anchor names a paper-side quantity, its expected value, unit, tolerance
    and a locatable source -- before any run exists;
  * the *first* `runs/*/manifest.json` records `anchors_sha256` (written by
    record_run.py).  Later edits to spec/anchors.json break that fingerprint and
    must be explained by a decision entry `{anchors_amendment: true,
    rule: "discriminator"}` -- i.e. an experiment decided the change, not a mood;
  * `held` / `violated` need evidence bound to a hashed report artifact;
  * at `stage=final` no anchor may stay `untested`, and a `violated` anchor must
    carry a `resolution` (the honest "why it is off" sentence).

Compatibility: a workspace with no spec/anchors.json, or whose earliest manifest
predates v3 (no `anchors_sha256` key), returns NOT_APPLICABLE instead of failing.
"""
import argparse
import json
from pathlib import Path

from common import finish, number, read_json, require, run, sha256, within

KINDS = ("paper", "supplement", "published_data", "analytic", "database", "author_material")
STATUSES = ("untested", "held", "violated")


def manifests(root):
    found = []
    for path in sorted((Path(root) / "runs").glob("*/manifest.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            found.append((str(doc.get("started") or ""), path, doc))
    found.sort(key=lambda item: item[0])
    return found


def amendments(root):
    path = Path(root) / "spec/decisions.json"
    if not path.is_file():
        return []
    try:
        items = read_json(path).get("items") or []
    except ValueError:
        return []
    return [i for i in items if isinstance(i, dict) and i.get("anchors_amendment") is True]


def check_item(item, root, stage):
    aid = item.get("id")
    require(isinstance(aid, str) and aid.strip(), "anchor id required")
    require(bool(item.get("quantity")), f"{aid}: quantity required")
    expected = number(item.get("expected"), f"{aid}.expected")
    require(bool(item.get("unit")), f"{aid}: unit required (write '1' when dimensionless)")
    tolerance = number(item.get("tolerance"), f"{aid}.tolerance", 0)
    require(tolerance > 0, f"{aid}: tolerance must be positive (a zero tolerance is not an anchor)")
    source = item.get("source")
    require(isinstance(source, dict) and source.get("kind") in KINDS,
            f"{aid}: source.kind must be one of {KINDS}")
    require(bool(source.get("locator")), f"{aid}: source.locator required (page/table/figure)")
    status = item.get("status")
    require(status in STATUSES, f"{aid}: status must be one of {STATUSES}")
    if status == "untested":
        require(stage != "final", f"{aid}: still untested at stage=final (score it or mark it violated)")
        return status
    evidence = item.get("evidence")
    require(isinstance(evidence, list) and evidence, f"{aid}: {status} needs bound evidence")
    for entry in evidence:
        require(isinstance(entry, dict), f"{aid}: evidence entry must be an object")
        path = within(root, entry.get("file"))
        require(path.is_file(), f"{aid}: evidence artifact missing: {entry.get('file')}")
        require(entry.get("sha256") == sha256(path), f"{aid}: evidence hash mismatch: {entry.get('file')}")
        require(entry.get("metric") is not None and entry.get("result") is not None,
                f"{aid}: evidence needs metric and result")
    if status == "violated":
        require(bool(item.get("resolution")),
                f"{aid}: a violated anchor must carry `resolution` (why it is off, in REPORT.md §3)")
    return status


def check(root):
    path = Path(root) / "spec/anchors.json"
    if not path.is_file():
        return finish("NOT_APPLICABLE", "no spec/anchors.json (pre-v3 workspace); anchors are optional")
    doc = read_json(path)
    require(isinstance(doc, dict), "anchors.json must be an object")
    project_doc = read_json(within(root, "spec/project.json"))
    stage = project_doc.get("stage", "planning")
    if stage == "planning":
        return finish("NOT_APPLICABLE", "stage=planning: anchors are frozen when the first run starts")

    items = doc.get("items")
    require(isinstance(items, list), "anchors.items must be a list")
    if not items:
        reason = doc.get("empty_reason")
        require(bool(reason),
                "empty anchors need empty_reason: declare the paper-side numbers you will be judged against")
        require(not str(reason).startswith("TEMPLATE:"),
                "spec/anchors.json is still the scaffold template: register the paper-side "
                "values (plateau/peak/gap) before the first record_run.py run")
        return finish("NOT_APPLICABLE", reason)

    ids = [i.get("id") for i in items if isinstance(i, dict)]
    require(len(set(ids)) == len(ids), "duplicate anchor ids")
    counts = dict.fromkeys(STATUSES, 0)
    for item in items:
        require(isinstance(item, dict), "anchor must be an object")
        counts[check_item(item, root, stage)] += 1

    runs = manifests(root)
    require(runs, "stage>=calibrated but no runs/*/manifest.json: run record_run.py before claiming calibration")
    first = runs[0][2]
    recorded = first.get("anchors_sha256")
    if not recorded:
        return finish("NOT_APPLICABLE",
                      "earliest run manifest has no anchors_sha256 (recorded before v3); "
                      "the next record_run.py run establishes the baseline")
    current = sha256(path)
    if current != recorded:
        allowed = [a for a in amendments(root) if a.get("rule") == "discriminator"]
        require(bool(allowed),
                "spec/anchors.json changed after the first run (sha256 mismatch) and no "
                "{anchors_amendment: true, rule: 'discriminator'} decision explains it")
        print(f"[DISCLOSURE] anchors amended by {', '.join(a['id'] for a in allowed)} after the baseline")

    summary = ", ".join(f"{k}={counts[k]}" for k in STATUSES if counts[k])
    print(f"  baseline anchors_sha256 {recorded[:12]} (first run {first.get('id', '?')}), "
          f"current {current[:12]}")
    return finish("PASS", f"{len(items)} pre-registered anchors hash-bound ({summary})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
