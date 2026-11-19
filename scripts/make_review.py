#!/usr/bin/env python3
"""Compile the human review packet after an autonomous run.

The model is expected to push a reproduction all the way to a scored result
*without* pausing for human input.  When it is done, it hands over two things:

  * REPORT.md  -- the reproduction report (what was achieved);
  * REVIEW.md  -- this packet (what still needs a human decision).

REVIEW.md is generated from machine-checked ledgers (spec/decisions.json and the
stored scoring reports), so the hand-off cannot drop a pending question on the
floor.  It is regenerated on every run: edit spec/decisions.json, never REVIEW.md.
"""
import argparse
import json
from pathlib import Path

from common import finish, project, read_json, require, run, sha256, within


def decisions(root):
    path = Path(root) / "spec/decisions.json"
    if not path.is_file():
        return {"items": []}, None
    doc = read_json(path)
    return doc, sha256(path)


def scored(root, tid):
    """Best-scoring report for a target: reports/<tid>.json wins, else shortest path."""
    hits = []
    for path in sorted(Path(root).rglob("*.json")):
        if path.parent.name == "reports" or "reports" in path.parts:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("target") == tid:
                hits.append((0 if path.name == f"{tid}.json" else 1, len(path.parts), path, payload))
    hits.sort(key=lambda h: (h[0], h[1]))
    if not hits:
        return None
    return hits[0][3]


