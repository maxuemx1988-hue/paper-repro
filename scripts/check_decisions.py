#!/usr/bin/env python3
"""Audit the autonomous decision ledger: what the model decided alone, and why.

An autonomous run must not silently absorb ambiguity.  Every non-trivial choice
is recorded in spec/decisions.json together with the alternatives that were on
the table, the pre-declared rule used to pick one, the evidence, and how
reversible the choice is.  This checker enforces the *policy*, never the physics:

  * `chosen` must be one of the declared `options` (no post-hoc story drift);
  * anything that changed the target set *after it was frozen* (`impact=scope`) must be
    human-confirmed; pre-freeze eligibility filtering that drops a target with no ground
    truth (`impact=eligibility`) is a mechanical autonomous call and may be `auto`;
  * a verdict-flipping choice that is low-confidence or irreversible must be
    *escalated* to the human queue rather than auto-decided;
  * one-way decisions must state how much it costs to reverse them;
  * every decision id appears in LOG.md as [DECISION:Dn].

Escalated items are NOT a failure: an autonomous run may legitimately end with
open questions.  They are queued by make_review.py and must be echoed in
REPORT.md section 3.  What is a failure is masking them.
"""
import argparse
import re
from common import artifact, finish, read_json, require, run, within

RULES = ("paper-literal", "least-commitment", "discriminator", "consistency",
         "analytic-limit", "external-benchmark")
STATUSES = ("auto", "escalated", "human_confirmed", "human_overridden")
IMPACTS = ("verdict", "scope", "numeric", "convention", "eligibility")
CONFIDENCE = ("high", "medium", "low")
REVERSIBILITY = ("reversible", "one-way")


def check(root):
    doc = read_json(within(root, "spec/decisions.json"))
    items = doc.get("items")
    require(isinstance(items, list), "decisions.items must be a list")
    if not items:
        require(bool(doc.get("empty_reason")),
                "empty decision ledger needs a reason (an autonomous run almost always decides something)")
        return finish("NOT_APPLICABLE", doc["empty_reason"])

    log = within(root, "LOG.md").read_text(encoding="utf-8")
    seen = set()
    queue = []
    counts = dict.fromkeys(STATUSES, 0)
    for item in items:
        did = item.get("id", "")
        require(re.fullmatch(r"D[0-9]+", did) is not None and did not in seen,
                f"invalid/duplicate decision id: {did!r}")
        seen.add(did)
        require(bool(item.get("question")), f"{did}: question required")
        require(bool(item.get("basis")), f"{did}: basis required")
        options = item.get("options")
        require(isinstance(options, list) and len(options) >= 2,
                f"{did}: at least two options must be on the record")
        require(all(isinstance(o, str) and o.strip() for o in options),
                f"{did}: options must be non-empty strings")
        require(len(set(options)) == len(options), f"{did}: duplicate options")
        chosen = item.get("chosen")
        require(chosen in options,
                f"{did}: chosen={chosen!r} is not one of the declared options (no post-hoc drift)")
        require(item.get("rule") in RULES,
                f"{did}: rule must be one of {RULES} (declare the rule *before* choosing)")
        reversibility = item.get("reversibility")
        require(reversibility in REVERSIBILITY, f"{did}: invalid reversibility")
        if reversibility == "one-way":
            require(bool(item.get("reverse_cost")),
                    f"{did}: one-way decision must state reverse_cost")
        confidence = item.get("confidence")
        require(confidence in CONFIDENCE, f"{did}: invalid confidence")
        impact = item.get("impact")
        require(impact in IMPACTS, f"{did}: invalid impact")
        status = item.get("status")
        require(status in STATUSES, f"{did}: invalid status")
        counts[status] += 1

        evidence = item.get("evidence") or []
        require(isinstance(evidence, list), f"{did}: evidence must be a list")
        requires_evidence = impact in ("verdict", "scope", "eligibility") or confidence == "high"
        if not evidence:
            require(not requires_evidence or bool(item.get("evidence_reason")),
                    f"{did}: {impact}/{confidence} decision needs bound evidence "
                    "(file+sha256) or an evidence_reason")
        for entry in evidence:
            path = artifact(root, entry)
            require(entry.get("metric") is not None and entry.get("result") is not None,
                    f"{did}: each evidence entry needs metric and result")
            require(path.is_file(), f"{did}: evidence artifact missing")

        if status == "escalated":
            require(bool(item.get("escalation_reason")),
                    f"{did}: escalated decision needs escalation_reason")
            queue.append(did)
        if status in ("human_confirmed", "human_overridden"):
            review = item.get("human_review")
            require(isinstance(review, dict)
                    and all(review.get(k) for k in ("by", "date", "note")),
                    f"{did}: {status} needs human_review{{by,date,note}}")

        # the autonomy policy itself
        if impact == "scope" and status == "auto":
            require(False, f"{did}: changing the target set is never auto-decided; escalate it")
        if impact == "verdict" and status == "auto" and (confidence != "high" or reversibility == "one-way"):
            require(False,
                    f"{did}: a verdict-flipping choice that is {confidence}/{reversibility} must be"
                    " escalated, not auto-decided")

        require(f"[DECISION:{did}]" in log,
                f"{did}: LOG.md must carry the exact marker [DECISION:{did}]")

    summary = ", ".join(f"{k}={counts[k]}" for k in STATUSES if counts[k])
    message = f"{len(seen)} decisions hash-bound ({summary})"
    if queue:
        message += f"; {len(queue)} pending human verdict queued via make_review.py: {', '.join(queue)}"
    return finish("PASS", message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
