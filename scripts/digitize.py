#!/usr/bin/env python3
"""从图片中按颜色提取曲线，用两点标定换算成数据坐标，输出 CSV。

    python digitize.py fig3.png \
        --bbox 120,80,860,600 \
        --xcal 120,0 --xcal 860,8 \
        --ycal 600,0 --ycal 80,1.0 \
        --color "#1f77b4" --tol 60 --xunit 1 --yunit 1 -o data/ground_truth/fig3.csv

参数说明：
  --bbox   绘图区像素框 x0,y0,x1,y1（左上角原点，含边界）；省略则用整图
  --xcal   "像素,数值"，给两次，线性插值（--logx 时为对数刻度）
  --ycal   同上，注意图像 y 向下增大
  --color  目标颜色 "#rrggbb"，或用 --gray 取深色（黑线）
  --tol    RGB 欧氏距离容差（0-441），默认 60
  --xmin/--xmax  可裁剪数据范围
输出：两列 CSV (x,y) + 同名 .meta.json 记录标定与不确定度。
不插值、不拟合、不平滑。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
from common import sha256


def load_rgb(path: pathlib.Path) -> np.ndarray:
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("[ERR] 需要 Pillow：pip install pillow")
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=float)


def parse_pair(s: str) -> tuple[float, float]:
    a, b = s.split(",")
    return float(a), float(b)


def to_data(px: np.ndarray, p1: float, v1: float, p2: float, v2: float, log: bool) -> np.ndarray:
    if p2 == p1:
        raise SystemExit("[ERR] 标定两点像素相同")
    if not np.isfinite([p1, p2, v1, v2]).all():
        raise SystemExit("[ERR] 标定点必须有限")
    if log:
        if v1 <= 0 or v2 <= 0:
            raise SystemExit("[ERR] 对数标定值必须为正")
        lv1, lv2 = np.log10(v1), np.log10(v2)
        out = lv1 + (px - p1) / (p2 - p1) * (lv2 - lv1)
        return np.power(10.0, out)
    return v1 + (px - p1) / (p2 - p1) * (v2 - v1)


def main() -> int:
    ap = argparse.ArgumentParser(description="曲线数字化")
    ap.add_argument("image")
    ap.add_argument("--bbox", default=None, help="x0,y0,x1,y1")
    ap.add_argument("--xcal", action="append", required=True, help='"px,val"（两次）')
    ap.add_argument("--ycal", action="append", required=True, help='"py,val"（两次）')
    ap.add_argument("--color", default=None, help='"#rrggbb"')
    ap.add_argument("--gray", action="store_true", help="取深色像素（黑线）")
    ap.add_argument("--gray-thr", type=float, default=110.0, help="灰度阈值")
    ap.add_argument("--tol", type=float, default=60.0)
    ap.add_argument("--logx", action="store_true")
    ap.add_argument("--logy", action="store_true")
    ap.add_argument("--xunit", required=True, help="横轴单位；无量纲写 1")
    ap.add_argument("--yunit", required=True, help="纵轴单位；无量纲写 1")
    ap.add_argument("--xmin", type=float, default=None)
    ap.add_argument("--xmax", type=float, default=None)
    ap.add_argument("--min-pixels", type=int, default=2, help="每列最少命中像素数")
    ap.add_argument("--gap-px", type=float, default=2.0, help="行间隔超过此值视为新簇（不连续）")
    ap.add_argument("--on-multi", choices=["skip", "all"], default="skip",
                    help="一列有多簇时：skip=跳过（默认，台阶处无单一真值）; all=全部输出")
    ap.add_argument("--max-span-px", type=float, default=8.0,
                    help="单列纵向跨度超过此值则视为竖直线段（默认跳过）")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    if len(args.xcal) != 2 or len(args.ycal) != 2:
        raise SystemExit("[ERR] --xcal 与 --ycal 各需两次")

    img = load_rgb(pathlib.Path(args.image).expanduser())
    h, w, _ = img.shape

    if args.bbox:
        x0, y0, x1, y1 = (int(float(v)) for v in args.bbox.split(","))
        x0, x1 = max(0, min(x0, x1)), min(w, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(h, max(y0, y1))
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    sub = img[y0:y1, x0:x1]

    if args.color:
        hexs = args.color.lstrip("#")
        target = np.array([int(hexs[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)
        dist = np.sqrt(((sub - target) ** 2).sum(axis=2))
        mask = dist <= args.tol
    elif args.gray:
        gray = sub.mean(axis=2)
        mask = gray <= args.gray_thr
    else:
        raise SystemExit("[ERR] 需要 --color 或 --gray")

    hit_cols = mask.sum(axis=0)
    xs_px, ys_px = [], []
    n_multi = 0
    n_vert = 0
    skipped_columns = []
    for c in range(mask.shape[1]):
        if hit_cols[c] < args.min_pixels:
            continue
        rows = np.nonzero(mask[:, c])[0].astype(float)
        # 按行间隔分簇：一列里出现分离的多簇 = 曲线在此处不连续（台阶/回线）
        gaps = np.diff(rows) > args.gap_px
        clusters = np.split(rows, np.nonzero(gaps)[0] + 1)
        clusters = [cl for cl in clusters if cl.size >= args.min_pixels]
        if not clusters:
            continue
        if len(clusters) > 1:
            n_multi += 1
            if args.on_multi == "skip":
                skipped_columns.append(c + x0)
                continue
            for cl in clusters:
                xs_px.append(c + x0)
                ys_px.append(float(np.median(cl)) + y0)
            continue
        span = float(clusters[0].max() - clusters[0].min())
        if span > args.max_span_px:
            # 单簇但纵向跨度过大 = 竖直线段（台阶/回线的陡峭部分），无单一真值
            n_vert += 1
            if args.on_multi == "skip":
                skipped_columns.append(c + x0)
                continue
            xs_px.append(c + x0)
            ys_px.append(float(np.median(clusters[0])) + y0)
            continue
        xs_px.append(c + x0)
        ys_px.append(float(np.median(clusters[0])) + y0)
    if not xs_px:
        raise SystemExit("[ERR] 没有命中像素：检查 --color / --tol / --bbox")
    xs_px = np.asarray(xs_px, float)
    ys_px = np.asarray(ys_px, float)

    xp1, xv1 = parse_pair(args.xcal[0])
    xp2, xv2 = parse_pair(args.xcal[1])
    yp1, yv1 = parse_pair(args.ycal[0])
    yp2, yv2 = parse_pair(args.ycal[1])

    if args.on_multi == "all":
        raise SystemExit("[ERR] 多分支不能合并为单值曲线；请分别提取为不同目标")
    x = to_data(xs_px, xp1, xv1, xp2, xv2, args.logx)
    y = to_data(ys_px, yp1, yv1, yp2, yv2, args.logy)

    order = np.argsort(x, kind="stable")
    x, y = x[order], y[order]

    if args.xmin is not None:
        k = x >= args.xmin
        x, y = x[k], y[k]
    if args.xmax is not None:
        k = x <= args.xmax
        x, y = x[k], y[k]

    if x.size < 3 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise SystemExit("[ERR] 裁剪后至少需要 3 个有限数据点")
    pixel_step = np.abs(np.diff(xs_px[order]))
    if args.xmin is not None or args.xmax is not None:
        pixel_step = None
    out = pathlib.Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(out, np.column_stack([x, y]), delimiter=",", header="x,y", comments="", fmt="%.10g")

    dx_per_px = abs((xv2 - xv1) / (xp2 - xp1)) if not args.logx else None
    dy_per_px = abs((yv2 - yv1) / (yp2 - yp1)) if not args.logy else None
    meta = {
        "image": str(pathlib.Path(args.image).resolve()),
        "image_sha256": sha256(args.image),
        "units": {"x": args.xunit, "y": args.yunit},
        "has_gaps": bool(skipped_columns),
        "excluded_x": to_data(np.asarray(skipped_columns, float), xp1, xv1, xp2, xv2, args.logx).tolist(),
        "max_sample_gap": float(np.diff(x).max()),
        "interpolation_policy": "不得跨越被跳过的列；缺口两侧应拆分成独立目标",
        "pixel_step": pixel_step.tolist() if pixel_step is not None else None,
        "bbox": [x0, y0, x1, y1],
        "xcal": [[xp1, xv1], [xp2, xv2]],
        "ycal": [[yp1, yv1], [yp2, yv2]],
        "logx": args.logx,
        "logy": args.logy,
        "color": args.color,
        "gray": args.gray,
        "tol": args.tol,
        "n_points": int(x.size),
        "n_multi_cluster_cols": int(n_multi),
        "n_vertical_cols": int(n_vert),
        "max_span_px": args.max_span_px,
        "on_multi": args.on_multi,
        "gap_px": args.gap_px,
        "x_range": [float(x.min()), float(x.max())],
        "y_range": [float(y.min()), float(y.max())],
        "uncertainty_note": "按 1 像素换算：dx_per_px=%s dy_per_px=%s；线宽与抗锯齿会引入同量级误差" % (dx_per_px, dy_per_px),
        "dx_per_px": dx_per_px,
        "dy_per_px": dy_per_px,
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[digitize] {out}  n={x.size}")
    print(f"           x∈[{x.min():g}, {x.max():g}]  y∈[{y.min():g}, {y.max():g}]")
    if n_multi or n_vert:
        print(f"           跳过：多簇列 {n_multi} 个，竖直线段列 {n_vert} 个（--on-multi all 可强制输出）")
    print(f"           不确定度 ≈ dx={dx_per_px}, dy={dy_per_px} (每像素)")
    print(f"           meta → {out.with_suffix('.meta.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
