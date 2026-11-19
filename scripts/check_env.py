#!/usr/bin/env python3
"""Compare explicit environment claims to simulation-produced runtime metadata."""
import argparse
import numpy as np
from common import artifact, finish, project, read_json, require, run, sha256, within


def check(root):
    cfg = read_json(within(root, project(root)["environment"]))
    metadata_path = artifact(root, cfg["runtime"])
    actual = read_json(metadata_path)
    expected = cfg.get("expected")
    require(isinstance(expected, dict) and {"python", "executable", "packages", "solver", "dtypes"} <= set(expected), "explicit python/executable/packages/solver/dtypes claims required")
    require(all(expected[k] for k in expected), "empty environment claims")
    require(isinstance(expected["packages"], dict), "expected packages must map names to exact versions")
    require(isinstance(expected["dtypes"], dict) and expected["dtypes"], "dtypes must map data keys to dtypes")
    bad = []
    for key, claim in expected.items():
        if actual.get(key) != claim:
            bad.append(f"{key}: expected {claim!r}, actual {actual.get(key)!r}")
    data_path = artifact(root, actual["data"])
    with np.load(data_path, allow_pickle=False) as data:
        for key, dtype in expected["dtypes"].items():
            if str(data[key].dtype) != dtype:
                bad.append(f"{key}: stored dtype {data[key].dtype} != {dtype}")
    require(isinstance(actual.get("solver"), str) and actual["solver"], "simulation must record actual solver entry point")
    manifest = read_json(artifact(root, cfg["run"]))
    require(manifest.get("returncode") == 0, "runtime metadata must come from successful run")
    for path in (metadata_path, data_path):
        name = str(path.relative_to(within(root, ".")))
        require(manifest.get("outputs", {}).get(name) == sha256(path), f"run does not bind {name}")
    for message in bad:
        print(message)
    return finish("FAIL" if bad else "PASS", "runtime metadata and stored dtypes match claims; solver field remains simulation-reported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root)))
