#!/usr/bin/env python3
"""Create a staged reproduction workspace; never overwrite existing files."""
import argparse
import json
from pathlib import Path


def create(root, title, level, official_code, reproduction_mode="paper"):
    root = Path(root).expanduser().resolve()
    for name in ("paper/refcode", "spec", "code/lib", "data/mine", "data/ground_truth",
                 "figures/mine", "figures/compare", "comparisons/official", "runs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    project = {
        "schema_version": 1, "title": title, "source": None, "level": level,
        "official_code": official_code, "reproduction_mode": reproduction_mode, "stage": "planning", "domain": None,
        "environment": "spec/environment.json", "independence": "spec/provenance.json",
        "targets": [{"id": "fig1", "type": "curve", "mode": "quantitative", "validation_subject": "paper_result", "criterion": None, "paper_figure": None,
                     "checks": {"loss": {"enabled": True, "config": "spec/fig1.loss.json"},
                                "visual": {"enabled": False, "reason": "尚未选择图像参考；若使用论文图必须启用"},
                                "effect": {"enabled": False, "reason": "尚未判定效应先验；全文扫描前复核"}}}]
    }
    loss = {
        "type": "curve", "domain": None, "grid_points": 201, "max_gap": None,
        "min_coverage": 1.0, "scale": None, "reference_uncertainty": None,
        "threshold_basis": None, "metrics": {"rms_norm": None},
        "mine": {"file": "data/mine/fig1.npz", "keys": ["x", "y"], "roles": {"x": "x", "y": "y"}, "units": {"x": None, "y": None}},
        "gt": {"file": "data/ground_truth/fig1.csv", "keys": ["x", "y"], "roles": {"x": "x", "y": "y"}, "units": {"x": None, "y": None}}
    }
    files = {
        "spec/project.json": project,
        "spec/fig1.loss.json": loss,
        "spec/calibration.json": {"not_applicable": {}, "assertions": []},
        "spec/environment.json": {"expected": {"python": None, "executable": None, "packages": {}, "solver": None, "dtypes": {}}, "runtime": {"file": "data/mine/runtime.json", "sha256": None}, "run": {"file": "runs/ID/manifest.json", "sha256": None}},
        "spec/provenance.json": {"declaration": None,
                                  "route": {"mode": "A" if official_code else "B", "basis": None, "code_absence_check": []},
                                  "official_metadata_used": [], "references": [], "comparisons": []},
        "spec/hypotheses.json": {"empty_reason": "尚未开展归因实验", "items": []},
        "spec/decisions.json": {"empty_reason": "尚未开始自主复现轮", "items": []},
        "spec/README.md": (Path(__file__).resolve().parent.parent / "references/spec_template.md").read_text(encoding="utf-8"),
        "REPORT.md": (Path(__file__).resolve().parent.parent / "references/report_template.md").read_text(encoding="utf-8"),
        "spec/domain_profile.md": (Path(__file__).resolve().parent.parent / "references/domains/_profile_template.md").read_text(encoding="utf-8"),
        "LOG.md": (Path(__file__).resolve().parent.parent / "references/log_template.md").read_text(encoding="utf-8"),
        "README.md": f"# {title}\n\n## 任务与验证等级\n\n见 spec/project.json。\n\n## 复现路线\n\n"
                     + ("Route A：有官方代码，可作建模期指导教练与（可选）对拍参考。\n"
                        if official_code else
                        "Route B：无官方代码，以论文正文/表格/补充数据为真值，解析极限与守恒关系替代官方实现作预言机。\n")
                     + "\n## 环境与运行方法\n\n## 参数与公式出处\n\n## 逐目标结果\n\n分别报告定量符合 / 定性一致 / 未达标 / 未完成及指标，不以脚本 PASS 代替科学结论。\n\n## 独立性与局限\n"
    }
    for name, content in files.items():
        path = root / name
        if path.exists():
            print(f"[SKIP] {path}")
            continue
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        path.write_text(content, encoding="utf-8")
        print(f"[CREATED] {path}")
    print("Fill planning Spec and JSON nulls; see references/protocol.md. Existing workspaces require explicit migration.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--title", required=True)
    parser.add_argument("--level", choices=("quick", "standard", "strict"), default="standard")
    parser.add_argument("--official-code", action="store_true")
    parser.add_argument("--reproduction-mode", choices=("paper", "independent", "author"), default="paper")
    args = parser.parse_args()
    if args.reproduction_mode == "author" and not args.official_code:
        parser.error("author mode requires --official-code")
    create(args.root, args.title, args.level, args.official_code, args.reproduction_mode)
