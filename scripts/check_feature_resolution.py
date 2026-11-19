#!/usr/bin/env python3
"""Require the sampling grid to resolve salient features of the reference curve.

For each salient local extremum in the reference, estimate its half-width and
reject the scan if the grid spacing is larger than half-width / FACTOR.
This prevents "PASS" on grids that skip over narrow peaks/valleys.
"""
from __future__ import annotations

import argparse
import numpy as np

from common import config_for, finish, number, require, run


def half_width(grid, y, i, kind):
    """Return the x-distance from extremum i to the half-height crossing."""
    peak = float(y[i])
    if kind == "max":
        target = peak - 0.5 * (peak - float(y.min()))
        left = right = i
        while left > 0 and y[left] >= target:
            left -= 1
        while right < y.size - 1 and y[right] >= target:
            right += 1
    else:
        target = peak + 0.5 * (float(y.max()) - peak)
        left = right = i
        while left > 0 and y[left] <= target:
            left -= 1
        while right < y.size - 1 and y[right] <= target:
            right += 1
    width = float(grid[right] - grid[left])
    return max(width, 0.0)


def salient_extrema(grid, y, rel=0.05):
    if grid.size < 5:
        return []
    span = float(np.ptp(y))
    if span <= 0:
        return []
    left = y[1:-1] - y[:-2]
    right = y[1:-1] - y[2:]
    bump = ((left > 0) & (right > 0)) | ((left < 0) & (right < 0))
    idx = [int(i) for i in (np.flatnonzero(bump) + 1)]
    out = []
    for k, i in enumerate(idx):
        p = idx[k - 1] if k > 0 else None
        q = idx[k + 1] if k + 1 < len(idx) else None
        yl = y[p] if p is not None else y[0]
        yr = y[q] if q is not None else y[-1]
        if y[i] > yl and y[i] > yr:
            kind, base, prom = "max", max(yl, yr), y[i] - max(yl, yr)
        else:
            kind, base, prom = "min", min(yl, yr), min(yl, yr) - y[i]
        if prom > rel * span:
            out.append((kind, int(i)))
    return out


def check(root, tid):
    cfg = config_for(root, tid, "loss")
    if cfg is None:
        return 0
    import check_loss
    mine_raw, _ = check_loss.load(root, cfg["mine"])
    gt_raw, _ = check_loss.load(root, cfg["gt"])
    # maps/heatmaps have no 1-D sampling axis; the grid-resolution question does not apply
    roles = set((cfg.get("mine") or {}).get("roles") or {}) | set((cfg.get("gt") or {}).get("roles") or {})
    if not {"x", "y"} <= roles:
        print("[DISCLOSURE] feature resolution skipped: %s target carries roles %s, no 1-D sampling axis"
              % (cfg.get("type"), sorted(roles)))
        return 0
    mine = {role: mine_raw[key] for role, key in cfg["mine"]["roles"].items()}
    gt = {role: gt_raw[key] for role, key in cfg["gt"]["roles"].items()}
    factor = number(cfg.get("resolution_factor", 3), "resolution_factor", 0)
    waiver = cfg.get("resolution_not_applicable")
    if waiver:
        require(isinstance(waiver, str) and waiver.strip(), "resolution_not_applicable needs a reason")
        print("[DISCLOSURE] feature resolution waived: " + waiver)
        return 0
    problems = []
    for name, d in (("mine", mine), ("reference", gt)):
        x = np.asarray(d["x"], dtype=float).ravel()
        y = np.asarray(d["y"], dtype=float).ravel()
        require(x.size >= 5 and (np.diff(x) > 0).all(), name + " x must be strictly increasing with >=5 points")
        spacing = float(np.min(np.diff(x)))
        for kind, i in salient_extrema(x, y):
            width = half_width(x, y, i, kind)
            if spacing > width / factor:
                problems.append("%s:%s@%.4g half_width=%.4g spacing=%.4g" % (name, kind, x[i], width, spacing))
    require(not problems, "sampling cannot resolve salient features -> " + "; ".join(problems))
    return finish("PASS", "native grids resolve salient reference features")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("target")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.target)))
