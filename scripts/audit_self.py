#!/usr/bin/env python3
"""Measure our own reproduction runs: where the time goes, where the churn is.

Reverse-engineering Mira showed the value of turning a session into statistics
instead of impressions (how many events, how many silent turns, how many size
revisions).  The same move applies to us: before adding gates, count what our
past workspaces actually suffered from.  Read-only, never part of validate.py.

Reported metrics (all from machine artefacts, nothing inferred from prose):

  * runs           -- total / failed / timed-out, and failed-without-output;
  * retries        -- identical commands repeated, i.e. blind re-runs;
  * churn          -- decision questions asked more than once (re-decided);
  * anchors        -- registered / held / violated / untested;
  * assets         -- registered artifacts, and how many targets never pinned one;
  * tuning         -- references flagged `used_for_tuning` (non-held-out acceptance).

Use it to pick the next optimisation instead of guessing.
"""
import argparse
import collections
import json
from pathlib import Path

from common import finish, run


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def scan(root):
    root = Path(root)
    runs = [load(p, {}) for p in sorted((root / "runs").glob("*/manifest.json"))]
    runs = [r for r in runs if isinstance(r, dict) and r.get("id")]
    failed = [r for r in runs if r.get("returncode") not in (0,)]
    timeouts = [r for r in runs if r.get("returncode") == 124]
    blind = [r for r in failed if not r.get("outputs")]
    commands = collections.Counter((r.get("command") or ["?"])[0] if isinstance(r.get("command"), list)
                                   else str(r.get("command")) for r in runs)
    retries = sum(c - 1 for c in commands.values() if c > 1)

    decisions = load(root / "spec/decisions.json", {})
    items = decisions.get("items") or []
    questions = collections.Counter(i.get("question", "") for i in items if isinstance(i, dict))
    churn = sum(c - 1 for c in questions.values() if c > 1)
    by_status = collections.Counter(i.get("status", "?") for i in items if isinstance(i, dict))
    by_impact = collections.Counter(i.get("impact", "?") for i in items if isinstance(i, dict))

    anchors = load(root / "spec/anchors.json", {})
    anchor_items = [i for i in (anchors.get("items") or []) if isinstance(i, dict)]
    anchor_status = collections.Counter(i.get("status", "untested") for i in anchor_items)

    artifacts = []
    ledger = root / "artifacts.jsonl"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                artifacts.append(json.loads(line))
            except ValueError:
                continue
    pinned = {a.get("target") for a in artifacts if a.get("target")}

    project = load(root / "spec/project.json", {})
    targets = [t.get("id") for t in (project.get("targets") or []) if isinstance(t, dict)]
    provenance = load(root / "spec/provenance.json", {})
    tuning = [r for r in (provenance.get("references") or [])
              if isinstance(r, dict) and r.get("used_for_tuning")]

    return {
        "runs": {"total": len(runs), "failed": len(failed), "timeout": len(timeouts),
                 "failed_without_output": len(blind), "blind_reruns": retries},
        "decisions": {"total": len(items), "refiled_questions": churn,
                      "by_status": dict(by_status), "by_impact": dict(by_impact)},
        "anchors": {"total": len(anchor_items), "by_status": dict(anchor_status)},
        "artifacts": {"registered": len(artifacts), "targets": len(targets),
                      "targets_without_artifact": sorted(set(targets) - pinned)},
        "tuning": {"used_for_tuning": len(tuning),
                   "files": [r.get("file") for r in tuning]},
    }


DIAGNOSIS = (
    (lambda m: m["runs"]["blind_reruns"] > 0,
     "重复命令多：先解决失败归因（protocol 失败分类表 + failure_class），再加检查器"),
    (lambda m: m["decisions"]["refiled_questions"] > 0,
     "决策 churn：协议/锚点不够硬，模型反复改尺寸或约定 -> 先做 anchors/budget"),
    (lambda m: m["anchors"]["total"] == 0 and m["runs"]["total"] > 0,
     "没有任何预注册锚点：数值可能已被事后调参，优先补 spec/anchors.json"),
    (lambda m: m["artifacts"]["targets_without_artifact"] and m["decisions"]["total"] > 0,
     "有目标从未登记中间产物：评审包无法回溯过程 -> 用 record_artifact.py 边做边钉"),
)


def report(root, as_json=False):
    metrics = scan(root)
    rows = [("跑批总数", metrics["runs"]["total"]),
            ("失败跑批", metrics["runs"]["failed"]),
            ("超时被杀", metrics["runs"]["timeout"]),
            ("失败且无产物（黑箱重试风险）", metrics["runs"]["failed_without_output"]),
            ("盲重跑（同一命令重复次数）", metrics["runs"]["blind_reruns"]),
            ("决策条数", metrics["decisions"]["total"]),
            ("同题重决策（churn）", metrics["decisions"]["refiled_questions"]),
            ("预注册锚点", metrics["anchors"]["total"]),
            ("锚点状态", metrics["anchors"]["by_status"] or "-"),
            ("登记产物", metrics["artifacts"]["registered"]),
            ("从未登记产物的目标", metrics["artifacts"]["targets_without_artifact"] or "-"),
            ("非留出参考（调参披露）", metrics["tuning"]["used_for_tuning"])]
    width = max(len(str(k)) for k, _ in rows)
    for key, value in rows:
        print(f"  {str(key):<{width}}  {value}")
    advice = [hint for test, hint in DIAGNOSIS if test(metrics)]
    print("\n[DIAGNOSIS]")
    for hint in advice or ["未发现明显结构性浪费；优先补覆盖面而不是加新门禁。"]:
        print(f"  - {hint}")
    if as_json:
        out = Path(root) / "reports/audit_self.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"metrics": metrics, "diagnosis": advice}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[audit] {out}")
    return finish("PASS", "self-audit only; not a scientific verdict, not part of validate.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    parser.add_argument("--json", action="store_true", help="同时写 reports/audit_self.json")
    args = parser.parse_args()
    raise SystemExit(run(lambda: report(args.root, args.json)))
