import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from scaffold import create


class Next(unittest.TestCase):
    """next.py exists to remove the model's freedom to choose the next step.

    The regression that matters is textual: one BLOCKED_BY line, one runnable NEXT
    line, and no reliance on the agent re-reading prose to pick a gate.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            create(self.root, "next fixture", "standard", True, "paper")
        doc = json.loads((self.root / "spec/project.json").read_text())
        doc.update(source="fixture DOI", domain="generic", stage="planning")
        doc["targets"][0]["criterion"] = "fixture criterion"
        (self.root / "spec/project.json").write_text(json.dumps(doc), encoding="utf-8")
        (self.root / "spec/anchors.json").unlink(missing_ok=True)

    def run_next(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "next.py"), str(self.root), *args],
                              capture_output=True, text=True, timeout=120)

    def test_prints_single_blocked_by_and_a_runnable_next(self):
        result = self.run_next()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        blocked = [l for l in result.stdout.splitlines() if l.startswith("BLOCKED_BY:")]
        self.assertEqual(len(blocked), 1, result.stdout)
        nexts = [l for l in result.stdout.splitlines() if l.startswith("NEXT: python3 scripts/")]
        self.assertEqual(len(nexts), 1, result.stdout)
        script = blocked[0].split(":", 1)[1].strip()
        if script.endswith(".json"):
            self.assertIn("check_spec.py", nexts[0])
            return
        self.assertIn(script, nexts[0])
        # the gate it names must actually be the one that fails
        gate = subprocess.run([sys.executable, str(SCRIPTS / script), str(self.root)],
                              capture_output=True, text=True, timeout=60)
        self.assertNotEqual(gate.returncode, 0)

    def test_why_pulls_the_protocol_anchor_only_on_demand(self):
        result = self.run_next()
        self.assertNotIn("WHY:", result.stdout)
        result = self.run_next("--why")
        self.assertIn("WHY:", result.stdout)
        self.assertIn("references/", result.stdout)

    def test_json_writes_the_step_list_for_later_diffing(self):
        self.run_next("--json")
        doc = json.loads((self.root / "reports/next.json").read_text())
        self.assertEqual(doc["stage"], "planning")
        self.assertTrue(doc["blocked_by"].endswith(".py"))
        self.assertTrue(any(step[0] == doc["blocked_by"] for step in doc["steps"]))


if __name__ == "__main__":
    unittest.main()
