#!/usr/bin/env python3
"""Check absolute effect against a predeclared reference, not a global 5% rule."""
import argparse
import numpy as np
from common import config_for, finish, number, require, run, within


def evaluate(y, cfg):
    y = np.asarray(y, dtype=float).ravel()
    require(y.size >= 3 and np.isfinite(y).all(), "effect needs >=3 finite points")
    expected = number(cfg.get("expected_span"), "expected_span", 0)
    uncertainty = number(cfg.get("uncertainty"), "uncertainty", 0)
    ratio = cfg.get("ratio_bounds")
    require(isinstance(ratio, list) and len(ratio) == 2, "ratio_bounds required")
    lo, hi = number(ratio[0], "ratio min", 0), number(ratio[1], "ratio max", 0)
    require(lo <= hi, "invalid ratio bounds")
    measured = float(np.ptp(y))
    print(f"span={measured:g}, expected={expected:g}, uncertainty={uncertainty:g}")
    if expected == 0:
        return measured <= uncertainty
    return max(0, expected * lo - uncertainty) <= measured <= expected * hi + uncertainty


def check(root, tid):
    cfg = config_for(root, tid, "effect")
    if cfg is None:
        return finish("NOT_APPLICABLE", "effect check disabled with reason in project config")
    with np.load(within(root, cfg.get("file")), allow_pickle=False) as data:
        ok = evaluate(data[cfg["key"]], cfg)
    return finish("PASS" if ok else "FAIL", "configured effect interval")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("target")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.target)))
