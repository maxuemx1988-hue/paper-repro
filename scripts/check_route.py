#!/usr/bin/env python3
"""Audit Route A (official code available) vs Route B (paper ground truth only).

The reproduction pipeline must work both for papers that ship reference code and for
papers that do not.  `official_code` in project.json selects the route, and each route
has a different *oracle*: Route A can interrogate the released implementation, Route B
can only interrogate the paper plus degenerate limits.  This checker enforces that the
workspace is honest about which route it is on and that Route B does not quietly reuse
Route A habits:

  * `provenance.route.mode` must match `official_code` (no undecided route at stage>=calibrated);
  * Route B must record where it looked for code (`code_absence_check`) — an unsearched
    absence is not an absence;
  * Route B may not use `official_comparison` references, and may not rest on digitised
    figures alone: at least one reference must be a printed number (paper/supplement/
    published_data/analytic/database/author_material);
  * Route B needs the substitute for the code oracle to exist: a calibration assertion
    of category `limit` or `invariant` (analytic-limit + conservation checks);
  * a digitised reference reviewed by a vision model must be hash-bound to that model's
    raw response (`*.visual_audit.json` → `vision.raw`), so "model" cannot be typed by hand;
  * at stage=final the report must name the route it ran on.

It never re-derives physics and never promotes a model reading to truth.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import artifact, finish, project, read_json, require, run, within

NUMERIC_KINDS = {"paper", "supplement", "published_data", "analytic", "database", "author_material"}
ROUTE_B_KINDS = NUMERIC_KINDS | {"digitized"}


def route_block(root, doc, prov):
    route = "A" if doc["official_code"] else "B"
    declared = prov.get("route")
    require(isinstance(declared, dict),
            'provenance.route 必须声明：{"mode": "%s", "basis": "<为什么走这条路>", '
            '"code_absence_check": [...]}（Route B 的 code_absence_check 列出查过代码的位置）' % route)
    require(declared.get("mode") == route,
            f'reproduction route 不一致：official_code={doc["official_code"]} 对应 Route {route}，'
            f'但 provenance.route.mode={declared.get("mode")!r}')
    require(isinstance(declared.get("basis"), str) and declared["basis"].strip(),
            "provenance.route.basis 必须说明依据（有代码？还是检索后确认无代码？）")
    return route, declared


def digitized_crop(root, csv, doc):
    """Locate the crop a digitised CSV came from: digitize metadata first, visual config second."""
    meta_path = csv.with_suffix(".meta.json")
    crop = None
    if meta_path.is_file():
        crop = (read_json(meta_path) or {}).get("image")
    if not crop:
        for target in doc.get("targets") or []:
            checks = target.get("checks") or {}
            loss_config = (checks.get("loss") or {}).get("config")
            if not loss_config:
                continue
            loss = read_json(within(root, loss_config))
            if str(within(root, loss["gt"]["file"])) != str(csv):
                continue
            visual = checks.get("visual") or {}
            if visual.get("enabled") and visual.get("config"):
                crop = read_json(within(root, visual["config"])).get("crop")
    require(bool(crop), f"digitized 参考无法定位源图：给 {csv} 写 digitize.py 的 .meta.json"
                        "（含 image）或在目标 visual 配置里声明 crop")
    path = Path(crop) if Path(crop).is_absolute() else within(root, crop)
    path = path.resolve()
    require(path.is_relative_to(Path(root).resolve()), f"crop 在项目外：{crop}")
    return path


def check_route_b(root, doc, prov, declared, refs):
    absence = declared.get("code_absence_check")
    require(isinstance(absence, list) and absence
            and all(isinstance(x, str) and x.strip() for x in absence),
            "Route B 必须登记 code_absence_check（查过 arXiv/作者主页/GitHub/补充材料的哪些位置）")
    kinds = {ref.get("kind") for ref in refs}
    require("official_comparison" not in kinds,
            "Route B 不能引用 official_comparison（无官方代码却用官方输出）")
    require(kinds <= ROUTE_B_KINDS, f"Route B 出现不允许的参考类型：{sorted(kinds - ROUTE_B_KINDS)}")
    require(bool(kinds & NUMERIC_KINDS),
            "Route B 至少要有一个印刷数值来源（正文/表格/补充数据/解析基准），"
            "不能只靠数字化图当唯一真值")

    calib = read_json(within(root, "spec/calibration.json"))
    categories = {a.get("category") for a in (calib.get("assertions") or []) if isinstance(a, dict)}
    require(bool(categories & {"limit", "invariant"}),
            "Route B 没有官方实现可对拍：标定必须至少含一条 category=limit 或 invariant 的断言"
            "（解析极限/守恒关系是替代预言机）")

    for ref in refs:
        if ref.get("kind") != "digitized":
            continue
        crop = digitized_crop(root, within(root, ref["file"]), doc)
        audit_path = crop.with_suffix(".visual_audit.json")
        require(audit_path.is_file(),
                f"digitized 参考缺视觉审计：{audit_path.relative_to(Path(root).resolve())}"
                "（用 scripts/vision.py audit 生成，再人工复核）")
        meta = read_json(audit_path)
        review = meta.get("review") or {}
        require(review.get("method") in ("human", "model", "ocr-assisted"),
                f"digitized 参考的 review.method 无效：{audit_path.name}")
        if review.get("method") == "model":
            vision = meta.get("vision") or {}
            require(bool(vision.get("model_used")),
                    f"{audit_path.name}: method=model 必须记录 vision.model_used")
            artifact(root, vision.get("raw"))     # hash-bound raw response

    if doc["stage"] == "final":
        report = within(root, "REPORT.md")
        require(report.is_file(), "final 阶段必须有 REPORT.md")
        text = report.read_text(encoding="utf-8")
        require(re.search(r"Route\s*B|路线\s*B|无官方代码", text),
                "Route B 的 REPORT.md 必须写明走的是 Route B（无官方代码、以论文真值为预言机）")
        require(re.search(r"数字化|digitiz|像素|pixel", text) if "digitized" in kinds else True,
                "使用 digitized 参考时报告必须披露数字化误差")


def check_route_a(root, doc, prov, declared, refs):
    kinds = {ref.get("kind") for ref in refs}
    # Releasing code but never comparing against it is legitimate (the code may only
    # have guided the modelling).  Say so instead of letting the reader assume a rerun.
    if "official_comparison" not in kinds:
        print("[note] Route A 但未登记 official_comparison：若官方代码只在建模期作指导，"
              "请在 provenance.route.basis 说明没有逐位对拍的原因")


def check(root):
    doc = project(root)
    prov = read_json(within(root, doc["independence"]))
    refs = prov.get("references")
    require(isinstance(refs, list) and refs, "provenance.references 不能为空")
    route, declared = route_block(root, doc, prov)
    if route == "B":
        check_route_b(root, doc, prov, declared, refs)
    else:
        check_route_a(root, doc, prov, declared, refs)
    return finish("PASS", f"Route {route} 声明与证据一致"
                          f"（参考 {len(refs)} 条；官方代码={'有' if doc['official_code'] else '无，走论文真值'}）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
