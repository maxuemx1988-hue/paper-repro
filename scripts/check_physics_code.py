#!/usr/bin/env python3
"""Check simulation code for forbidden hardcoded fits and syntax."""
import argparse
import ast
from pathlib import Path
from common import Incomplete, run, within

FORBIDDEN_TARGETS = {"rxx", "r_xx", "rxy", "r_xy", "conductance", "trans_fit", "fit_curve"}
FORBIDDEN_FUNCS = {"exp", "gaussian", "polyfit"}


def check_directory(root):
    code_dir = Path(root) / "code"
    if not code_dir.exists():
        raise Incomplete(f"code directory {code_dir} does not exist")
    py_files = list(code_dir.rglob("*.py"))
    if not py_files:
        raise Incomplete("no python files in code directory")

    has_syntax_error = False
    for py in py_files:
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as e:
            print(f"[FAIL] syntax error in {py.name}: {e}")
            has_syntax_error = True
            continue

        # AST 遍历检查观测量硬编码拟合
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = {t.id.lower() for t in node.targets if isinstance(t, ast.Name)}
                if targets.intersection(FORBIDDEN_TARGETS):
                    val_str = ast.unparse(node.value).lower()
                    if any(f"{fn}(" in val_str for fn in FORBIDDEN_FUNCS):
                        raise Incomplete(f"forbidden hardcoded fit in {py.name}: assigning '{ast.unparse(node.value)}' to physical observable {targets}")

    if has_syntax_error:
        return 1
    print(f"[PASS] physics code audit passed: {len(py_files)} files verified")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check_directory(args.root)))
