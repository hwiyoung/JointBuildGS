#!/usr/bin/env python3
"""A3a aux-v4a: recompute observation geometry with zeta=45.700.

No reconstruction/retraining. Texture/lowtex columns are carried over from v3
and explicitly marked contaminated for this step.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import platform
import subprocess
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
import population_aux_v3 as v3  # noqa: E402
from projection_datum import describe_projection_config, projection_geoid_m  # noqa: E402


REPO = Path("/workspace/JointBuildGS")
DOCS = REPO / "docs"
MOB = REPO / "results/tum_transfer/mob/overseg_lever"
RUN_ID = "20260703_aux_v4a"
RUN_DIR = REPO / "phases" / "p2-gsjso" / "runs" / RUN_ID
FIG_DIR = DOCS / "figs/aux_v4a"
OUT_DOCS = DOCS / "population_aux_v4.csv"
OUT_RESULTS = MOB / "population_aux_v4.csv"
BESTVIEW_OUT = MOB / "population_aux_v4_bestview.json"
CROSS_CSV = DOCS / "bucket_crosswalk_v2.csv"
CROSS_MD = DOCS / "bucket_crosswalk_v2.md"
REPORT_MD = DOCS / "aux_v4_change_report.md"
V3_DOCS = DOCS / "population_aux_v3.csv"
SUCCESS_CSV = REPO / "phases/p0-audit/runs/w2_1d_bucket_relabel_20260612_final/docs/W2_1c_paired_status.csv"
ROOT_SPEC = REPO / "기준문서_방법론·모집단·비교설계_v1.md"
GEOID_M = 45.700
UNCERTAINTY_M = 0.05
GEOM_ALLOW_M = 2.0
MASK_ALLOW_M = 0.3
NADIR_MAX_DEG = 20.0


TEXTURE_COLS = ["roof_lowtex_frac", "roof_grad_p10", "roof_sat_frac", "roof_periodicity", "roof_lowtex_v4"]
OBS_COLS = [
    "n_samples",
    "n_views_nadir",
    "n_views_oblique",
    "n_views_total",
    "median_pair_angle_deg",
    "frac_pairs_10_60deg",
    "median_incidence_deg",
    "frac_views_incidence_le60",
    "roof_obs_covered_frac",
    "recon_score_median",
    "recon_score_p10",
    "occlusion_frac_approx",
]


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover
        return f"unavailable: {exc}"


def fnum(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def percentile_nearest(vals: list[float], q: float) -> float:
    vals = sorted(v for v in vals if v is not None and np.isfinite(v))
    if not vals:
        return float("nan")
    idx = min(len(vals) - 1, max(0, math.ceil(q * len(vals)) - 1))
    return float(vals[idx])


def load_v3_rows() -> dict[str, dict[str, str]]:
    return {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(V3_DOCS))}


def load_footprints():
    feats = json.load(open(v3.GEOJSON))["features"]
    fp = {}
    for feat in feats:
        bid = feat["properties"]["building_id"].replace("DEBY_LOD2_", "")
        geom = feat["geometry"]
        ring = geom["coordinates"][0] if geom["type"] == "Polygon" else max((p[0] for p in geom["coordinates"]), key=len)
        nv = len(ring) - 1 if len(ring) > 1 and ring[0] == ring[-1] else len(ring)
        prev = fp.get(bid)
        if prev is None or nv > prev[0]:
            fp[bid] = (
                nv,
                feat["properties"].get("area_m2"),
                np.array(ring, float),
                (
                    feat["properties"]["min_x"],
                    feat["properties"]["min_y"],
                    feat["properties"]["max_x"],
                    feat["properties"]["max_y"],
                ),
            )
    return fp


def recompute_aux() -> tuple[list[dict[str, object]], dict[str, str]]:
    np.random.seed(0)
    old = load_v3_rows()
    sr = json.load(open(v3.DATA / "work/opf/opf/scene_reference_frame.json"))
    width, height, params = v3.parse_cam_model(v3.DATA / "work/colmap/sparse/0/cameras.txt")
    cams = v3.parse_cameras(v3.DATA / "work/colmap/sparse/0/images.txt", sr)
    fp = load_footprints()
    bids = sorted(fp)
    print(f"[v4a] {len(cams)} cameras, {len(bids)} buildings, zeta={projection_geoid_m():.3f}")
    rows = []
    best_view = {}
    neighbor = []

    for bi, bid in enumerate(bids):
        nverts, area, ring, bbox = fp[bid]
        row: dict[str, object] = {
            "building_id": f"DEBY_LOD2_{bid}",
            "footprint_area_m2": round(float(area), 2) if area else "",
            "n_exterior_vertices": nverts,
        }
        roof_type, roof, wall = v3.gml_building(bid)
        if not roof:
            row.update({k: "" for k in OBS_COLS})
            rows.append(row)
            continue
        points, normals = v3.sample_roof(roof)
        if len(points) == 0:
            row.update({k: "" for k in OBS_COLS})
            rows.append(row)
            continue
        points_ellip = v3.as_ellipsoidal_points(points)
        roof_z = float(np.median(points[:, 2]))
        zmax = float(points[:, 2].max())
        neighbor.append((float(np.mean(ring[:, 0])), float(np.mean(ring[:, 1])), zmax, bid))

        corners = np.array(
            [
                [bbox[0], bbox[1], roof_z],
                [bbox[2], bbox[1], roof_z],
                [bbox[2], bbox[3], roof_z],
                [bbox[0], bbox[3], roof_z],
            ]
        )
        candidates = []
        for ci, cam in enumerate(cams):
            uv, front = v3.project(corners, cam, width, height, params, sr)
            if (
                front.any()
                and np.nanmax(uv[:, 0]) >= 0
                and np.nanmin(uv[:, 0]) < width
                and np.nanmax(uv[:, 1]) >= 0
                and np.nanmin(uv[:, 1]) < height
            ):
                candidates.append(ci)

        ns = len(points)
        per_sample = [[] for _ in range(ns)]
        for ci in candidates:
            cam = cams[ci]
            uv, front = v3.project(points, cam, width, height, params, sr)
            inframe = front & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
            if not inframe.any():
                continue
            vec = cam.center - points_ellip
            dist = np.linalg.norm(vec, axis=1)
            unit = vec / np.maximum(dist[:, None], 1e-9)
            cosinc = np.clip(np.abs(np.sum(unit * normals, axis=1)), -1, 1)
            inc = np.degrees(np.arccos(cosinc))
            nadir = np.degrees(np.arccos(np.clip(unit[:, 2], -1, 1)))
            for si in np.where(inframe)[0]:
                per_sample[si].append((float(inc[si]), float(dist[si]), unit[si], ci, float(nadir[si])))

        n_nadir = n_oblique = n_total = covered = 0
        pair_angles = []
        incidence_all = []
        recon = []
        best_nadir = (1e9, None)
        best_incidence = (1e9, None)
        for si, visible in enumerate(per_sample):
            if not visible:
                continue
            visible.sort(key=lambda t: t[0])
            for inc, dist, unit, ci, nad in visible:
                incidence_all.append(inc)
                if nad <= v3.NADIR_MAX_DEG:
                    n_nadir += 1
                else:
                    n_oblique += 1
                if nad < best_nadir[0]:
                    best_nadir = (nad, cams[ci].name)
                if inc < best_incidence[0]:
                    best_incidence = (inc, cams[ci].name)
            n_total += len(visible)
            vv = visible[: v3.MAXV_PAIR]
            rays = np.array([t[2] for t in vv])
            incs = np.array([t[0] for t in vv])
            dists = np.array([t[1] for t in vv])
            if len(vv) >= 2:
                cosine = np.clip(rays @ rays.T, -1, 1)
                angles = np.degrees(np.arccos(cosine))
                iu, ju = np.triu_indices(len(vv), k=1)
                pang = angles[iu, ju]
                pair_angles.extend(pang.tolist())
                good = bool(np.any((pang >= v3.PAIR_LO) & (pang <= v3.PAIR_HI)))
                wp = np.exp(-((pang - v3.PAR_PEAK) ** 2) / (2 * v3.PAR_SIG**2))
                wi = np.maximum(0.0, np.cos(np.radians(0.5 * (incs[iu] + incs[ju]))))
                dm = 0.5 * (dists[iu] + dists[ju])
                wd = np.where(
                    dm < v3.D_LO,
                    np.maximum(0, dm / v3.D_LO),
                    np.where(dm > v3.D_HI, np.maximum(0, 1 - (dm - v3.D_HI) / v3.D_HI), 1.0),
                )
                recon.append(float(np.sum(wp * wi * wd)))
                if good:
                    covered += 1
            else:
                recon.append(0.0)

        row.update(
            {
                "n_samples": ns,
                "n_views_nadir": round(n_nadir / ns, 2),
                "n_views_oblique": round(n_oblique / ns, 2),
                "n_views_total": round(n_total / ns, 2),
                "median_pair_angle_deg": round(float(np.median(pair_angles)), 2) if pair_angles else "",
                "frac_pairs_10_60deg": round(float(np.mean([(v3.PAIR_LO <= a <= v3.PAIR_HI) for a in pair_angles])), 3)
                if pair_angles
                else "",
                "median_incidence_deg": round(float(np.median(incidence_all)), 2) if incidence_all else "",
                "frac_views_incidence_le60": round(float(np.mean([(i <= v3.INC_OK_DEG) for i in incidence_all])), 3)
                if incidence_all
                else "",
                "roof_obs_covered_frac": round(covered / ns, 3),
                "recon_score_median": round(float(np.median(recon)), 3) if recon else 0.0,
                "recon_score_p10": round(float(np.percentile(recon, 10)), 3) if recon else 0.0,
                "_best_view": (best_nadir[1] if best_nadir[0] <= v3.NADIR_MAX_DEG else best_incidence[1]) or "",
                "_cx": float(np.mean(ring[:, 0])),
                "_cy": float(np.mean(ring[:, 1])),
                "_zmax": zmax,
            }
        )
        for col in TEXTURE_COLS:
            row[col] = old.get(bid, {}).get(col, "")
        row["lowtex_version"] = "v4a_carryover_v3_contaminated"
        best_view[row["building_id"]] = row.get("_best_view", "")
        rows.append(row)
        if (bi + 1) % 20 == 0:
            print(f"[v4a] {bi+1}/{len(bids)} buildings")

    nb = np.array([(x, y, z) for x, y, z, _ in neighbor]) if neighbor else np.zeros((0, 3))
    for row in rows:
        if "_cx" not in row:
            row["occlusion_frac_approx"] = ""
            continue
        cx = float(row["_cx"])
        cy = float(row["_cy"])
        zt = float(row["_zmax"])
        if len(nb) == 0:
            row["occlusion_frac_approx"] = 0.0
            continue
        dist = np.sqrt((nb[:, 0] - cx) ** 2 + (nb[:, 1] - cy) ** 2)
        near = (dist > 1) & (dist < 30.0)
        taller = near & (nb[:, 2] > zt + 2.0)
        row["occlusion_frac_approx"] = round(float(taller.sum() / max(1, near.sum())), 3) if near.any() else 0.0
    return rows, best_view


def write_aux(rows: list[dict[str, object]], best_view: dict[str, str]) -> None:
    cols = [
        "building_id",
        "footprint_area_m2",
        "n_exterior_vertices",
        "n_samples",
        "n_views_nadir",
        "n_views_oblique",
        "n_views_total",
        "median_pair_angle_deg",
        "frac_pairs_10_60deg",
        "median_incidence_deg",
        "frac_views_incidence_le60",
        "roof_obs_covered_frac",
        "recon_score_median",
        "recon_score_p10",
        *TEXTURE_COLS,
        "lowtex_version",
        "occlusion_frac_approx",
    ]
    for out in (OUT_DOCS, OUT_RESULTS):
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as fo:
            writer = csv.DictWriter(fo, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in cols})
    BESTVIEW_OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(best_view, open(BESTVIEW_OUT, "w"), ensure_ascii=False, indent=2)


def canonical_status():
    canon = glob.glob(str(REPO / "phases/p0-audit/runs/w2_1_roofer_default_*/building_reconstruction_status.csv"))[0]
    status = {}
    for row in csv.DictReader(open(canon)):
        status.setdefault(row["building_id"].replace("DEBY_LOD2_", ""), {})[row["input"].lower()] = row
    return status


def gen48_and_ctrl114(status: dict[str, dict[str, dict[str, str]]]) -> tuple[list[str], list[str]]:
    gen48 = []
    ctrl114 = []
    for bid, by_input in status.items():
        als = by_input.get("als", {})
        dim = by_input.get("dim", {})
        if als.get("has_lod22") == "True" and dim.get("has_lod22") == "True":
            ctrl114.append(bid)
        if als.get("has_lod22") == "True" and dim.get("has_lod22") != "True" and dim.get("reason") != "missing_lod22_geometry":
            gen48.append(bid)
    return sorted(gen48), sorted(ctrl114)


def load_old_crosswalk() -> dict[str, dict[str, str]]:
    return {r["building_id"].replace("DEBY_LOD2_", ""): r for r in csv.DictReader(open(DOCS / "bucket_crosswalk.csv"))}


def classify(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    aux = {str(r["building_id"]).replace("DEBY_LOD2_", ""): r for r in rows}
    status = canonical_status()
    gen48, ctrl114 = gen48_and_ctrl114(status)
    inc_vals = [fnum(aux[b].get("frac_views_incidence_le60")) for b in ctrl114 if b in aux]
    recon_vals = [fnum(aux[b].get("recon_score_median")) for b in ctrl114 if b in aux]
    inc_thr = percentile_nearest([v for v in inc_vals if v is not None], 0.10)
    recon_thr = percentile_nearest([v for v in recon_vals if v is not None], 0.10)
    recon_a1 = float(min(v for v in recon_vals if v is not None))
    g8 = {r["bid"]: r for r in csv.DictReader(open(MOB / "gen_8way.csv"))}
    oldb = {r["bid"]: r["bucket"] for r in csv.DictReader(open(MOB / "d12_buckets.csv"))}
    oldcw = load_old_crosswalk()
    veto_arms = ["gs_seed_sparse", "gs_seed_dense", "gs_seed_acmp", "raw_sparse", "raw_acmp"]
    rows_out = []
    for bid in gen48:
        r = aux.get(bid, {})
        inc60 = fnum(r.get("frac_views_incidence_le60"))
        recon = fnum(r.get("recon_score_median"))
        area = fnum(r.get("footprint_area_m2"))
        g = g8.get(bid, {})
        recovered = [arm for arm in veto_arms if g.get(arm) == "1"]
        veto = bool(recovered)
        a_cand = (inc60 is not None and inc60 < inc_thr) and (recon is not None and recon < recon_thr)
        if a_cand and veto:
            new_class = "경계_방법회복"
        elif a_cand and recon is not None and recon < recon_a1:
            new_class = "A1_촬영확실"
        elif a_cand:
            new_class = "A2_촬영경계"
        else:
            new_class = "수동판정"
        old_class = oldcw.get(bid, {}).get("new_class", "")
        rows_out.append(
            {
                "building_id": f"DEBY_LOD2_{bid}",
                "old_bucket": oldb.get(bid, "?"),
                "old_class": old_class,
                "new_class": new_class,
                "moved": int(old_class != new_class),
                "a_cand": int(a_cand),
                "veto_recovered": ";".join(recovered),
                "frac_views_incidence_le60": "" if inc60 is None else round(inc60, 3),
                "recon_score_median": "" if recon is None else round(recon, 3),
                "n_views_nadir": r.get("n_views_nadir", ""),
                "dim_rf_pt_density": status.get(bid, {}).get("dim", {}).get("rf_pt_density", ""),
                "dim_reason": status.get(bid, {}).get("dim", {}).get("reason", ""),
                "area_m2": "" if area is None else round(area, 2),
            }
        )
    metrics = {
        "inc60_p10_thr": inc_thr,
        "recon_p10_thr": recon_thr,
        "recon_min_a1_thr": recon_a1,
        "n_gen48": len(gen48),
        "n_ctrl114": len(ctrl114),
        "class_counts": dict(Counter(r["new_class"] for r in rows_out)),
        "old_counts": dict(Counter(oldcw.get(b, {}).get("new_class", "?") for b in gen48)),
    }
    return rows_out, metrics


def write_crosswalk(rows: list[dict[str, object]], metrics: dict[str, object]) -> None:
    cols = list(rows[0].keys())
    with open(CROSS_CSV, "w", newline="") as fo:
        writer = csv.DictWriter(fo, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(r["new_class"] for r in rows)
    old_counts = Counter(r["old_class"] for r in rows)
    moved = [r for r in rows if int(r["moved"]) == 1]
    new_candidates = [r for r in rows if r["new_class"] in {"A1_촬영확실", "A2_촬영경계", "경계_방법회복"}]
    old21 = [r for r in rows if r["old_class"] in {"A1_촬영확실", "A2_촬영경계", "경계_방법회복"}]
    old21_density_zero = all(float(r["dim_rf_pt_density"] or 0.0) == 0.0 for r in old21)
    old21_nadir_zero = all(float(r["n_views_nadir"] or 0.0) == 0.0 for r in old21)
    new_density_zero = all(float(r["dim_rf_pt_density"] or 0.0) == 0.0 for r in new_candidates)
    new_nadir_zero = all(float(r["n_views_nadir"] or 0.0) == 0.0 for r in new_candidates)
    lines = [
        "# bucket_crosswalk_v2 -- aux-v4a 취득 한계 재유도",
        "",
        "> 재구성/재학습 없음. 판정 금지. `population_aux_v4.csv` 관측기하와 잠긴 규칙을 적용했다.",
        "",
        "## 기준",
        "",
        f"- dense 성공 그룹: {metrics['n_ctrl114']}동 (`als_has_lod22=True AND dim_has_lod22=True`).",
        f"- 생성축 대상: {metrics['n_gen48']}동.",
        f"- `frac_views_incidence_le60` p10 임계: {metrics['inc60_p10_thr']:.3f}.",
        f"- `recon_score_median` p10 임계: {metrics['recon_p10_thr']:.3f}.",
        f"- `A1_촬영확실`용 recon 최저 대조 임계: {metrics['recon_min_a1_thr']:.3f}.",
        "- 사실 거부권: sparse/acmp/GS 계열 중 하나라도 LoD2.2 회복이면 `경계_방법회복`.",
        "- lowtex 컬럼은 이 단계에서 갱신하지 않고 `v4a_carryover_v3_contaminated`로 표기했다.",
        "",
        "## 15·6·27 숫자",
        "",
        f"- A1+A2 취득 한계: {counts.get('A1_촬영확실', 0) + counts.get('A2_촬영경계', 0)}동.",
        f"- 경계·방법회복: {counts.get('경계_방법회복', 0)}동.",
        f"- 수동판정 후보: {counts.get('수동판정', 0)}동.",
        f"- 이전 crosswalk 기준 A1+A2={old_counts.get('A1_촬영확실', 0) + old_counts.get('A2_촬영경계', 0)}, 경계·방법회복={old_counts.get('경계_방법회복', 0)}, 나머지={len(rows) - old_counts.get('A1_촬영확실', 0) - old_counts.get('A2_촬영경계', 0) - old_counts.get('경계_방법회복', 0)}.",
        "",
        "## 21후보 재확인",
        "",
        f"- 기존 21후보 수: {len(old21)}동.",
        f"- 기존 21후보 전원 DIM 밀도 0: {old21_density_zero}.",
        f"- 기존 21후보 전원 수직 뷰 0: {old21_nadir_zero}.",
        f"- A3a 새 후보(A1+A2+경계·방법회복) 수: {len(new_candidates)}동.",
        f"- A3a 새 후보 전원 DIM 밀도 0: {new_density_zero}.",
        f"- A3a 새 후보 전원 수직 뷰 0: {new_nadir_zero}.",
        "",
        "| building_id | old_class | new_class | dim_rf_pt_density | n_views_nadir | veto_recovered |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in old21:
        lines.append(
            f"| {row['building_id']} | {row['old_class']} | {row['new_class']} | {row['dim_rf_pt_density']} | {row['n_views_nadir']} | {row['veto_recovered']} |"
        )
    lines.extend(
        [
            "",
            "## 이동 요약",
            "",
            f"- old_class와 new_class가 달라진 행: {len(moved)} / {len(rows)}.",
            "- `수동판정`은 A3b 카드 생성 대상의 기본 목록이다. 최종 수동판정 대상 확정은 김휘영.",
            "",
            "## 파일",
            "",
            "- CSV: `docs/experiments/input-and-alignment/bucket_crosswalk/tables/bucket_crosswalk_v2.csv`",
            "- 관측기하: `docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv`",
        ]
    )
    CROSS_MD.write_text("\n".join(lines) + "\n")


def write_figures(rows: list[dict[str, object]], cross: list[dict[str, object]]) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    v4 = {str(r["building_id"]): r for r in rows}
    v3rows = {r["building_id"]: r for r in csv.DictReader(open(V3_DOCS))}
    fields = ["n_views_nadir", "frac_views_incidence_le60", "recon_score_median", "occlusion_frac_approx"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for ax, field in zip(axes.ravel(), fields):
        xs, ys = [], []
        for bid, r3 in v3rows.items():
            r4 = v4.get(bid)
            if not r4:
                continue
            a = fnum(r3.get(field))
            b = fnum(r4.get(field))
            if a is None or b is None:
                continue
            xs.append(a)
            ys.append(b)
        ax.scatter(xs, ys, s=10, alpha=0.55)
        if xs and ys:
            lo = min(min(xs), min(ys))
            hi = max(max(xs), max(ys))
            ax.plot([lo, hi], [lo, hi], "k--", lw=0.8)
        ax.set_title(field)
        ax.set_xlabel("v3")
        ax.set_ylabel("v4a")
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "aux_v4a_v3_vs_v4_scatter.png", dpi=140)
    plt.close(fig)

    cnt = Counter(r["new_class"] for r in cross)
    labels = ["A1_촬영확실", "A2_촬영경계", "경계_방법회복", "수동판정"]
    plot_labels = ["A1 acquisition", "A2 boundary", "method recovery", "manual review"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(plot_labels, [cnt.get(x, 0) for x in labels], color=["#4c78a8", "#72b7b2", "#f58518", "#b279a2"])
    ax.set_ylabel("buildings")
    ax.set_title("aux-v4a class counts")
    ax.tick_params(axis="x", labelrotation=20)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "aux_v4a_class_counts.png", dpi=140)
    plt.close(fig)


def write_report(rows: list[dict[str, object]], cross: list[dict[str, object]], metrics: dict[str, object]) -> None:
    cnt = Counter(r["new_class"] for r in cross)
    moved = [r for r in cross if int(r["moved"]) == 1]
    new_candidates = [r for r in cross if r["new_class"] in {"A1_촬영확실", "A2_촬영경계", "경계_방법회복"}]
    old21 = [r for r in cross if r["old_class"] in {"A1_촬영확실", "A2_촬영경계", "경계_방법회복"}]
    spec_note = (
        "`기준문서_방법론·모집단·비교설계_v1.md`는 현재 checkout 루트에서 발견되지 않아 직접 인용하지 못했다."
        if not ROOT_SPEC.exists()
        else "`기준문서_방법론·모집단·비교설계_v1.md` §1.6을 입력 기준으로 확인했다."
    )
    lines = [
        "# aux_v4_change_report -- A3a 관측기하 v4a",
        "",
        "> 재구성/재학습 없음. 판정 금지. 수치·관찰만 기록한다.",
        "",
        "## 0. 높이 맞추기 규약과 허용오차",
        "",
        f"- image-projection 기본 `orthometric_geoid_m` = {GEOID_M:.3f} m.",
        "- 3D/씨드 경로 `-556` 전환 여부는 별도 판정 대기이며, 이 커밋에서 건드리지 않았다.",
        f"- 확정 zeta 불확실성 ±{UNCERTAINTY_M:.2f} m.",
        f"- 관측기하 허용 ±{GEOM_ALLOW_M:.1f} m 대비 {GEOM_ALLOW_M / UNCERTAINTY_M:.0f}배 여유.",
        f"- 픽셀 마스크 허용 약 {MASK_ALLOW_M:.1f} m 대비 {MASK_ALLOW_M / UNCERTAINTY_M:.0f}배 여유.",
        f"- 기준문서 확인 상태: {spec_note}",
        "",
        "## 1. 산출",
        "",
        "- `docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv`: v3와 같은 관측기하 정의로 199동 재계산.",
        "- lowtex 관련 컬럼은 v3 값을 이월하고 `lowtex_version=v4a_carryover_v3_contaminated`로 표시.",
        "- `docs/experiments/input-and-alignment/bucket_crosswalk/tables/bucket_crosswalk_v2.csv`, `docs/experiments/input-and-alignment/bucket_crosswalk/reports/bucket_crosswalk_v2.md`: 48동 old->new 이동표.",
        f"- 그림: `{(FIG_DIR / 'aux_v4a_v3_vs_v4_scatter.png').relative_to(REPO)}`, `{(FIG_DIR / 'aux_v4a_class_counts.png').relative_to(REPO)}`.",
        "",
        "## 2. 재산출 임계",
        "",
        f"- dense 성공 그룹: {metrics['n_ctrl114']}동.",
        f"- `frac_views_incidence_le60` p10: {metrics['inc60_p10_thr']:.3f}.",
        f"- `recon_score_median` p10: {metrics['recon_p10_thr']:.3f}.",
        f"- `recon_score_median` 대조 최저값(A1 밴드): {metrics['recon_min_a1_thr']:.3f}.",
        "",
        "## 3. 15·6·27 변동",
        "",
        "| 묶음 | count |",
        "|---|---:|",
        f"| A1+A2 취득 한계 | {cnt.get('A1_촬영확실', 0) + cnt.get('A2_촬영경계', 0)} |",
        f"| 경계·방법회복 | {cnt.get('경계_방법회복', 0)} |",
        f"| 수동판정 후보 | {cnt.get('수동판정', 0)} |",
        "",
        f"- old_class와 new_class가 달라진 행: {len(moved)} / {len(cross)}.",
        f"- 기존 21후보 수: {len(old21)}.",
        f"- 기존 21후보 전원 DIM 밀도 0: {all(float(r['dim_rf_pt_density'] or 0.0) == 0.0 for r in old21)}.",
        f"- 기존 21후보 전원 수직 뷰 0: {all(float(r['n_views_nadir'] or 0.0) == 0.0 for r in old21)}.",
        f"- A3a 새 후보(A1+A2+경계·방법회복) 수: {len(new_candidates)}.",
        "",
        "## 4. 수동판정 후보 목록",
        "",
        ", ".join(r["building_id"].replace("DEBY_LOD2_", "") for r in cross if r["new_class"] == "수동판정"),
        "",
        "## 5. 관찰",
        "",
        "- zeta 기본값 변경은 image-projection 경로의 orthometric 입력 변환에만 적용됐다.",
        "- lowtex 갱신은 A3b로 남겨두었으므로 v4a의 수동판정 후보는 lowtex-v5 전 최종 목록이 아니다.",
        "- 최종 subclass 확정과 수동판정 대상 확정은 김휘영 세션에서만 한다.",
        "",
        "## 6. 판정 필요 지점",
        "",
        "1. 15·6·27 묶음 변동을 A3b 카드 대상의 입력으로 볼지 여부.",
        "2. `수동판정` 후보 목록을 A3b evidence_cards_v3 대상으로 확정할지 여부.",
        "3. 누락된 루트 기준문서 §1.6을 별도 파일로 보강할지 여부.",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n")


def write_versions(metrics: dict[str, object]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {RUN_ID}",
        f"git_head: {git_head()}",
        "command: python phases/p2-gsjso/scripts/aux_v4a.py",
        f"projection_config: {describe_projection_config()}",
        f"geoid_m: {GEOID_M:.6f}",
        f"python: {platform.python_version()}",
        f"numpy: {np.__version__}",
        "container: jointbuildgs:dev; Docker --user",
        "crs: geo EPSG:25832; OPF/COLMAP EPSG:32632 local with ellipsoidal Z",
        "reconstruction_or_retraining: none",
        f"inc60_p10_thr: {metrics['inc60_p10_thr']:.6f}",
        f"recon_p10_thr: {metrics['recon_p10_thr']:.6f}",
        f"recon_min_a1_thr: {metrics['recon_min_a1_thr']:.6f}",
        "lowtex: carried from v3; marked contaminated",
        "",
    ]
    (RUN_DIR / "versions.txt").write_text("\n".join(lines))


def main() -> None:
    if abs(projection_geoid_m() - GEOID_M) > 1e-6:
        raise RuntimeError(f"configs/projection_datum.json must have orthometric_geoid_m={GEOID_M}, got {projection_geoid_m()}")
    rows, best_view = recompute_aux()
    write_aux(rows, best_view)
    cross, metrics = classify(rows)
    write_crosswalk(cross, metrics)
    write_figures(rows, cross)
    write_report(rows, cross, metrics)
    write_versions(metrics)
    print(f"[done] {OUT_DOCS}")
    print(f"[done] {CROSS_CSV}")
    print(f"[done] {CROSS_MD}")
    print(f"[done] {REPORT_MD}")
    print(f"[summary] class_counts={metrics['class_counts']}")


if __name__ == "__main__":
    main()
