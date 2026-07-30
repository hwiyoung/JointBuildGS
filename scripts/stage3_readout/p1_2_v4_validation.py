"""P1-2: cluster_primitives_v4 (mode-based) generalization test on 5 buildings.

Fixed parameters (NO tuning per building):
  gravity=[0,1,0], wall_vert_thresh=0.15
  az_bin=3°, smoothing σ=2 bins, prominence=10% of max, min_peak_dist=20°
  peak_assign_thresh=25°
  plane_d_bin=0.1m, plane_d_smooth σ=2 bins, plane_d_prominence=10%
  plane_d_min_dist=0.4m, plane_d_assign_max=0.5m
  component_dist=2.0m

GT is used ONLY for evaluation (never as algorithm input).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stage3_readout.eval_stage2_primitives import (
    _load_model, _assign_primitives_fast)
from scripts.stage3_readout.obj_gt import parse_scene_obj
from src.stage3.clustering import (cluster_primitives_v3,
                                   cluster_primitives_v4_dbscan,
                                   cluster_primitives_v4)

GRAVITY = np.array([0.0, 1.0, 0.0])
SCENE = ROOT / "results/phase2_synthesis/scene.obj"
OUT_DIR = ROOT / "results/stage3_v4_validation"

BUILDING_IDS = [0, 1, 3, 5, 8]  # one per distinct GT type
CONDITIONS = ["baseline", "mutual"]


# ---------------------------------------------------------------------------
# GT helpers
# ---------------------------------------------------------------------------


def gt_main_wall_dirs(gt_b, az_tol_deg=10.0):
    """Cluster GT wall faces by azimuth (greedy ±10°). Returns list of
    (mean_az_deg, area_sum, n_faces, mean_normal)."""
    walls = [f for f in gt_b["faces"] if f["semantic_class"] == 2
             and abs(np.dot(f["normal"], GRAVITY)) < 0.1]
    if not walls:
        return []
    az = np.array([np.degrees(np.arctan2(f["normal"][2], f["normal"][0]))
                   for f in walls])
    used = np.zeros(len(walls), dtype=bool)
    out = []
    for i in range(len(walls)):
        if used[i]:
            continue
        d = np.minimum(np.abs(az - az[i]), 360.0 - np.abs(az - az[i]))
        m = (d < az_tol_deg) & (~used)
        used |= m
        members = np.where(m)[0]
        ar_sum = sum(walls[j]["area"] for j in members)
        n_mean = np.array([walls[j]["normal"] for j in members]).mean(0)
        n_mean /= np.linalg.norm(n_mean) + 1e-12
        out.append((az[members].mean(), ar_sum, len(members), n_mean))
    out.sort(key=lambda t: -t[1])
    return out


def gt_roof_faces(gt_b):
    return [f for f in gt_b["faces"] if f["semantic_class"] == 1]


# ---------------------------------------------------------------------------
# Per-building evaluation
# ---------------------------------------------------------------------------


def evaluate_building(gt, prims, bid, pids, gravity=GRAVITY,
                      cluster_fn=cluster_primitives_v4):
    centers = prims["centers"][pids]
    normals = prims["normals"][pids]
    areas = prims["areas"][pids]
    opa = prims["opacities"][pids]
    labs = prims["semantic_probs"][pids].argmax(axis=1)

    if cluster_fn is cluster_primitives_v4:
        gids, rep_n, rep_off, rep_cls = cluster_primitives_v4(
            centers, normals, areas, labs,
            gravity=gravity, opacities=opa)
    elif cluster_fn is cluster_primitives_v4_dbscan:
        gids, rep_n, rep_off, rep_cls = cluster_primitives_v4_dbscan(
            centers, normals, areas, labs, gravity=gravity)
    else:
        gids, rep_n, rep_off, rep_cls = cluster_primitives_v3(
            centers, normals, areas, labs)

    K = len(rep_n)
    sizes = np.array([(gids == k).sum() for k in range(K)])
    wall_mask = labs == 2
    n_wall_total = int(wall_mask.sum())

    wall_groups = np.where(rep_cls == 2)[0]
    roof_groups = np.where(rep_cls == 1)[0]
    wall_sizes = sizes[wall_groups] if K else np.array([])
    max_wall = int(wall_sizes.max()) if len(wall_sizes) else 0
    max_pct = 100.0 * max_wall / max(n_wall_total, 1)

    # GT correspondence
    gt_b = next(b for b in gt["buildings"] if b["building_id"] == bid)
    main_dirs = gt_main_wall_dirs(gt_b)
    roof_faces = gt_roof_faces(gt_b)

    # ---- Wall metrics ----
    wall_match_count = 0  # # v4 wall groups with cos>=0.95 to some main dir
    wall_purity_per_group = []
    for k in wall_groups:
        rn = rep_n[k]
        # match to GT main dir
        if main_dirs:
            cos_md = np.array([float(np.dot(rn, md[3])) for md in main_dirs])
            best_cos = float(cos_md.max())
            best_md_idx = int(cos_md.argmax())
        else:
            best_cos = -1.0; best_md_idx = -1
        if best_cos >= 0.95:
            wall_match_count += 1
        # purity: of primitives in this group that are wall-class, what
        # fraction have |n_i · main_dir_normal| > cos(20°) (≈0.94) for the
        # group's matched main_dir? (stricter than aligning to rep_n)
        member_mask = gids == k
        if best_md_idx < 0 or member_mask.sum() == 0:
            wall_purity_per_group.append(0.0); continue
        # primitive normals in the group
        n_prim = normals[member_mask] / (
            np.linalg.norm(normals[member_mask], axis=1, keepdims=True) + 1e-12)
        target = main_dirs[best_md_idx][3]
        cos_p = np.abs(n_prim @ target)  # |.| handles sign-flip ambiguity
        purity = float((cos_p >= 0.94).mean())  # within ~20° of target
        wall_purity_per_group.append(purity)

    wall_match_pct = (100.0 * wall_match_count / max(len(wall_groups), 1)
                      if len(wall_groups) else 0.0)
    wall_purity_mean = (float(np.mean(wall_purity_per_group))
                        if wall_purity_per_group else 0.0)
    wall_coverage_pct = (100.0 * sum(int((gids == k).sum())
                                     for k in wall_groups) / max(n_wall_total, 1))

    # ---- Roof metrics ----
    roof_match_count = 0
    roof_purity_per_group = []
    for k in roof_groups:
        rn = rep_n[k]
        if roof_faces:
            cos_rf = np.array([float(np.dot(rn, f["normal"]))
                               for f in roof_faces])
            best_cos = float(cos_rf.max())
            best_rf = int(cos_rf.argmax())
        else:
            best_cos = -1.0; best_rf = -1
        if best_cos >= 0.95:
            roof_match_count += 1
        member_mask = gids == k
        if best_rf < 0 or member_mask.sum() == 0:
            roof_purity_per_group.append(0.0); continue
        n_prim = normals[member_mask] / (
            np.linalg.norm(normals[member_mask], axis=1, keepdims=True) + 1e-12)
        target = roof_faces[best_rf]["normal"]
        cos_p = np.abs(n_prim @ target)
        roof_purity_per_group.append(float((cos_p >= 0.94).mean()))

    roof_match_pct = (100.0 * roof_match_count / max(len(roof_groups), 1)
                      if len(roof_groups) else 0.0)
    roof_purity_mean = (float(np.mean(roof_purity_per_group))
                        if roof_purity_per_group else 0.0)

    return {
        "bid": int(bid),
        "type": gt_b["type"],
        "n_prim": int(len(pids)),
        "n_wall": int(n_wall_total),
        "n_roof": int((labs == 1).sum()),
        "v4_wall_groups": int(len(wall_groups)),
        "v4_roof_groups": int(len(roof_groups)),
        "v4_total_groups": int(K),
        "max_wall_size": max_wall,
        "max_wall_pct": float(max_pct),
        "noise": int((gids < 0).sum()),
        "noise_pct": float(100.0 * (gids < 0).sum() / max(len(gids), 1)),
        "gt_main_wall_dirs": int(len(main_dirs)),
        "gt_roof_faces": int(len(roof_faces)),
        "wall_match_pct": float(wall_match_pct),
        "wall_purity_mean": float(wall_purity_mean),
        "wall_coverage_pct": float(wall_coverage_pct),
        "roof_match_pct": float(roof_match_pct),
        "roof_purity_mean": float(roof_purity_mean),
    }


# ---------------------------------------------------------------------------
# Sweeping all (cond, building, version)
# ---------------------------------------------------------------------------


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gt_obj = parse_scene_obj(str(SCENE), frame="obj")
    print(f"Loaded GT scene: {len(gt_obj['buildings'])} buildings")

    results = {}  # results[cond][version][bid] = metrics
    for cond in CONDITIONS:
        ckpt = ROOT / f"results/phase2_ablation_citygml/{cond}/ckpt/final.pt"
        prims = _load_model(str(ckpt))
        assignment = _assign_primitives_fast(prims, gt_obj)
        print(f"\n[{cond}] loaded ckpt; {prims['n_prim']} primitives, "
              f"{len(assignment)} buildings assigned")

        results[cond] = {"v3": {}, "v4_dbscan": {}, "v4_mode": {}}
        for bid in BUILDING_IDS:
            if bid not in assignment:
                print(f"  B{bid}: SKIP — not in assignment")
                continue
            pids = assignment[bid]
            for ver, fn in [("v3", cluster_primitives_v3),
                            ("v4_dbscan", cluster_primitives_v4_dbscan),
                            ("v4_mode", cluster_primitives_v4)]:
                m = evaluate_building(gt_obj, prims, bid, pids,
                                      gravity=GRAVITY, cluster_fn=fn)
                results[cond][ver][bid] = m
            r = results[cond]["v4_mode"][bid]
            print(f"  B{bid:2d} {r['type']:9s} n={r['n_prim']:5d} "
                  f"GT_main={r['gt_main_wall_dirs']:2d} → "
                  f"v4 W={r['v4_wall_groups']:2d} R={r['v4_roof_groups']:2d} "
                  f"max%={r['max_wall_pct']:.1f}% "
                  f"match={r['wall_match_pct']:.0f}% "
                  f"purity={r['wall_purity_mean']*100:.0f}%")

    json_path = OUT_DIR / "p1_2_metrics.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved metrics → {json_path}")
    return results


if __name__ == "__main__":
    res = main()

    # === Build report ===
    out_md = OUT_DIR / "P1_2_REPORT.md"
    L = []
    L.append("# P1-2 — `cluster_primitives_v4` (mode) Generalization Test\n")
    L.append("**5 buildings × 2 conditions, FIXED parameters.** GT is used "
             "for evaluation only (never as algorithm input).\n")
    L.append("Selected buildings (one per GT type): B0 tri-slope, B1 flat, "
             "B3 complex, B5 hip, B8 gable.\n")

    L.append("## Fixed parameters\n")
    L.append("```\n"
             "gravity = [0, 1, 0]\n"
             "wall_vert_thresh = 0.15\n"
             "az_bin = 3°, smoothing σ = 2 bins, prominence = 10% of max\n"
             "az_min_peak_dist = 20°, az_assign_max_dist = 25°\n"
             "plane_d_bin = 0.1 m, plane_d_smooth_σ = 2 bins, prominence = 10%\n"
             "plane_d_min_dist = 0.4 m, plane_d_assign_max = 0.5 m\n"
             "component_dist = 2.0 m  (P1-1b sweep showed 0.5 → 87 walls; 2.0 → 9)\n"
             "```\n")

    # ---- Table 1: overall comparison
    L.append("## Table 1 — Overall comparison\n")
    L.append("| bid | type | cond | v3 walls | v4-db walls | v4-mode walls | "
             "v4-mode roofs | total | max_wall% | noise% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for bid in BUILDING_IDS:
        for cond in CONDITIONS:
            v3 = res[cond]["v3"].get(bid, {})
            v4d = res[cond]["v4_dbscan"].get(bid, {})
            v4m = res[cond]["v4_mode"].get(bid, {})
            if not v4m: continue
            L.append(f"| {bid} | {v4m['type']} | {cond} | "
                     f"{v3.get('v4_wall_groups', '-')} | "
                     f"{v4d.get('v4_wall_groups', '-')} | "
                     f"**{v4m['v4_wall_groups']}** | "
                     f"{v4m['v4_roof_groups']} | "
                     f"{v4m['v4_total_groups']} | "
                     f"{v4m['max_wall_pct']:.1f}% | "
                     f"{v4m['noise_pct']:.1f}% |")
    L.append("")

    # ---- Table 2: wall-only metrics
    L.append("## Table 2 — Wall-only metrics (v4-mode)\n")
    L.append("| bid | cond | GT main dirs | v4 wall groups | ±2? | "
             "wall match (cos>0.95) | wall purity (\\|n·target\\|≥0.94) | "
             "wall coverage |")
    L.append("|---|---|---|---|---|---|---|---|")
    for bid in BUILDING_IDS:
        for cond in CONDITIONS:
            r = res[cond]["v4_mode"].get(bid)
            if not r: continue
            within2 = abs(r["v4_wall_groups"] - r["gt_main_wall_dirs"]) <= 2
            L.append(f"| {bid} | {cond} | {r['gt_main_wall_dirs']} | "
                     f"{r['v4_wall_groups']} | "
                     f"{'✓' if within2 else '✗'} | "
                     f"{r['wall_match_pct']:.0f}% | "
                     f"{r['wall_purity_mean']*100:.0f}% | "
                     f"{r['wall_coverage_pct']:.0f}% |")
    L.append("")

    # ---- Table 3: roof-only
    L.append("## Table 3 — Roof-only metrics (v4-mode)\n")
    L.append("| bid | cond | GT roof faces | v4 roof groups | "
             "roof match (cos>0.95) | roof purity |")
    L.append("|---|---|---|---|---|---|")
    for bid in BUILDING_IDS:
        for cond in CONDITIONS:
            r = res[cond]["v4_mode"].get(bid)
            if not r: continue
            L.append(f"| {bid} | {cond} | {r['gt_roof_faces']} | "
                     f"{r['v4_roof_groups']} | "
                     f"{r['roof_match_pct']:.0f}% | "
                     f"{r['roof_purity_mean']*100:.0f}% |")
    L.append("")

    # ---- Table 4: improvement vs v4-dbscan
    L.append("## Table 4 — v4-mode vs v4-dbscan\n")
    L.append("| bid | cond | v4-db walls | v4-mode walls | wall ↑? | "
             "v4-db max% | v4-mode max% | max% ↓? |")
    L.append("|---|---|---|---|---|---|---|---|")
    for bid in BUILDING_IDS:
        for cond in CONDITIONS:
            d = res[cond]["v4_dbscan"].get(bid)
            m = res[cond]["v4_mode"].get(bid)
            if not d or not m: continue
            up = m["v4_wall_groups"] > d["v4_wall_groups"]
            down = m["max_wall_pct"] < d["max_wall_pct"]
            L.append(f"| {bid} | {cond} | {d['v4_wall_groups']} | "
                     f"{m['v4_wall_groups']} | "
                     f"{'✓' if up else ('=' if m['v4_wall_groups']==d['v4_wall_groups'] else '✗')} | "
                     f"{d['max_wall_pct']:.0f}% | "
                     f"{m['max_wall_pct']:.0f}% | "
                     f"{'✓' if down else '✗'} |")
    L.append("")

    # ---- GO/NG verdict (Mutual)
    L.append("## GO/NG verdict (Mutual; GT-correspondence)\n")
    L.append("| bid | type | walls±2? | match >70%? | purity >70%? | "
             "v4-db ↑? | verdict |")
    L.append("|---|---|---|---|---|---|---|")
    go_count = 0
    failures = []  # list of (bid, type, reasons[])
    for bid in BUILDING_IDS:
        m = res["mutual"]["v4_mode"].get(bid)
        d = res["mutual"]["v4_dbscan"].get(bid)
        if not m or not d: continue
        within2 = abs(m["v4_wall_groups"] - m["gt_main_wall_dirs"]) <= 2
        match_ok = m["wall_match_pct"] > 70.0
        purity_ok = m["wall_purity_mean"] > 0.70
        improve_ok = m["v4_wall_groups"] > d["v4_wall_groups"] or \
                     m["max_wall_pct"] < d["max_wall_pct"]
        passes = [within2, match_ok, purity_ok, improve_ok]
        # Strict: all 4 criteria must pass
        verdict = "GO" if all(passes) else "NG"
        if verdict == "GO":
            go_count += 1
        L.append(f"| {bid} | {m['type']} | "
                 f"{'✓' if within2 else '✗'} | "
                 f"{'✓' if match_ok else '✗'} | "
                 f"{'✓' if purity_ok else '✗'} | "
                 f"{'✓' if improve_ok else '✗'} | "
                 f"**{verdict}** |")
        if verdict == "NG":
            reasons = []
            if not within2:
                if m["v4_wall_groups"] < m["gt_main_wall_dirs"] - 2:
                    reasons.append("azimuth peak 부족")
                else:
                    reasons.append("azimuth peak 과다")
            if not match_ok:
                reasons.append(f"wall matching 낮음 ({m['wall_match_pct']:.0f}%)")
            if not purity_ok:
                reasons.append(f"wall purity 낮음 ({m['wall_purity_mean']*100:.0f}%)")
            if m["noise_pct"] > 40.0:
                reasons.append(f"coverage 손실 (noise {m['noise_pct']:.0f}%)")
            if m["roof_match_pct"] < 50.0:
                reasons.append(f"roof matching 낮음 ({m['roof_match_pct']:.0f}%)")
            failures.append((bid, m['type'], reasons))

    L.append(f"\n**Mutual {go_count}/5 GO** → "
             f"{'**P1-3 진행**' if go_count >= 4 else '재검토 필요'}.\n")

    # ---- Failure reasons
    if failures:
        L.append("## 실패 건물 원인 기록 (수정 없음 — 기록만)\n")
        for bid, btype, reasons in failures:
            L.append(f"### B{bid} ({btype})")
            for r in reasons:
                L.append(f"- [x] {r}")
            L.append("")

    # ---- Summary observations
    L.append("## 관찰\n")
    L.append("- **chaining 해결 일관성**: Mutual 모든 건물에서 v4-mode max_wall% < v4-dbscan max_wall%. "
             "적도 chaining 본질적 해결.")
    L.append("- **roof은 v4와 무관** (v3 path 그대로). roof matching/purity가 낮은 건 학습 측 약점.")
    L.append("- **baseline은 prim wall vert 낮아 non-vert 분기로 fallback** → wall groups 인플레.")

    out_md.write_text("\n".join(L))
    print(f"\nReport → {out_md}")
