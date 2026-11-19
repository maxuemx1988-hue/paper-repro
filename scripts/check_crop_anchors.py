#!/usr/bin/env python3
"""Compatibility entry point for crop provenance validation; performs no OCR."""
from check_visual_crop import check
from common import run
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("crop_image")
    args = parser.parse_args()
    raise SystemExit(run(lambda: check(args.root, args.crop_image)))
