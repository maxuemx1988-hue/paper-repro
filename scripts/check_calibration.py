#!/usr/bin/env python3
"""Evaluate configured calibration assertions; not a proof of model correctness."""
import argparse
import numpy as np
from common import finish, number, project, read_json, require, run, within

CATEGORIES = {"limit", "invariant", "paper"}


def check_one(a, root):
    require(isinstance(a, dict), "assertion must be an object")
    require(a.get("category") in CATEGORIES, "invalid calibration category")
    require(bool(a.get("id")) and bool(a.get("desc")), "assertion id/desc required")
    path = within(root, a.get("file"))
    key = a.get("key")
    require(isinstance(key, str) and bool(key), "assertion key required")
    if path.suffix == ".npz":
        with np.load(path, allow_pickle=False) as data:
            arr = np.asarray(data[key], dtype=float).ravel()
    elif path.suffix == ".json":
        arr = np.asarray(read_json(path)[key], dtype=float).ravel()
    else:
        require(False, "calibration supports NPZ or JSON")
    require(arr.size > 0 and np.isfinite(arr).all(), "empty/nonfinite calibration data")
    kind = a.get("kind")
    if kind == "range":
        lo = number(a.get("min"), "min")
        hi = number(a.get("max"), "max")
        require(lo <= hi, "min > max")
        return bool(((arr >= lo) & (arr <= hi)).all())
    require(kind in ("value", "abs", "identity"), "unknown assertion kind")
    if "index" in a:
        i = a["index"]
        require(type(i) is int and 0 <= i < arr.size, "invalid index")
        value = float(arr[i])
    else:
        require(arr.size == 1, "scalar assertion needs index for arrays")
        value = float(arr[0])
    expected = number(a.get("expect"), "expect")
    atol = number(a.get("atol", 0), "atol", 0)
    rtol = number(a.get("rtol", 0), "rtol", 0) if kind == "value" else 0
    require(atol + rtol * abs(expected) > 0, "positive effective tolerance required")
    return abs(value - expected) <= atol + rtol * abs(expected)


def check(root):
    project(root)
    cfg = read_json(within(root, "spec/calibration.json"))
    assertions = cfg.get("assertions")
    require(isinstance(assertions, list) and assertions, "assertions must be nonempty")
    waived = cfg.get("not_applicable", {})
    require(isinstance(waived, dict) and set(waived) <= CATEGORIES, "invalid category waivers")
    require(all(isinstance(v, str) and v.strip() for v in waived.values()), "waivers need reasons")
    categories = {a.get("category") for a in assertions if isinstance(a, dict)}
    require(CATEGORIES <= categories | set(waived), "missing limit/invariant/paper coverage or reasoned waiver")
    require(not categories.intersection(waived), "category cannot be both tested and waived")
    ids = [a.get("id") for a in assertions]
    require(len(set(ids)) == len(ids), "duplicate assertion ids")
    failed = []
    for a in assertions:
        ok = check_one(a, root)
        print(f"  {'PASS' if ok else 'FAIL'} {a['id']}: {a['desc']}")
        if not ok:
            failed.append(a["id"])
    return finish("FAIL" if failed else "PASS", "configured calibration assertions evaluated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
