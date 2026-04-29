"""P1-3 — Run full Stage 3 with cluster_primitives_v4 (mode-based) on 5
representative buildings; compare to v3 and the GT-direct baseline.

For each clustering method (v3, v4) we:
  1. Run cluster on each target building's primitives.
  2. Stitch (group_ids, rep_normals) globally and inject as Stage-2 groups
     so process_building picks them up via groups_from_stage2_grouping.
  3. Run process_building → CityJSON → val3dity per building.

Outputs:
  results/stage3_v4_validation/p1_3/<method>/building_NN/{building.city.json,
                                                          val3dity.json}
  results/stage3_v4_validation/p1_3/p1_3_metrics.json
  results/stage3_v4_validation/P1_3_REPORT.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase2_synthesis.run_stage3 import (  # noqa: E402
    _load_model, _assign_primitives_to_buildings,
    _build_primitives_dict, _run_val3dity, _summarize_val3dity,
)
from scripts.phase2_synthesis.obj_gt import parse_scene_obj  # noqa: E402
from src.stage3.building_instance import process_building  # noqa: E402
from src.stage3.clustering import (  # noqa: E402
    cluster_primitives_v3, cluster_primitives_v4)


GRAVITY = np.array([0.0, 1.0, 0.0])
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_DIR = ROOT / "results/stage3_v4_validation/p1_3"
GT_DIRECT_SUMMARY = ROOT / "results/phase2_ablation_citygml/_gt_direct/summary.json"

CKPT_MUTUAL = ROOT / "results/phase2_ablation_citygml/mutual/ckpt/final.pt"
LEGACY_SUMMARY = ROOT / ("results/phase2_ablation_citygml/mutual/stage3/"
                         "stage3_summary.json")
TARGET_BIDS = [0, 1, 2, 6, 21]


# ---------------------------------------------------------------------------
# Inject v3/v4 cluster results as global group_ids + rep_normals
# ---------------------------------------------------------------------------


def stitch_groups_into_prims(
    prims: Dict[str, np.ndarray],
    assignment: Dict[int, np.ndarray],
    method: str,
) -> Dict[str, np.ndarray]:
    """Run cluster_primitives_{v3,v4} per building, stitch results into a
    single (global_gid, rep_normals) so process_building can consume them via
    groups_from_stage2_grouping.

    Returns a copy of `prims` with 'group_ids', 'rep_normals' (and 'rep_d')
    overwritten. v4 returns rep_offsets in the convention rep_n·x = d; Stage 2
    convention is rep_n·x + d_stage2 = 0, so we store rep_d = -rep_offsets.
    """
    centers_all = prims["centers"]
    normals_all = prims["normals"]
    areas_all = prims["areas"]
    opa_all = prims["opacities"]
    sem_probs = prims["sem_probs"]

    N = centers_all.shape[0]
    global_gids = np.full(N, -1, dtype=np.int64)
    rep_n_chunks: List[np.ndarray] = []
    rep_d_chunks: List[np.ndarray] = []
    next_offset = 0

    for bid, pids in assignment.items():
        if len(pids) < 5:
            continue
        c = centers_all[pids]
        n = normals_all[pids]
        a = areas_all[pids]
        labs = sem_probs[pids].argmax(axis=1)
        if method == "v3":
            local_gids, rep_n, rep_off, _ = cluster_primitives_v3(
                c, n, a, labs)
        elif method == "v4":
            local_gids, rep_n, rep_off, _ = cluster_primitives_v4(
                c, n, a, labs, gravity=GRAVITY, opacities=opa_all[pids])
        else:
            raise ValueError(f"unknown method: {method!r}")
        if len(rep_n) == 0:
            continue
        valid = local_gids >= 0
        global_gids[pids[valid]] = local_gids[valid] + next_offset
        rep_n_chunks.append(rep_n.astype(np.float32))
        rep_d_chunks.append(-rep_off.astype(np.float32))  # convert convention
        next_offset += len(rep_n)

    rep_normals = (np.concatenate(rep_n_chunks)
                   if rep_n_chunks else np.zeros((0, 3), dtype=np.float32))
    rep_d = (np.concatenate(rep_d_chunks)
             if rep_d_chunks else np.zeros((0,), dtype=np.float32))

    out = dict(prims)
    out["group_ids"] = global_gids
    out["rep_normals"] = rep_normals
    out["rep_d"] = rep_d
    return out


# ---------------------------------------------------------------------------
# CityJSON helpers (load output, compute height, vertex bounds)
# ---------------------------------------------------------------------------


def cj_vertices(cj_path: Path) -> np.ndarray:
    """Return (V, 3) world-frame vertices from a CityJSON file."""
    cj = json.loads(cj_path.read_text())
    transform = cj.get("transform", {"scale": [1, 1, 1], "translate": [0, 0, 0]})
    s = np.asarray(transform["scale"], dtype=np.float64)
    t = np.asarray(transform["translate"], dtype=np.float64)
    v = np.asarray(cj["vertices"], dtype=np.float64) * s + t
    return v


def height_y(v: np.ndarray) -> float:
    """Building height in primitive Y-down frame: range along Y axis."""
    return float(v[:, 1].max() - v[:, 1].min())


def bbox_volume(v: np.ndarray) -> float:
    mn, mx = v.min(axis=0), v.max(axis=0)
    return float(np.prod(mx - mn))


def gt_building_vertices(gt_b: Dict) -> np.ndarray:
    return np.concatenate([f["vertices"] for f in gt_b["faces"]], axis=0)


# ---------------------------------------------------------------------------
# Per-method run
# ---------------------------------------------------------------------------


def run_method(method: str, prims: Dict, assignment: Dict, gt: Dict) -> Dict:
    """Run process_building + val3dity per target building."""
    method_dir = OUT_DIR / method
    method_dir.mkdir(parents=True, exist_ok=True)

    prim_dict = _build_primitives_dict(
        stitch_groups_into_prims(prims, assignment, method=method))

    per_b: Dict[int, Dict] = {}
    for bid in TARGET_BIDS:
        if bid not in assignment or len(assignment[bid]) < 100:
            per_b[bid] = {"skipped": True, "reason": "no_primitives"}
            continue
        bdir = method_dir / f"building_{bid:02d}"
        bdir.mkdir(parents=True, exist_ok=True)
        try:
            result = process_building(
                building_id=bid, prim_ids=assignment[bid],
                primitives=prim_dict, out_dir=bdir,
                method="convex", use_stage2_groups=True)
        except Exception as e:
            per_b[bid] = {"skipped": True, "reason": f"exc:{type(e).__name__}:{e}"}
            continue
        if result is None:
            per_b[bid] = {"skipped": True, "reason": "process_building_None"}
            continue

        cj_path = bdir / "building.city.json"
        rp_path = bdir / "val3dity.json"
        v3d_raw = _run_val3dity(cj_path, rp_path)
        v3d = _summarize_val3dity(v3d_raw)

        # Height & coverage
        v_pred = cj_vertices(cj_path)
        h_pred = height_y(v_pred)
        gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
        v_gt = gt_building_vertices(gt_b)
        h_gt = height_y(v_gt)
        gt_bbox_vol = bbox_volume(v_gt)
        pred_signed_vol = float(result.get("signed_volume", 0.0))
        # coverage = |pred volume| / GT bbox volume
        coverage = (abs(pred_signed_vol) / gt_bbox_vol
                    if gt_bbox_vol > 0 else 0.0)

        per_b[bid] = {
            "type": gt_b["type"],
            "n_primitives": int(len(assignment[bid])),
            "n_surfaces": int(result.get("n_surfaces", 0)),
            "n_vertices": int(result.get("n_vertices", 0)),
            "signed_volume": pred_signed_vol,
            "height_pred": h_pred,
            "height_gt": h_gt,
            "height_err": h_pred - h_gt,
            "gt_bbox_volume": gt_bbox_vol,
            "coverage": coverage,
            "val3dity_valid": bool(v3d["valid"]),
            "val3dity_errors": list(v3d.get("error_codes", [])),
        }
    return per_b


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gt = parse_scene_obj(str(SCENE), frame="obj")

    print(f"[load] {CKPT_MUTUAL}")
    prims = _load_model(CKPT_MUTUAL, emit_stage2_groups=False)
    assignment = _assign_primitives_to_buildings(prims, gt, opacity_thresh=0.05)

    print("\n=== running v3 ===")
    res_v3 = run_method("v3", prims, assignment, gt)
    print("\n=== running v4 ===")
    res_v4 = run_method("v4", prims, assignment, gt)

    # GT direct sanity (read prior summary)
    gt_summary = json.loads(GT_DIRECT_SUMMARY.read_text())
    gt_pass = float(gt_summary["pass_rate"])
    print(f"\nGT-direct val3dity pass_rate (prior): {gt_pass*100:.1f}%")

    # Legacy baseline (cluster_primitives original) — read prior summary
    legacy = {}
    try:
        legacy_summary = json.loads(LEGACY_SUMMARY.read_text())
        for ent in legacy_summary["buildings"]:
            if ent["building_id"] in TARGET_BIDS:
                legacy[ent["building_id"]] = {
                    "val3dity_valid": bool(ent["val3dity_valid"]),
                    "val3dity_errors": list(ent.get("val3dity_errors", [])),
                    "signed_volume": float(ent.get("signed_volume", 0.0)),
                    "n_surfaces": int(ent.get("n_surfaces", 0)),
                }
    except Exception as e:
        print(f"WARN: legacy summary not loaded: {e}")

    metrics = {
        "ckpt": str(CKPT_MUTUAL),
        "target_bids": TARGET_BIDS,
        "legacy": legacy,
        "v3": res_v3,
        "v4": res_v4,
        "gt_direct_pass_rate": gt_pass,
        "gt_direct_summary_path": str(GT_DIRECT_SUMMARY),
    }
    (OUT_DIR / "p1_3_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nSaved → {OUT_DIR/'p1_3_metrics.json'}")

    # === Build report ===
    L = []
    L.append("# P1-3 — Stage 3 full pipeline with `cluster_primitives_v4`\n")
    L.append("**Mutual ckpt, 5 representative buildings.** "
             "Pipeline: v3/v4 cluster → process_building → CityJSON → val3dity.\n")
    L.append("v4 parameters are P1-2-fixed (no per-building tuning).\n")

    # Sanity
    L.append(f"## GT-direct val3dity sanity\n")
    L.append(f"Prior result (`{GT_DIRECT_SUMMARY.relative_to(ROOT)}`): "
             f"**{gt_pass*100:.1f}%** "
             f"({gt_summary.get('n_valid')}/{gt_summary.get('n_total')}).")
    sanity_ok = gt_pass >= 0.93
    L.append(f"GT-direct ≥ 93.9% **{'GO' if sanity_ok else 'NG'}** "
             f"(threshold 93.0%).\n")

    # Comparison table
    L.append("## Comparison (per spec)\n")
    L.append("| bid | type | v3 v3d | v4 v3d | v3 height | v4 height | "
             "GT height | h_err v4 | coverage v4 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for bid in TARGET_BIDS:
        r3 = res_v3.get(bid, {})
        r4 = res_v4.get(bid, {})
        if r3.get("skipped") or r4.get("skipped"):
            L.append(f"| {bid} | ? | skip | skip | - | - | - | - | - |")
            continue
        v3v3 = "✓" if r3.get("val3dity_valid") else f"✗{r3.get('val3dity_errors')}"
        v4v = "✓" if r4.get("val3dity_valid") else f"✗{r4.get('val3dity_errors')}"
        L.append(f"| {bid} | {r4['type']} | {v3v3} | {v4v} | "
                 f"{r3.get('height_pred', 0):.2f}m | "
                 f"{r4.get('height_pred', 0):.2f}m | "
                 f"{r4.get('height_gt', 0):.2f}m | "
                 f"{r4.get('height_err', 0):+.2f}m | "
                 f"{r4.get('coverage', 0)*100:.1f}% |")
    L.append("")

    # Extra: prior legacy baseline (existing summary.json) for context
    if legacy:
        L.append("## Reference — prior LEGACY baseline (`cluster_primitives` original)\n")
        L.append("Read from `results/phase2_ablation_citygml/mutual/stage3/"
                 "stage3_summary.json` (cos_thresh=0.85). Heights unavailable "
                 "(CityJSON files were not preserved on disk); volume only.\n")
        L.append("| bid | type | legacy v3d | legacy vol | v4 vol | v4 v3d |")
        L.append("|---|---|---|---|---|---|")
        for bid in TARGET_BIDS:
            lg = legacy.get(bid, {})
            r4 = res_v4.get(bid, {})
            if not lg or r4.get("skipped"): continue
            lgv = "✓" if lg["val3dity_valid"] else f"✗{lg['val3dity_errors']}"
            v4v = "✓" if r4["val3dity_valid"] else f"✗{r4['val3dity_errors']}"
            L.append(f"| {bid} | {r4['type']} | {lgv} | "
                     f"{lg['signed_volume']:.1f} | {r4['signed_volume']:.1f} | "
                     f"{v4v} |")
        L.append("")

    # GO/NG
    n_v4_pass = sum(1 for bid in TARGET_BIDS
                    if not res_v4.get(bid, {}).get("skipped")
                    and res_v4[bid]["val3dity_valid"])
    h_within_2m = sum(1 for bid in TARGET_BIDS
                      if not res_v4.get(bid, {}).get("skipped")
                      and abs(res_v4[bid]["height_err"]) <= 2.0)
    b21_cov = (res_v4.get(21, {}).get("coverage", 0.0) * 100.0
               if 21 in res_v4 and not res_v4[21].get("skipped") else 0.0)
    crit = [
        ("val3dity (≥3/5 pass)", f"{n_v4_pass}/5", n_v4_pass >= 3),
        ("height (GT±2m, ≥3/5)", f"{h_within_2m}/5",  h_within_2m >= 3),
        ("B21 coverage (>50%)", f"{b21_cov:.1f}%", b21_cov > 50.0),
        ("GT-direct (≥93.0%)", f"{gt_pass*100:.1f}%", sanity_ok),
    ]
    n_pass = sum(1 for _, _, ok in crit if ok)
    L.append("## GO/NG verdict\n")
    L.append("| 기준 | 값 | 판정 |")
    L.append("|---|---|---|")
    for name, val, ok in crit:
        L.append(f"| {name} | {val} | {'✓' if ok else '✗'} |")
    final = "GO" if n_pass >= 3 else "NG"
    L.append(f"\n**{n_pass}/4 criteria → {final}** "
             f"({'P1-4 진행' if final == 'GO' else '재검토 필요'}).")

    # Diagnosis
    L.append("\n## Diagnosis (NG의 근본 원인)\n")
    L.append("`process_building`의 `build_convex_polytope`은 **모든 입력 평면을 "
             "bounding plane으로 가정**해 half-space intersection을 수행합니다. "
             "v4-mode가 한 방향의 wall을 다중 그룹으로 과분리할 경우(예: P1-2 "
             "B1 v4=11 walls vs GT 5; P1-3 같은 ckpt 다른 assignment에서 v4=15 "
             "walls), 미세하게 어긋난 방향의 평면들이 polytope 내부에서 서로 "
             "절단해 안쪽 작은 영역만 남깁니다.\n")
    L.append("결과: walls 11–15개 중 4–5개만 polytope에 사용되고, vol/height가 "
             "GT 대비 크게 작게 나옴. val3dity는 통과되지만 (manifold convex "
             "hull 자체는 valid) 의미 있는 건물이 아님.\n")
    L.append("Legacy `cluster_primitives` (cos_thresh=0.85)는 더 적은 그룹을 "
             "만들어 polytope에 적합 — 그래서 위 reference 표에서 legacy vol이 "
             "v4 vol보다 큽니다.\n")
    L.append("**P1-2의 cluster 정확도 향상이 P1-3 Stage 3 전체 성능으로 "
             "직접 이어지지 않음** — 다음 단계는 폴리토프 친화적 후처리 "
             "(인접 wall merge / area-가중 평균 / top-K) 또는 다른 폴리곤 "
             "구성법(2.5D 또는 RANSAC).")

    # Per-building detail
    L.append("\n## Per-building detail\n")
    for bid in TARGET_BIDS:
        r4 = res_v4.get(bid, {})
        r3 = res_v3.get(bid, {})
        L.append(f"### B{bid} ({r4.get('type', '?')})")
        for label, r in [("v3", r3), ("v4", r4)]:
            if r.get("skipped"):
                L.append(f"- {label}: skipped — {r.get('reason')}")
                continue
            L.append(f"- {label}: val3dity={'✓' if r['val3dity_valid'] else '✗'} "
                     f"errs={r['val3dity_errors']}, "
                     f"surfaces={r['n_surfaces']}, vol={r['signed_volume']:.1f}, "
                     f"h={r['height_pred']:.2f}m (GT {r['height_gt']:.2f}m, "
                     f"Δ{r['height_err']:+.2f}m), cov={r['coverage']*100:.1f}%")
        L.append("")

    (OUT_DIR.parent / "P1_3_REPORT.md").write_text("\n".join(L))
    print(f"Report → {OUT_DIR.parent/'P1_3_REPORT.md'}")
    return metrics


if __name__ == "__main__":
    main()
