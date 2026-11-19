#!/usr/bin/env python3
"""Check declared reference use and recorded ordering, not truth or cognitive independence."""
import argparse
import ast
from datetime import datetime
from pathlib import Path
from common import artifact, finish, number, project, read_json, require, run, within

KINDS = {"paper", "supplement", "published_data", "author_material", "analytic", "database", "digitized", "official_comparison"}
PURPOSES = {"calibration", "validation", "implementation_comparison"}


def successful_run(root, record):
    manifest = read_json(artifact(root, record))
    require(manifest.get("returncode") == 0, "reference/comparison run must succeed")
    return manifest


def check_order(baseline, later):
    require(baseline.get("snapshot") and baseline.get("outputs"), "baseline needs code/config and output hashes")
    require(baseline.get("snapshot_unchanged") is True, "baseline snapshot changed during run")
    start, finish_time = datetime.fromisoformat(later["started"]), datetime.fromisoformat(baseline["finished"])
    require(start.tzinfo is not None and finish_time.tzinfo is not None, "run times need timezones")
    require(finish_time <= start, "comparison precedes baseline finish")


def check(root):
    doc = project(root)
    cfg = read_json(within(root, doc["independence"]))
    require(bool(cfg.get("declaration")) and isinstance(cfg.get("official_metadata_used"), list), "declaration and explicit metadata list required")
    refs = cfg.get("references")
    require(isinstance(refs, list) and refs, "reference provenance required")
    registered = {}
    for ref in refs:
        path = artifact(root, ref)
        require(path not in registered, f"duplicate reference: {path}")
        registered[path] = ref
        require(ref.get("kind") in KINDS, "invalid reference kind")
        for key in ("citation", "extraction", "version", "locator", "conditions", "uncertainty_basis"):
            require(isinstance(ref.get(key), str) and ref[key].strip(), f"reference.{key} required")
        number(ref.get("uncertainty"), "reference uncertainty", 0)
        purposes = ref.get("purposes")
        require(isinstance(purposes, list) and purposes and all(p in PURPOSES for p in purposes), "invalid reference purposes")
        require(isinstance(ref.get("used_for_tuning"), bool), "used_for_tuning must be explicit")
        if ref["used_for_tuning"]:
            require(bool(ref.get("reuse_disclosure")), "tuned reference needs reuse_disclosure")
        if ref["kind"] == "digitized":
            require(bool(ref.get("fallback_reason")), "digitized reference needs fallback_reason")
        if ref["kind"] == "official_comparison":
            require(doc["official_code"], "official output contradicts official_code=false")
            require(path.is_relative_to(within(root, "comparisons/official")), "official outputs must be under comparisons/official")
            manifest = successful_run(root, ref.get("run"))
            name = str(path.relative_to(Path(root).resolve()))
            require(manifest.get("outputs", {}).get(name) == ref["sha256"], "official run must bind reference output")
            if doc["reproduction_mode"] == "independent":
                check_order(successful_run(root, ref.get("baseline_run")), manifest)
    for t in doc["targets"]:
        loss = read_json(within(root, t["checks"]["loss"]["config"]))
        gt = within(root, loss["gt"]["file"])
        require(gt in registered, f"unregistered reference: {gt}")
        ref = registered[gt]
        subject = t["validation_subject"]
        purpose = "implementation_comparison" if subject == "author_implementation" else "validation"
        require(purpose in ref["purposes"], f"{t['id']}: reference lacks purpose {purpose}")
        if ref["kind"] == "official_comparison":
            require(subject == "author_implementation", "official rerun alone validates author implementation, not published paper result")
        if ref["kind"] == "digitized":
            require(t["checks"]["visual"]["enabled"], "digitized reference requires visual review")
        # 论文图复现硬性要求：数值计算在论文中有对应图时，必须复现该图并做左右并排对比。
        if t.get("paper_figure"):
            require(t["checks"]["visual"]["enabled"],
                    f"{t['id']}: paper_figure={t['paper_figure']} 是硬性要求 — 必须启用 visual 复现并排对比图")
            vcfg = read_json(within(root, t["checks"]["visual"]["config"]))
            for key in ("crop", "mine_image", "plot_metadata", "comparison_image"):
                require(bool(vcfg.get(key)),
                        f"{t['id']}: 论文图对比的 visual 配置必须含 {key}")
        if ref["used_for_tuning"]:
            print(f"[DISCLOSURE] {t['id']}: reference used for tuning; not held-out validation")
    files = list((Path(root) / "code").rglob("*.py"))
    require(files, "no implementation/runner")
    if doc["reproduction_mode"] == "independent":
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    require(not {"refcode", "official", "01_official_code"}.intersection(name.split(".")), f"official import in independent mode: {path}")
    comparisons = cfg.get("comparisons", [])
    require(isinstance(comparisons, list), "comparisons must be a list")
    require(doc["official_code"] or not comparisons, "official comparisons contradict official_code=false")
    for comparison in comparisons:
        check_order(successful_run(root, comparison["baseline_run"]), successful_run(root, comparison["comparison_run"]))
    return finish("PASS", "reference use/recorded ordering consistent; no proof of truth, held-out independence or independent authorship")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
