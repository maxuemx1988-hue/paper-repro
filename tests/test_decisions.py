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
from check_decisions import check as check_decisions
from check_review import check as check_review
from make_review import check as make_review


class Decisions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            create(self.root, "decision fixture", "standard", True, "paper")
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture DOI", domain="generic", stage="final")
        doc["targets"][0]["criterion"] = "fixture criterion"
        self.write("spec/project.json", doc)
        self.write("spec/evidence.txt", "measured 1.0\n")
        self.log = "# 迭代日志\n"
        self.write_log()
        self.write("reports/fig1.json", {"target": "fig1", "status": "PASS",
                                         "metrics": {"rms_norm": 0.0042}})

    def write(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        return path

    def write_log(self, *ids):
        text = "# 迭代日志\n" + "".join(f"\n- [DECISION:{i}] fixture rationale\n" for i in ids)
        self.write("LOG.md", text)

    def item(self, **over):
        base = {
            "id": "D1", "question": "横轴单位取哪个？",
            "options": ["每单位胞", "每超胞"], "chosen": "每单位胞",
            "rule": "discriminator", "basis": "图注自洽性检验",
            "evidence": [{"file": "spec/evidence.txt",
                          "sha256": sha256(self.root / "spec/evidence.txt"),
                          "metric": "hexagon_sum", "result": 126.0}],
            "reversibility": "reversible", "reverse_cost": "只改轴标注",
            "confidence": "high", "impact": "convention", "status": "auto",
        }
        base.update(over)
        return base

    def ledger(self, *items):
        self.write("spec/decisions.json", {"items": list(items)})
        self.write_log(*[i["id"] for i in items])

    def test_empty_ledger_with_reason_is_not_applicable(self):
        self.write("spec/decisions.json", {"empty_reason": "尚未开始", "items": []})
        self.assertEqual(check_decisions(self.root), 0)

    def test_empty_ledger_without_reason_is_incomplete(self):
        self.write("spec/decisions.json", {"items": []})
        with self.assertRaises(Incomplete):
            check_decisions(self.root)

    def test_valid_auto_decision_passes(self):
        self.ledger(self.item())
        self.assertEqual(check_decisions(self.root), 0)

    def test_chosen_must_be_one_of_the_options(self):
        self.ledger(self.item(chosen="第三条路"))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)

    def test_target_set_change_cannot_be_automatic(self):
        self.ledger(self.item(impact="scope", status="auto"))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)

    def test_low_confidence_verdict_must_escalate(self):
        self.ledger(self.item(impact="verdict", confidence="low", status="auto"))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)
        self.ledger(self.item(impact="verdict", confidence="low", status="escalated",
                              escalation_reason="两种读法差 7%，判别实验无法定案"))
        self.assertEqual(check_decisions(self.root), 0)

    def test_one_way_decision_needs_reverse_cost(self):
        self.ledger(self.item(reversibility="one-way", reverse_cost=""))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)

    def test_log_marker_is_required(self):
        self.write("spec/decisions.json", {"items": [self.item()]})
        self.write("LOG.md", "# 迭代日志\n\n没有任何标记\n")
        with self.assertRaises(Incomplete):
            check_decisions(self.root)

    def test_human_confirmation_needs_reviewer(self):
        self.ledger(self.item(status="human_confirmed"))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)
        self.ledger(self.item(status="human_confirmed",
                              human_review={"by": "reviewer-a", "date": "2026-02-14", "note": "同意"}))
        self.assertEqual(check_decisions(self.root), 0)

    def test_high_confidence_needs_bound_evidence(self):
        self.ledger(self.item(evidence=[]))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)
        self.ledger(self.item(evidence=[], evidence_reason="本文正文直接给出该约定"))
        self.assertEqual(check_decisions(self.root), 0)

    def test_evidence_hash_is_verified(self):
        self.ledger(self.item(evidence=[{"file": "spec/evidence.txt", "sha256": "0" * 64,
                                         "metric": "m", "result": 1.0}]))
        with self.assertRaises(Incomplete):
            check_decisions(self.root)

    def test_packet_is_generated_and_verified(self):
        self.ledger(self.item())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            make_review(self.root)
        self.assertIn("D1", (self.root / "REVIEW.md").read_text())
        self.assertEqual(check_review(self.root), 0)

    def test_packet_must_cover_pending_decision(self):
        self.ledger(self.item(impact="verdict", confidence="low", status="escalated",
                              escalation_reason="待裁决"),
                    self.item(id="D2", question="第二个问题", impact="verdict",
                              confidence="low", status="escalated", escalation_reason="待裁决"))
        with contextlib.redirect_stdout(io.StringIO()):
            make_review(self.root)
        review = self.root / "REVIEW.md"
        self.assertIn("`D2`", review.read_text())
        # stripping a pending row makes the hand-off hide an open question
        review.write_text(review.read_text().replace("`D2`", "DD"), encoding="utf-8")
        with self.assertRaises(Incomplete):
            check_review(self.root)

    def test_stale_packet_is_rejected(self):
        self.ledger(self.item())
        with contextlib.redirect_stdout(io.StringIO()):
            make_review(self.root)
        self.ledger(self.item(basis="结论后来改了"))
        with self.assertRaises(Incomplete):
            check_review(self.root)


if __name__ == "__main__":
    unittest.main()