def artifacts(root):
    """Append-only artifact ledger written by record_artifact.py (may be absent)."""
    path = Path(root) / "artifacts.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("path"):
            rows.append(row)
    return rows


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def build(root):
    doc = project(root)
    ledger, digest = decisions(root)
    items = ledger.get("items") or []

    targets = []
    for target in doc["targets"]:
        payload = scored(root, target["id"])
        targets.append({
            "id": target["id"],
            "subject": target["validation_subject"],
            "status": (payload or {}).get("status", "未评分"),
            "metrics": (payload or {}).get("metrics", {}),
        })

    pending = [i for i in items if i.get("status") == "escalated"]
    auto = [i for i in items if i.get("status") == "auto"]
    human = [i for i in items if i.get("status") in ("human_confirmed", "human_overridden")]

    lines = ["# 人工评审包", "",
             "> 本文件由 `make_review.py` 生成，**请勿手改**。要裁决请在 `spec/decisions.json` 里",
             "> 填 `human_review{by,date,note}` 并改 `status`，然后重跑 `make_review.py` 与 `validate.py`。",
             ("> 自动流程跑到这里后，**%d 条决策已由人工确认**（见 §3）。" % len(human)
              if human else "> 自动流程在**没有任何人工输入**的情况下跑到了这里。"), ""]

    lines += ["## 0. 本轮自动产出", "",
              f"- 论文：{doc['title']}",
              f"- 来源：{doc['source']}",
              f"- 阶段：`{doc['stage']}`；验证等级：`{doc['level']}`；复现模式：`{doc['reproduction_mode']}`",
              f"- 目标：{len(targets)} 个；决策台账：{len(items)} 条（其中待裁决 {len(pending)} 条）",
              f"- 报告：`REPORT.md`；决策台账 `spec/decisions.json`（sha256 `{(digest or 'n/a')[:12]}`）", "",
              *table(["目标", "验证对象", "评分状态", "指标"],
                     [[t["id"], t["subject"], t["status"],
                       ", ".join(f"{k}={v}" for k, v in t["metrics"].items()) or "-"]
                      for t in targets]), ""]

    lines += [f"## 1. 待裁决（escalated）：{len(pending)} 项", ""]
    if pending:
        lines += table(["ID", "问题", "选项", "已暂选", "为何升级"],
                       [[f"`{i['id']}`", i["question"], " ／ ".join(i["options"]),
                         i["chosen"], i.get("escalation_reason", "-")] for i in pending])
    else:
        lines += ["无。自动流程未遇到必须由人裁决的判定级歧义。"]
    lines += [""]

    lines += [f"## 2. 已自动决策（auto）：{len(auto)} 项", ""]
    if auto:
        lines += table(["ID", "问题", "选择", "规则", "置信", "影响", "可逆性"],
                       [[f"`{i['id']}`", i["question"], i["chosen"], i["rule"],
                         i["confidence"], i["impact"], i["reversibility"]] for i in auto])
    else:
        lines += ["无。"]
    lines += [""]

    lines += [f"## 3. 已人工确认：{len(human)} 项", ""]
    if human:
        lines += table(["ID", "问题", "选择", "状态", "评审人", "日期", "结论"],
                       [[f"`{i['id']}`", i["question"], i["chosen"], i["status"],
                         i["human_review"]["by"], i["human_review"]["date"],
                         i["human_review"]["note"]] for i in human])
    else:
        lines += ["无（本轮尚未有人工裁决）。"]
    lines += [""]

    lines += ["## 4. 评审动作", ""]
    if pending:
        lines += [f"1. 逐条裁决 §1 的 {len(pending)} 项：在 `spec/decisions.json` 填写 "
                  "`human_review{by,date,note}`，把 `status` 改为 `human_confirmed` 或 `human_overridden`，"
                  "并在 `basis` 补充你的依据。"]
    else:
        lines += ["1. 无需裁决：确认 §2 的自动决策可以接受（不同意就把该条改成 `human_overridden`）。"]
    lines += ["2. 复核 `REPORT.md` §3 的局限清单，尤其是被标记为非留出的参考。",
              "3. 重跑 `python3 scripts/validate.py .` 确认门禁仍全绿。",
              "4. 若裁决改变了任何结论，更新 `REPORT.md` §1/§3 并重跑 `check_report.py`。",
              "5. 通读 §2 里 `impact=verdict` 的自动决策；它们已经满足「高置信且可逆」，但仍是结论的受力点。", ""]

    lines += [("## 5. 复现结论（自动汇总；%d 条决策已人工确认，整篇结论仍须复核）" % len(human)
               if human else "## 5. 复现结论（自动汇总，未经人工签署）"), ""]
    ok = [t for t in targets if t["status"] == "PASS"]
    lines += [f"自动评分下 PASS 的目标 {len(ok)}/{len(targets)}。这些是数值协议结果，**不等同**科学结论；"
              "逐目标判定与证据绑定见 `REPORT.md` §1。", ""]

    ledger_rows = artifacts(root)
    lines += [f"## 6. 过程时间线：{len(ledger_rows)} 份登记产物", ""]
    if ledger_rows:
        lines += ["由 `record_artifact.py` 边做边钉（append-only，按 sha256 去重）：", ""]
        lines += table(["时间", "类别", "产物", "目标", "说明", "取代"],
                       [[r.get("ts", "-"), r.get("kind", "-"), f"`{r['path']}`",
                         r.get("target") or "-", (r.get("note") or "-").replace("|", "/"),
                         f"`{r['supersedes']}`" if r.get("supersedes") else "-"]
                        for r in ledger_rows])
    else:
        lines += ["未登记中间产物（本轮没有跑 `record_artifact.py create` / `record_artifact.py <path>`）；"
                  "过程只能从 `LOG.md` 与 `runs/` 反推。"]
    lines += [""]

    text = "\n".join(lines) + "\n"
    return doc, digest, items, pending, targets, text


def check(root):
    doc, digest, items, pending, targets, text = build(root)
    within(root, "REVIEW.md").write_text(text, encoding="utf-8")
    payload = {
        "generated_by": "make_review.py",
        "stage": doc["stage"],
        "decisions_sha256": digest,
        "pending": [i["id"] for i in pending],
        "auto": len([i for i in items if i.get("status") == "auto"]),
        "targets": {t["id"]: {"status": t["status"], **t["metrics"]} for t in targets},
        "artifacts": [r["path"] for r in artifacts(root)],
    }
    out = within(root, "reports/review.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return finish("PASS",
                  f"评审包已生成：{len(items)} 条决策，{len(pending)} 项待裁决 -> REVIEW.md，"
                  "reports/review.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
