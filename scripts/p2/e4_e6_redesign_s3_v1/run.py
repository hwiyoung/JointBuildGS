#!/usr/bin/env python3
"""S3 adapter for the frozen rendered-depth shared-footprint Stage-3 pipeline.

Runs the sealed 199-building fusion -> SMRF -> Roofer chain over the two S2
arms (E4_V2_STATIC, E5_V2_F1) with the exact shared standard footprint.
"""
from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1 import run as base


base.CONDITIONS = ("E4_V2_STATIC", "E5_V2_F1")


if __name__ == "__main__":
    base.main()
