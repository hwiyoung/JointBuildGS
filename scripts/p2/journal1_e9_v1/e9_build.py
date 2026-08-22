#!/usr/bin/env python3
"""E9 conflict-aware selective union — fuse adapter over the sealed chain.

Rule (configs/p2/journal1_e9_v1/e9_union_v1.json, pre-registered): keep every
current (E2) point; keep an ALS point only where no current point exists within
`fill_radius_m` in XY (pure fill). Overlap ALS is dropped even when consistent —
the current data already covers it more precisely, so dropping costs no
information and removes the double-surface channel. Dropped points are counted
as CONSISTENT or CONFLICTED (|dz| vs conflict_tau_m) — the conflict statistics
are the verification layer's raw material.

Everything after the fuse step reuses the sealed A2 machinery byte-identically
(prepare/verify/record-roofer/finalize/crops via scripts.p2.journal1_phase_a_v1.
a2_build_e7_e8 with the condition roster patched to E9). Non-confirmatory;
scientific_verdict stays null.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.p2.journal1_phase_a_v1 import a2_build_e7_e8 as a2

REPO = Path(__file__).resolve().parents[3]
E9_CONFIG = json.load(open(REPO / "configs/p2/journal1_e9_v1/e9_union_v1.json"))
RULE = E9_CONFIG["rule"]

a2.CONDITIONS = ("E9",)
a2.LINEAGE = dict(getattr(a2, "LINEAGE", {}))
a2.LINEAGE["E9"] = (
    "Conflict-aware selective union (no training): E2 current geometry + ALS fill-only "
    f"(fill radius {RULE['fill_radius_m']} m, conflict tau {RULE['conflict_tau_m']} m), sealed chain"
)


def fuse_e9(output_root: Path, artifact_root: Path,
            delta_xy_east_m: float = 0.0, delta_z_m: float = 0.0,
            mode: str = "fill_only") -> dict:
    import laspy
    from scipy.spatial import cKDTree

    work = output_root / "work" / "E9"
    receipt_path = work / "fused_surface_receipt.json"
    if receipt_path.is_file():
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    fused_path = work / "fused_surface.laz"
    if fused_path.exists():
        raise RuntimeError(f"unsealed fused output refuses overwrite: {fused_path}")
    config = a2.load_sealed_base()
    bounds = a2.crop_bounds(config["scene"])
    als_world, als_rows = a2._load_als_world(artifact_root, bounds)
    delta = (float(delta_xy_east_m), float(delta_z_m))
    if any(delta):
        als_world = als_world + np.asarray([delta[0], 0.0, delta[1]], dtype=np.float64)
        try:
            gate = a2._als_registration_gate(als_world, artifact_root)
        except RuntimeError as exc:
            gate = {"passed": False, "measurement_failure": str(exc)}
        gate["gate_role"] = "MEASUREMENT_ONLY_UNDER_INJECTED_DELTA"
    else:
        gate = a2._als_registration_gate(als_world, artifact_root)

    e2_path = artifact_root / a2.E2_CLASSIFIED_REL
    xyz_parts, rgb_parts = [], []
    with laspy.open(e2_path) as reader:
        for chunk in reader.chunk_iterator(a2.CHUNK):
            xyz_parts.append(np.column_stack((np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z))))
            rgb_parts.append(np.column_stack((
                np.asarray(chunk.red, dtype=np.uint16),
                np.asarray(chunk.green, dtype=np.uint16),
                np.asarray(chunk.blue, dtype=np.uint16),
            )))
    e2_xyz = np.concatenate(xyz_parts)
    e2_rgb = np.concatenate(rgb_parts)
    del xyz_parts, rgb_parts

    tree = cKDTree(e2_xyz[:, :2])
    d_xy, nn = tree.query(als_world[:, :2], k=1, workers=-1)
    overlap = d_xy <= float(RULE["fill_radius_m"])
    dz = np.abs(als_world[:, 2] - e2_xyz[nn, 2])
    conflicted = overlap & (dz > float(RULE["conflict_tau_m"]))
    fill = ~overlap
    if mode == "fill_only":
        keep_mask = fill
    elif mode == "drop_duplicates_only":
        # v2: drop only duplicate-consistent overlap; vertically-separated
        # overlap (E2 saw a different surface at this XY) is FLAGGED fill.
        keep_mask = fill | conflicted
    else:
        raise RuntimeError(f"unknown E9 mode: {mode}")
    selection = {
        "mode": mode,
        "als_total": int(len(als_world)),
        "pure_fill": int(fill.sum()),
        "overlap_duplicate_consistent": int((overlap & ~conflicted).sum()),
        "overlap_vertically_separated": int(conflicted.sum()),
        "kept_total": int(keep_mask.sum()),
        "conflict_share_of_overlap": round(float(conflicted.sum() / max(1, overlap.sum())), 4),
    }
    kept = als_world[keep_mask]

    writer, header = a2._open_fused_writer(fused_path)
    try:
        for start in range(0, len(e2_xyz), a2.CHUNK):
            a2._write_block(writer, header, e2_xyz[start:start + a2.CHUNK], e2_rgb[start:start + a2.CHUNK])
        for start in range(0, len(kept), a2.CHUNK):
            block = kept[start:start + a2.CHUNK]
            a2._write_block(writer, header, block,
                             np.full((len(block), 3), a2.ALS_GRAY, dtype=np.uint16))
    finally:
        writer.close()

    receipt = {
        "schema": "jointbuildgs.p2.journal1_e9_v1.fused_surface.v1",
        "task_id": E9_CONFIG["task_id"],
        "condition_id": "E9",
        "status": "FUSED_SURFACE_READY",
        "created_utc": a2.now_utc(),
        "lineage": a2.LINEAGE["E9"],
        "rule": RULE,
        "selection": selection,
        "training_executed": False,
        "raw_als_sources": als_rows,
        "datum_transform": {"source": "2022_ALS_ORTHOMETRIC", "target": "2024_CAMERA_ELLIPSOIDAL", "z_shift_m": 45.7},
        "delta_injection": (
            {"dx_east_m": delta[0], "dz_m": delta[1], "synthetic": True,
             "purpose": "PHASE_D_DELTA_SHIFT_REGISTRATION_RESIDUAL_PROBE",
             "not_real_als_lineage": True}
            if any(delta) else None
        ),
        "registration": gate,
        "e2_source": {"path": str(e2_path), "sha256": a2.E2_CLASSIFIED_SHA256,
                       "geometry_only": True, "class_labels_dropped": True},
        "point_count": {"e2": int(len(e2_xyz)), "als_fill": int(len(kept)),
                         "total": int(len(e2_xyz) + len(kept))},
        "fused_surface": a2.file_record(fused_path, output_root),
        "official_PASS_usable": None,
        "scientific_verdict": None,
    }
    a2.write_new(receipt_path, a2.canonical_json_bytes(receipt))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("prepare", "fuse", "verify-classified", "record-roofer", "finalize", "crops"):
        p = sub.add_parser(name)
        p.add_argument("--output-root", type=Path, required=True)
        if name in ("prepare", "fuse"):
            p.add_argument("--artifact-root", type=Path, required=True)
        if name == "fuse":
            p.add_argument("--delta-xy-east-m", type=float, default=0.0)
            p.add_argument("--delta-z-m", type=float, default=0.0)
            p.add_argument("--rule-mode", default="fill_only",
                           choices=("fill_only", "drop_duplicates_only"))
        if name == "record-roofer":
            p.add_argument("--exit-code", type=int, required=True)
            p.add_argument("--runtime-seconds", type=int, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = a2.prepare(args.output_root, args.artifact_root)
    elif args.mode == "fuse":
        result = fuse_e9(args.output_root, args.artifact_root,
                          args.delta_xy_east_m, args.delta_z_m, args.rule_mode)
    elif args.mode == "verify-classified":
        result = a2.verify_classified(args.output_root, "E9")
    elif args.mode == "record-roofer":
        result = a2.record_roofer(args.output_root, "E9", args.exit_code, args.runtime_seconds)
    elif args.mode == "crops":
        result = a2.crops(args.output_root, "E9")
    else:
        result = a2.finalize(args.output_root, ("E9",))
    print(json.dumps({k: v for k, v in result.items()
                       if k not in ("rows", "raw_als_sources", "outputs")},
                      ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
