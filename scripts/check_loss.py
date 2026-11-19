#!/usr/bin/env python3
"""Evaluate a predeclared curve/scalar/table/map protocol. No implicit units or fitting."""
import argparse
import json
from pathlib import Path
import numpy as np
from common import config_for, finish, number, read_json, require, run, sha256, target, within

def salient_extrema(x, y, rel=0.05):
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.size < 5:
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
            kind = "max"
            base = max(yl, yr)
            prom = y[i] - base
        else:
            kind = "min"
            base = min(yl, yr)
            prom = base - y[i]
        if prom > rel * span:
            out.append((kind, float(x[i])))
    return out

def load(root, spec):
    path = within(root, spec.get("file"))
    units_claim = spec.get("units")
    keys, roles = spec.get("keys"), spec.get("roles")
    require(isinstance(keys, list) and keys and all(isinstance(k, str) for k in keys), "array keys required")
    require(isinstance(roles, dict) and "y" in roles and set(roles) <= {"x", "y", "coordinates"}, "canonical role mapping required")
    require(set(roles.values()) <= set(keys), "role refers to absent key")
    require(isinstance(units_claim, dict) and set(roles.values()) <= set(units_claim), "explicit units required for every role")
    require(all(isinstance(v, str) and v.strip() for v in units_claim.values()), "unit must be nonempty (use '1' for dimensionless)")
    if path.suffix == ".npz":
        with np.load(path, allow_pickle=False) as data:
            arrays = {k: np.asarray(data[k], dtype=float) for k in spec["keys"]}
            units = json.loads(str(data["units"])) if "units" in data else None
    else:
        raw = np.genfromtxt(path, delimiter=spec.get("delimiter", ","), names=True)
        arrays = {k: np.atleast_1d(np.asarray(raw[k], dtype=float)) for k in spec["keys"]}
        metadata = read_json(path.with_suffix(".meta.json"))
        units = metadata.get("units")
        if metadata.get("has_gaps"):
            domain = spec.get("valid_domain")
            require(isinstance(domain, list) and len(domain) == 2, "digitized gaps require a separate valid_domain segment per target")
            lo, hi = number(domain[0], "segment lo"), number(domain[1], "segment hi")
            require(lo < hi, "invalid segment domain")
            require(not any(lo <= v <= hi for v in metadata.get("excluded_x", [])), "segment crosses excluded digitization columns")
            require("excluded_x" in metadata, "gap locations unavailable; re-extract reference")
    require(units is not None and all(units.get(k) == v for k, v in spec["units"].items()), f"{path}: units metadata mismatch")
    require(all(a.size and np.isfinite(a).all() for a in arrays.values()), f"{path}: empty/nonfinite data; missing values must be resolved explicitly")
    return arrays, path


def curve_grid(mine, gt, cfg):
    xm, ym = mine["x"].ravel(), mine["y"].ravel()
    xg, yg = gt["x"].ravel(), gt["y"].ravel()
    for x, y in ((xm, ym), (xg, yg)):
        require(x.size == y.size and x.size >= 3 and (np.diff(x) > 0).all(), "curve x must be strictly increasing, unique, with >=3 points")
    domain = cfg.get("domain")
    require(isinstance(domain, list) and len(domain) == 2, "domain=[lo,hi] required")
    lo, hi = number(domain[0], "domain lo"), number(domain[1], "domain hi")
    require(lo < hi, "invalid domain")
    count = cfg.get("grid_points")
    require(type(count) is int and count >= 3, "grid_points must be integer >=3")
    gap = number(cfg.get("max_gap"), "max_gap", 0)
    require(gap > 0, "max_gap must be positive; split discontinuous curves into separate targets")
    coverage_min = number(cfg.get("min_coverage"), "min_coverage", 0, 1)
    require(coverage_min > 0, "min_coverage must be positive")
    left, right = max(lo, xm[0], xg[0]), min(hi, xm[-1], xg[-1])
    coverage = max(0, right - left) / (hi - lo)
    require(coverage + 1e-12 >= coverage_min, f"insufficient coverage: {coverage:.3%} < {coverage_min:.3%}")
    for x in (xm, xg):
        touches = (x[:-1] < right) & (x[1:] > left)
        require(not (np.diff(x)[touches] > gap).any(), "sampling gap exceeds max_gap; no interpolation across missing segments")
    grid = np.linspace(lo, hi, count)
    grid = grid[(grid >= left) & (grid <= right)]
    require(grid.size >= 3, "too few covered comparison grid points")
    return grid, np.interp(grid, xm, ym), np.interp(grid, xg, yg), coverage


