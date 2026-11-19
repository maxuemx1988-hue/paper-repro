#!/usr/bin/env python3
"""Deprecated: whole-image alpha blending is not an acceptance check."""
import argparse
from common import finish

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?")
    parser.parse_args()
    raise SystemExit(finish("INCOMPLETE", "deprecated; use side-by-side generation or explicit common-axis data plots"))
