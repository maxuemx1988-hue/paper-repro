#!/usr/bin/env python3
"""Validate the reproduction report: structure and evidence binding, not truth.

REPORT.md is the deliverable that a reproduction produced *after* the numbers
were scored.  This checker never re-scores physics.  It verifies that

  * the report exists, has the six required sections and no placeholders;
  * every declared target appears exactly once in the verdict table and nowhere
    else, with a verdict from the fixed vocabulary;
  * a verdict of 定量符合/定性一致 quotes a metric that agrees with the stored
    scoring report, and that report is PASS and belongs to the same target
    (this is what stops hand-written "looks good" numbers);
  * the gate-chain section names the checks that were actually run;
  * the limitations section is non-empty and discloses tuning when any
    reference was used for tuning;
  * the method and provenance sections describe how to rerun and what the
    references are, including the digitised fallback when no data were published;
  * every decision that was escalated for human verdict is echoed in §3, so an
    autonomous run cannot bury an open question in the deliverable.

A missing report at stage < final is NOT_APPLICABLE, not a failure: the report
is a final-stage deliverable.
"""
import argparse
import json
import re
from pathlib import Path

from common import finish, project, read_json, require, run, within

SECTIONS = [
    "## 0. 结论摘要",
    "## 1. 逐目标结果",
    "## 2. 门禁与证据",
    "## 3. 局限与未完成项",
    "## 4. 复现方法",
    "## 5. 参考来源与调参披露",
]
VERDICT_QUANT = "定量符合"
VERDICT_QUAL = "定性一致"
VERDICT_MISS = "未达标"
VERDICT_TODO = "未完成"
VERDICTS = {VERDICT_QUANT, VERDICT_QUAL, VERDICT_MISS, VERDICT_TODO}
PASSING = {VERDICT_QUANT, VERDICT_QUAL}
PLACEHOLDER = re.compile(r"[⟪⟫]|^(tbd|待填|待定|-|—|)$", re.I)
NUMBER = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?|-?\d+(?:[eE][-+]?\d+)?")


def section_bodies(text):
    """Split the report into {heading: body} for the known headings."""
    out = {}
    positions = []
    for heading in SECTIONS:
        index = text.find(heading)
        if index < 0:
            continue
        positions.append((index, heading))
    positions.sort()
    for k, (index, heading) in enumerate(positions):
        end = positions[k + 1][0] if k + 1 < len(positions) else len(text)
        out[heading] = text[index + len(heading):end].strip()
    return out


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def verdict_table(body):
    """Return the rows of the first Markdown table whose header has 目标 and 判定."""
    lines = body.splitlines()
    for i in range(len(lines) - 1):
        head = lines[i].strip()
        rule = lines[i + 1].strip()
        if not (head.startswith("|") and re.fullmatch(r"\|[\s:\-|]+\|", rule)):
            continue
        header = cells(head)
        if not any("目标" in c for c in header) or not any("判定" in c for c in header):
            continue
        rows = []
        for line in lines[i + 2:]:
            if not line.strip().startswith("|"):
                break
            rows.append(dict(zip(header, cells(line))))
        return header, rows
    return None, None


def pick(row, *needles):
    for key, value in row.items():
        if any(n in key for n in needles):
            return value
    return None


def scoring_report(root, tids, row, tid):
    """Locate and load the stored scoring report referenced by this row."""
    evidence = pick(row, "证据", "报告", "report")
    require(bool(evidence), f"{tid}: 证据列必须给出 reports/... 评分报告路径")
    match = re.search(r"[A-Za-z0-9_./-]*reports/[A-Za-z0-9_./-]+\.json", evidence)
    require(bool(match), f"{tid}: 证据列里找不到 reports/*.json 路径")
    path = within(root, match.group(0))
    require(path.is_file(), f"{tid}: 评分报告不存在 {match.group(0)}")
    payload = read_json(path)
    require(payload.get("target") == tid,
            f"{tid}: 评分报告 {match.group(0)} 属于 {payload.get('target')!r}，目标不匹配")
    return path, payload


