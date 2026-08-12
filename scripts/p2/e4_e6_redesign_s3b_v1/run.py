#!/usr/bin/env python3
"""S3b: readout-resolution ablation (render_downscale 0.25 -> 0.5).

Single deliberate deviation from the sealed v1 fusion contract: the rendered
fusion resolution. Every other frozen parameter (voxel, SMRF, Roofer defaults,
classification boundary) must remain byte-identical, and the wrapped validator
enforces exactly that by normalising only the ablated key before delegating to
the sealed check. Applies identically to E3/E4-v2/E5-v2.
"""
import copy

from scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1 import run as base

base.CONDITIONS = ("E3_GS_image", "E4_V2_STATIC", "E5_V2_F1")

_sealed_validate = base.validate_config
ABLATED_RENDER_DOWNSCALE = 0.5


def validate_config_s3b(config):
    normalised = copy.deepcopy(dict(config))
    fusion = dict(normalised.get("fusion", {}))
    if fusion.get("render_downscale") != ABLATED_RENDER_DOWNSCALE:
        raise RuntimeError("S3b requires the ablated render_downscale 0.5")
    fusion["render_downscale"] = 0.25
    normalised["fusion"] = fusion
    _sealed_validate(normalised)


base.validate_config = validate_config_s3b


if __name__ == "__main__":
    base.main()
