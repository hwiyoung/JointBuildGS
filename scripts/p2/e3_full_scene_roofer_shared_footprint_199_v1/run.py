#!/usr/bin/env python3
"""E3-only adapter for the frozen rendered-depth shared-footprint Stage-3 pipeline."""
from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1 import run as base


base.CONDITIONS = ("E3_GS_image",)


if __name__ == "__main__":
    base.main()
