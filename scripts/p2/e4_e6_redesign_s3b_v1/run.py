"""S3b: readout-resolution ablation (render_downscale 0.5) for E3/E4v2/E5v2."""
from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1 import run as base


base.CONDITIONS = ("E3_GS_image", "E4_V2_STATIC", "E5_V2_F1")


if __name__ == "__main__":
    base.main()
