"""3막 스크리닝 — N=12 건물에서 ALS(2022)가 실제로 낡았는가 (자연 양성 개수 측정).

Question (user, 2026-08-24): how many buildings actually carry NATURAL ALS
staleness? B173's legacy readout proved at least one (the old sloped-roof points
in the union came from the existing asset). This screen measures, per
change∧insufficient building (N=12, user-adjusted), the per-cell roof-height
disagreement between the registered ALS patch and current UAS LiDAR (E1 cls6):

  cell(1 m): dz = median_z(ALS roof) − median_z(E1 cls6), cells with both
  stale_share = fraction of common cells with |dz| > 1.0 m

Screening only (not a verdict): stale_share >= 0.2 marks a natural-positive
CANDIDATE for the act-3 case study. Frames: E1 crops are viewer-local
(world − [690700,5335700,550]); ALS loader is scene-local (world − WORLD_SHIFT)
with the +45.7 m datum shift already applied → both are lifted to EPSG world
(ellipsoidal z) before comparison. CPU, sealed inputs only.
scientific_verdict: null.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/workspace/JointBuildGS")
sys.path.insert(0, str(REPO))
from scripts.p2.c4_existing_als_v1 import prepare_prior as official  # noqa: E402
from scripts.phd.judge_trial_v1.act1_delta_probe import load_als_with_intensity  # noqa: E402
from shapely import contains_xy  # noqa: E402
from shapely.geometry import shape  # noqa: E402

E1_CROP_DIR = Path("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1"
                   "/P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E1")
E1_LOCAL_SHIFT = np.asarray([690700.0, 5335700.0, 550.0])
FOOTPRINTS = Path("/artifacts/JointBuildGS/phase-payloads/p2/c1_c2_shared_footprint_199_v3"
                  "/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a"
                  "/freeze/shared_footprints_199.geojson")
AX10 = Path("/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/P2-ARRGS-AX10-v1"
            "/population_2x2.json")
ALS_ROOT = Path("/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/als")
OUT = Path("/artifacts/JointBuildGS/phase-payloads/phd/PHD-JUDGE-TRIAL-v1/act3_screen")

CELL = 1.0
DZ_STALE_M = 1.0
STALE_SHARE_SCREEN = 0.2


def read_ply(p: Path):
    raw = open(p, "rb").read()
    head_end = raw.find(b"end_header\n") + len(b"end_header\n")
    head = raw[:head_end].decode("ascii", errors="replace")
    n = int([l for l in head.splitlines() if l.startswith("element vertex")][0].split()[-1])
    m = {"float": "<f4", "float32": "<f4", "double": "<f8", "uchar": "u1", "uint8": "u1",
         "ushort": "<u2", "uint16": "<u2", "int": "<i4", "uint": "<u4"}
    dt = [(name, m[t]) for t, name in
          (l.split()[1:] for l in head.splitlines() if l.startswith("property"))]
    return np.frombuffer(raw, dtype=np.dtype(dt), count=n, offset=head_end)


def cell_median_z(xy: np.ndarray, z: np.ndarray) -> dict:
    cid = (np.floor(xy[:, 0] / CELL).astype(np.int64) << 32) \
        + np.floor(xy[:, 1] / CELL).astype(np.int64)
    order = np.argsort(cid, kind="mergesort")
    cid_s, z_s = cid[order], z[order]
    bounds = np.r_[0, np.flatnonzero(cid_s[1:] != cid_s[:-1]) + 1, len(cid_s)]
    return {int(cid_s[i0]): float(np.median(z_s[i0:i1]))
            for i0, i1 in zip(bounds[:-1], bounds[1:]) if i1 - i0 >= 3}


def main() -> None:
    n_ids = json.loads(AX10.read_text())["tables"]["user_adjusted"]["N_stable_ids"]
    fps = {f["properties"].get("stable_id") or f["properties"].get("gml_id"): f["geometry"]
           for f in json.loads(FOOTPRINTS.read_text())["features"]}

    # one ALS pass over the union bbox of all targets
    polys = {sid: shape(fps[sid]).buffer(1.0) for sid in n_ids}
    xs = [p.bounds[i] for p in polys.values() for i in (0, 2)]
    ys = [p.bounds[i] for p in polys.values() for i in (1, 3)]
    als_xyz, _, _ = load_als_with_intensity(
        ALS_ROOT, np.asarray([min(xs) - 5, min(ys) - 5]), np.asarray([max(xs) + 5, max(ys) + 5]))
    als_world = als_xyz + official.WORLD_SHIFT  # ellipsoidal z (datum shift applied in loader)

    report = {}
    for sid in n_ids:
        poly = polys[sid]
        m = contains_xy(poly, als_world[:, 0], als_world[:, 1])
        als_b = als_world[m]
        crops = sorted(E1_CROP_DIR.glob(f"B*_{sid}.points.ply"))
        if not crops or len(als_b) < 50:
            report[sid] = {"skipped": f"e1_crop={bool(crops)} als_pts={int(m.sum())}"}
            continue
        a = read_ply(crops[0])
        e1 = np.column_stack([np.asarray(a["x"], np.float64), np.asarray(a["y"], np.float64),
                              np.asarray(a["z"], np.float64)]) + E1_LOCAL_SHIFT
        cls = np.asarray(a["classification"]) if "classification" in a.dtype.names else None
        if cls is not None:
            e1 = e1[cls == 6]
        e1 = e1[contains_xy(poly, e1[:, 0], e1[:, 1])]
        if len(e1) < 50:
            report[sid] = {"skipped": f"e1_cls6_pts={len(e1)}"}
            continue
        gz_als = np.quantile(als_b[:, 2], 0.05)
        als_roof = als_b[als_b[:, 2] > gz_als + 2.0]
        if len(als_roof) < 30:
            als_roof = als_b  # low structures: keep all

        ca = cell_median_z(als_roof[:, :2], als_roof[:, 2])
        ce = cell_median_z(e1[:, :2], e1[:, 2])
        common = sorted(set(ca) & set(ce))
        if len(common) < 10:
            report[sid] = {"skipped": f"common_cells={len(common)}"}
            continue
        dz = np.asarray([ca[c] - ce[c] for c in common])
        stale = np.abs(dz) > DZ_STALE_M
        report[sid] = {
            "n_common_cells": len(common),
            "dz_median_m": round(float(np.median(dz)), 2),
            "dz_p90_abs_m": round(float(np.quantile(np.abs(dz), 0.9)), 2),
            "stale_share_gt1m": round(float(stale.mean()), 3),
            "natural_positive_candidate": bool(stale.mean() >= STALE_SHARE_SCREEN),
        }

    n_cand = sum(1 for v in report.values() if v.get("natural_positive_candidate"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "als_staleness_screen_v1.json").write_text(
        json.dumps({"schema": "phd_act3_als_staleness_screen_v1",
                    "definition": {"cell_m": CELL, "dz_stale_m": DZ_STALE_M,
                                   "screen_threshold": STALE_SHARE_SCREEN,
                                   "population": "AX-10 N user-adjusted 12"},
                    "n_candidates": n_cand, "report": report,
                    "scientific_verdict": None}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps({"n_natural_positive_candidates": n_cand, "report": report},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
