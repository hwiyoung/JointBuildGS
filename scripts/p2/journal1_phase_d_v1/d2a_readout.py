#!/usr/bin/env python3
"""D2a smoke readout: GS(delta) vs GS(0) vs union rows on building 4906982.

Extracts a surface from the smoke 20k checkpoint and the sealed E4 20k anchor
the same way (55-view rendered median-depth fusion, 0.10 m voxel), converts to
the viewer-local frame, crops to the shared footprint of DEBY_LOD2_4906982,
and scores both against the dual GT suites with the sealed evaluator functions.
Union rows for the same building come from the sealed A2/D1 evaluations.

SMOKE-ONLY caveats (recorded in the receipt): crop is footprint-only (no +3 m
ring, no SMRF classification) and applies to both GS extractions identically;
union rows use the sealed class-6 footprint+3 m crops, so compare unions to
unions and GS to GS across delta, not GS to union absolutely.
Non-confirmatory; scientific_verdict stays null. Run in-container with GPU.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import yaml

from torch import nn

from scripts.p2.c3_utarget199_postprocess_v1.render_gs import GaussianModel2D
from scripts.p2.c4_existing_als_v1.prepare_prior import WORLD_SHIFT
from scripts.p2.journal1_phase_a_v1.geometry_eval import (
    FaceSet,
    eval_building_arm,
    load_lod2_faces,
    read_ply,
    roof_points,
    subsample,
    pca_normals,
)
from src.stage2.dataloader import ColmapDataset
from src.stage2.renderer import render

REPO = Path("/workspace/JointBuildGS")
ART = Path("/artifacts/JointBuildGS")
SID = "DEBY_LOD2_4906982"
J1 = json.load(open(REPO / "configs/p2/journal1_phase_a_v1/run_v2_e7e8.json"))
VIEWER_ORIGIN = np.asarray(J1["origin"], dtype=np.float64)
BASE = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
FUSED = REPO / "configs/p2/e3_local_4906982_fused_vis_conf_v1/fused_vis_conf.yaml"


def corridor_to_viewer(xyz_corridor: np.ndarray) -> np.ndarray:
    return xyz_corridor + (WORLD_SHIFT - VIEWER_ORIGIN)


def load_full_state_model(path: Path, device: str) -> GaussianModel2D:
    """Corridor full-state checkpoints wrap the model payload (optimizer/RNG
    included), so weights-only loading is unavailable; trusted sealed bytes."""
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = payload["model"]["state_dict"] if "model" in payload else payload["state_dict"]
    required = {"means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"}
    if not required.issubset(state):
        raise RuntimeError("checkpoint state is incomplete")
    model = GaussianModel2D.__new__(GaussianModel2D)
    nn.Module.__init__(model)
    model.sh_degree = 3
    model.max_sh_degree = 3
    model.active_sh_degree = 3
    model.num_classes = 4
    for name in sorted(required):
        setattr(model, name, nn.Parameter(state[name].to(device=device), requires_grad=False))
    model.surface_seed_mask = torch.zeros(len(state["means"]), dtype=torch.bool, device=device)
    model.eval()
    return model


def fuse_checkpoint(checkpoint: Path, device: str = "cuda") -> np.ndarray:
    cfg = yaml.safe_load(BASE.read_text())
    cfg.update(yaml.safe_load(FUSED.read_text())["overrides"])
    names = list(cfg["visible_views"])
    dataset = ColmapDataset(cfg["data_root"], downscale=0.5, load_depth=False,
                            load_normal=False, load_semantic=False, visible_views=names)
    model = load_full_state_model(checkpoint, device)
    voxel = 0.10
    keys_all, sums_all, counts_all = [], [], []
    with torch.no_grad():
        for index in range(len(dataset)):
            batch = dataset[index]
            width, height = int(batch["width"]), int(batch["height"])
            w2c = batch["w2c"].to(device)
            intrinsics = batch["K"].to(device)
            out = render(model, w2c, intrinsics, width, height, sh_degree=3,
                         render_mode="RGB+ED", near_plane=0.01, far_plane=500.0,
                         bg_color=torch.ones(3, device=device), depth_mode="median")
            depth = out["depth_median"]
            mask = torch.isfinite(depth) & (depth > 0.01) & (depth < 500.0) & (out["alpha"] >= 0.5)
            if not int(mask.sum()):
                continue
            yy, xx = torch.nonzero(mask, as_tuple=True)
            z = depth[yy, xx]
            cam = torch.stack(((xx - intrinsics[0, 2]) / intrinsics[0, 0] * z,
                                (yy - intrinsics[1, 2]) / intrinsics[1, 1] * z, z), dim=1)
            c2w = torch.linalg.inv(w2c)
            local = (cam @ c2w[:3, :3].T + c2w[:3, 3]).cpu().numpy().astype(np.float64)
            keys = np.floor(local / voxel).astype(np.int64)
            order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
            keys, local = keys[order], local[order]
            starts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0) != 0, axis=1)) + 1]
            keys_all.append(keys[starts])
            sums_all.append(np.add.reduceat(local, starts, axis=0))
            counts_all.append(np.diff(np.r_[starts, len(keys)]).astype(np.float64))
    keys = np.concatenate(keys_all)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    keys = keys[order]
    sums = np.concatenate(sums_all)[order]
    counts = np.concatenate(counts_all)[order]
    starts = np.r_[0, np.flatnonzero(np.any(np.diff(keys, axis=0) != 0, axis=1)) + 1]
    support = np.add.reduceat(counts, starts)
    centroid = np.add.reduceat(sums, starts, axis=0) / support[:, None]
    keep = np.diff(np.r_[starts, len(keys)]) >= 2  # >=2-view voxel support
    return centroid[keep]


def crop_footprint(xyz_viewer: np.ndarray) -> np.ndarray:
    import shapely
    from shapely.affinity import translate
    from shapely.geometry import shape

    payload = json.load(open(J1["footprints_geojson"]))
    feature = next(f for f in payload["features"] if f["properties"]["stable_id"] == SID)
    poly = translate(shape(feature["geometry"]), xoff=-VIEWER_ORIGIN[0], yoff=-VIEWER_ORIGIN[1])
    inside = shapely.contains_xy(poly, xyz_viewer[:, 0], xyz_viewer[:, 1])
    return xyz_viewer[inside]


def score(points_viewer: np.ndarray, faceset, e1_roof, e1_norm) -> list[dict]:
    rows = eval_building_arm(points_viewer, None, faceset, e1_roof, e1_norm, J1, False)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-checkpoint", required=True)
    parser.add_argument("--anchor-checkpoint", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    lod2 = load_lod2_faces(J1["gml_tiles"], {SID}, J1["origin"], J1["lod2_z_shift_to_viewer_m"])
    faceset = FaceSet(lod2[SID], J1["lod2_sample_step"]) if SID in lod2 else None
    e1_path = next(Path(J1["e1_reference_dir"]).glob(f"*_{SID}.points.ply"))
    e1_xyz, e1_cls = read_ply(e1_path)
    e1_roof, _ = roof_points(e1_xyz, e1_cls)
    e1_roof, _ = subsample(e1_roof, J1["max_points_per_arm"])
    e1_norm = pca_normals(e1_roof, J1["knn"])

    results = {}
    for label, ckpt in (("GS55_dx050_20k", args.smoke_checkpoint),
                         ("GS55_delta0_20k", args.anchor_checkpoint)):
        fused_corridor = fuse_checkpoint(Path(ckpt))
        viewer = corridor_to_viewer(fused_corridor)
        crop = crop_footprint(viewer)
        rows = score(crop, faceset, e1_roof, e1_norm)
        results[label] = {"checkpoint": str(ckpt), "crop_points": int(len(crop)), "rows": rows}
        print(f"[d2a-readout] {label}: {len(crop)} pts", flush=True)
        for row in rows:
            keep = {k: row.get(k) for k in ("gt", "f1@0.5", "completeness@0.5",
                                              "precision@0.5", "acc_median", "z_spread",
                                              "normal_med_deg")}
            print("  ", json.dumps(keep), flush=True)

    payload = {
        "schema": "jointbuildgs.p2.journal1_phase_d_v1.d2a_readout.v1",
        "task_id": "P2-JOURNAL1-PHASE-D-v1-D2A",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "building": SID,
        "extraction": "55-view rendered median-depth fusion, 0.10 m voxel, >=2-view support, footprint-only crop (no ring, no SMRF) — identical for both GS arms",
        "caveat": "GS rows comparable across delta; union rows (sealed A2/D1 class-6 footprint+3m crops) are a separate lineage — compare deltas within lineage",
        "results": results,
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"[d2a-readout] → {args.out}")


if __name__ == "__main__":
    main()
