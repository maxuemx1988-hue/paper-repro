#!/usr/bin/env python3
"""Upgrade an existing reproduction workspace to the current skill schema.

The skill grows new mandatory structure (Route A/B declaration, `paper_figure`,
vision-bound crops).  Old workspaces then fail `validate.py` for reasons that are
purely structural, and the honest fix differs per field:

  * **auto** — mechanically derivable from what the workspace already says
    (e.g. `route.mode` follows `official_code`, `basis` quotes where the code lives);
  * **manual** — would assert a scientific fact the upgrade cannot know
    (which paper figure a target reproduces, where somebody searched for code).
    Inventing those is source fabrication, so this tool only prints them.

Usage:
    python3 scripts/upgrade_project.py <dir>                 # dry run: what is missing
    python3 scripts/upgrade_project.py <dir> --apply         # apply only the auto items
    python3 scripts/upgrade_project.py <dir> --apply \
        --paper-figure fig2_upper=Fig2(a) \
        --code-absence "arXiv source;GitHub search;author homepage"

Every applied item is echoed as `[AUTO]`, every remaining item as `[EVIDENCE]`: those
are not questions for the user, they are work the autonomous round must do itself
(run the code, search for the official repo, audit the crop with vision.py) and then
pass back through --paper-figure/--code-absence.  Nothing here is ever guessed; the
originals are copied to `<file>.pre-upgrade-<UTC>` before the first modification.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from common import read_json

OFFICIAL_DIR = "paper/refcode"
FIGURE_STEM = re.compile(r"^fig(?:ure)?[_-]?(\d+)([a-z])?", re.IGNORECASE)


# --------------------------------------------------------------------------- helpers

def load(root, name):
    path = Path(root) / name
    try:
        doc = read_json(path) if path.is_file() else None
    except Exception:
        doc = None
    return doc if isinstance(doc, dict) else None


def dump(path, doc):
    """Write JSON keeping key order; back the previous version up first."""
    path = Path(path)
    if path.is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_name(f"{path.name}.pre-upgrade-{stamp}"))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def local_files(base):
    base = Path(base)
    return sorted(p for p in base.rglob("*") if p.is_file()) if base.is_dir() else []


def figure_guess(root, target):
    """Best-effort *proposal* for paper_figure: never applied without the user's word."""
    checks = target.get("checks") or {}
    config = (checks.get("visual") or {}).get("config")
    stem = None
    if config:
        visual = load(root, config) or {}
        crop = visual.get("crop")
        if isinstance(crop, str) and crop:
            stem = Path(crop).stem
    if stem is None:
        loss_config = (checks.get("loss") or {}).get("config")
        loss = load(root, loss_config) if loss_config else {}
        gt = (loss or {}).get("gt") or {}
        gt_file = gt.get("file")
        if isinstance(gt_file, str):
            meta = load(root, str(Path(gt_file).with_suffix(".meta.json")))
            image = (meta or {}).get("image")
            stem = Path(image).stem if isinstance(image, str) else Path(gt_file).stem
    if not stem:
        return None
    match = FIGURE_STEM.match(stem)
    if not match:
        return None
    panel = match.group(2)
    return f"Fig{match.group(1)}" + (f"({panel})" if panel else "")


# --------------------------------------------------------------------------- scan