def check(root):
    doc = project(root)
    report = within(root, "REPORT.md")
    if doc["stage"] != "final":
        require(not report.exists() or report.read_text(encoding="utf-8").strip(),
                "REPORT.md 存在但为空")
        return finish("NOT_APPLICABLE",
                      "复现报告是 final 阶段交付物；当前 stage=%s" % doc["stage"])
    require(report.is_file(),
            "final 阶段必须输出 REPORT.md（模板见 references/report_template.md）")
    text = report.read_text(encoding="utf-8")
    require(not re.search(r"[⟪⟫]", text), "报告仍有 ⟪⟫ 占位符")
    bodies = section_bodies(text)
    missing = [h for h in SECTIONS if h not in bodies]
    require(not missing, "缺少章节或标题不匹配: " + ", ".join(missing))
    for heading, body in bodies.items():
        require(not PLACEHOLDER.match(body.strip()) and body.strip(),
                f"{heading} 不能为空")

    header, rows = verdict_table(bodies["## 1. 逐目标结果"])
    require(rows, "§1 需要一张含 目标/判定 列的 Markdown 表格")
    ids = [t["id"] for t in doc["targets"]]
    seen = {}
    for row in rows:
        tid = pick(row, "目标")
        require(bool(tid), "§1 表格每行都要有目标 id")
        tid = tid.strip("` ")
        require(tid in ids, f"§1 出现未在 project.json 声明的目标 {tid!r}")
        require(tid not in seen, f"§1 目标 {tid} 重复出现")
        verdict = pick(row, "判定")
        require(verdict in VERDICTS,
                f"{tid}: 判定必须是 {'/'.join(sorted(VERDICTS))} 之一（得到 {verdict!r}）")
        seen[tid] = (row, verdict)
    absent = [t for t in ids if t not in seen]
    require(not absent, "§1 遗漏目标: " + ", ".join(absent))

    checked = 0
    for tid, (row, verdict) in seen.items():
        if verdict not in PASSING:
            continue
        path, payload = scoring_report(root, ids, row, tid)
        require(payload.get("status") == "PASS",
                f"{tid}: 判定为{verdict}，但评分报告 {path.name} 状态是 {payload.get('status')}")
        quoted = pick(row, "指标", "rms", "误差")
        require(bool(quoted), f"{tid}: 判定为{verdict} 时必须写出指标数值")
        numbers = [float(v) for v in NUMBER.findall(quoted.replace(",", ""))]
        require(numbers, f"{tid}: 指标列里没有可解析的数值")
        metrics = payload.get("metrics") or {}
        candidates = [v for k, v in metrics.items()
                      if isinstance(v, (int, float)) and not k.endswith(("_dx", "_dy"))]
        require(candidates, f"{tid}: 评分报告里没有可比对的数值指标")
        ok = any(any(abs(n - c) <= 1e-6 * max(1.0, abs(c)) for c in candidates)
                 for n in numbers)
        require(ok,
                f"{tid}: 报告里的指标 {numbers} 与评分报告 {list(metrics)} 不一致"
                "（不允许手写未经评分的数字）")
        checked += 1

    gates = bodies["## 2. 门禁与证据"]
    named = set(re.findall(r"check_[a-z_]+\.py", gates))
    require(len(named) >= 3, "§2 至少列出三个实际运行过的 check_*.py")
    if any(t.get("paper_figure") for t in doc["targets"]):
        require(bool(re.search(r"并排|side_by_side", gates)),
                "存在 paper_figure 目标：§2 必须记录左右并排对比图（figures/compare/*_side_by_side.png）")

    limits = bodies["## 3. 局限与未完成项"]
    require(len(limits.splitlines()) >= 1, "§3 需要逐条列出局限或未完成项")
    prov = read_json(within(root, doc["independence"]))
    refs = prov.get("references") or []
    if any(r.get("used_for_tuning") for r in refs):
        require(re.search(r"调参|tuning|非留出|held-out", limits + bodies["## 5. 参考来源与调参披露"]),
                "存在 used_for_tuning=true 的参考，§3 或 §5 必须披露非留出验收")

    method = bodies["## 4. 复现方法"]
    require(re.search(r"\bpython3?\b", method), "§4 需要给出可重跑的命令（含 python）")

    provenance = bodies["## 5. 参考来源与调参披露"]
    require(doc["reproduction_mode"] in provenance,
            f"§5 必须写明 reproduction_mode={doc['reproduction_mode']}")
    kinds = {r.get("kind") for r in refs}
    if kinds:
        require("kind" in provenance,
                "§5 需要逐条列出参考的 kind（写成 `kind=paper` 这类可核对的枚举）")
    if "digitized" in kinds:
        # naming the kind as `digitized` is not a disclosure; the fallback reason
        # (why no numerical source existed) and the extraction must be stated
        require(re.search(r"回退|fallback|像素|pixel|截图|数字化提取|digitisation|digitization", provenance),
                "§5 需说明数字化提取的回退理由（为何没有可用数值来源）与误差估计")

    # an autonomous run must surface what it refused to decide alone
    ledger = within(root, "spec/decisions.json")
    if ledger.is_file():
        items = read_json(ledger).get("items") or []
        pending = [i.get("id") for i in items if i.get("status") == "escalated"]
        if pending:
            require(re.search(r"待裁决|escalat|人工", limits),
                    "存在 escalated 决策：§3 必须披露待人工裁决项")
            absent = [d for d in pending if d not in limits]
            require(not absent,
                    "§3 必须逐条点名待裁决决策 id（含选择题与影响）: " + ", ".join(absent))

    return finish("PASS",
                  f"报告结构与证据绑定有效（{len(seen)} 个目标，{checked} 条判定绑定评分报告）；"
                  "科学结论仍须人工复核")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