def evaluate(mine, gt, cfg, mode="quantitative"):
    kind = cfg.get("type")
    require(kind in ("curve", "scalar", "table", "map"), "invalid validation type")
    grid, coverage = None, 1.0
    if kind == "curve":
        grid, ym, yg, coverage = curve_grid(mine, gt, cfg)
    else:
        ym, yg = mine["y"], gt["y"]
        require(ym.shape == yg.shape, "array shapes differ")
        if kind == "scalar":
            require(ym.size == 1, "scalar protocol needs exactly one value")
        else:
            require("coordinates" in mine and "coordinates" in gt, "table/map require coordinates (including row/column or axis identities)")
            require(mine["coordinates"].shape == gt["coordinates"].shape and np.array_equal(mine["coordinates"], gt["coordinates"]), "coordinate/order mismatch; resampling must be explicit")
    scale = number(cfg.get("scale"), "scale", 0)
    require(scale > 0, "scale must be positive")
    number(cfg.get("reference_uncertainty"), "reference_uncertainty", 0)
    require(bool(cfg.get("threshold_basis")), "threshold_basis required")
    metrics = cfg.get("metrics")
    require(isinstance(metrics, dict) and metrics, "metrics required")
    require(set(metrics) <= {"rms_norm", "min_r", "amp_ratio", "peak", "peak_not_applicable"}, "unknown metric")
    if mode == "quantitative":
        require("rms_norm" in metrics, "quantitative protocol requires rms_norm")
    else:
        require({"min_r", "amp_ratio"} <= set(metrics), "qualitative protocol requires min_r AND amp_ratio")
    rms = float(np.sqrt(np.mean(((ym - yg) / scale) ** 2)))
    result = {"rms_norm": rms, "coverage": coverage}
    failed = []
    if "rms_norm" in metrics:
        if rms > number(metrics["rms_norm"], "rms_norm tolerance", 0):
            failed.append("rms_norm")
    if "min_r" in metrics:
        cutoff = number(metrics["min_r"], "min_r", -1, 1)
        require(np.std(ym) > 0 and np.std(yg) > 0, "correlation undefined for constant data")
        result["r"] = float(np.corrcoef(ym.ravel(), yg.ravel())[0, 1])
        if result["r"] < cutoff:
            failed.append("min_r")
    if "amp_ratio" in metrics:
        bounds = metrics["amp_ratio"]
        require(isinstance(bounds, list) and len(bounds) == 2, "amp_ratio needs [min,max]")
        lo, hi = number(bounds[0], "amp min", 0), number(bounds[1], "amp max", 0)
        require(lo <= hi and np.ptp(yg) > 0, "invalid amplitude bounds or constant reference")
        result["amp_ratio"] = float(np.ptp(ym) / np.ptp(yg))
        if not lo <= result["amp_ratio"] <= hi:
            failed.append("amp_ratio")
    peaks = metrics.get("peak")
    if peaks is not None:
        require(grid is not None, "peak metric only supports curves")
        specs = peaks if isinstance(peaks, list) else [peaks]
        require(isinstance(specs, list) and specs, "peak must be an object or a nonempty list")
        for index, p in enumerate(specs):
            require(isinstance(p, dict), "peak entry must be an object")
            require(p.get("kind") in ("max", "min"), "peak kind must be max/min")
            window = p.get("window")
            require(isinstance(window, list) and len(window) == 2, "peak window required")
            low = number(window[0], "peak window lo")
            high = number(window[1], "peak window hi")
            require(grid[0] <= low < high <= grid[-1], "peak window outside covered domain")
            mask = (grid >= low) & (grid <= high)
            require(mask.sum() >= 3, "peak window needs >=3 grid points")
            x = grid[mask]
            a = ym[mask]
            b = yg[mask]
            extremum = np.argmax if p["kind"] == "max" else np.argmin
            i = int(extremum(a))
            j = int(extremum(b))
            suffix = "" if len(specs) == 1 else str(index + 1)
            dx = float(abs(x[i] - x[j]))
            dy = float(abs(a[i] - b[j]))
            result["peak" + suffix + "_dx"] = dx
            result["peak" + suffix + "_dy"] = dy
            if dx > number(p.get("x_tol"), "peak x_tol", 0) or dy > number(p.get("y_tol"), "peak y_tol", 0):
                failed.append("peak" + suffix)
    if "peak_not_applicable" in metrics:
        require(metrics.get("peak") is None, "conflict")
        reason = metrics["peak_not_applicable"]
        require(isinstance(reason, str) and reason.strip(), "reason")
        print("[DISCLOSURE] peak windows waived: " + reason)
    elif grid is not None:
        declared = metrics.get("peak")
        specs = declared if isinstance(declared, list) else ([declared] if declared else [])
        uncovered = []
        for kind, pos in salient_extrema(grid, yg):
            if not any(s.get("kind") == kind and s["window"][0] <= pos <= s["window"][1] for s in specs):
                uncovered.append(kind + "@" + format(pos, ".4g"))
        require(not uncovered, "salient extrema lack declared peak windows: " + ", ".join(uncovered))
    require(all(np.isfinite(v) for v in result.values()), "nonfinite computed metrics")
    return {"metrics": result, "failed": failed}


def check(root, tid, report=None):
    item = target(root, tid)
    cfg = config_for(root, tid, "loss")
    require(cfg["type"] == item["type"], "target/protocol type mismatch")
    if cfg["type"] == "curve":
        for spec in (cfg["mine"], cfg["gt"]):
            if "valid_domain" in spec:
                require(spec["valid_domain"] == cfg["domain"], "segment valid_domain must equal protocol domain")
    mine, mp = load(root, cfg["mine"])
    gt, gp = load(root, cfg["gt"])
    role_units = [{role: spec["units"][key] for role, key in spec["roles"].items()} for spec in (cfg["mine"], cfg["gt"])]
    require(role_units[0] == role_units[1], "input role units differ; convert explicitly")
    # The public keys map canonical roles to stored array names.
    mine = {role: mine[key] for role, key in cfg["mine"]["roles"].items()}
    gt = {role: gt[key] for role, key in cfg["gt"]["roles"].items()}
    result = evaluate(mine, gt, cfg, item["mode"])
    result.update(target=tid, status="FAIL" if result["failed"] else "PASS", mode=item["mode"],
                  validation_subject=item["validation_subject"],
                  mine_sha256=sha256(mp), gt_sha256=sha256(gp),
                  config_sha256=sha256(within(root, item["checks"]["loss"]["config"])))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if report:
        out = Path(report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return finish(result["status"], f"{item['mode']} protocol only; not an overall reproduction verdict")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("target")
    parser.add_argument("--report")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.target, args.report)))

