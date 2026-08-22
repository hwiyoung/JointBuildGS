#!/usr/bin/env python3
"""Export the D2a GS surfaces (delta=0 anchor and delta=0.5 smoke) as
viewer-local per-building crops for the 8882 conditions viewer, so the
"does the GS fusion show a displacement?" question is answerable by eye.

Footprint+3 m crop for display context (class byte 6 for roof-ish display);
same 55-view median-depth fusion as the D2a readout. GPU, in-container.
Non-confirmatory; scientific_verdict stays null.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.p2.e4_e6_redesign_s3_v1.build_viewer_assets import write_ply
from scripts.p2.journal1_phase_d_v1.d2a_readout import (
    J1,
    SID,
    VIEWER_ORIGIN,
    corridor_to_viewer,
    fuse_checkpoint,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-checkpoint", required=True)
    parser.add_argument("--anchor-checkpoint", required=True)
    parser.add_argument("--out-root", required=True)
    args = parser.parse_args()
    import shapely
    from shapely.affinity import translate
    from shapely.geometry import shape

    payload = json.load(open(J1["footprints_geojson"]))
    feature = next(f for f in payload["features"] if f["properties"]["stable_id"] == SID)
    index = int(feature["properties"]["population_index"])
    poly = translate(shape(feature["geometry"]).buffer(3.0),
                     xoff=-VIEWER_ORIGIN[0], yoff=-VIEWER_ORIGIN[1])

    for label, ckpt in (("GS55_dx050", args.smoke_checkpoint),
                         ("GS55_0", args.anchor_checkpoint)):
        viewer = corridor_to_viewer(fuse_checkpoint(Path(ckpt)))
        inside = shapely.contains_xy(poly, viewer[:, 0], viewer[:, 1])
        crop = viewer[inside]
        out = Path(args.out_root) / label / f"B{index:03d}_{SID}.points.ply"
        rgb = np.full((len(crop), 3), 200, dtype=np.uint8)
        cls = np.full(len(crop), 6, dtype=np.uint8)
        write_ply(out, crop, rgb, cls)
        print(f"[d2a-export] {label}: {len(crop)} pts -> {out}")


if __name__ == "__main__":
    main()
