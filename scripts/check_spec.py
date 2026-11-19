#!/usr/bin/env python3
"""Validate structured project fields and staged Spec, not scientific completeness."""
import argparse
import re
from common import finish, project, require, run, within


def check(root):
    doc = project(root)
    path = within(root, "spec/README.md")
    text = path.read_text(encoding="utf-8")
    require(not re.search(r"[⟪⟫]", text), "unfilled Spec markers")
    for i in "①②③④⑤⑥⑦":
        match = re.search(r"^## " + i + r"[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        require(match is not None and bool(match[1].strip()), f"missing/empty section {i}")
    for t in doc["targets"]:
        require("paper_figure" in t,
                f"{t['id']}: 必须显式声明 paper_figure（无数值图填 null，有则列出论文图 id 列表）")
        pf = t.get("paper_figure")
        require(pf is None or (isinstance(pf, list) and pf and all(isinstance(x, str) and x.strip() for x in pf)),
                f"{t['id']}: paper_figure 只能是 null 或非空字符串列表（论文图 id，如 Fig3(b)）")
        for entry in t["checks"].values():
            if entry.get("enabled"):
                require(within(root, entry["config"]).is_file(), f"missing config: {entry['config']}")
    return finish("PASS", f"Spec structure valid ({doc['stage']}); scientific review still required")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