def scan(root, args):
    """Return (auto_ops, manual_notes). An op is (label, path, new_doc)."""
    root = Path(root)
    auto, manual = [], []
    project = load(root, "spec/project.json")
    provenance = load(root, "spec/provenance.json")
    if project is None or provenance is None:
        raise SystemExit("[ERR] 不是复现工作区：缺 spec/project.json 或 spec/provenance.json")

    route = "A" if project.get("official_code") else "B"
    declared = provenance.get("route")
    if not isinstance(declared, dict):
        code_dir = Path(root) / OFFICIAL_DIR
        files = local_files(code_dir)
        if route == "A":
            where = (f"{OFFICIAL_DIR}（{len(files)} 个文件）" if files
                     else "工作区未放代码，official_code=true 但 paper/refcode 为空")
            basis = f"official_code=true：官方实现位于 {where}；结构化迁移时按 official_code 补全，请核对来源"
        else:
            basis = "official_code=false：迁移时按此推断论文未随附代码；code_absence_check 需补真实检索记录"
        absence = list(args.code_absence or [])
        provenance["route"] = {"mode": route, "basis": basis, "code_absence_check": absence}
        auto.append(("provenance.route", "spec/provenance.json", provenance))
        if route == "B" and not absence:
            manual.append("Route B 的 code_absence_check 为空：用 --code-absence 或手填查过代码的位置"
                          "（arXiv source / GitHub 搜索 / 作者主页 / 补充材料）")
    elif declared.get("mode") != route:
        manual.append(f"provenance.route.mode={declared.get('mode')!r} 与 official_code 推断的 Route {route} 冲突："
                      "先确认到底有没有官方代码，再改官方代码标记或 route（两侧不一致时 validate 会拒绝）")

    mapping = dict(args.paper_figure or {})
    for target in project.get("targets") or []:
        tid = target.get("id")
        if "paper_figure" in target:
            continue
        if tid in mapping:
            ids = [x.strip() for x in mapping[tid].split(",") if x.strip()]
            target["paper_figure"] = ids or None
            auto.append((f"targets[{tid}].paper_figure = {target['paper_figure']}", "spec/project.json", project))
        else:
            guess = figure_guess(root, target)
            hint = f"，可能是 {guess}" if guess else ""
            manual.append(f"target {tid!r} 缺 paper_figure：该计算在论文里有图就填图 id（如 'Fig2(a)'），"
                          f"确实无图才填 null{hint}；用 --paper-figure {tid}={guess or 'FigN(a)'} 写入")

    for ref in provenance.get("references") or []:
        if not isinstance(ref, dict) or ref.get("kind") != "digitized":
            continue
        name = ref.get("file")
        if not isinstance(name, str) or not (root / name).is_file():
            manual.append(f"digitized 参考 {name!r} 文件不存在：补真实数字化结果，不要留悬空引用")
            continue
        crop = audit_crop_path(root, name, project)
        if crop is None:
            manual.append(f"digitized 参考 {name} 无法定位源图：补 {Path(name).with_suffix('.meta.json')} 的 "
                          "\"image\" 字段，或在目标 visual 配置里声明 crop")
        elif not crop.with_suffix(".visual_audit.json").is_file():
            manual.append(f"缺 {crop.with_suffix('.visual_audit.json').relative_to(root)}："
                          f"跑 python3 scripts/vision.py audit . {crop.relative_to(root)} --pdf paper/<pdf> "
                          f"--page N --bbox \"x0,y0,x1,y1\" --subfigure \"FigN(x)\"，再人工复核")
    return auto, manual


def audit_crop_path(root, csv_name, project):
    meta = load(root, str(Path(csv_name).with_suffix(".meta.json"))) or {}
    crop = meta.get("image")
    if not isinstance(crop, str) or not crop:
        for target in project.get("targets") or []:
            checks = target.get("checks") or {}
            loss_config = (checks.get("loss") or {}).get("config")
            if not loss_config:
                continue
            gt = ((load(root, loss_config) or {}).get("gt") or {}).get("file")
            if gt != csv_name:
                continue
            visual = checks.get("visual") or {}
            if visual.get("enabled") and visual.get("config"):
                crop = (load(root, visual["config"]) or {}).get("crop")
    if not isinstance(crop, str) or not crop:
        return None
    path = Path(crop)
    return path if path.is_absolute() else Path(root) / path


# --------------------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    parser.add_argument("--apply", action="store_true", help="写回可机械推导的项（manual 项永不自动写）")
    parser.add_argument("--paper-figure", action="append", metavar="TID=Fig2(a),Fig2(b)",
                        help="为该目标声明论文图 id；重复给出多个目标")
    parser.add_argument("--code-absence", action="append", metavar="WHERE",
                        help="Route B 的代码检索记录，重复给出多个位置")
    args = parser.parse_args(argv)
    args.paper_figure = [(item.split("=", 1)[0].strip(), item.split("=", 1)[1])
                         for item in args.paper_figure or [] if "=" in item]

    auto, manual = scan(args.root, args)
    if not auto and not manual:
        print("[PASS] 工作区已是最新结构：无需迁移")
        return 0

    files, labels = {}, {}
    for label, name, doc in auto:
        files[name] = doc                 # one write per file, last state wins
        labels.setdefault(name, []).append(label)
    if args.apply:
        for name, doc in files.items():
            dump(Path(args.root) / name, doc)
            for label in labels[name]:
                print(f"[AUTO] {name}: {label}")
    else:
        for name, entries in labels.items():
            for label in entries:
                print(f"[WOULD] {name}: {label}")
    for note in manual:
        print(f"[EVIDENCE] {note}")

    if not args.apply:
        print("\n这是 dry run：确认后用 --apply 写回 [WOULD] 项。"
              "[EVIDENCE] 项不要问用户——自主轮自己跑代码/检索/审计后补 --paper-figure/--code-absence（拒绝编造）。")
    elif manual:
        print(f"\n已写回 {len(files)} 个文件（{sum(len(v) for v in labels.values())} 项）；"
              f"仍有 {len(manual)} 项要自主轮补证据（跑代码/检索/视觉审计），补齐前 validate.py 不会通过。")
    else:
        print(f"\n已写回 {len(files)} 个文件；迁移完成，重跑 python3 scripts/validate.py {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
