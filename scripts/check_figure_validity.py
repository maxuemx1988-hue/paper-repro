#!/usr/bin/env python3
"""Check figure validity and visibility against plot metadata."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image
from common import Incomplete, config_for, project, read_json, run, within


def check(root, tid):
    cfg = config_for(root, tid, "visual")
    if cfg is None:
        return 0
    meta = read_json(within(root, cfg["plot_metadata"]))
    data = np.load(within(root, meta["data"]["file"]))
    y = np.asarray(data[meta["ykey"]], dtype=float)
    if not np.all(np.isfinite(y)):
        raise Incomplete("non-finite values in plotted data")

    # 通用平线/死线检查 (Dead Line Guard)
    span = float(np.max(y) - np.min(y))
    mean_val = float(np.mean(y))
    std_val = float(np.std(y))
    if span < 1e-6 and len(y) > 2:
        raise Incomplete(f"dead flat line detected (span={span:.2e}): physical response missing")

    ymin, ymax = meta["yaxis"]["limits"]
    visible = np.sum((y >= ymin) & (y <= ymax))
    min_visible = cfg.get("min_visible", 1)
    if min_visible <= 1:
        needed = max(1, round(min_visible * len(y)))
    else:
        needed = int(min_visible)
    if visible < needed:
        raise Incomplete(f"only {visible}/{len(y)} plotted points inside visible axis limits")
    with Image.open(within(root, cfg["mine_image"])) as im:
        if im.width < 50 or im.height < 50:
            raise Incomplete(f"image {im.size} too small to show figure")

    # 论文图复现硬性要求：paper_figure 非空时，必须有论文原图与已生成的并排对比图。
    doc = project(root)
    target = next((t for t in doc["targets"] if t["id"] == tid), None)
    if target and target.get("paper_figure"):
        for key in ("crop", "comparison_image"):
            path = within(root, cfg.get(key, ""))
            if not path.is_file():
                raise Incomplete(
                    f"paper_figure={target['paper_figure']} 要求已有 {key} 并排对比产物: {cfg.get(key)}")
            with Image.open(path) as im:
                if im.width < 50 or im.height < 50:
                    raise Incomplete(f"{key} {im.size} too small for a paper comparison")
    print(f"[PASS] figure {tid} validated: {visible}/{len(y)} points visible inside [{ymin}, {ymax}]")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("target")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.target)))
