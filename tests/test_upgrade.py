"""Workspace upgrade: auto items only, manual items never invented."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import scaffold
import upgrade_project
from check_route import check as check_route
from common import sha256


class Upgrade(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "ws"
        self.root.mkdir()
        self.out = io.StringIO()
        ctx = contextlib.redirect_stdout(self.out)
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)

    def workspace(self, official_code=True):
        scaffold.create(self.root, "upgrade fixture", "standard", official_code)
        doc = self.project()
        doc.update(stage="calibrated", source="arXiv:0000.0000", domain="generic")
        doc["targets"][0]["criterion"] = "fixture criterion"
        self.save("spec/project.json", doc)
        gt = self.root / "data/ground_truth/fig1.csv"
        gt.parent.mkdir(parents=True, exist_ok=True)
        gt.write_text("x,y\n0,0\n1,1\n", encoding="utf-8")
        prov = self.provenance()
        prov["references"] = [dict(file="data/ground_truth/fig1.csv", sha256=sha256(gt), kind="paper",
                                   citation="fixture DOI", extraction="fixture transcription", version="v1",
                                   locator="Table 1", conditions="fixture", uncertainty=0.01,
                                   uncertainty_basis="fixture rounding", purposes=["validation"],
                                   used_for_tuning=False)]
        self.save("spec/provenance.json", prov)

    def project(self):
        return json.loads((self.root / "spec/project.json").read_text(encoding="utf-8"))

    def provenance(self):
        return json.loads((self.root / "spec/provenance.json").read_text(encoding="utf-8"))

    def save(self, name, obj):
        (self.root / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_upgrade(self, *extra):
        self.out.truncate(0)
        self.out.seek(0)
        code = upgrade_project.main([str(self.root), *extra])
        return code, self.out.getvalue()

    def test_route_backfilled_from_official_code(self):
        self.workspace(official_code=True)
        prov = self.provenance()
        prov.pop("route")
        self.save("spec/provenance.json", prov)
        code, text = self.run_upgrade("--apply")
        self.assertEqual(code, 0)
        self.assertIn("[AUTO] spec/provenance.json: provenance.route", text)
        route = self.provenance()["route"]
        self.assertEqual(route["mode"], "A")
        self.assertTrue(route["basis"].strip())
        self.assertEqual(check_route(self.root), 0)

    def test_dry_run_writes_nothing(self):
        self.workspace(official_code=False)
        prov = self.provenance()
        prov.pop("route")
        self.save("spec/provenance.json", prov)
        before = (self.root / "spec/provenance.json").read_text(encoding="utf-8")
        _, text = self.run_upgrade()
        self.assertIn("[WOULD]", text)
        self.assertEqual((self.root / "spec/provenance.json").read_text(encoding="utf-8"), before)

    def test_route_b_stays_manual_until_search_recorded(self):
        self.workspace(official_code=False)
        prov = self.provenance()
        prov.pop("route")
        self.save("spec/provenance.json", prov)
        _, text = self.run_upgrade("--apply")
        self.assertIn("[EVIDENCE]", text)
        self.assertEqual(self.provenance()["route"]["code_absence_check"], [])
        with self.assertRaises(Exception):
            check_route(self.root)                     # unsearched absence is not an absence

        prov = self.provenance()
        prov.pop("route")
        self.save("spec/provenance.json", prov)
        self.run_upgrade("--apply", "--code-absence", "arXiv source", "--code-absence", "GitHub search")
        self.assertEqual(self.provenance()["route"]["code_absence_check"], ["arXiv source", "GitHub search"])

    def test_paper_figure_never_guessed(self):
        self.workspace()
        project = self.project()
        project["targets"][0].pop("paper_figure")
        self.save("spec/project.json", project)
        _, text = self.run_upgrade("--apply")
        self.assertIn("[EVIDENCE]", text)
        self.assertNotIn("paper_figure", self.project()["targets"][0])
        self.run_upgrade("--apply", "--paper-figure", "fig1=Fig2(a),Fig2(b)")
        self.assertEqual(self.project()["targets"][0]["paper_figure"], ["Fig2(a)", "Fig2(b)"])

    def test_figure_guess_from_visual_crop(self):
        self.workspace()
        self.save("spec/fig1.visual.json", {
            "crop": "data/ground_truth/fig3b_panel.png", "mine_image": "figures/mine/fig1.png",
            "plot_metadata": "figures/mine/fig1.plot.json",
            "comparison_image": "figures/compare/fig1_side_by_side.png", "min_visible": 0.95})
        project = self.project()
        project["targets"][0]["paper_figure"] = ["placeholder"]
        project["targets"][0]["checks"]["visual"] = {"enabled": True, "config": "spec/fig1.visual.json"}
        project["targets"][0].pop("paper_figure")
        self.save("spec/project.json", project)
        _, text = self.run_upgrade()
        self.assertIn("Fig3(b)", text)                  # proposal only, never written

    def test_digitized_reference_needs_audit(self):
        self.workspace()
        gt = self.root / "data/ground_truth/fig1.csv"
        gt.parent.mkdir(parents=True, exist_ok=True)
        gt.write_text("x,y\n0,0\n1,1\n", encoding="utf-8")
        gt.with_suffix(".meta.json").write_text(json.dumps({"image": "data/ground_truth/fig1_crop.png"}),
                                                encoding="utf-8")
        (self.root / "data/ground_truth/fig1_crop.png").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "data/ground_truth/fig1_crop.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        prov = self.provenance()
        prov["references"] = [{"file": "data/ground_truth/fig1.csv", "sha256": "0" * 64,
                               "kind": "digitized"}]
        self.save("spec/provenance.json", prov)
        _, text = self.run_upgrade()
        self.assertIn("fig1_crop.visual_audit.json", text)

    def test_idempotent(self):
        self.workspace(official_code=True)
        prov = self.provenance()
        prov.pop("route")
        self.save("spec/provenance.json", prov)
        self.run_upgrade("--apply")
        _, text = self.run_upgrade("--apply")
        self.assertIn("无需迁移", text)


if __name__ == "__main__":
    unittest.main()
