"""S3c: Stage-3 readout for the v3 (TIN 0.25m prior) arms."""
from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1 import run as base


base.CONDITIONS = ("E4_V3_TIN025", "E5_V3_F1_TIN025")


if __name__ == "__main__":
    base.main()
