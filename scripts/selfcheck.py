#!/usr/bin/env python3
"""Check resource structure, Python syntax, CLI help and regression tests (not paper physics)."""
import argparse
import ast
from pathlib import Path
import re
import subprocess
import sys


def check(root):
    errors = []
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    if not re.match(r"---\nname: paper-repro\ndescription: .+\n", skill):
        errors.append("invalid skill frontmatter")
    for ref in ("references/protocol.md", "references/checklists.md", "references/spec_template.md",
                "references/report_template.md"):
        if not (root / ref).is_file():
            errors.append(f"missing {ref}")
    for pack in (root / "references/domains").glob("*.md"):
        if pack.name.startswith("_"):
            continue
        text = pack.read_text(encoding="utf-8")
        if any(f"## {i}." not in text for i in range(8)):
            errors.append(f"missing domain sections: {pack}")
        for key in ("pack_version:", "scope_includes:", "scope_excludes:", "verified_cases:"):
            if key not in text:
                errors.append(f"domain pack missing header '{key}': {pack}")
    if not (root / "references/domains/_profile_template.md").is_file():
        errors.append("missing references/domains/_profile_template.md")
    scripts = sorted((root / "scripts").glob("*.py"))
    for path in scripts:
        try:
            text = path.read_text(encoding="utf-8")
            ast.parse(text, filename=str(path))
            # Never execute self, helpers or tests as a CLI.
            if path.name == "selfcheck.py" or 'if __name__ == "__main__":' not in text:
                continue
            result = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True, timeout=10)
            if result.returncode:
                errors.append(f"{path.name} --help: {result.stderr.strip()}")
        except (SyntaxError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{path.name}: {exc}")
    if not list((root / "tests").glob("test_*.py")):
        errors.append("no regression tests found")
    try:
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"], timeout=60)
        if result.returncode:
            errors.append("regression tests failed")
    except subprocess.TimeoutExpired:
        errors.append("regression tests timed out")
    for error in errors:
        print(f"[FAIL] {error}")
    print(f"[{'FAIL' if errors else 'PASS'}] resource structure, syntax, CLI help and regression tests; {len(scripts)} scripts")
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(check(Path(__file__).resolve().parent.parent))
