#!/usr/bin/env python3
"""Record whether preserved E4/E5/E6 conditions used ground-truth depth."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ARTIFACTS = Path("/artifacts/JointBuildGS")
SOURCE = ARTIFACTS / "phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1"
OUTPUT = ARTIFACTS / "phase-payloads/p2/e3_local_4906982_fused_vis_conf_v1/P2-E3-LOCAL-4906982-FUSED-VIS-CONF-v1/e4_e6_depth_lineage.json"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    paths = {
        "data_roles": SOURCE / "prep/data_roles.md",
        "inventory": SOURCE / "prep/inventory.json",
        "existing_als": SOURCE / "prep/existing_als_synthetic_receipt.json",
        "lod_prior": SOURCE / "prep/lod_prior/receipt.json",
        "building_weight": SOURCE / "prep/w_b.json",
    }
    inventory = json.loads(paths["inventory"].read_text())
    als = json.loads(paths["existing_als"].read_text())
    lod = json.loads(paths["lod_prior"].read_text())
    weights = json.loads(paths["building_weight"].read_text())
    body = {
        "schema": "jointbuildgs.p2.e3_local_4906982_fused_vis_conf_v1.e4_e6_lineage.v1",
        "answer": "E4/E5/E6 were not all trained with ground-truth depth.",
        "common_E3_E6_image_evidence": {
            "views": inventory["exact_view_manifest"]["count"],
            "depth_map_files": inventory["depth_map_files"],
            "normal_map_files": inventory["normal_map_files"],
            "role": "common image-derived COLMAP/OpenMVS evidence",
        },
        "E4": {
            "extra_prior": "existing ALS sparse 3D geometry",
            "source_point_count": als["raw_selected_point_count"],
            "voxel_point_count": als["voxel_point_count"],
            "synthetic_changes": als["changes"],
            "ground_truth_depth": False,
        },
        "E5": {
            "extra_prior": "same existing ALS as E4 with building-wise consistency weight",
            "building_4906982_w_b": weights["buildings"]["DEBY_LOD2_4906982"],
            "ground_truth_depth": False,
        },
        "E6": {
            "extra_prior": "LoD2 surface planes",
            "reference_role": lod["reference_role"],
            "sample_count": lod["sample_count"],
            "diagnostic_reference_derived": True,
        },
        "current_ULS": {
            "path": inventory["evaluation_scan"]["path"],
            "training_allowed": inventory["evaluation_scan"]["training_allowed"],
            "role": "evaluation only",
        },
        "interpretation": "E4/E5 stability can come from direct 3D ALS constraints on absolute Z and surface orientation; E6 is a reference-derived diagnostic and is not an honest GT-free comparison.",
        "source_sha256": {name: {"path": str(path), "sha256": digest(path)} for name, path in paths.items()},
        "scientific_verdict": None,
    }
    OUTPUT.write_text(json.dumps(body, indent=2) + "\n")
    print(json.dumps(body, indent=2))


if __name__ == "__main__":
    main()
