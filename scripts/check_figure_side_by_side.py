#!/usr/bin/env python3
"""Generate a side-by-side image. Generation success is NOT validation."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from common import config_for, finish, run, within


def make_side_by_side(root, tid):
    cfg = config_for(root, tid, "visual")
    if cfg is None:
        return finish("NOT_APPLICABLE", "visual check disabled with reason")
    images = []
    for name in ("crop", "mine_image"):
        with Image.open(within(root, cfg[name])) as im:
            rgb = im.convert("RGB")
            height = min(800, rgb.height)
            images.append(rgb.resize((max(1, round(rgb.width * height / rgb.height)), height)))
    height = max(im.height for im in images)
    canvas = Image.new("RGB", (sum(im.width for im in images) + 60, height + 80), "white")
    draw = ImageDraw.Draw(canvas)
    x = 20
    for im, label in zip(images, ("Paper original", "Reproduced (unverified)")):
        draw.text((x, 15), label, fill="black")
        canvas.paste(im, (x, 50))
        x += im.width + 20
    out = within(root, cfg["comparison_image"])
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"[GENERATED] {out}; run check_figure_validity.py separately")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("target")
    args = parser.parse_args()
    raise SystemExit(run(lambda: make_side_by_side(args.root, args.target)))
