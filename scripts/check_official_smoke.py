#!/usr/bin/env python3
"""Require a smoke comparison against released official data before long computations.

If the workspace ships official output data (paper/refcode/**), the cheap way to catch a
structural modelling error is to compare a handful of published numbers first, instead of
guessing at numerics.  This check enforces that such a comparison exists and is recorded.

spec/provenance.json must contain:
    "official_smoke": {
        "file": "paper/refcode/<...>.mat",     # released data used as the reference
        "sha256": "<hash of that file>",
        "compared": ["V1", "V2", ...],          # non-empty list of quantity names
        "data_file": "data/mine/smoke_official.npz",
        "passed": true,
        "date": "<ISO date>",
        "tolerance": "<string: acceptance basis>"
    }
The data_file must exist, be an NPZ/JSON with at least one finite finite-size array.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from common import finish, read_json, require, run, sha256, within

OFFICIAL_DIR = "paper/refcode"
SUFFIXES = {".mat", ".npz", ".csv", ".dat", ".txt"}
# released *data* only: package manifests and docs share the same suffixes and
# must not be mistaken for published output (a requirements.txt used to block
# every workspace that vendored a third-party repo)
NOT_DATA = ("requirements", "readme", "license", "licence", "setup", "changelog",
            "contributing", "install", "makefile", "pyproject", "environment")


def official_files(root):
    base = Path(root) / OFFICIAL_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*")
                  if p.suffix.lower() in SUFFIXES
                  and not p.name.lower().startswith(NOT_DATA))


def check(root):
    files = official_files(root)
    if not files:
        return finish("NOT_APPLICABLE", "no released official data under paper/refcode")

    prov = read_json(within(root, "spec/provenance.json"))
    smoke = prov.get("official_smoke")
    require(isinstance(smoke, dict),
            "official data present: record a smoke comparison in provenance.official_smoke "
            "(compare a few published numbers before any long computation)")

    ref = within(root, smoke.get("file"))
    require(ref.is_file(), f"official_smoke.file missing: {smoke.get('file')}")
    require(smoke.get("sha256") == sha256(ref), "official_smoke.sha256 mismatch (data changed)")
    compared = smoke.get("compared")
    require(isinstance(compared, list) and compared and all(isinstance(c, str) and c.strip() for c in compared),
            "official_smoke.compared must be a non-empty list of quantity names")
    require(bool(smoke.get("tolerance")), "official_smoke.tolerance (acceptance basis) required")
    require(bool(smoke.get("date")), "official_smoke.date required")
    require(smoke.get("passed") is True,
            "official_smoke.passed must be true: the smoke comparison did not agree")

    data_path = within(root, smoke.get("data_file"))
    require(data_path.is_file(), f"official_smoke.data_file missing: {smoke.get('data_file')}")
    arrays = []
    if data_path.suffix == ".npz":
        with np.load(data_path, allow_pickle=False) as data:
            items = [(k, data[k]) for k in data.files if k not in ("units", "meta")]
    else:
        items = [(k, v) for k, v in read_json(data_path).items() if k not in ("units", "meta")]
    for _, value in items:
        try:
            arr = np.asarray(value, dtype=float).ravel()
        except (TypeError, ValueError):
            continue          # non-numeric bookkeeping such as label strings
        if arr.size:
            arrays.append(arr)
    require(arrays and all(a.size and np.isfinite(a).all() for a in arrays),
            "official_smoke.data_file must contain finite numeric arrays")
    return finish("PASS",
                  f"smoke comparison recorded against {Path(smoke['file']).name} "
                  f"({len(compared)} quantities)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
