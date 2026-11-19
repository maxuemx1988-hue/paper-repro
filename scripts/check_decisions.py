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

v3.1 adds the *E2 test*, because dogfooding showed the gap: an escalated item used
to need only a plausible `escalation_reason` string, so "the machine cannot tell the
two readings apart" passed as prose while a 10-minute computation could in fact
tell them apart.  Now an escalated decision must list its `discriminators` with a
cost, and may only skip one it genuinely cannot afford (budget.json ceiling).
"No discriminator exists" is treated as a claim that has to be paid for.
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

# What counts as "cheap enough that you must run it before escalating", in hours.
# CPU hours come from measured throughput; engineering hours are the human-time cost
# of writing/instrumenting the experiment.  Override in spec/budget.json as
# {"escalation_ceiling": {"cpu_hours": 0.5, "eng_hours": 1.0}}.
DEFAULT_CEILING = {"cpu_hours": 0.5, "eng_hours": 1.0}


def ceiling(root):
    path = within(root, "spec/budget.json")
    limits = dict(DEFAULT_CEILING)
    if path.is_file():
        try:
            override = read_json(path).get("escalation_ceiling") or {}
        except (OSError, ValueError):
            override = {}
        for key in limits:
            value = override.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                limits[key] = float(value)
    return limits


def check_discriminators(item, did, limits):
    """An escalation must show that the deciding experiment is out of reach, not that
    it was never thought of.  Each entry: experiment, cost_cpu_hours, cost_eng_hours,
    status in {run, skipped}; `run` needs outcome (and decisive must be false),
    `skipped` needs why *and* a cost above at least one ceiling."""
    entries = item.get("discriminators")
    require(isinstance(entries, list) and entries,
            f"{did}: escalated decision needs discriminators[] — list the experiments that could "
            "settle it with their cost, or prove none exists")
    for entry in entries:
        require(isinstance(entry, dict), f"{did}: discriminator entries must be objects")
        require(bool(entry.get("experiment")),
                f"{did}: each discriminator needs experiment text")
        costs = {}
        for key, default in (("cost_cpu_hours", 0.0), ("cost_eng_hours", 0.0)):
            value = entry.get(key, default)
            require(isinstance(value, (int, float)) and value >= 0,
                    f"{did}: discriminator needs numeric {key}")
            costs[key] = float(value)
        status = entry.get("status")
        require(status in ("run", "skipped"),
                f"{did}: discriminator status must be run or skipped (got {status!r})")
        if status == "run":
            require(bool(entry.get("outcome")),
                    f"{did}: a run discriminator must record its outcome")
            require(not entry.get("decisive"),
                    f"{did}: you ran a decisive discriminator — record the verdict instead of "
                    "escalating (status must not be 'escalated')")
        else:
            require(bool(entry.get("why")),
                    f"{did}: a skipped discriminator must say why it was not run")
            affordable = (costs["cost_cpu_hours"] <= limits["cpu_hours"]
                          and costs["cost_eng_hours"] <= limits["eng_hours"])
            require(not affordable,
                    f"{did}: skipped discriminator '{entry['experiment']}' costs "
                    f"{costs['cost_cpu_hours']} CPU-h / {costs['cost_eng_hours']} eng-h, both under "
                    f"the ceiling {limits['cpu_hours']}/{limits['eng_hours']} — run it before "
                    "escalating; if it truly cannot decide, say that in the outcome")


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
    limits = ceiling(root)
    # legacy workspaces predate the field; only enforce it once the ledger declares it
    has_discriminators = any("discriminators" in item for item in items if isinstance(item, dict))
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
            if has_discriminators:
                check_discriminators(item, did, limits)
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
