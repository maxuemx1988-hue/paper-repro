#!/usr/bin/env python3
"""Verify the review packet is fresh and drops no pending decision.

make_review.py generates REVIEW.md from spec/decisions.json.  This checker makes
sure the packet still matches the ledger: if a decision was escalated after the
last packet was built, the hand-off would otherwise hide it.  It compares hashes
and the pending set; it does not judge the decisions themselves.
"""
import argparse
from pathlib import Path

from common import finish, read_json, require, run, sha256, within


def check(root):
    ledger = Path(root) / "spec/decisions.json"
    if not ledger.is_file():
        return finish("NOT_APPLICABLE", "no decision ledger; review packet not applicable")
    doc = read_json(ledger)
    items = doc.get("items") or []
    if not items:
        return finish("NOT_APPLICABLE", doc.get("empty_reason") or "empty decision ledger")

    packet = read_json(within(root, "reports/review.json"))
    require(packet.get("generated_by") == "make_review.py",
            "reports/review.json must come from make_review.py")
    digest = sha256(ledger)
    require(packet.get("decisions_sha256") == digest,
            "review packet is stale: spec/decisions.json changed after make_review.py ran")

    pending = [i["id"] for i in items if i.get("status") == "escalated"]
    require(packet.get("pending") == pending,
            f"review packet pending {packet.get('pending')} != ledger escalated {pending}")

    text = within(root, "REVIEW.md").read_text(encoding="utf-8")
    missing = [did for did in pending if f"`{did}`" not in text]
    require(not missing, "REVIEW.md omits escalated decisions: " + ", ".join(missing))
    return finish("PASS",
                  f"review packet fresh（{len(pending)} 项待裁决，sha256 绑定 spec/decisions.json）；"
                  "裁决本身仍须人工签署")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
