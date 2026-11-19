import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import Incomplete, sha256
from scaffold import create
from check_report import check as check_report

TABLE_HEAD = (
    "| 目标 | 判定 | 指标 | 说明 | 证据 |\n"
    "|---|---|---|---|---|\n"
)


class Report(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            create(self.root, "report fixture", "standard", True, "paper")
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture DOI", domain="generic", stage="final")
        doc["targets"][0]["criterion"] = "fixture criterion"
        self.write("spec/project.json", doc)
        self.doc = doc
        self.write("spec/provenance.json", {
            "declaration": "fixture", "official_metadata_used": [],
            "references": [{
                "file": "data/ground_truth/fig1.csv",
                "sha256": self._ref_hash(), "kind": "paper", "citation": "fixture",
                "extraction": "fixture", "version": "v1", "locator": "Table 1",
                "conditions": "fixture", "uncertainty": 0.01,
                "uncertainty_basis": "fixture", "purposes": ["validation"],
                "used_for_tuning": False}],
            "comparisons": []})
        self.write("reports/fig1.json", {"target": "fig1", "status": "PASS",
                                         "metrics": {"rms_norm": 0.0042}})

    def _ref_hash(self):
        path = self.root / "data/ground_truth/fig1.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
        return sha256(path)

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")
        return path

    def report(self, verdict="定量符合", metric="rms_norm=0.0042",
               evidence="reports/fig1.json", limits="- 参考被用于调参，非留出验证。",
               provenance=None, drop_target=False):
        body = ["# 复现报告", ""]
        body += ["## 0. 结论摘要", "paper_result 的 fig1 达到定量符合。", ""]
        body += ["## 1. 逐目标结果", TABLE_HEAD.rstrip()]
        if not drop_target:
            body.append(f"| fig1 | {verdict} | {metric} | 说明 | {evidence} |")
        body += ["", "## 2. 门禁与证据",
                 "| 检查 | 命令 | 结果 |", "|---|---|---|",
                 "| check_spec.py | python3 check_spec.py . | PASS |",
                 "| check_loss.py | python3 check_loss.py . fig1 | PASS |",
                 "| check_calibration.py | python3 check_calibration.py . | PASS |", "",
                 "绑定运行 runs/run1/manifest.json。", ""]
        body += ["## 3. 局限与未完成项", limits, ""]
        body += ["## 4. 复现方法", "```bash", "python3 code/run.py", "```", ""]
        body += ["## 5. 参考来源与调参披露",
                 (provenance if provenance is not None else
                  "reproduction_mode=paper；参考 kind=paper，不确定度 0.01；"
                  "参考参与调参，故本次为非留出验证。"), ""]
        return self.write("REPORT.md", "\n".join(body))

    def test_report_not_required_before_final(self):
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc["stage"] = "calibrated"
        self.write("spec/project.json", doc)
        (self.root / "REPORT.md").unlink()
        self.assertEqual(check_report(self.root), 0)

    def test_final_requires_the_report(self):
        (self.root / "REPORT.md").unlink()
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_unfilled_template_is_rejected(self):
        self.assertIn("⟪", (self.root / "REPORT.md").read_text())
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_complete_report_passes(self):
        self.report()
        self.assertEqual(check_report(self.root), 0)

    def test_hand_written_metric_is_rejected(self):
        self.report(metric="rms_norm=0.0011")
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_missing_target_row_is_rejected(self):
        self.report(drop_target=True)
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_unknown_verdict_is_rejected(self):
        self.report(verdict="看起来不错")
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_failed_scoring_report_cannot_be_claimed_as_passing(self):
        self.write("reports/fig1.json", {"target": "fig1", "status": "FAIL",
                                         "metrics": {"rms_norm": 0.0042}})
        self.report()
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_report_from_another_target_is_rejected(self):
        self.write("reports/fig1.json", {"target": "fig9", "status": "PASS",
                                         "metrics": {"rms_norm": 0.0042}})
        self.report()
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_tuning_must_be_disclosed(self):
        self.write("spec/provenance.json", {
            "declaration": "fixture", "official_metadata_used": [],
            "references": [{
                "file": "data/ground_truth/fig1.csv",
                "sha256": self._ref_hash(), "kind": "paper", "citation": "fixture",
                "extraction": "fixture", "version": "v1", "locator": "Table 1",
                "conditions": "fixture", "uncertainty": 0.01,
                "uncertainty_basis": "fixture", "purposes": ["validation"],
                "used_for_tuning": True,
                "reuse_disclosure": "conventions were chosen against this figure"}],
            "comparisons": []})
        self.report(limits="- 没有其他局限。", provenance="reproduction_mode=paper；参考 kind=paper。")
        with self.assertRaises(Incomplete):
            check_report(self.root)
        self.report(limits="- 参考参与调参，因此不是留出验证。")
        self.assertEqual(check_report(self.root), 0)

    def test_undisclosed_reference_kind_is_rejected(self):
        self.report(provenance="reproduction_mode=paper；所有参考均已登记。")
        with self.assertRaises(Incomplete):
            check_report(self.root)

    def test_digitized_reference_needs_digitisation_disclosure(self):
        prov = json.loads((self.root / "spec/provenance.json").read_text())
        prov["references"][0]["kind"] = "digitized"
        prov["references"][0]["fallback_reason"] = "no published numbers"
        self.write("spec/provenance.json", prov)
        # naming the kind is not enough: the digitisation fallback must be stated
        self.report(provenance="reproduction_mode=paper；kind=digitized；不是留出验证（调参）。")
        with self.assertRaises(Incomplete):
            check_report(self.root)
        self.report(provenance="reproduction_mode=paper；kind=digitized；无数值来源，故用数字化提取。"
                               "不是留出验证（调参）。")
        self.assertEqual(check_report(self.root), 0)

    def test_escalated_decision_must_be_echoed(self):
        self.write("spec/decisions.json", {"items": [{
            "id": "D2", "question": "第二层平移取 −v 还是 0？",
            "options": ["−v", "0"], "chosen": "−v", "rule": "discriminator",
            "basis": "两种取法只差 7%，不足以定案",
            "evidence": [], "evidence_reason": "判别实验证据尚不足以定案",
            "reversibility": "reversible", "reverse_cost": "重跑扫描",
            "confidence": "low", "impact": "verdict", "status": "escalated",
            "escalation_reason": "判定级歧义且现有判别实验无法定案"}]})
        (self.root / "LOG.md").write_text("# 迭代日志\n\n[DECISION:D2]\n", encoding="utf-8")
        self.report(limits="- 没有其他局限。")
        with self.assertRaises(Incomplete):
            check_report(self.root)
        self.report(limits="- 待人工裁决的决策 D2：第二层平移 −v vs 0，影响下带边结论。")
        self.assertEqual(check_report(self.root), 0)


if __name__ == "__main__":
    unittest.main()
