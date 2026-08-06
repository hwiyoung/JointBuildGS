from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TASK_REL = Path("phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1")
EXACT_MANIFEST_REL = Path("artifacts/manifests/gate_s0/common_base_r2b/exact_937_member_crosswalk_v1.json")
FOOTPRINT_REL = Path(
    "phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
    "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/"
    "freeze/shared_footprints_199.geojson"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repository_root.resolve()
    artifacts = args.artifact_root.resolve()
    task = artifacts / TASK_REL
    prep = task / "prep"
    prep.mkdir(parents=True, exist_ok=True)
    exact_manifest = repo / EXACT_MANIFEST_REL
    footprint = artifacts / FOOTPRINT_REL
    data_root = artifacts / "phase-payloads/p0-audit/data/work/mvs/colmap_dense"
    als = [
        artifacts / f"phase-payloads/p0-audit/data/raw/als/{tile}.laz"
        for tile in ("690_5335", "690_5336", "691_5335", "691_5336")
    ]
    evaluation_scan = artifacts / "phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
    lod2 = [
        artifacts / f"phase-payloads/p0-audit/data/raw/lod2/{tile}.gml"
        for tile in ("690_5334", "690_5336")
    ]
    required = [exact_manifest, footprint, evaluation_scan, *als, *lod2]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    manifest = json.loads(exact_manifest.read_text(encoding="utf-8"))
    names = sorted(str(row["basename"]) for row in manifest["rows"])
    if len(names) != 937 or len(set(names)) != 937:
        raise RuntimeError("exact view membership must be 937 unique names")
    missing_images = [name for name in names if not (data_root / "images" / name).is_file()]
    if missing_images:
        raise RuntimeError(f"missing exact images: {missing_images[:5]}")
    eval_views = [name for index, name in enumerate(names, start=1) if index % 8 == 0]
    train_views = [name for name in names if name not in set(eval_views)]
    roles = {
        "schema": "jointbuildgs.p2.e1_e6.view_roles.v1",
        "rule": "LEXICOGRAPHICALLY_SORTED_EVERY_8TH_TO_EVAL",
        "exact_visible_count": len(names),
        "train_count": len(train_views),
        "eval_count": len(eval_views),
        "train_views": train_views,
        "eval_views": eval_views,
    }
    (prep / "view_roles.json").write_text(json.dumps(roles, indent=2) + "\n", encoding="utf-8")
    footprint_data = json.loads(footprint.read_text(encoding="utf-8"))
    stable_ids = sorted(str(feature["properties"]["stable_id"]) for feature in footprint_data["features"])
    if len(stable_ids) != 199:
        raise RuntimeError("shared footprint population must contain 199 buildings")
    # Frozen deterministic draw from the 146 footprints with >=20 jointly
    # valid raw MVS/Existing-ALS DSM cells.  Coverage eligibility prevents a
    # synthetic change from receiving an undefined w_b merely because one DSM
    # has no support; selection remains outcome-free within that pool.
    selected = [
        "DEBY_LOD2_4907520",
        "DEBY_LOD2_4907196",
        "DEBY_LOD2_4908165",
        "DEBY_LOD2_4907517",
        "DEBY_LOD2_108250120",
        "DEBY_LOD2_42364609",
        "DEBY_LOD2_4959323",
        "DEBY_LOD2_4907188",
        "DEBY_LOD2_4908168",
    ]
    synthetic = {
        "schema": "jointbuildgs.p2.e1_e6.synthetic_changes.v1",
        "seed": 20260806,
        "eligibility": "RAW_MVS_AND_EXISTING_ALS_DSM_OVERLAP_AT_LEAST_20_CELLS",
        "eligible_building_count": 146,
        "verified_real_construction_or_demolition_count": 0,
        "reason": "fewer than five verified real changes; prior evidence had candidates only",
        "shared_footprint_modified": False,
        "raw_input_modified": False,
        "changes": [
            *({"stable_id": value, "operation": "REMOVE_PRIOR_GEOMETRY", "simulates": "NEW_CONSTRUCTION"} for value in selected[:4]),
            *({"stable_id": value, "operation": "INSERT_DONOR_PRIOR_GEOMETRY", "donor_stable_id": selected[index - 4], "simulates": "DEMOLITION"} for index, value in enumerate(selected[4:6], start=4)),
            *({"stable_id": value, "operation": "SCALE_PRIOR_HEIGHT", "scale": 0.7 if index % 2 == 0 else 1.3} for index, value in enumerate(selected[6:])),
        ],
        "scientific_verdict": None,
    }
    (prep / "synthetic_changes.json").write_text(json.dumps(synthetic, indent=2) + "\n", encoding="utf-8")
    rows = [
        "# E1–E6 data roles",
        "",
        "| 역할 | 확정 소스 | 용도 |",
        "|---|---|---|",
        f"| 이미지+포즈 | `{data_root}/images` + `sparse/` (exact 937) | E2–E6 common base; sorted every 8th held out |",
        f"| 기구축 LoD prior | `{lod2[0]}`, `{lod2[1]}` | E6 diagnostic planes; GroundSurface XY supplies shared footprint |",
        f"| footprint | `{footprint}` (199 stable IDs) | R_shared, building aggregation and w_b |",
        f"| 기구축 LiDAR prior | `{als[0].parent}` four exact ALS tiles | E4/E5 identical seed and sparse supervision |",
        f"| 평가 기준 | `{evaluation_scan}` | geometry/semantic evaluation only; training path deny-listed |",
        "",
        "All coordinates are normalized to EPSG:25832. Existing ALS receives the frozen +45.7 m vertical shift; MVS receives the frozen GS-local-to-world translation [690953, 5336071, 604].",
        "Evaluation density is measured during Phase 0 and the extracted E3–E6 clouds target 50–100 pt/m2.",
    ]
    (prep / "data_roles.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    inventory = {
        "schema": "jointbuildgs.p2.e1_e6.inventory.v1",
        "exact_view_manifest": {"path": str(exact_manifest), "sha256": sha256(exact_manifest), "count": 937},
        "images": {"path": str(data_root / "images"), "count": 937},
        "depth_map_files": len(list((data_root / "stereo/depth_maps").glob("*"))),
        "normal_map_files": len(list((data_root / "stereo/normal_maps").glob("*"))),
        "shared_footprint": {"path": str(footprint), "sha256": sha256(footprint), "count": 199},
        "existing_als": [{"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in als],
        "evaluation_scan": {"path": str(evaluation_scan), "bytes": evaluation_scan.stat().st_size, "sha256": sha256(evaluation_scan), "training_allowed": False},
        "lod2": [{"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in lod2],
        "status": "PHASE0_INVENTORY_COMPLETE",
        "scientific_verdict": None,
    }
    (prep / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
