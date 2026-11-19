#!/usr/bin/env python3
"""Validate the per-paper domain instance profile: pack pinning, section coverage, row rules.

Checks structure and evidence, not whether the physics mapping is correct.
"""
import argparse
import hashlib
import re
from pathlib import Path
from common import finish, project, require, run, within

DOMAINS = Path(__file__).resolve().parent.parent / "references/domains"
STATUS_INSTANTIATE = ("采用", "实例化")
STATUS_EXTEND = ("扩展", "偏离")
PLACEHOLDER = re.compile(r"[⟪⟫]|^(tbd|待填|待定|-|—|)$", re.I)
SECTIONS = [f"§{i}" for i in range(8)]


def tables(text):
    """Yield (header, rows) for every Markdown table in text."""
    lines = text.splitlines()
    found = []
    for i in range(len(lines) - 1):
        start = lines[i].strip()
        rule = lines[i + 1].strip()
        if not (start.startswith("|") and re.fullmatch(r"\|[\s:\-|]+\|", rule)):
            continue
        cells = lambda row: [c.strip() for c in row.strip().strip("|").split("|")]
        header = cells(start)
        rows = []
        for row in lines[i + 2:]:
            if not row.strip().startswith("|"):
                break
            rows.append(cells(row))
        found.append((header, rows))
    return found


def filled(value):
    return isinstance(value, str) and not PLACEHOLDER.match(value.strip())


def binding(all_tables):
    out = {}
    for header, rows in all_tables:
        for row in rows:
            if len(row) >= 2 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*|失效条件|缺口", row[0]):
                out[row[0]] = row[1]
    return out


def status_index(header):
    for i, cell in enumerate(header):
        if "状态" in cell:
            return i
    return None


def mapping(all_tables):
    for header, rows in all_tables:
        si = status_index(header)
        if si is not None and rows and any(row and row[0].startswith("§") for row in rows):
            return si, rows
    return None, None


def check(root):
    doc = project(root)
    path = within(root, "spec/domain_profile.md")
    require(path.is_file(), "missing spec/domain_profile.md; run scaffold.py or copy references/domains/_profile_template.md")
    text = path.read_text(encoding="utf-8")
    require(not re.search(r"[⟪⟫]", text), "unfilled domain_profile markers")

    all_tables = tables(text)
    bind = binding(all_tables)
    require(filled(bind.get("pack")), "domain_profile: pack is required (or 'generic')")
    require(filled(bind.get("pack_sha256")) or bind.get("pack") == "generic",
            "domain_profile: pack_sha256 is required to pin the generic pack")
    require(filled(bind.get("失效条件") or bind.get("invalidate_on")),
            "domain_profile: 失效条件/invalidate_on is required (stale profile is a silent failure)")

    pack = bind["pack"].strip()
    if pack == "generic":
        require(filled(bind.get("缺口") or bind.get("gap")),
                "domain_profile: pack 'generic' requires a 缺口/gap note")
        require(doc["domain"] == "generic", "project.domain must be 'generic' when the profile declares generic")
    else:
        require(doc["domain"] == pack, f"project.domain '{doc['domain']}' != profile pack '{pack}'")
        pack_path = DOMAINS / f"{pack}.md"
        require(pack_path.is_file(), f"unknown domain pack: {pack}")
        declared = bind["pack_sha256"].strip().lower()
        require(re.fullmatch(r"[0-9a-f]{64}", declared), "pack_sha256 must be 64 hex characters")
        actual = hashlib.sha256(pack_path.read_bytes()).hexdigest()
        require(declared == actual,
                f"pack has changed since this profile was written ({declared[:12]}… != {actual[:12]}…); review the profile")

    rows = mapping(all_tables)[1]
    si = mapping(all_tables)[0]
    require(rows is not None, "domain_profile: mapping table over §0–§7 with a 状态 column is required")
    seen = {}
    for row in rows:
        if not row or not row[0].startswith("§"):
            continue
        section = row[0].split()[0].rstrip("：:").strip()
        require(section in SECTIONS, f"domain_profile: unknown section '{section}'")
        require(section not in seen, f"domain_profile: duplicate row {section}")
        seen[section] = row
        status = row[si] if len(row) > si else ""
        require(status in STATUS_INSTANTIATE + STATUS_EXTEND + ("不适用",),
                f"{section}: status must be one of 采用/实例化/扩展/偏离/不适用 (got '{status}')")
        detail = row[si + 1] if len(row) > si + 1 else ""
        locator = row[si + 2] if len(row) > si + 2 else ""
        if status in STATUS_INSTANTIATE:
            require(filled(detail), f"{section}: '{status}' requires the 本文实例 value")
        elif status in STATUS_EXTEND:
            require(filled(locator), f"{section}: '{status}' requires a 定位 (paper page / supp number / derivation)")
        else:
            require(filled(locator) or filled(detail), f"{section}: '不适用' requires a reason")
    missing = [s for s in SECTIONS if s not in seen]
    require(not missing, f"domain_profile: missing rows for {', '.join(missing)}")

    for header, rows_ in all_tables:
        si = status_index(header)
        if si is None or not any("候选" in c for c in header):
            continue
        for row in rows_:
            status = row[si] if len(row) > si else ""
            require(status == "待验证" or status.startswith("已验收"),
                    f"promotion row '{row[0]}': status must be 待验证 or 已验收:<evidence>")
            if status.startswith("已验收"):
                evidence = status.partition(":")[2].strip()
                require(filled(evidence), f"promotion row '{row[0]}': 已验收 requires evidence after ':' (e.g. 已验收:runs/ID/manifest.json)")

    return finish("PASS", f"domain profile pinned to {pack}; structural review only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
