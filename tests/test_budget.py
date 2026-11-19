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
from check_budget import check as check_budget


class Budget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            create(self.root, "budget fixture", "standard", True, "paper")
        self.stage("calibrated")

    def stage(self, stage):
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture DOI", domain="generic", stage=stage)
        doc["targets"][0]["criterion"] = "fixture criterion"
        self.write("spec/project.json", doc)

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        return path

    def run_manifest(self, rid="R1", seconds=1200, count=None):
        manifest = self.write(f"runs/{rid}/manifest.json",
                              {"id": rid, "started": "2026-01-01T00:00:00+00:00",
                               "finished": f"2026-01-01T{seconds // 3600:02d}:"
                                           f"{seconds % 3600 // 60:02d}:{seconds % 60:02d}+00:00"})
        return {"file": f"runs/{rid}/manifest.json", "sha256": sha256(manifest)}

    def doc(self, **over):
        base = {"estimate": {"cpu_hours": 300, "planned_configs": 300,
                             "basis": "8/3 n^3 * 20 layers * 150 pts / 1e9 flops"},
                "paths_considered": ["缩到 L=10", "块对角算法", "GPU 批处理"],
                "chosen": {"configs": 300, "chunk_size": 25, "resume": True},
                "measured": [{"chunk": "c01", "done": 25,
                              "run": self.run_manifest("R1", 1200)}],
                "eta_hours": 4.0, "eta_basis": "measured 48 s/config from runs/R1",
                "churn_count": 0}
        base.update(over)
        return base

    def gate(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = run(lambda: check_budget(self.root))
        return code, out.getvalue()

    def test_pass_with_estimate_and_measured_throughput(self):
        self.write("spec/budget.json", self.doc())
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn("measured 48.000 s/unit", out)
        self.assertIn("chosen mitigation chunked (25)", out)

    def test_blocks_eta_from_tool_message_and_missing_measured(self):
        doc = self.doc(eta_hours=9.0, eta_basis="after 1200 seconds the tool killed the job")
        self.write("spec/budget.json", doc)
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("eta_basis must cite measured throughput", out)

        doc = self.doc()
        doc["measured"] = []
        self.write("spec/budget.json", doc)
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("bound to runs/*/manifest.json", out)

        doc = self.doc(estimate={"cpu_hours": 300, "planned_configs": 400, "basis": ""})
        self.write("spec/budget.json", doc)
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("estimate.basis required", out)

    def test_blocks_scale_reduction_without_a_decision(self):
        doc = self.doc()
        doc["chosen"]["configs"] = 120
        self.write("spec/budget.json", doc)
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("budget_amendment", out)

        self.write("spec/decisions.json", {"items": [
            {"id": "D1", "question": "主图构型数 400 还是 120？", "options": ["400", "120"],
             "chosen": "120", "rule": "discriminator", "basis": "实测 48 s/config，300h 超预算",
             "reversibility": "reversible", "confidence": "high", "impact": "numeric",
             "status": "auto", "budget_amendment": True}]})
        code, out = self.gate()
        self.assertEqual(code, 0, out)

    def test_not_applicable_without_file_or_with_reason(self):
        (self.root / "spec/budget.json").unlink()    # pre-v3 workspace
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn("NOT_APPLICABLE", out)

        self.write("spec/budget.json", {"not_applicable": "单点计算 < 30 s，无扫描"})
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn("无扫描", out)

        self.stage("final")
        self.write("spec/budget.json", {"not_applicable": "TEMPLATE: fill estimate/chosen/measured"})
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn("still the scaffold template", out)


if __name__ == "__main__":
    unittest.main()
