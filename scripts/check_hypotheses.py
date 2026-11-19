#!/usr/bin/env python3
"""Validate structured hypotheses and evidence bindings; cannot prove completeness of history."""
import argparse
import re
from common import artifact, finish, read_json, require, run, sha256, within


def check(root):
    doc = read_json(within(root, "spec/hypotheses.json"))
    items = doc.get("items")
    require(isinstance(items, list), "hypotheses.items must be a list")
    if not items:
        require(bool(doc.get("empty_reason")), "empty hypothesis ledger needs a reason")
        return finish("NOT_APPLICABLE", doc["empty_reason"])
    seen = set()
    log = within(root, "LOG.md").read_text(encoding="utf-8")
    for item in items:
        hid = item.get("id", "")
        require(re.fullmatch(r"H[0-9]+", hid) is not None and hid not in seen, "invalid/duplicate hypothesis id")
        seen.add(hid)
        require(all(item.get(k) for k in ("claim", "experiment", "prediction")), f"{hid}: claim/experiment/prediction required")
        status = item.get("status")
        require(status in ("open", "supported", "falsified", "retired"), f"{hid}: invalid status")
        if status in ("supported", "falsified"):
            require(bool(item.get("premise")), f"{hid}: premise required")
            require(item.get("evidence"), f"{hid}: evidence required")
            manifest = read_json(artifact(root, item["run"]))
            require(manifest.get("returncode") == 0, f"{hid}: evidence run failed")
            for evidence in item["evidence"]:
                path = artifact(root, evidence)
                require(evidence.get("metric") and evidence.get("result") is not None, f"{hid}: measured metric/result required")
                name = str(path.relative_to(within(root, ".")))
                require(manifest.get("outputs", {}).get(name) == sha256(path), f"{hid}: run does not bind evidence")
        if status == "falsified":
            require(bool(item.get("retraction")), f"{hid}: retraction explanation required")
            require(f"[RETRACT:{hid}]" in log, f"{hid}: missing exact [RETRACT:{hid}] log marker")
    return finish("PASS", "hypothesis fields and evidence hashes valid; causal conclusions require review")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
