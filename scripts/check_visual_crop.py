#!/usr/bin/env python3
"""Check crop provenance and a recorded review; does not prove a model saw the image."""
import argparse
from pathlib import Path
from PIL import Image
from common import artifact, finish, number, read_json, require, run


def audit_crop(root, crop, expected_x=None, expected_y=None):
    path = Path(root) / crop
    meta = read_json(path.with_suffix(".visual_audit.json"))
    image = artifact(root, meta["image"])
    require(image.resolve() == path.resolve(), "crop path differs from reviewed image")
    artifact(root, meta["pdf"])
    require(type(meta.get("page")) is int and meta["page"] >= 1, "page must be 1-based")
    bbox = meta.get("bbox_pdf")
    require(isinstance(bbox, list) and len(bbox) == 4, "PDF bbox required")
    coords = [number(v, "bbox coordinate") for v in bbox]
    require(coords[0] < coords[2] and coords[1] < coords[3], "invalid PDF bbox")
    require(bool(meta.get("subfigure_id")), "subfigure_id required")
    for key, expected in (("xaxis", expected_x), ("yaxis", expected_y)):
        axis = meta[key]
        require(isinstance(axis.get("label"), str) and axis["label"], f"{key} label required")
        require(isinstance(axis.get("unit"), str), f"{key} unit required (use '1' for dimensionless)")
        limits = axis.get("limits")
        require(isinstance(limits, list) and len(limits) == 2, f"{key} limits required")
        require(number(limits[0], key) < number(limits[1], key), "axis limits must increase")
        require(axis.get("scale") in ("linear", "log"), "axis scale required")
        require(axis["scale"] != "log" or limits[0] > 0, "log axis must be positive")
        if expected is not None:
            require(axis["label"] == expected, f"{key} label mismatch")
    review = meta.get("review", {})
    require(review.get("method") in ("human", "model", "ocr-assisted"), "review method required")
    require(all(review.get(k) for k in ("reviewer", "time", "notes")), "reviewer/time/notes required")
    if review["method"] == "model":
        # a model reading must stay attached to the exact response that produced it:
        # writing method=model by hand is not a review
        vision = meta.get("vision")
        require(isinstance(vision, dict), "model review needs a vision block written by scripts/vision.py audit")
        require(bool(vision.get("model_used")), "vision.model_used required")
        require(vision.get("model_used") == review.get("reviewer"),
                "review.reviewer must name the model that actually answered")
        raw = artifact(root, vision.get("raw"))
        require(raw.is_file(), "vision.raw must be the hash-bound raw response")
    with Image.open(path) as image:
        image.verify()
    return meta


def check(root, crop, x=None, y=None):
    audit_crop(root, crop, x, y)
    return finish("PASS", "crop hashes and recorded review fields valid; visual correctness remains a review responsibility")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("crop_image")
    parser.add_argument("--expected-xlabel")
    parser.add_argument("--expected-ylabel")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.crop_image, args.expected_xlabel, args.expected_ylabel)))
