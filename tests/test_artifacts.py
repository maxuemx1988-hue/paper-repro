import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import run
from scaffold import create
from record_artifact import add, listing, read_ledger


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with contextlib.redirect_stdout(io.StringIO()):
            create(self.root, "artifact fixture", "standard", True, "paper")

    def write(self, name, text="fixture bytes"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def call(self, fn, *args, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run(lambda: fn(*args, **kwargs))
        return code, out.getvalue()

    def test_pass_append_and_dedupe_by_content(self):
        self.write("figures/mine/fig3.png", "png bytes A")
        code, out = self.call(add, self.root, "figures/mine/fig3.png", "figure", "fig3", "reproduction", None)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(read_ledger(self.root)), 1)

        # same bytes under a delivery path: counted once, not twice (Mira's bug)
        self.write("delivery/fig3.png", "png bytes A")
        code, out = self.call(add, self.root, "delivery/fig3.png", "delivery", "fig3", "copy", None)
        self.assertEqual(code, 0, out)
        self.assertIn("already registered", out)
        self.assertEqual(len(read_ledger(self.root)), 1)

    def test_pass_records_supersede_edge_and_lists_timeline(self):
        self.write("figures/mine/fig3.png", "draft")
        self.write("figures/mine/fig3_final.png", "final")
        self.call(add, self.root, "figures/mine/fig3.png", "figure", "fig3", "draft", None)
        code, out = self.call(add, self.root, "figures/mine/fig3_final.png", "figure", "fig3",
                              "after legend fix", "figures/mine/fig3.png")
        self.assertEqual(code, 0, out)
        rows = read_ledger(self.root)
        self.assertEqual(rows[1]["supersedes"], "figures/mine/fig3.png")
        code, out = self.call(listing, self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("<- figures/mine/fig3.png", out)
        self.assertIn("2 artifacts registered", out)

    def test_not_applicable_when_empty_and_blocks_unknown_supersede(self):
        code, out = self.call(listing, self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("no artifacts registered yet", out)

        self.write("figures/mine/fig3.png", "bytes")
        code, out = self.call(add, self.root, "figures/mine/fig3.png", "figure", "fig3", "", "figures/nope.png")
        self.assertEqual(code, 2, out)
        self.assertIn("is not a registered artifact", out)


if __name__ == "__main__":
    unittest.main()
