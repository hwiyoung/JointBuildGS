#!/usr/bin/env python3
"""S1 bundle writer — phd_s3_verify_s1_bundle_v1 (verification page 1 data).

ZERO continuous optimization steps: emits the S1 plane-hypothesis stage only,
reusing the legacy arrgs_v1 scene/candidate code unmodified (real_scene roofer
candidates + footprint walls + gapfill; synthetic gable GT + distractors).
Inliers are recomputed post-hoc for EVERY plane under the registered contract
rule (tau_m = legacy RANSAC tol, in-support test); RANSAC-internal counts are
untouched. ALS prior points are o_init-only overlay (source=1, never judged).
LoD2 roof faces / synthetic GT surfaces are evaluation-only (gt_planes).

Per run: manifest.json, s1_points.ply, s1_planes.json, s1_orphans.json,
s1_view.json under <out_root>/runs/<name>/.

Usage (container):
  bash scripts/p2/arrgs_v1/run_host.sh <gpu> \
      scripts/phd/s3_verify_v1/build_s1_bundle.py [run ...]   # default: all
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, REPO / "scripts/p2/arrgs_v1", REPO / "scripts/p2/journal1_phase_a_v1"):
    sys.path.insert(0, str(p))

from bundle_io import (read_ply_points, write_s1_points_ply, thin_stride,  # noqa: E402
                       unit_plane, lift_ring_xy, vertical_rect, plane_inliers)

CFG = json.load(open(REPO / "configs/phd/s3_verify_v1/s1_bundle_v1.json"))
EVAL_CFG = json.load(open(REPO / "configs/p2/arrgs_v1/eval_arrgs_v1.json"))
GRAVITY_CKPT = ("/artifacts/JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/"
                "freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/"
                "030-dense_mvs_and_gravity.json")

SOURCE_MAP = {"prior_als": "prior", "mvs": "mvs", "footprint": "footprint",
              "gapfill": "gapfill", "gt": "synthetic_gt",
              "distractor": "synthetic_distractor"}
GT_MIN_AREA = 5.0   # s1_gt_match.py MIN_AREA
NZ_VERTICAL = 0.1   # below this |n_z| the support is a vertical wall rectangle
TAU = float(CFG["inlier"]["tau_m"])
BUF = float(CFG["inlier"]["support_buffer_m"])
EXCLUDE_SOURCES = set(CFG.get("exclude_sources", []))
INLIER_DEF = ("source==0(mvs_current) point with |signed point-plane distance| <= tau_m "
              "AND in-plane projection inside the support polygon buffered by "
              "support_buffer_m; ALS prior (source=1) is o_init-only overlay, never judged")


def gravity_angle(n, up):
    return float(np.degrees(np.arccos(min(1.0, abs(float(np.dot(n, up)))))))


def ring_area(ring3d):
    v = np.asarray(ring3d, dtype=np.float64)
    return 0.5 * float(np.linalg.norm(
        sum(np.cross(v[i] - v[0], v[i + 1] - v[0]) for i in range(1, len(v) - 1))))


def expand_planes(raw_planes, fp_xy, ground_z, top_z):
    """Legacy candidate dicts -> one contract entry per support ring (3D)."""
    entries = []
    for p in raw_planes:
        n, d = unit_plane(p["n"], p["d"])
        src = SOURCE_MAP[p["source"]]
        if src in EXCLUDE_SOURCES:
            continue
        rings = p.get("support") or [np.asarray(fp_xy)[:, :2].tolist()]
        for ring in rings:
            if abs(n[2]) < NZ_VERTICAL:
                ring3d = vertical_rect(ring, n, d, ground_z, top_z)
            else:
                if len(ring) < 3:
                    continue
                ring3d = lift_ring_xy(ring, n, d)
            entries.append({"n": n, "d": d, "source": src, "ring": ring3d})
    return entries


def emit_planes(entries, xyz, mvs_mask, up):
    planes_json = []
    inlier_union = np.zeros(len(xyz), dtype=bool)
    for i, e in enumerate(entries):
        idx, dist = plane_inliers(xyz, mvs_mask, e["n"], e["d"], e["ring"], TAU, BUF)
        inlier_union[idx] = True
        rms = float(np.sqrt(np.mean(dist[idx] ** 2))) if len(idx) else None
        planes_json.append({
            "plane_id": f"p{i:03d}",
            "source": e["source"],
            "n": [round(float(v), 6) for v in e["n"]],
            "d": round(float(e["d"]), 4),
            "support_local": np.round(e["ring"], 3).tolist(),
            "inlier_idx": [int(k) for k in idx],
            "inlier_count": int(len(idx)),
            "inlier_rms_m": round(rms, 4) if rms is not None else None,
            "gravity_angle_deg": round(gravity_angle(e["n"], up), 2),
            "gt_match": None,
        })
    return planes_json, inlier_union


def match_gt(planes_json, gt_faces):
    """s1_gt_match.py rule: best candidate by ang + off*20, offset at the GT
    centroid; thresholds from prereg (ANG_TOL/OFF_TOL lineage). Evaluation-only."""
    max_ang = float(CFG["prereg"]["gt_match"]["max_angle_deg"])
    max_off = float(CFG["prereg"]["gt_match"]["max_offset_m"])
    gt_json, cents = [], []
    for gi, (ring, n, d) in enumerate(gt_faces):
        gt_json.append({"gt_plane_id": f"g{gi:03d}",
                        "n": [round(float(v), 6) for v in n],
                        "d": round(float(d), 4),
                        "support_local": np.round(ring, 3).tolist(),
                        "matched_plane_ids": []})
        cents.append(np.asarray(ring, dtype=np.float64).mean(axis=0))
    for p in planes_json:
        if p["source"] == "footprint" or not gt_faces:
            continue
        pn, pd = np.asarray(p["n"]), p["d"]
        best = None
        for gi, (ring, n, d) in enumerate(gt_faces):
            ang = float(np.degrees(np.arccos(min(1.0, abs(float(pn @ n))))))
            off = abs(float(pn @ cents[gi] - pd))
            within = ang <= max_ang and off <= max_off
            if within:  # face-side: any candidate within thresholds counts
                gt_json[gi]["matched_plane_ids"].append(p["plane_id"])
            if within and (best is None or ang + off * 20 < best[1] + best[2] * 20):
                best = (gi, ang, off)
        if best:  # plane-side: its best face among those within thresholds
            p["gt_match"] = {"gt_plane_id": f"g{best[0]:03d}",
                             "angle_deg": round(best[1], 2),
                             "offset_m": round(best[2], 3)}
    return gt_json


def write_run(out_dir, *, name, s1_mode, dataset, crs, local_offset, xyz, rgb, src,
              entries, gt_faces, fp_xy, ground_z, top_z, gravity, stride, n_orig,
              extra_manifest=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    up = -np.asarray(gravity, dtype=np.float64)
    up /= np.linalg.norm(up)
    mvs_mask = src == 0
    planes_json, inlier_union = emit_planes(entries, xyz, mvs_mask, up)
    gt_json = match_gt(planes_json, gt_faces)
    orphan_idx = np.nonzero(mvs_mask & ~inlier_union)[0]
    n_mvs = int(mvs_mask.sum())
    orphan_ratio = float(len(orphan_idx)) / max(1, n_mvs)

    write_s1_points_ply(out_dir / "s1_points.ply", xyz, rgb, src)
    json.dump({"planes": planes_json, "gt_planes": gt_json,
               "gt_evaluation_only": True},
              open(out_dir / "s1_planes.json", "w"))
    json.dump({"orphan_idx": [int(k) for k in orphan_idx],
               "orphan_ratio": orphan_ratio},
              open(out_dir / "s1_orphans.json", "w"))
    json.dump({"footprint_local": np.round(np.asarray(fp_xy)[:, :2], 3).tolist(),
               "ground_z": round(float(ground_z), 3),
               "top_z": round(float(top_z), 3),
               "gravity": [round(float(v), 6) for v in gravity]},
              open(out_dir / "s1_view.json", "w"), indent=1)
    manifest = {
        "schema": "phd_s3_verify_s1_bundle_v1",
        "bundle_name": name,
        "stage": "s1",
        "s1_mode": s1_mode,
        "dataset": dataset,
        "crs": crs,
        "local_offset": [float(v) for v in local_offset],
        "inlier_def": {"tau_m": TAU, "support_buffer_m": BUF,
                       "target": "mvs_current", "definition": INLIER_DEF},
        "candidate_exclusions": sorted(EXCLUDE_SOURCES),
        "prereg": dict(CFG["prereg"], proposal=True),
        "counts": {"points_total": int(len(xyz)), "points_mvs": n_mvs,
                   "points_als": int(len(xyz) - n_mvs),
                   "planes": len(planes_json), "orphans": int(len(orphan_idx))},
        "thinning": {"max_points": int(CFG["thin_max_points"]), "stride": int(stride),
                     "original_count": int(n_orig)},
        "scientific_verdict": None,
        "not_official": True,
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=1)
    print(f"[s1-bundle] {name}: pts {len(xyz)} (mvs {n_mvs} als {len(xyz)-n_mvs}) "
          f"planes {len(planes_json)} gt {len(gt_json)} "
          f"orphans {len(orphan_idx)} ({orphan_ratio:.3f})", flush=True)


def gt_faces_from_lod2(faces):
    out = []
    for verts, n in faces:
        v = np.asarray(verts, dtype=np.float64)
        if len(v) > 3 and np.allclose(v[0], v[-1]):
            v = v[:-1]
        if len(v) < 3 or ring_area(v) < GT_MIN_AREA:
            continue
        out.append((v, np.asarray(n, dtype=np.float64), float(n @ v.mean(axis=0))))
    return out


def build_real(name, out_root, gravity, lod2_faces):
    from real_scene import load_real_scene, A2_CROPS, VIEWER_SHIFT
    from xreal_run import scene_for, BUILDINGS, E2_DIR
    scene = scene_for(name)
    scene["skip_images"] = True
    sc = load_real_scene(scene, device=None)
    bkey, sid = BUILDINGS[name]["bkey"], BUILDINGS[name]["stable_id"]
    mvs_xyz, mvs_rgb, _ = read_ply_points(Path(E2_DIR) / f"{bkey}.points.ply")
    als_xyz, als_rgb, _ = read_ply_points(A2_CROPS / "E7" / f"{bkey}.points.ply")
    # degenerate rgb (all-zero crop exports) reads as black on the dark viewer
    if mvs_rgb is None or not mvs_rgb.any():
        mvs_rgb = np.full((len(mvs_xyz), 3), 180, dtype=np.uint8)
    if als_rgb is None or not als_rgb.any():
        als_rgb = np.full((len(als_xyz), 3), 120, dtype=np.uint8)
    xyz = np.concatenate([mvs_xyz, als_xyz])
    rgb = np.concatenate([mvs_rgb, als_rgb]).astype(np.uint8)
    src = np.concatenate([np.zeros(len(mvs_xyz), np.uint8),
                          np.ones(len(als_xyz), np.uint8)])
    keep, stride = thin_stride(len(xyz), CFG["thin_max_points"])
    entries = expand_planes(sc["planes"], sc["footprint"], sc["ground_z"], sc["top_z"])
    write_run(out_root / "runs" / name,
              name=name, s1_mode=sc["s1_mode"],
              dataset={"kind": "real", "bkey": bkey, "stable_id": sid},
              crs="EPSG:25832", local_offset=VIEWER_SHIFT.tolist(),
              xyz=xyz[keep], rgb=rgb[keep], src=src[keep],
              entries=entries, gt_faces=gt_faces_from_lod2(lod2_faces.get(sid, [])),
              fp_xy=sc["footprint"], ground_z=sc["ground_z"], top_z=sc["top_z"],
              gravity=gravity, stride=stride, n_orig=len(xyz))
    return {"name": name, "out_dir": out_root / "runs" / name,
            "dataset_kind": "real",
            "planes": [p for p in sc["planes"]
                       if SOURCE_MAP[p["source"]] not in EXCLUDE_SOURCES],
            "entries": entries, "fp_xy": np.asarray(sc["footprint"]),
            "ground_z": sc["ground_z"], "top_z": sc["top_z"],
            "xyz": xyz[keep], "src": src[keep],
            "stride": stride, "n_als_orig": len(als_xyz)}


def build_synth(out_root):
    from synthetic import gt_surfaces, candidate_planes, _sample_poly
    surfaces, _inside, fp = gt_surfaces("gable")
    rng = np.random.default_rng(int(CFG["synth_seed"]))
    pts_all, rgb_all = [], []
    for poly3d, n, base in surfaces[1:]:  # [0] = context ground, outside model domain
        pts, uvs, (nn, _e1, _e2) = _sample_poly(poly3d, n, spacing=0.15)
        if len(pts) == 0:
            continue
        pts = pts + nn[None, :] * rng.normal(0.0, 0.02, size=(len(pts), 1))
        checker = ((np.floor(uvs[:, 0]) + np.floor(uvs[:, 1])) % 2) * 0.22
        col = np.clip(np.asarray(base)[None, :] * (0.85 + checker[:, None])
                      + rng.normal(0, 0.03, size=(len(pts), 3)), 0, 1)
        pts_all.append(pts)
        rgb_all.append((col * 255).astype(np.uint8))
    mvs_xyz = np.concatenate(pts_all)
    mvs_rgb = np.concatenate(rgb_all)
    # pseudo-ALS: no real prior exists, so sample the GT faces deterministically
    # (config synth_als) as source==1 so the SAME pillar o_init machinery runs
    sa = CFG.get("synth_als")
    als_parts = []
    if sa:
        spacing_als = float(sa["density_per_m2"]) ** -0.5
        rng_als = np.random.default_rng(int(sa["seed"]))
        for poly3d, n, _base in surfaces[1:]:
            pts, _uvs, (nn, _e1, _e2) = _sample_poly(poly3d, n, spacing=spacing_als)
            if len(pts):
                als_parts.append(pts + nn[None, :] * rng_als.normal(
                    0.0, float(sa["noise_sigma_m"]), size=(len(pts), 1)))
    als_xyz = np.concatenate(als_parts) if als_parts else np.zeros((0, 3))
    xyz = np.concatenate([mvs_xyz, als_xyz])
    rgb = np.concatenate([mvs_rgb, np.full((len(als_xyz), 3), 120, np.uint8)])
    src = np.concatenate([np.zeros(len(mvs_xyz), np.uint8),
                          np.ones(len(als_xyz), np.uint8)])
    keep, stride = thin_stride(len(xyz), CFG["thin_max_points"])

    ground_z, top_z = 0.0, float(max(s[0][:, 2].max() for s in surfaces[1:]))
    roofL, roofR = surfaces[1], surfaces[2]
    cands, _fp = candidate_planes("gable")
    sup_xy = {"roofL": roofL[0][:, :2].tolist(), "roofR": roofR[0][:, :2].tolist(),
              "distractor_flat": np.asarray(fp).tolist(),
              "distractor_offset": roofL[0][:, :2].tolist()}
    for i, (a, b) in enumerate(zip(np.asarray(fp), np.roll(np.asarray(fp), -1, axis=0))):
        sup_xy[f"wall{i}"] = [a.tolist(), b.tolist()]
    for p in cands:
        p["support"] = [sup_xy[p["id"]]]
    entries = expand_planes(cands, fp, ground_z, top_z)
    gt_faces = [(s[0], np.asarray(s[1], dtype=np.float64),
                 float(np.asarray(s[1]) @ np.asarray(s[0]).mean(axis=0)))
                for s in (roofL, roofR)]
    write_run(out_root / "runs" / "SYNTH_GABLE",
              name="SYNTH_GABLE", s1_mode="synthetic",
              dataset={"kind": "synthetic", "synth_kind": "gable"},
              crs="local", local_offset=[0.0, 0.0, 0.0],
              xyz=xyz[keep], rgb=rgb[keep], src=src[keep],
              entries=entries, gt_faces=gt_faces,
              fp_xy=np.asarray(fp), ground_z=ground_z, top_z=top_z,
              gravity=[0.0, 0.0, -1.0], stride=stride, n_orig=len(xyz),
              extra_manifest={"synthetic_als": True} if sa else None)
    return {"name": "SYNTH_GABLE", "out_dir": out_root / "runs" / "SYNTH_GABLE",
            "dataset_kind": "synthetic",
            "planes": [p for p in cands
                       if SOURCE_MAP[p["source"]] not in EXCLUDE_SOURCES],
            "entries": entries, "fp_xy": np.asarray(fp),
            "ground_z": ground_z, "top_z": top_z,
            "xyz": xyz[keep], "src": src[keep],
            "stride": stride, "n_als_orig": len(als_xyz)}


def real_context(real_runs):
    """(gravity, lod2_faces) shared by all real runs; (None, {}) when none."""
    if not real_runs:
        return None, {}
    ck = json.load(open(GRAVITY_CKPT))["payload"]["gravity"]
    assert not ck["hardcoded_gravity"]
    gravity = ck["gravity"]  # frozen terrain-MVS-normals estimate (down vector)
    from xreal_run import BUILDINGS
    from geometry_eval import load_lod2_faces
    sids = {BUILDINGS[r]["stable_id"] for r in real_runs}
    lod2_faces = load_lod2_faces(EVAL_CFG["gml_tiles"], sids, EVAL_CFG["origin"],
                                 EVAL_CFG["lod2_z_shift_to_viewer_m"])
    return gravity, lod2_faces


def main():
    runs = sys.argv[1:] or CFG["runs"]
    out_root = Path(CFG["out_root"])
    gravity, lod2_faces = real_context([r for r in runs if r != "SYNTH_GABLE"])
    for r in runs:
        if r == "SYNTH_GABLE":
            build_synth(out_root)
        else:
            build_real(r, out_root, gravity, lod2_faces)


if __name__ == "__main__":
    main()
