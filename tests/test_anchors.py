import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import sha256, run
from scaffold import create
from check_anchors import check as check_anchors


class Anchors(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            create(self.root, "anchor fixture", "standard", True, "paper")
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture DOI", domain="generic", stage="calibrated")
        doc["targets"][0]["criterion"] = "fixture criterion"
        self.write("spec/project.json", doc)
        self.write("reports/fig1.json", {"target": "fig1", "status": "PASS",
                                         "metrics": {"plateau": 0.392}})

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        return path

    def anchor(self, **over):
        item = {"id": "A1", "quantity": "plateau_square_Mz", "expected": 0.390, "unit": "e2/h",
                "tolerance": 0.01, "source": {"kind": "paper", "locator": "Fig.3(b) plateau"},
                "status": "held",
                "evidence": [{"file": "reports/fig1.json",
                              "sha256": sha256(self.root / "reports/fig1.json"),
                              "metric": "plateau", "result": 0.392}]}
        item.update(over)
        return item

    def baseline(self, anchors_path, rid="R1"):
        """First run records the anchors fingerprint, exactly as record_run.py does."""
        return self.write(f"runs/{rid}/manifest.json",
                          {"id": rid, "started": "2026-01-01T00:00:00+00:00",
                           "anchors_sha256": sha256(anchors_path)})

    def gate(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = run(lambda: check_anchors(self.root))
        return code, out.getvalue()

    def test_pass_when_preregistered_and_hash_bound(self):
        path = self.write("spec/anchors.json", {"items": [self.anchor()]})
        self.baseline(path)
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn("pre-registered anchors hash-bound", out)

    def test_blocks_template_and_post_hoc_edit(self):
        self.write("spec/anchors.json", {"empty_reason": "TEMPLATE: register before the first run",
                                         "items": []})
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("still the scaffold template", out)

        path = self.write("spec/anchors.json", {"items": [self.anchor()]})
        self.baseline(path)
        # widening the tolerance after seeing 0.392 "just fits" -> fingerprint breaks
        self.write("spec/anchors.json", {"items": [self.anchor(tolerance=0.05)]})
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("changed after the first run", out)

        # a discriminator decision makes the amendment legitimate, not silent
        self.write("spec/decisions.json", {"items": [
            {"id": "D1", "question": "anchors 允差是否按文献误差重定？", "options": ["保持", "放宽"],
             "chosen": "放宽", "rule": "discriminator", "basis": "补跑 L=20 得到 0.392±0.004",
             "reversibility": "reversible", "confidence": "high", "impact": "numeric",
             "status": "auto", "anchors_amendment": True}]})
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn("amended by D1", out)

    def test_not_applicable_without_file_or_baseline(self):
        (self.root / "spec/anchors.json").unlink()    # pre-v3 workspace: no anchors.json
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn("NOT_APPLICABLE", out)

        path = self.write("spec/anchors.json", {"items": [self.anchor()]})
        self.write("runs/R0/manifest.json", {"id": "R0", "started": "2025-01-01T00:00:00+00:00"})
        code, out = self.gate()          # earliest manifest predates v3 -> disclose, don't fail
        self.assertEqual(code, 0, out)
        self.assertIn("no anchors_sha256", out)

    def test_final_forbids_untested_and_violated_needs_resolution(self):
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc["stage"] = "final"
        self.write("spec/project.json", doc)
        path = self.write("spec/anchors.json", {"items": [self.anchor(status="untested")]})
        self.baseline(path)
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("still untested", out)

        path = self.write("spec/anchors.json", {"items": [self.anchor(status="violated")]})
        self.baseline(path, "R2")
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("violated anchor must carry `resolution`", out)


if __name__ == "__main__":
    unittest.main()
