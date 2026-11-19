"""Route A/B eligibility audit and model-reviewed crops (structure only, no physics)."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import Incomplete, sha256
from check_route import check as check_route
from check_visual_crop import audit_crop


class RouteChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = io.StringIO()
        ctx = contextlib.redirect_stdout(self.out)
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.fixture()

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return path

    def reference(self, file, kind="paper", **extra):
        return dict(file=file, sha256=sha256(self.root / file), kind=kind,
                    citation="fixture DOI", extraction="fixture transcription", version="v1",
                    locator="Table 1", conditions="fixture parameters", uncertainty=0.01,
                    uncertainty_basis="fixture rounding", purposes=["validation"],
                    used_for_tuning=False, **extra)

    def fixture(self, official_code=False):
        self.write("spec/project.json", {
            "schema_version": 1, "title": "route fixture", "source": "fixture DOI",
            "level": "standard", "official_code": official_code,
            "reproduction_mode": "paper", "stage": "calibrated", "domain": "generic",
            "environment": "spec/environment.json", "independence": "spec/provenance.json",
            "targets": [{
                "id": "fig1", "type": "curve", "mode": "quantitative",
                "validation_subject": "paper_result", "criterion": "fixture criterion",
                "paper_figure": None,
                "checks": {"loss": {"enabled": True, "config": "spec/fig1.loss.json"},
                           "visual": {"enabled": False, "reason": "fixture uses a printed table"},
                           "effect": {"enabled": False, "reason": "not a perturbative effect"}}}]})
        gt = self.root / "data/ground_truth/fig1.csv"
        gt.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(gt, np.column_stack([np.linspace(0, 1, 5)] * 2), delimiter=",", header="x,y", comments="")
        (gt.with_suffix(".meta.json")).write_text(json.dumps({"units": {"x": "1", "y": "1"}}), encoding="utf-8")
        self.write("spec/fig1.loss.json", {"type": "curve", "mine": {"file": "data/mine/fig1.npz"},
                                           "gt": {"file": "data/ground_truth/fig1.csv"}})
        self.write("spec/calibration.json", {
            "assertions": [{"id": "C1", "category": "limit", "desc": "analytic limit"}],
            "not_applicable": {"invariant": "fixture", "paper": "fixture"}})
        self.provenance([self.reference("data/ground_truth/fig1.csv")],
                        route={"mode": "B", "basis": "no code searched",
                               "code_absence_check": ["arXiv", "GitHub", "author page"]})

    def provenance(self, refs, route=None, **extra):
        cfg = dict(declaration="fixture provenance", official_metadata_used=[],
                   references=refs, comparisons=[], **extra)
        if route is not None:
            cfg["route"] = route
        self.write("spec/provenance.json", cfg)
        return cfg

    def test_route_b_happy_path(self):
        self.assertEqual(check_route(self.root), 0)

    def test_route_must_be_declared_and_match(self):
        self.provenance([self.reference("data/ground_truth/fig1.csv")])
        with self.assertRaises(Incomplete):
            check_route(self.root)
        self.provenance([self.reference("data/ground_truth/fig1.csv")],
                        route={"mode": "A", "basis": "mismatch", "code_absence_check": []})
        with self.assertRaises(Incomplete):
            check_route(self.root)

    def test_route_b_needs_search_record(self):
        self.provenance([self.reference("data/ground_truth/fig1.csv")],
                        route={"mode": "B", "basis": "assumed absent", "code_absence_check": []})
        with self.assertRaises(Incomplete):
            check_route(self.root)

    def test_route_b_needs_numeric_anchor_and_limit(self):
        digitized = self.reference("data/ground_truth/fig1.csv", "digitized", fallback_reason="only a figure exists")
        self.provenance([digitized], route={"mode": "B", "basis": "no code",
                                            "code_absence_check": ["arXiv"]})
        with self.assertRaises(Incomplete):          # digitised alone is not an anchor
            check_route(self.root)
        self.write("spec/calibration.json", {
            "assertions": [{"id": "C1", "category": "paper", "desc": "paper value"}],
            "not_applicable": {"invariant": "fixture", "limit": "fixture"}})
        with self.assertRaises(Incomplete):          # no limit/invariant oracle in Route B
            check_route(self.root)

    def test_route_b_forbids_official_outputs(self):
        ref = self.reference("data/ground_truth/fig1.csv")
        ref["kind"] = "official_comparison"
        self.provenance([ref], route={"mode": "B", "basis": "no code", "code_absence_check": ["arXiv"]})
        with self.assertRaises(Incomplete):
            check_route(self.root)

    def test_digitized_needs_hash_bound_model_response(self):
        crop = self.root / "data/ground_truth/fig1_crop.png"
        Image.new("RGB", (8, 8), "white").save(crop)
        pdf = self.root / "paper/paper.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"fixture pdf")
        axes = {"xaxis": {"label": "x", "unit": "1", "limits": [0, 1], "scale": "linear"},
                "yaxis": {"label": "y", "unit": "1", "limits": [0, 1], "scale": "linear"}}
        audit = crop.with_suffix(".visual_audit.json")
        base = dict(image=dict(file="data/ground_truth/fig1_crop.png", sha256=sha256(crop)),
                    pdf=dict(file="paper/paper.pdf", sha256=sha256(pdf)),
                    page=1, bbox_pdf=[0, 0, 10, 10], subfigure_id="a", **axes)
        base["review"] = dict(method="model", reviewer="kimi-k3", time="2026-01-01", notes="fixture")
        audit.write_text(json.dumps(base), encoding="utf-8")
        with self.assertRaises(Incomplete):          # method=model without vision binding
            audit_crop(self.root, "data/ground_truth/fig1_crop.png")
        raw = self.write("data/ground_truth/fig1_crop.vision.json", {"reading": "fixture"})
        base["vision"] = {"model_used": "kimi-k3", "raw": {"file": "data/ground_truth/fig1_crop.vision.json",
                                                           "sha256": sha256(raw)}}
        audit.write_text(json.dumps(base), encoding="utf-8")
        self.assertEqual(audit_crop(self.root, "data/ground_truth/fig1_crop.png")["subfigure_id"], "a")
        # the same audit backs a digitised reference, so Route B now walks its digitised branch
        self.write("data/ground_truth/fig1.meta.json", {
            "units": {"x": "1", "y": "1"},
            "image": "data/ground_truth/fig1_crop.png"})
        digitized = self.reference("data/ground_truth/fig1.csv", "digitized",
                                   fallback_reason="no released data, only a figure")
        self.provenance([self.reference("data/ground_truth/fig1.csv"), digitized],
                        route={"mode": "B", "basis": "no code found",
                               "code_absence_check": ["arXiv", "GitHub"]})
        self.assertEqual(check_route(self.root), 0)

    def test_final_report_names_route_b(self):
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc["stage"] = "final"
        self.write("spec/project.json", doc)
        with self.assertRaises(Incomplete):
            check_route(self.root)
        (self.root / "REPORT.md").write_text("## 3. 局限与未完成项\n- 走 Route B，无官方代码。\n", encoding="utf-8")
        self.assertEqual(check_route(self.root), 0)

    def test_route_a_still_works(self):
        self.fixture(official_code=True)
        self.provenance([self.reference("data/ground_truth/fig1.csv")],
                        route={"mode": "A", "basis": "author code released with the paper",
                               "code_absence_check": []})
        self.assertEqual(check_route(self.root), 0)


if __name__ == "__main__":
    unittest.main()
