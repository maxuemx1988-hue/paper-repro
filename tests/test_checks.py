import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import Incomplete, sha256
from check_calibration import check_one
from check_effect import evaluate as effect
from check_loss import evaluate as loss
from check_physics_code import check_directory
from check_visual_crop import audit_crop
from check_figure_side_by_side import make_side_by_side
from check_figure_validity import check as check_figure
from scaffold import create
from check_hypotheses import check as check_hypotheses
from check_loss import load
from check_independence import check as check_provenance
from check_fix_log import check as check_fix_log, current_code_digest


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = io.StringIO()
        self.silent = contextlib.redirect_stdout(self.output)
        self.silent.__enter__()
        self.addCleanup(self.silent.__exit__, None, None, None)

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def write_report(self, mode, kind):
        """A final-stage REPORT.md matching what the fixture actually scored."""
        text = "\n".join([
            "# 复现报告", "",
            "## 0. 结论摘要", f"fixture 在 {mode} 模式下对 fig1 得到定量符合。", "",
            "## 1. 逐目标结果",
            "| 目标 | 判定 | 指标 | 说明 | 证据 |", "|---|---|---|---|---|",
            "| fig1 | 定量符合 | rms_norm=0.0 | synthetic identity fixture | reports/fig1.json |", "",
            "## 2. 门禁与证据",
            "check_spec.py / check_loss.py / check_calibration.py 均通过；绑定 runs/test/manifest.json。", "",
            "## 3. 局限与未完成项",
            "- synthetic fixture，无物理含义；official_code=false 时走 Route B（无官方代码，以论文真值为预言机）。", "",
            "## 4. 复现方法", "```bash", "python3 code/model.py", "```", "",
            "## 5. 参考来源与调参披露",
            f"reproduction_mode={mode}；kind={kind}；无未披露的调参。", ""])
        (self.root / "REPORT.md").write_text(text, encoding="utf-8")

    def reference(self, file, kind="paper", **extra):
        return dict(file=file, sha256=sha256(self.root / file), kind=kind,
                    citation="fixture DOI", extraction="fixture transcription", version="v1",
                    locator="Table 1", conditions="fixture parameters", uncertainty=0.01,
                    uncertainty_basis="fixture rounding", purposes=["validation"], used_for_tuning=False, **extra)

    def provenance_fixture(self, kind="paper", mode="paper"):
        create(self.root, "reference fixture", "standard", True, mode)
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture", domain="generic")
        doc["targets"][0]["criterion"] = "fixture comparison"
        self.write("spec/project.json", doc)
        (self.root / "code/runner.py").write_text("import official.model\n", encoding="utf-8")
        file = "comparisons/official/ref.csv" if kind == "official_comparison" else "data/ground_truth/ref.csv"
        (self.root / file).write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
        loss_cfg = json.loads((self.root / "spec/fig1.loss.json").read_text())
        loss_cfg["gt"]["file"] = file
        self.write("spec/fig1.loss.json", loss_cfg)
        ref = self.reference(file, kind)
        if kind == "official_comparison":
            manifest = self.write("runs/official/manifest.json", dict(returncode=0, started="2026-01-02T00:00:00+00:00", outputs={file:ref["sha256"]}))
            ref["run"] = dict(file="runs/official/manifest.json", sha256=sha256(manifest))
            ref["purposes"] = ["implementation_comparison"]
            doc["targets"][0]["validation_subject"] = "author_implementation"
            self.write("spec/project.json", doc)
        cfg = dict(declaration="fixture provenance", official_metadata_used=[], references=[ref], comparisons=[])
        self.write("spec/provenance.json", cfg)
        return doc, cfg

    def test_text_reference_without_screenshot_and_tuning_disclosure(self):
        _, cfg = self.provenance_fixture()
        self.assertEqual(check_provenance(self.root), 0)
        ref = cfg["references"][0]
        ref["used_for_tuning"] = True
        self.write("spec/provenance.json", cfg)
        with self.assertRaises(Incomplete):
            check_provenance(self.root)
        ref["reuse_disclosure"] = "fit quality only, not held-out validation"
        self.write("spec/provenance.json", cfg)
        self.assertEqual(check_provenance(self.root), 0)
        ref["purposes"] = ["calibration"]
        self.write("spec/provenance.json", cfg)
        with self.assertRaises(Incomplete):
            check_provenance(self.root)

    def test_official_reference_allowed_but_not_paper_truth(self):
        doc, cfg = self.provenance_fixture("official_comparison", "author")
        self.assertEqual(check_provenance(self.root), 0)
        doc["targets"][0]["validation_subject"] = "paper_result"
        cfg["references"][0]["purposes"].append("validation")
        self.write("spec/project.json", doc)
        self.write("spec/provenance.json", cfg)
        with self.assertRaises(Incomplete):
            check_provenance(self.root)
        doc["targets"][0]["validation_subject"] = "author_implementation"
        self.write("spec/project.json", doc)
        manifest = self.write("runs/official/manifest.json", dict(returncode=0, outputs={}))
        cfg["references"][0]["run"]["sha256"] = sha256(manifest)
        self.write("spec/provenance.json", cfg)
        with self.assertRaises(Incomplete):
            check_provenance(self.root)

    def test_independent_official_reference_requires_prior_baseline(self):
        _, cfg = self.provenance_fixture("official_comparison", "independent")
        (self.root / "code/runner.py").write_text("# independently implemented fixture\n", encoding="utf-8")
        with self.assertRaises(Incomplete):
            check_provenance(self.root)
        baseline = dict(returncode=0, snapshot={"code/runner.py":"fixture"}, outputs={"baseline":"fixture"}, snapshot_unchanged=True, finished="2026-01-01T00:00:00+00:00")
        path = self.write("runs/baseline/manifest.json", baseline)
        cfg["references"][0]["baseline_run"] = dict(file="runs/baseline/manifest.json", sha256=sha256(path))
        self.write("spec/provenance.json", cfg)
        self.assertEqual(check_provenance(self.root), 0)
        (self.root / "code/runner.py").write_text("import official.model\n", encoding="utf-8")
        with self.assertRaises(Incomplete):
            check_provenance(self.root)
        (self.root / "code/runner.py").write_text("# independent fixture\n", encoding="utf-8")
        baseline["finished"] = "2026-01-03T00:00:00+00:00"
        path = self.write("runs/baseline/manifest.json", baseline)
        cfg["references"][0]["baseline_run"]["sha256"] = sha256(path)
        self.write("spec/provenance.json", cfg)
        with self.assertRaises(Incomplete):
            check_provenance(self.root)

    def test_digitized_reference_needs_fallback_and_visual(self):
        doc, cfg = self.provenance_fixture("digitized")
        with self.assertRaises(Incomplete):
            check_provenance(self.root)
        cfg["references"][0]["fallback_reason"] = "no released numerical data found"
        self.write("spec/provenance.json", cfg)
        with self.assertRaises(Incomplete):
            check_provenance(self.root)
        doc["targets"][0]["checks"]["visual"] = dict(enabled=True, config="spec/visual.json")
        self.write("spec/project.json", doc)
        self.assertEqual(check_provenance(self.root), 0)

    def assertion(self, **kwargs):
        return dict(id="C1", category="limit", desc="test", kind="range", file="cal.npz", key="y", min=0, max=2, **kwargs)

    def protocol(self):
        return dict(type="curve", domain=[0, 1], grid_points=101, max_gap=0.11,
                    min_coverage=1, scale=1, reference_uncertainty=0.01,
                    threshold_basis="independent uncertainty estimate", metrics={"rms_norm": 0.02, "peak": {"kind": "max", "window": [0.2, 0.8], "x_tol": 0.01, "y_tol": 0.01}})

    def curve(self):
        x = np.linspace(0, 1, 11)
        return {"x": x, "y": np.sin(x * np.pi)}

    def test_calibration_empty_nan_and_inf_rejected(self):
        for y in ([], [np.nan], [np.inf]):
            np.savez(self.root / "cal.npz", y=y)
            with self.assertRaises(Incomplete):
                check_one(self.assertion(), self.root)

    def test_calibration_range_and_bounds(self):
        np.savez(self.root / "cal.npz", y=[1, 1.5])
        self.assertTrue(check_one(self.assertion(), self.root))
        cfg = self.assertion()
        cfg["max"] = 1.1
        self.assertFalse(check_one(cfg, self.root))
        del cfg["max"]
        with self.assertRaises(Incomplete):
            check_one(cfg, self.root)

    def test_json_calibration_and_index(self):
        self.write("cal.json", {"T": [1, 2]})
        cfg = dict(id="C1", category="limit", desc="test", kind="value", file="cal.json", key="T", index=0, expect=1, rtol=1e-6)
        self.assertTrue(check_one(cfg, self.root))
        cfg["index"] = -1
        with self.assertRaises(Incomplete):
            check_one(cfg, self.root)

    def test_effect_zero_and_expected_interval(self):
        cfg = dict(expected_span=1, uncertainty=0.01, ratio_bounds=[0.8, 1.2])
        self.assertFalse(effect([0, 0, 0], cfg))
        self.assertTrue(effect([0, 0.5, 1], cfg))
        self.assertFalse(effect([0, 1, 2], cfg))
        cfg["expected_span"] = 0
        self.assertTrue(effect([0, 0, 0], cfg))

    def test_identical_curve_passes(self):
        data = self.curve()
        result = loss(data, data, self.protocol())
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["metrics"]["coverage"], 1)

    def test_partial_domain_and_gaps_rejected(self):
        data = self.curve()
        for indices in (slice(0, 4), [0, 1, 9, 10]):
            sparse = {k: v[indices] for k, v in data.items()}
            with self.assertRaises(Incomplete):
                loss(sparse, data, self.protocol())

    def test_duplicates_nonfinite_rejected(self):
        for bad_x in ([0, 0, 1], [0, np.nan, 1]):
            with self.assertRaises(Incomplete):
                loss({"x": np.array(bad_x), "y": np.ones(3)}, self.curve(), self.protocol())

    def test_peak_actually_fails(self):
        data = self.curve()
        cfg = self.protocol()
        cfg["metrics"] = {"rms_norm": 2, "peak": {"kind": "max", "window": [0.1, 0.9], "x_tol": 0.01, "y_tol": 0.01}}
        shifted = {"x": data["x"], "y": np.sin((data["x"] - 0.2) * np.pi)}
        self.assertIn("peak", loss(shifted, data, cfg)["failed"])

    def test_multiple_peak_windows(self):
        data = self.curve()
        cfg = self.protocol()
        cfg["metrics"] = {"rms_norm": 2, "peak": [
            {"kind": "max", "window": [0.1, 0.6], "x_tol": 0.01, "y_tol": 0.01},
            {"kind": "max", "window": [0.6, 0.9], "x_tol": 0.01, "y_tol": 0.01}]}
        result = loss(data, data, cfg)
        self.assertEqual(result["failed"], [])
        self.assertIn("peak1_dx", result["metrics"])
        self.assertIn("peak2_dy", result["metrics"])
        bumped = dict(x=data["x"], y=data["y"] + 0.5 * np.exp(-((data["x"] - 0.75) / 0.05) ** 2))
        failed = loss(bumped, data, cfg)["failed"]
        self.assertIn("peak2", failed)
        self.assertNotIn("peak1", failed)

    def test_feature_resolution_skips_map_targets(self):
        """A map/heatmap target has no 1-D sampling axis: skip instead of KeyError."""
        import check_feature_resolution as fr
        create(self.root, "map fixture", "standard", True)
        doc = json.loads((self.root / "spec/project.json").read_text(encoding="utf-8"))
        doc.update(source="fixture DOI", domain="generic", stage="final")
        doc["targets"][0]["criterion"] = "fixture criterion"
        (self.root / "spec/project.json").write_text(json.dumps(doc), encoding="utf-8")
        cfg = json.loads((self.root / "spec/fig1.loss.json").read_text(encoding="utf-8"))
        cfg["type"] = "map"
        cfg["mine"] = {"file": "data/mine/fig1.npz", "keys": ["y", "coord"],
                       "roles": {"y": "y", "coordinates": "coord"}, "units": {"y": "1", "coord": "1"}}
        cfg["gt"] = dict(cfg["mine"], file="data/ground_truth/fig1.npz")
        (self.root / "spec/fig1.loss.json").write_text(json.dumps(cfg), encoding="utf-8")
        for name in ("data/mine/fig1.npz", "data/ground_truth/fig1.npz"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(path, y=np.ones((2, 2)), coord=np.arange(8).reshape(4, 2),
                     units=json.dumps({"y": "1", "coord": "1"}))
        self.assertEqual(fr.check(self.root, "fig1"), 0)

    def test_feature_resolution_gate(self):
        import check_feature_resolution as fr
        x = np.linspace(0, 1, 200)
        y = np.exp(-((x - 0.5) / 0.01) ** 2)
        ext = fr.salient_extrema(x, y)
        self.assertTrue(any(k == "max" for k, i in ext))
        i = next(i for k, i in ext if k == "max")
        w = fr.half_width(x, y, i, "max")
        self.assertLess(w / 3, 0.2)

    def test_amplitude_upper_bound(self):
        data = self.curve()
        cfg = self.protocol()
        cfg["metrics"] = {"min_r": 0.9, "amp_ratio": [0.8, 1.2], "peak": {"kind": "max", "window": [0.2, 0.8], "x_tol": 0.01, "y_tol": 0.01}}
        self.assertIn("amp_ratio", loss({"x": data["x"], "y": data["y"] * 5}, data, cfg, "qualitative")["failed"])

    def test_scalar_and_map_coordinates(self):
        cfg = self.protocol()
        cfg["type"] = "scalar"
        cfg["metrics"] = {"rms_norm": 0.02}
        self.assertEqual(loss({"y": np.array([1])}, {"y": np.array([1])}, cfg)["failed"], [])
        cfg["type"] = "map"
        data = {"y": np.ones((2, 2)), "coordinates": np.arange(8).reshape(4, 2)}
        self.assertFalse(loss(data, data, cfg)["failed"])
        changed = copy.deepcopy(data)
        changed["coordinates"][0, 0] = 99
        with self.assertRaises(Incomplete):
            loss(changed, data, cfg)

    def test_missing_code_incomplete_and_recursive_syntax(self):
        with self.assertRaises(Incomplete):
            check_directory(self.root)
        path = self.root / "code/lib/model.py"
        path.parent.mkdir(parents=True)
        path.write_text("def bad(:", encoding="utf-8")
        self.assertEqual(check_directory(self.root), 1)
        path.write_text("import numpy as np\nR = np.exp(-1)\n", encoding="utf-8")
        self.assertEqual(check_directory(self.root), 0)

    def test_visual_hash_and_axis_binding(self):
        crop = self.root / "crop.png"
        Image.new("RGB", (100, 100), "white").save(crop)
        pdf = self.root / "paper.pdf"
        pdf.write_bytes(b"test provenance only")
        axis = dict(label="x", unit="1", limits=[0, 1], scale="linear")
        meta = dict(image=dict(file="crop.png", sha256=sha256(crop)), pdf=dict(file="paper.pdf", sha256=sha256(pdf)),
                    page=1, bbox_pdf=[0, 0, 10, 10], subfigure_id="a", xaxis=axis, yaxis=axis,
                    review=dict(method="human", reviewer="tester", time="2026-01-01", notes="review fixture"))
        self.write("crop.visual_audit.json", meta)
        self.assertEqual(audit_crop(self.root, "crop.png")["subfigure_id"], "a")
        with self.assertRaises(Incomplete):
            audit_crop(self.root, "crop.png", expected_x="wrong")
        Image.new("RGB", (100, 100), "black").save(crop)
        with self.assertRaises(Incomplete):
            audit_crop(self.root, "crop.png")

    def test_scaffold_never_overwrites_and_incomplete(self):
        create(self.root, "test", "quick", False)
        readme = self.root / "README.md"
        readme.write_text("preserved", encoding="utf-8")
        create(self.root, "other", "strict", True)
        self.assertEqual(readme.read_text(), "preserved")
        result = subprocess.run([sys.executable, str(SCRIPTS / "check_spec.py"), str(self.root)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)

    def test_record_run_success_and_failure(self):
        (self.root / "code").mkdir()
        (self.root / "spec").mkdir()
        for code in (0, 1):
            command = [sys.executable, str(SCRIPTS / "record_run.py"), str(self.root), "--command", sys.executable, "-c", f"raise SystemExit({code})"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, code, result.stderr)
        records = list((self.root / "runs").glob("*/manifest.json"))
        self.assertEqual(len(records), 2)
        self.assertEqual({json.loads(p.read_text())["returncode"] for p in records}, {0, 1})

    def test_visual_workflow_accepts_negative_data_and_checks_axes(self):
        create(self.root, "visual fixture", "quick", False)
        project = json.loads((self.root / "spec/project.json").read_text())
        project.update(source="fixture", domain="generic")
        project["targets"][0]["criterion"] = "signed signal"
        project["targets"][0]["checks"]["visual"] = {"enabled":True, "config":"spec/visual.json"}
        self.write("spec/project.json", project)
        crop = self.root / "data/ground_truth/crop.png"
        mine = self.root / "figures/mine/fig1.png"
        for p in (crop, mine):
            Image.new("RGB", (200, 200), "white").save(p)
        pdf = self.root / "paper/paper.pdf"
        pdf.write_bytes(b"provenance fixture")
        xa = dict(label="x", unit="1", limits=[0, 1], scale="linear")
        ya = dict(label="signal", unit="1", limits=[-2, 0], scale="linear")
        review = dict(method="human", reviewer="fixture", time="2026-01-01", notes="synthetic review")
        self.write("data/ground_truth/crop.visual_audit.json", dict(image=dict(file="data/ground_truth/crop.png", sha256=sha256(crop)), pdf=dict(file="paper/paper.pdf", sha256=sha256(pdf)), page=1, bbox_pdf=[0, 0, 10, 10], subfigure_id="a", xaxis=xa, yaxis=ya, review=review))
        data = self.root / "data/mine/fig1.npz"
        np.savez(data, x=[0, 0.5, 1], y=[-1, -0.5, -1], units=json.dumps({"x":"1", "y":"1"}))
        metadata = dict(image=dict(file="figures/mine/fig1.png", sha256=sha256(mine)), data=dict(file="data/mine/fig1.npz", sha256=sha256(data)), xaxis=xa, yaxis=ya, xkey="x", ykey="y", review=review)
        self.write("figures/mine/fig1.plot.json", metadata)
        self.write("spec/visual.json", dict(crop="data/ground_truth/crop.png", mine_image="figures/mine/fig1.png", plot_metadata="figures/mine/fig1.plot.json", comparison_image="figures/compare/fig1.png", min_visible=1))
        self.assertEqual(make_side_by_side(self.root, "fig1"), 0)
        self.assertEqual(check_figure(self.root, "fig1"), 0)
        metadata["yaxis"] = {**ya, "limits":[0, 2]}
        self.write("figures/mine/fig1.plot.json", metadata)
        with self.assertRaises(Incomplete):
            check_figure(self.root, "fig1")

    def test_launch_failure_and_timeout_are_recorded(self):
        for command, timeout, expected in ((["/nonexistent/paper-repro-command"], "5", 127), ([sys.executable, "-c", "import time; time.sleep(5)"], "0.1", 124)):
            before = set((self.root / "runs").glob("*/manifest.json"))
            result = subprocess.run([sys.executable, str(SCRIPTS / "record_run.py"), str(self.root), "--timeout", timeout, "--command", *command], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            record = (set((self.root / "runs").glob("*/manifest.json")) - before).pop()
            self.assertEqual(json.loads(record.read_text())["returncode"], expected)

    def test_exact_hypothesis_retraction(self):
        evidence = self.write("data/evidence.json", {"value": 0})
        record = self.write("runs/test/manifest.json", {"returncode": 0, "outputs": {"data/evidence.json": sha256(evidence)}})
        item = dict(id="H1", claim="cause", experiment="ablation", prediction="value > 1", status="falsified", premise="baseline A", retraction="observed zero",
                    run=dict(file="runs/test/manifest.json", sha256=sha256(record)),
                    evidence=[dict(file="data/evidence.json", sha256=sha256(evidence), metric="value", result=0)])
        self.write("spec/hypotheses.json", {"items": [item]})
        (self.root / "LOG.md").write_text("[RETRACT:H2] unrelated", encoding="utf-8")
        with self.assertRaises(Incomplete):
            check_hypotheses(self.root)
        (self.root / "LOG.md").write_text("[RETRACT:H1] cause rejected", encoding="utf-8")
        self.assertEqual(check_hypotheses(self.root), 0)

    def test_digitization_gap_and_unit_guard(self):
        path = self.root / "curve.csv"
        path.write_text("x,y\n0,0\n0.5,1\n1,0\n", encoding="utf-8")
        self.write("curve.meta.json", {"units": {"x": "1", "y": "1"}, "has_gaps": True, "excluded_x": [0.4]})
        spec = dict(file="curve.csv", units={"x": "1", "y": "1"}, keys=["x", "y"], roles={"x":"x", "y":"y"})
        with self.assertRaises(Incomplete):
            load(self.root, spec)
        spec["valid_domain"] = [0, 1]
        with self.assertRaises(Incomplete):
            load(self.root, spec)
        spec["valid_domain"] = [0.5, 1]
        self.assertIn("x", load(self.root, spec)[0])
        spec["units"]["y"] = "V"
        with self.assertRaises(Incomplete):
            load(self.root, spec)


    def fix_log_space(self):
        """Minimal workspace: code + a passing run whose snapshot is the current code."""
        (self.root / "code").mkdir(parents=True, exist_ok=True)
        (self.root / "code/model.py").write_text("CODE_CONST = 1\n", encoding="utf-8")
        self.manifest("runs/ok/manifest.json", 0, sha256(self.root / "code/model.py"))
        return current_code_digest(self.root)

    def manifest(self, name, returncode, code_sha):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"returncode": returncode,
                                    "started": "2026-01-01T00:00:00+00:00",
                                    "snapshot": {"code/model.py": code_sha}}), encoding="utf-8")
        return path

    def test_fix_log_requires_entries_or_declaration(self):
        self.fix_log_space()
        (self.root / "LOG.md").write_text("# 迭代日志\n", encoding="utf-8")
        with self.assertRaises(Incomplete):
            check_fix_log(self.root)

    def test_fix_log_accepts_none_declaration_with_clean_history(self):
        self.fix_log_space()
        (self.root / "LOG.md").write_text(
            "# 迭代日志\n\n[FIX:NONE] 全部实现一次成型，runs/ 里没有失败运行可登记\n", encoding="utf-8")
        self.assertEqual(check_fix_log(self.root), 0)

    def test_fix_log_rejects_none_declaration_when_a_run_failed(self):
        digest = self.fix_log_space()
        self.manifest("runs/bad/manifest.json", 1, digest)
        (self.root / "LOG.md").write_text(
            "# 迭代日志\n\n[FIX:NONE] 实现一次成型，没有失败运行需要登记\n", encoding="utf-8")
        with self.assertRaises(Incomplete) as caught:
            check_fix_log(self.root)
        self.assertIn("runs/bad/manifest.json", str(caught.exception))

    def test_fix_log_rejects_none_declaration_without_recent_passing_run(self):
        (self.root / "code").mkdir(parents=True, exist_ok=True)
        (self.root / "code/model.py").write_text("CODE_CONST = 2\n", encoding="utf-8")
        self.manifest("runs/stale/manifest.json", 0, "stale")
        (self.root / "LOG.md").write_text(
            "# 迭代日志\n\n[FIX:NONE] 没有失败运行需要登记\n", encoding="utf-8")
        with self.assertRaises(Incomplete) as caught:
            check_fix_log(self.root)
        self.assertIn("passing recorded run", str(caught.exception))

    def test_final_workspace_end_to_end(self):
        create(self.root, "fixture", "standard", False)
        cfg = json.loads((self.root / "spec/project.json").read_text())
        cfg.update(source="test DOI", domain="generic", stage="final")
        cfg["targets"][0]["criterion"] = "identity fixture"
        self.write("spec/project.json", cfg)
        (self.root / "spec/README.md").write_text("\n".join(f"## {i} field\nfixture" for i in "①②③④⑤⑥⑦"), encoding="utf-8")
        (self.root / "spec/domain_profile.md").write_text(
            "| 项 | 值 |\n|---|---|\n| pack | generic |\n| 缺口 | no reusable pack for this fixture |\n| 失效条件 | a reusable pack covers this fixture |\n\n"
            "| pack 段 | 状态 | 本文实例 | 定位／理由 |\n|---|---|---|---|\n"
            + "".join(f"| §{i} | 不适用 | fixture | synthetic fixture, no domain knowledge |\n" for i in range(8))
            + "\n| 约定 | 本文取值 | 定位／状态 |\n|---|---|---|\n"
            + "| fixture const | 1 | code/model.py::CODE_CONST |\n",
            encoding="utf-8")
        (self.root / "code/model.py").write_text("# synthetic regression fixture, not physics\nCODE_CONST = 1\n", encoding="utf-8")
        x = np.linspace(0, 1, 11)
        data = self.root / "data/mine/fig1.npz"
        np.savez(data, x=x, y=x, units=json.dumps({"x":"1", "y":"1"}))
        gt = self.root / "data/ground_truth/fig1.csv"
        np.savetxt(gt, np.column_stack([x, x]), delimiter=",", header="x,y", comments="")
        self.write("data/ground_truth/fig1.meta.json", {"units": {"x":"1", "y":"1"}})
        protocol = self.protocol()
        for name, file in (("mine", "data/mine/fig1.npz"), ("gt", "data/ground_truth/fig1.csv")):
            protocol[name] = dict(file=file, keys=["x", "y"], roles={"x":"x", "y":"y"}, units={"x":"1", "y":"1"})
        self.write("spec/fig1.loss.json", protocol)
        assertion = dict(id="C1", category="limit", desc="fixture identity", kind="value", file="data/mine/fig1.npz", key="y", index=10, expect=1, atol=1e-10)
        self.write("spec/calibration.json", {"assertions":[assertion], "not_applicable":{"invariant":"fixture", "paper":"fixture"}})
        expected = dict(python="3.test", executable="/fixture/python", packages={"numpy":"fixture"}, solver="fixture.identity", dtypes={"x":"float64", "y":"float64"})
        runtime = self.write("data/mine/runtime.json", {**expected, "data":{"file":"data/mine/fig1.npz", "sha256":sha256(data)}})
        manifest = self.write("runs/test/manifest.json", {"returncode":0, "started":"2026-01-01T00:00:00+00:00", "snapshot":{"code/model.py":sha256(self.root / "code/model.py")}, "outputs":{"data/mine/fig1.npz":sha256(data), "data/mine/runtime.json":sha256(runtime)}})
        self.write("spec/environment.json", {"expected":expected, "runtime":{"file":"data/mine/runtime.json", "sha256":sha256(runtime)}, "run":{"file":"runs/test/manifest.json", "sha256":sha256(manifest)}})
        (self.root / "LOG.md").write_text("# 迭代日志\n\n| 时间 | ID | 症状 | 根因 | 改动 | 证据 | 结果 |\n|---|---|---|---|---|---|---|\n| 2026-01-01 | [FIX:F1] | synthetic fixture | identity | add model | run=runs/test/manifest.json | PASS |\n", encoding="utf-8")

        self.write("spec/provenance.json", {"declaration":"synthetic fixture, not physics", "route": {"mode":"B", "basis":"fixture has no official code", "code_absence_check":["arXiv","GitHub","author page"]}, "official_metadata_used":[], "references":[self.reference("data/ground_truth/fig1.csv", "analytic")], "comparisons":[]})
        self.write_report("paper", "analytic")
        result = subprocess.run([sys.executable, str(SCRIPTS / "validate.py"), str(self.root)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Official outputs are valid numerical references in an explicitly scoped target.
        official = self.root / "comparisons/official/fig1.npz"
        official.write_bytes(data.read_bytes())
        official_run = self.write("runs/official/manifest.json", {"returncode":0, "outputs":{"comparisons/official/fig1.npz":sha256(official)}})
        cfg.update(official_code=True, reproduction_mode="author")
        cfg["targets"][0]["validation_subject"] = "author_implementation"
        self.write("spec/project.json", cfg)
        protocol["gt"]["file"] = "comparisons/official/fig1.npz"
        self.write("spec/fig1.loss.json", protocol)
        ref = self.reference("comparisons/official/fig1.npz", "official_comparison", run=dict(file="runs/official/manifest.json", sha256=sha256(official_run)))
        ref["purposes"] = ["implementation_comparison"]
        self.write("spec/provenance.json", dict(declaration="synthetic author-run fixture", route=dict(mode="A", basis="author code shipped with the paper", code_absence_check=[]), official_metadata_used=[], references=[ref], comparisons=[]))
        self.write_report("author", "official_comparison")
        result = subprocess.run([sys.executable, str(SCRIPTS / "validate.py"), str(self.root)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cfg_env = json.loads((self.root / "spec/environment.json").read_text())
        cfg_env["expected"]["dtypes"]["y"] = "float32"
        self.write("spec/environment.json", cfg_env)
        result = subprocess.run([sys.executable, str(SCRIPTS / "check_env.py"), str(self.root)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_selfcheck_help_does_not_recurse(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "selfcheck.py"), "--help"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)

    def test_domain_profile_gate(self):
        pack = SCRIPTS.parent / "references/domains/quantum-transport.md"
        digest = sha256(pack)
        create(self.root, "profile fixture", "standard", False)
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture", domain="quantum-transport")
        doc["targets"][0]["criterion"] = "fixture"
        self.write("spec/project.json", doc)

        def run_profile():
            return subprocess.run([sys.executable, str(SCRIPTS / "check_domain_profile.py"), str(self.root)],
                                  capture_output=True, text=True, timeout=10)

        # scaffolded template is structurally present but unfilled
        self.assertTrue((self.root / "spec/domain_profile.md").is_file())
        self.assertEqual(run_profile().returncode, 2)

        rows = [("§0", "偏离", "x", "paper p.2"), ("§1", "采用", "J=(e2/h)T V", "paper Eq.2"),
                ("§2", "扩展", "x", "supp S2"), ("§3", "扩展", "x", "supp S7"),
                ("§4", "采用", "paper figures", "p.3"), ("§5", "扩展", "x", "supp S5"),
                ("§6", "扩展", "x", "derived"), ("§7", "采用", "scipy.linalg.solve", "protocol")]
        good = "# profile\n\n## 0. 绑定\n\n| 项 | 值 |\n|---|---|\n"
        good += f"| pack | quantum-transport |\n| pack_sha256 | {digest} |\n| 失效条件 | pack hash changes |\n"
        good += "\n## 1. 映射表\n\n| pack 段 | 状态 | 本文实例 | 定位／理由 |\n|---|---|---|---|\n"
        good += "".join(f"| {a} | {b} | {c} | {d} |\n" for a, b, c, d in rows)
        path = self.root / "spec/domain_profile.md"

        def put(text):
            path.write_text(text, encoding="utf-8")
            return run_profile()

        self.assertEqual(put(good).returncode, 0)
        self.assertEqual(put(good.replace(digest, "0" * 64)).returncode, 2, "stale pack hash must block")
        self.assertEqual(put(good.replace(f"| {digest} |", "|  |")).returncode, 2, "unpinned pack must block")
        self.assertEqual(put(good.replace("| §3 | 扩展 | x | supp S7 |\n", "")).returncode, 2, "missing section must block")
        self.assertEqual(put(good.replace("| §1 | 采用 | J=(e2/h)T V |", "| §1 | 采用 |  |")).returncode, 2,
                         "adopted row needs an instance value")
        self.assertEqual(put(good.replace("| §2 | 扩展 | x | supp S2 |", "| §2 | 扩展 | x |  |")).returncode, 2,
                         "extended row needs a locator")
        self.assertEqual(put(good.replace("| §5 | 扩展 |", "| §5 | 随便 |")).returncode, 2, "unknown status must block")
        promoted = good + "\n| ID | 候选条目 | 回流向 | 状态 |\n|---|---|---|---|\n| P1 | 条目 | quantum-transport §8 | 已验收 |\n"
        self.assertEqual(put(promoted).returncode, 2, "promotion without evidence must block")
        self.assertEqual(put(promoted.replace("| 已验收 |", "| 待验证 |")).returncode, 0)

    def test_profile_anchor_and_official_smoke_gates(self):
        create(self.root, "anchor fixture", "standard", False)
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture", domain="generic")
        doc["targets"][0]["criterion"] = "fixture"
        self.write("spec/project.json", doc)
        (self.root / "code").mkdir(exist_ok=True)
        (self.root / "code/model.py").write_text("EDGE_X = 30.0\n", encoding="utf-8")

        def profile(locator):
            return ("| 项 | 值 |\n|---|---|\n| pack | generic |\n| 缺口 | fixture |\n| 失效条件 | never |\n\n"
                    "| pack 段 | 状态 | 本文实例 | 定位／理由 |\n|---|---|---|---|\n"
                    + "".join(f"| §{i} | 不适用 | fixture | fixture reason |\n" for i in range(8))
                    + f"\n| 约定 | 本文取值 | 定位／状态 |\n|---|---|---|\n| 左竖条 | 30 | {locator} |\n")

        def run(script):
            return subprocess.run([sys.executable, str(SCRIPTS / script), str(self.root)],
                                  capture_output=True, text=True, timeout=10)

        (self.root / "spec/domain_profile.md").write_text(profile("code/model.py::EDGE_X"), encoding="utf-8")
        self.assertEqual(run("check_profile_anchors.py").returncode, 0)
        (self.root / "spec/domain_profile.md").write_text(profile("code/model.py::MISSING"), encoding="utf-8")
        self.assertEqual(run("check_profile_anchors.py").returncode, 2, "unresolved symbol must block")
        (self.root / "spec/domain_profile.md").write_text(profile("code/nope.py::EDGE_X"), encoding="utf-8")
        self.assertEqual(run("check_profile_anchors.py").returncode, 2, "missing anchor file must block")
        (self.root / "spec/domain_profile.md").write_text(profile(""), encoding="utf-8")
        self.assertEqual(run("check_profile_anchors.py").returncode, 2, "empty locator must block")

        # official data present but no smoke record -> INCOMPLETE
        ref = self.root / "paper/refcode/demo/data.mat"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_bytes(b"fixture")
        prov = json.loads((self.root / "spec/provenance.json").read_text())
        self.write("spec/provenance.json", prov)
        self.assertEqual(run("check_official_smoke.py").returncode, 2, "missing smoke record must block")
        np.savez(self.root / "data/mine/smoke_official.npz", v1=[1.0], v2=[0.0])
        prov["official_smoke"] = {"file": "paper/refcode/demo/data.mat", "sha256": sha256(ref),
                                  "compared": ["V1"], "data_file": "data/mine/smoke_official.npz",
                                  "passed": True, "date": "2026-01-01", "tolerance": "2%"}
        self.write("spec/provenance.json", prov)
        self.assertEqual(run("check_official_smoke.py").returncode, 0)
        prov["official_smoke"]["passed"] = False
        self.write("spec/provenance.json", prov)
        self.assertEqual(run("check_official_smoke.py").returncode, 2, "failed smoke must block")
