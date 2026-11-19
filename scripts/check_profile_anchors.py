#!/usr/bin/env python3
"""Bind the domain profile's convention table to real code symbols.

Motivation: a value can be written into the Spec and never reach the implementation
(e.g. "the left strip is 20 a0 wide" documented but the code default stays 0).  This check
requires every convention row to carry a locator, and every locator written as
``code/<path>::<SYMBOL>`` to resolve to an existing file that really contains SYMBOL.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import finish, project, require, run, within

ANCHOR = re.compile(r"(code/[\w./-]+\.py)::([A-Za-z_][\w.]*)")
PLACEHOLDER = re.compile(r"[⟪⟫]|^(tbd|待填|待定|-|—|)$", re.I)


def tables(text):
    lines = text.splitlines()
    found = []
    for i in range(len(lines) - 1):
        head = lines[i].strip()
        rule = lines[i + 1].strip()
        if not (head.startswith("|") and re.fullmatch(r"\|[\s:\-|]+\|", rule)):
            continue
        cells = lambda row: [c.strip() for c in row.strip().strip("|").split("|")]
        rows = []
        for row in lines[i + 2:]:
            if not row.strip().startswith("|"):
                break
            rows.append(cells(row))
        found.append((cells(head), rows))
    return found


def convention_table(all_tables):
    for head, rows in all_tables:
        if any("约定" in c for c in head) and rows:
            return rows
    return None


def check(root):
    project(root)
    path = within(root, "spec/domain_profile.md")
    require(path.is_file(), "missing spec/domain_profile.md")
    text = path.read_text(encoding="utf-8")
    require(not re.search(r"[⟪⟫]", text), "unfilled domain_profile markers")

    rows = convention_table(tables(text))
    require(rows is not None, "domain_profile: a 约定表 (convention table) is required")
    problems, anchors = [], 0
    for row in rows:
        if not row or PLACEHOLDER.match(row[0].strip()):
            continue
        name = row[0]
        locator = row[-1] if len(row) > 1 else ""
        if PLACEHOLDER.match(locator):
            problems.append(f"{name}: locator column is empty")
            continue
        for match in ANCHOR.finditer(" ".join(row)):
            rel, symbol = match.group(1), match.group(2)
            target = within(root, rel)
            if not target.is_file():
                problems.append(f"{name}: anchor file missing {rel}")
                continue
            body = target.read_text(encoding="utf-8")
            leaf = symbol.split(".")[-1]
            if leaf not in body:
                problems.append(f"{name}: symbol '{leaf}' not found in {rel}")
                continue
            anchors += 1
    require(not problems, "convention anchors unresolved: " + "; ".join(problems[:6]))
    return finish("PASS", f"{len(rows)} convention rows located; {anchors} code anchors resolved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
