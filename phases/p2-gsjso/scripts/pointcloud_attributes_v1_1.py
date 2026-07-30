#!/usr/bin/env python3
"""Point-cloud input attributes v1.1.

Observation only: no reconstruction, no retraining, and no image projection.
This script reuses the v1 measurement functions, adds DIM/ALS fallback
footprint clips, and records the v1.14 datum decision in every row.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import laspy
import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pointcloud_attributes_v1 as base


ARMS = base.ARMS
RUN_ID = "20260706_attr_v1_1"
HEIGHT_CONSTANT_M = 45.760
HEIGHT_CONSTANT_LABEL = "v1.14_section_1.6_zeta_45.7_QA_45.760"
HISTORICAL_ORTHO_TO_ELLIP_M = 48.0
HISTORICAL_REF_OFFSET_M = 48.165
SENSITIVITY_CONSTANTS = (48.0, 48.165, 45.760)
SOURCE_DIM = Path("phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz")
SOURCE_ALS = Path("results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz")
SOURCE_ACMP = Path("results/tum_transfer/mob_analysis/p0c_step2/acmp_classified.laz")
W2_RUN = Path("phases/p0-audit/runs/w2_1_roofer_default_20260612_152729")
W3_RUN = Path("phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747")


@dataclass
class FallbackSource:
    path: Path
    source: str
    z_add_m: float
    z_history: str

    def __post_init__(self) -> None:
        las = laspy.read(str(self.path))
        self.x = np.asarray(las.x, dtype=np.float64)
        self.y = np.asarray(las.y, dtype=np.float64)
        self.z_base = np.asarray(las.z, dtype=np.float64)
        self.cls = np.asarray(las.classification, dtype=np.uint8)
        self.grid = base.SortedGrid(np.column_stack([self.x, self.y]), 10.0)

    def clip(self, poly: Polygon) -> tuple[np.ndarray, np.ndarray]:
        minx, miny, maxx, maxy = poly.bounds
        idx = self.grid.query_bbox(minx, miny, maxx, maxy)
        if len(idx) == 0:
            return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8)
        m = contains_xy(poly, self.x[idx], self.y[idx])
        idx = idx[m]
        if len(idx) == 0:
            return np.empty((0, 3), dtype=np.float64), np.empty((0,), dtype=np.uint8)
        z = self.z_base[idx] + self.z_add_m
        return np.column_stack([self.x[idx], self.y[idx], z]), self.cls[idx]


@dataclass
class LoadedArm:
    points: base.ArmPoints
    datum_kind: str
    datum_shift_from_v1_m: float
    source_laz_path: str

    def scenario_points(self, height_constant_m: float) -> base.ArmPoints:
        if self.datum_kind != "orthometric_plus_constant":
            return self.points
        delta = height_constant_m - HEIGHT_CONSTANT_M
        xyz = self.points.xyz.copy()
        if len(xyz):
            xyz[:, 2] += delta
        ap = base.ArmPoints(
            xyz=xyz,
            cls=self.points.cls,
            source=self.points.source,
            path=self.points.path,
            z_history=self.points.z_history.replace(f"+{HEIGHT_CONSTANT_M:.3f}", f"+{height_constant_m:.3f}"),
            note=self.points.note,
        )
        return ap


def read_v1_rows(path: Path) -> tuple[list[str], dict[tuple[str, str], dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), {(r["building_id"], r["arm"]): r for r in rows}


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def fmt(v, digits: int = 6) -> str:
    return base.fmt(v, digits=digits)


def float_or_none(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        if math.isfinite(float(v)):
            return float(v)
        return None
    s = str(v).strip()
    if s == "" or s.lower() == "none":
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def bool_str(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).lower()


def load_arm(
    repo: Path,
    arm: str,
    bid: str,
    poly: Polygon,
    fallbacks: dict[str, FallbackSource],
) -> LoadedArm:
    existing = repo / f"phases/p0-audit/runs/mob_eval/{arm}/{bid}_orig_classified.las"
    if existing.exists():
        xyz, cls = base.read_las_footprint(existing, poly)
        datum_kind = "ellipsoidal_as_is"
        shift = 0.0
        if arm in {"raw_acmp", "raw_lidar"}:
            datum_kind = "orthometric_plus_constant"
            shift = HEIGHT_CONSTANT_M - HISTORICAL_ORTHO_TO_ELLIP_M
            if len(xyz):
                xyz[:, 2] += shift
            z_history = (
                "existing mob_eval ellip-unified clip; source history was orthometric "
                f"+{HISTORICAL_ORTHO_TO_ELLIP_M:.3f} m, adjusted {shift:+.3f} m "
                f"to {HEIGHT_CONSTANT_LABEL}"
            )
        else:
            z_history = (
                "existing mob_eval raw_dense clip; DIM ellipsoidal/local+604 history as-is; "
                f"reference comparisons use {HEIGHT_CONSTANT_LABEL}"
            )
        return LoadedArm(
            base.ArmPoints(
                xyz=xyz,
                cls=cls,
                source="existing_mob_eval_clip",
                path=str(existing.relative_to(repo)),
                z_history=z_history,
            ),
            datum_kind=datum_kind,
            datum_shift_from_v1_m=shift,
            source_laz_path=str(existing.relative_to(repo)),
        )

    fb = fallbacks.get(arm)
    if fb is None:
        return LoadedArm(
            base.ArmPoints(
                xyz=np.empty((0, 3), dtype=np.float64),
                cls=np.empty((0,), dtype=np.uint8),
                source="missing_clip",
                path=str(existing.relative_to(repo)),
                z_history="none",
                note="building-level clip absent",
            ),
            datum_kind="none",
            datum_shift_from_v1_m=0.0,
            source_laz_path=str(existing.relative_to(repo)),
        )

    xyz, cls = fb.clip(poly)
    return LoadedArm(
        base.ArmPoints(
            xyz=xyz,
            cls=cls,
            source=fb.source,
            path=str(fb.path.relative_to(repo)),
            z_history=fb.z_history,
            note="non-persistent fallback footprint clip; no reconstruction or Roofer rerun",
        ),
        datum_kind="orthometric_plus_constant" if arm in {"raw_acmp", "raw_lidar"} else "ellipsoidal_as_is",
        datum_shift_from_v1_m=0.0 if arm != "raw_acmp" else HEIGHT_CONSTANT_M - HISTORICAL_ORTHO_TO_ELLIP_M,
        source_laz_path=str(fb.path.relative_to(repo)),
    )


def changed_axes(v1: dict[str, str] | None, row: dict[str, object]) -> list[str]:
    if v1 is None:
        return ["new_row"]
    axes = []
    cols = [
        "clip_source",
        "n_points_footprint",
        "pt_density_m2",
        "coverage_frac",
        "hole_frac",
        "roof_point_count",
        "ground_point_count",
        "local_plane_rms_m",
        "m3c2_mean_m",
        "m3c2_median_abs_m",
        "m3c2_rms_m",
        "floater_frac",
        "label_proxy_frac_all",
        "label_proxy_frac_ground",
        "density_reason",
        "coverage_reason",
        "m3c2_reason",
        "floater_reason",
        "label_proxy_reason",
    ]
    for col in cols:
        if col not in v1:
            continue
        nv = row.get(col)
        ov = v1.get(col)
        nf = float_or_none(nv)
        of = float_or_none(ov)
        if nf is not None or of is not None:
            if (nf is None) != (of is None) or (nf is not None and of is not None and abs(nf - of) > 5e-6):
                axes.append(col)
            continue
        if fmt(nv) != str(ov):
            axes.append(col)
    return axes


def annotate_change(
    row: dict[str, object],
    loaded: LoadedArm,
    v1_by_key: dict[tuple[str, str], dict[str, str]],
) -> None:
    key = (str(row["building_id"]), str(row["arm"]))
    v1 = v1_by_key.get(key)
    axes = changed_axes(v1, row)
    reasons = []
    if v1 is None:
        reasons.append("not_in_v1")
    else:
        if v1.get("clip_source") == "missing_clip" and row.get("clip_source") != "missing_clip":
            reasons.append("filled_missing_clip")
        if str(row.get("arm")) in {"raw_acmp", "raw_lidar", "raw_dense"}:
            reasons.append("datum_constant_v1_14_45p760")
        if v1.get("m3c2_reason") == "missing_lidar_clip" and row.get("m3c2_reason") != "missing_lidar_clip":
            reasons.append("m3c2_recomputed_after_lidar_fill")
    if not axes:
        reasons.append("unchanged_numeric")
    row["v1_clip_source"] = v1.get("clip_source", "none") if v1 else "none"
    row["v1_m3c2_reason"] = v1.get("m3c2_reason", "none") if v1 else "none"
    row["v1_1_changed_axes"] = ";".join(axes) if axes else "none"
    row["v1_1_change_reason"] = ";".join(dict.fromkeys(reasons))
    row["v1_1_height_constant_m"] = HEIGHT_CONSTANT_M
    row["v1_1_height_constant_source"] = HEIGHT_CONSTANT_LABEL
    row["datum_shift_from_v1_m"] = loaded.datum_shift_from_v1_m
    row["source_laz_path"] = loaded.source_laz_path


def scenario_ref_metrics(
    xyz: np.ndarray,
    cls: np.ndarray,
    roofs: list[base.RoofSurface],
    args,
    height_constant_m: float,
) -> tuple[float | None, float | None]:
    if len(xyz) == 0:
        return None, None
    old = base.GEOID_MED_M
    base.GEOID_MED_M = height_constant_m
    try:
        fallback_ref = max((s.z_max for s in roofs), default=None)
        zref, _ = base.local_ref_z(xyz[:, 0], xyz[:, 1], roofs, fallback_ref)
    finally:
        base.GEOID_MED_M = old
    if zref is None:
        return None, None
    ground = cls == 2
    floater = xyz[:, 2] > (zref + args.floater_margin_m)
    high_ground = ground & (xyz[:, 2] > (zref - args.label_proxy_roof_minus_m))
    return float(np.mean(floater)), float(np.sum(high_ground) / len(xyz))


def collect_sensitivity(
    bid: str,
    loaded: dict[str, LoadedArm],
    roofs: list[base.RoofSurface],
    args,
    bucket: dict[float, dict[str, list[float]]],
) -> None:
    for hc in SENSITIVITY_CONSTANTS:
        scenario = {arm: loaded[arm].scenario_points(hc) for arm in ARMS}
        for arm in ARMS:
            ap = scenario[arm]
            floater, label = scenario_ref_metrics(ap.xyz, ap.cls, roofs, args, hc)
            if floater is not None:
                bucket[hc]["floater_frac"].append(floater)
            if label is not None:
                bucket[hc]["label_proxy_frac_all"].append(label)
        lidar_roof = scenario["raw_lidar"].xyz[scenario["raw_lidar"].cls == 6]
        if len(lidar_roof) < args.m3c2_min_neighbors:
            continue
        for arm in ("raw_dense", "raw_acmp"):
            source_roof = scenario[arm].xyz[scenario[arm].cls == 6]
            m3, reason = base.m3c2_against_lidar(
                source_roof,
                lidar_roof,
                args.m3c2_normal_radius_m,
                args.m3c2_proj_radius_m,
                args.m3c2_min_neighbors,
                args.m3c2_max_cores,
                seed=base.stable_seed(bid, arm, "m3c2_sens"),
            )
            if reason == "ok" and m3.get("m3c2_mean_m") is not None:
                bucket[hc]["m3c2_mean_m"].append(float(m3["m3c2_mean_m"]))


def median_iqr_text(vals: list[float], digits: int = 4) -> tuple[str, str, str]:
    med, q1, q3 = base.median_iqr(vals)
    if med is None:
        return "none", "none", "0"
    return fmt(med, digits), f"{q1:.{digits}g}-{q3:.{digits}g}", str(len(vals))


def write_csv(path: Path, rows: list[dict[str, object]], v1_fields: list[str]) -> None:
    extra = [
        "v1_clip_source",
        "v1_m3c2_reason",
        "v1_1_changed_axes",
        "v1_1_change_reason",
        "v1_1_height_constant_m",
        "v1_1_height_constant_source",
        "datum_shift_from_v1_m",
        "source_laz_path",
    ]
    fieldnames = list(v1_fields)
    for k in extra:
        if k not in fieldnames:
            fieldnames.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k)) for k in fieldnames})


def plot_104586480_topview(points: dict[str, base.ArmPoints], rows: dict[str, dict[str, object]], poly: Polygon, out: Path) -> None:
    labels = [("raw_lidar", "ALS"), ("raw_dense", "DIM")]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), sharex=True, sharey=True)
    class_colors = {2: "#009E73", 6: "#D55E00"}
    for ax, (arm, label) in zip(axes, labels):
        ap = points[arm]
        xyz, cls = ap.xyz, ap.cls
        if len(xyz):
            idx = base.deterministic_sample(len(xyz), 12000, base.stable_seed("104586480", arm, "topview"))
            zz = xyz[idx, 2]
            ax.scatter(xyz[idx, 0], xyz[idx, 1], c="#9AA0A6", s=2, alpha=0.35, linewidths=0)
            for c, color in class_colors.items():
                m = cls[idx] == c
                if np.any(m):
                    ax.scatter(xyz[idx[m], 0], xyz[idx[m], 1], c=color, s=3, alpha=0.65, linewidths=0, label=f"class {c}")
            if np.ptp(zz) > 0:
                q = np.percentile(zz, [5, 50, 95])
                ax.text(
                    0.02,
                    0.02,
                    f"z p5/p50/p95={q[0]:.2f}/{q[1]:.2f}/{q[2]:.2f} m",
                    transform=ax.transAxes,
                    fontsize=8,
                    bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
                )
        x, y = poly.exterior.xy
        ax.plot(x, y, color="black", lw=1.2)
        r = rows[arm]
        ground_frac = float_or_none(r.get("label_proxy_frac_all"))
        cov = float_or_none(r.get("coverage_frac"))
        n = int(float_or_none(r.get("n_points_footprint")) or 0)
        ax.set_title(f"{label}: n={n}, coverage={fmt(cov, 3)}, proxy={fmt(ground_frac, 3)}")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(True, alpha=0.2)
        ax.legend(loc="upper right", fontsize=7)
    fig.suptitle("DEBY_LOD2_104586480 footprint top-view: ALS vs DIM")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)


def load_acmp_4907019(repo: Path) -> dict[str, object]:
    city = repo / "phases/p0-audit/runs/mob_eval/raw_acmp/DEBY_LOD2_4907019_orig.city.json"
    metrics = repo / "phases/p0-audit/runs/mob_eval/raw_acmp/DEBY_LOD2_4907019_orig_metrics.json"
    val = repo / "phases/p0-audit/runs/mob_eval/raw_acmp/DEBY_LOD2_4907019_orig_val3dity.json"
    attrs = json.loads(city.read_text(encoding="utf-8"))["CityObjects"]["DEBY_LOD2_4907019"]["attributes"]
    met = json.loads(metrics.read_text(encoding="utf-8"))
    vald = json.loads(val.read_text(encoding="utf-8"))
    return {
        "rf_roof_planes": attrs.get("rf_roof_planes"),
        "rf_rmse_lod22": attrs.get("rf_rmse_lod22"),
        "val3dity_valid": vald.get("validity"),
        "plane_rms": met.get("plane_rms"),
        "roof_density": met.get("roof_density"),
        "paths": [str(city.relative_to(repo)), str(metrics.relative_to(repo)), str(val.relative_to(repo))],
    }


def source_fingerprints(repo: Path, status_used: Path) -> dict[str, tuple[str, str]]:
    paths = {
        "status_csv": status_used,
        "w2_config": repo / W2_RUN / "config.yaml",
        "w2_versions": repo / W2_RUN / "versions.txt",
        "w3_repeatability_versions": repo / W3_RUN / "versions.txt",
        "w3_run2_als_status": repo / W3_RUN / "status/run_2/als_default.csv",
        "w3_run2_dim_status": repo / W3_RUN / "status/run_2/dim_default.csv",
        "w3_repeatability_building_status": repo / "phases/p0-audit/docs/W3_2b_roofer_repeatability_building_status.csv",
        "dim_fallback_source": repo / SOURCE_DIM,
        "als_fallback_source": repo / SOURCE_ALS,
        "acmp_fallback_source": repo / SOURCE_ACMP,
    }
    out: dict[str, tuple[str, str]] = {}
    for label, path in paths.items():
        if path.exists():
            out[label] = (str(path.relative_to(repo)), sha256_file(path))
    return out


def write_versions(path: Path, args, provenance: dict[str, str], rows: list[dict[str, object]], fps: dict[str, tuple[str, str]]) -> None:
    clip_counts = defaultdict(int)
    for r in rows:
        clip_counts[(r["arm"], r["clip_source"])] += 1
    def cmd_out(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as e:
            return f"not_available:{e.filename}"
        return (r.stdout or r.stderr).strip()
    lines = [
        f"run_id: {RUN_ID}",
        "task: attr-v1.1",
        f"created_utc: {datetime.now(timezone.utc).isoformat()}",
        "mode: observation only; no reconstruction; no retraining; no image projection",
        f"git_head: {cmd_out(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {cmd_out(['git', 'branch', '--show-current'])}",
        'run_command: docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/pointcloud_attributes_v1_1.py',
        "",
        "height_datum:",
        f"  selected_constant_m: {HEIGHT_CONSTANT_M:.3f}",
        f"  selected_constant_source: {HEIGHT_CONSTANT_LABEL}",
        f"  rejected_history_constants_m: ACMP_fallback_v1={HISTORICAL_ORTHO_TO_ELLIP_M:.3f}; ref_compare_v1={HISTORICAL_REF_OFFSET_M:.3f}",
        "  raw_dense: DIM ellipsoid/local+604 history as-is",
        "  raw_acmp/raw_lidar_existing: historical orthometric+48.000 clips shifted -2.240 m for v1.1 metrics",
        "  raw_acmp/raw_lidar_fallback: source orthometric LAZ +45.760 m",
        "",
        "inputs_with_sha256:",
    ]
    for label, (rel, sha) in fps.items():
        lines.append(f"  {label}: {rel} sha256={sha}")
    lines += [
        "",
        "clip_source_counts:",
    ]
    for arm in ARMS:
        for source in sorted({s for (a, s) in clip_counts if a == arm}):
            lines.append(f"  {arm}.{source}: {clip_counts[(arm, source)]}")
    lines += [
        "",
        "parameters:",
        f"  grid_cell_m: {args.grid_cell_m}",
        f"  local_plane_radius_m: {args.local_plane_radius_m}",
        f"  m3c2_normal_radius_m: {args.m3c2_normal_radius_m}",
        f"  m3c2_proj_radius_m: {args.m3c2_proj_radius_m}",
        f"  floater_margin_m: {args.floater_margin_m}",
        f"  label_proxy_roof_minus_m: {args.label_proxy_roof_minus_m}",
        "",
        "outputs:",
        "  docs/archive/pointcloud_attributes/v1_1/tables/pointcloud_attributes_v1_1.csv",
        "  docs/experiments/input-and-alignment/pointcloud_attributes/reports/W_pointcloud_attributes.md",
        "  docs/figs/pointcloud_attributes_v1_1/arm_distribution.png",
        "  docs/figs/pointcloud_attributes_v1_1/als_scatter.png",
        "  docs/figs/pointcloud_attributes_v1_1/ref_invalid_104586480_topview.png",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def md_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    header = rows[0]
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return out


def build_v11_section(
    rows: list[dict[str, object]],
    sensitivity: dict[float, dict[str, list[float]]],
    b_rows: dict[str, dict[str, object]],
    density_qa: dict[str, object],
    acmp_4907019: dict[str, object],
    fps: dict[str, tuple[str, str]],
    provenance: dict[str, str],
) -> str:
    clip_counts = defaultdict(int)
    for r in rows:
        clip_counts[(r["arm"], r["clip_source"])] += 1
    reason_counts = defaultdict(int)
    axis_counts = defaultdict(int)
    m3c2_recomputed = 0
    m3c2_still_missing_lidar = 0
    for r in rows:
        reason_counts[str(r.get("v1_1_change_reason", "none"))] += 1
        for axis in str(r.get("v1_1_changed_axes", "none")).split(";"):
            if axis and axis != "none":
                axis_counts[axis] += 1
        if r.get("v1_m3c2_reason") == "missing_lidar_clip" and r.get("m3c2_reason") != "missing_lidar_clip":
            m3c2_recomputed += 1
        if r.get("m3c2_reason") == "missing_lidar_clip":
            m3c2_still_missing_lidar += 1
    summary = base.make_summary_table(rows)
    lines: list[str] = [
        "---",
        "",
        "# W pointcloud attributes v1.1",
        "",
        "> 재구성/재학습 없음. 이미지-투영 불사용. 수치와 관찰만 기록한다. CRS는 EPSG:25832.",
        "",
        "## v1.1 입력·높이 기준",
        "",
        f"- 기준문서 확인: 루트 기준문서 v1.14 (2026-07-05). §1.6의 확정값은 ζ=45.7 m, QA 유효값은 {HEIGHT_CONSTANT_M:.3f} m이다.",
        f"- v1의 +48.0은 `phases/p2-gsjso/scripts/tum_mob_raw_to_npz.py`와 `docs/experiments/input-and-alignment/pointcloud_attributes/reports/W_pointcloud_attributes.md`의 ACMP/LiDAR raw-arm 관행값이다. v1.1에서는 orthometric ACMP/ALS에 +{HEIGHT_CONSTANT_M:.3f} m를 썼다.",
        f"- v1의 +48.165는 `phases/p2-gsjso/scripts/pointcloud_attributes_v1.py`의 `GEOID_MED_M`으로, 참조 LoD2 지붕 Z를 raw-arm 높이와 비교할 때만 더했던 값이다.",
        "- 기존 mob_eval raw_acmp/raw_lidar 클립은 ellip-unified 이력의 기존 클립이며, 생성 이력은 orthometric +48.000 m이다. v1.1 metric 계산에서는 이 행들을 -2.240 m 평행이동해 +45.760 m 기준에 맞췄다.",
        "- raw_dense는 기존 DIM ellipsoid/local+604 이력을 as-is로 두고, 참조 LoD2와의 비교 상수만 +45.760 m로 맞췄다.",
        "",
        "## v1.1 클립 출처",
        "",
        "| arm | source | n_rows |",
        "|---|---|---:|",
    ]
    for arm in ARMS:
        for source in sorted({s for (a, s) in clip_counts if a == arm}):
            lines.append(f"| {arm} | {source} | {clip_counts[(arm, source)]} |")
    lines += [
        "",
        "## v1.1 축별·arm별 분포",
        "",
        "| 축 | arm | n | median | IQR |",
        "|---|---|---:|---:|---:|",
    ]
    for label, arm, n, med, q1, q3 in summary:
        iqr = "none" if q1 is None else f"{q1:.4g}-{q3:.4g}"
        lines.append(f"| {label} | {arm} | {n} | {fmt(med, 4)} | {iqr} |")
    lines += [
        "",
        "그림:",
        "",
        "- Arm 대조 분포: `docs/figs/pointcloud_attributes_v1_1/arm_distribution.png`",
        "- ALS 대비 산점: `docs/figs/pointcloud_attributes_v1_1/als_scatter.png`",
        "",
        "관찰:",
    ]
    for col, text in [
        ("pt_density_m2", "밀도"),
        ("coverage_frac", "0.5 m 격자 점유율"),
        ("local_plane_rms_m", "국소 평면 RMS"),
        ("floater_frac", "부유점 비율"),
        ("label_proxy_frac_all", "라벨 프록시 비율"),
    ]:
        vals = {arm: base.median_iqr(base.numeric_values(rows, arm, col))[0] for arm in ARMS}
        lines.append(
            f"- {text}: median raw_dense={fmt(vals['raw_dense'], 4)}, raw_acmp={fmt(vals['raw_acmp'], 4)}, raw_lidar={fmt(vals['raw_lidar'], 4)}."
        )
    lines += [
        "",
        "## [A] 높이 상수 출처·민감도",
        "",
        "| 상수 시나리오 | 부유점 frac median | n | 라벨 프록시 frac median | n | M3C2 mean median m | n |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for hc in SENSITIVITY_CONSTANTS:
        fm, _, fn = median_iqr_text(sensitivity[hc]["floater_frac"])
        lm, _, ln = median_iqr_text(sensitivity[hc]["label_proxy_frac_all"])
        mm, _, mn = median_iqr_text(sensitivity[hc]["m3c2_mean_m"])
        lines.append(f"| {hc:.3f} | {fm} | {fn} | {lm} | {ln} | {mm} | {mn} |")
    lines += [
        "",
        "높이상수 관계:",
        "",
        "- 같은 자에 올릴 때의 v1.1 채택 상수는 +45.760 m이다. 기준문서 §1.6의 ζ=45.7 m는 논문 본문용 반올림값이고, QA와 계산에는 45.760 m를 썼다.",
        "- +48.000/+48.165는 기존 raw-arm 관행과 v1 참조 비교 상수의 이력값이다. 기준문서 §1.6에 따라 v1.1에서는 확정 상수로 보정하고, 각 행의 `z_datum_history`에 원래 이력과 보정량을 남겼다.",
        "",
        "## [B] 104586480 ref_invalid 신규 후보 재료",
        "",
        "| arm | n | coverage | ground_label_frac_all | roof_points | z_p05 | z_p50 | z_p95 | pt_density | local_RMS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, label in [("raw_lidar", "ALS"), ("raw_dense", "DIM")]:
        r = b_rows[arm]
        lines.append(
            f"| {label} | {fmt(r.get('n_points_footprint'))} | {fmt(r.get('coverage_frac'), 4)} | "
            f"{fmt(r.get('ground_label_frac_all'), 4)} | {fmt(r.get('roof_point_count'))} | "
            f"{fmt(r.get('z_p05'), 3)} | {fmt(r.get('z_p50'), 3)} | {fmt(r.get('z_p95'), 3)} | "
            f"{fmt(r.get('pt_density_m2'), 3)} | {fmt(r.get('local_plane_rms_m'), 3)} |"
        )
    lines += [
        "",
        "- 그림: `docs/figs/pointcloud_attributes_v1_1/ref_invalid_104586480_topview.png`",
        "- §2.4 본문에 명시된 ID 42364663·42364667과 대조하면 104586480은 그 두 본문 명시 ID가 아니다. P0 기록에는 `W2_1c_reference_mismatch_exclusions.csv`와 `W3_summary.md`에서 reference_mismatch 재료로 이미 남아 있다.",
        "- 재료 성격: ALS와 DIM의 footprint 내부 라벨·높이 분포가 다르고, P0 기록은 시간차/참조 형상/점군 라벨 오류 가능성을 분리하지 않고 reference/temporal mismatch 후보로 남겼다.",
        "",
        "## [C] 클립 보강 및 QA",
        "",
        f"- v1 missing_clip에서 v1.1로 채운 행: raw_dense {clip_counts[('raw_dense', 'fallback_dim_footprint_clip')]}행, raw_lidar {clip_counts[('raw_lidar', 'fallback_als_footprint_clip')]}행.",
        f"- v1에서 `missing_lidar_clip`이던 M3C2 중 v1.1에서 재계산된 행: {m3c2_recomputed}행. v1.1에도 남은 `missing_lidar_clip`: {m3c2_still_missing_lidar}행.",
        "- v1 대비 변경 사유 상위:",
    ]
    for reason, count in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]:
        lines.append(f"  - {reason}: {count}")
    lines += [
        "- v1 대비 변경 축 상위:",
    ]
    for axis, count in sorted(axis_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]:
        lines.append(f"  - {axis}: {count}")
    lines += [
        f"- 새 raw_dense fallback의 status density delta: n={density_qa['n']}, median={fmt(density_qa['median'], 4)}, IQR={density_qa['iqr']}.",
    ]
    outliers = density_qa.get("outliers", [])
    if outliers:
        lines.append("- 큰 density delta 후보(abs(delta)>max(5 pt/m2, 25% status_density)):")
        for item in outliers[:20]:
            lines.append(f"  - {item}")
    else:
        lines.append("- 큰 density delta 후보(abs(delta)>max(5 pt/m2, 25% status_density)): none.")
    lines += [
        "",
        "## [D] 4907019 raw_acmp read-out",
        "",
        f"- 4907019 raw_acmp orig: rf_roof_planes={acmp_4907019['rf_roof_planes']}, rf_rmse_lod22={float(acmp_4907019['rf_rmse_lod22']):.6f}, val3dity_valid={bool_str(acmp_4907019['val3dity_valid'])}; metrics plane_rms={float(acmp_4907019['plane_rms']):.6f}, roof_density={float(acmp_4907019['roof_density']):.6f}.",
        "",
        "## [E] 회귀 결과 변수 지문·datum-free 확인",
        "",
        "| 항목 | 경로 | sha256 |",
        "|---|---|---|",
    ]
    for label in ["status_csv", "w2_config", "w2_versions", "w3_repeatability_versions"]:
        rel, sha = fps.get(label, ("missing", "missing"))
        lines.append(f"| {label} | `{rel}` | `{sha}` |")
    lines += [
        "",
        "- attr-v1이 참조한 status CSV는 `w2_1_roofer_default_20260612_152729` 산출물이다. W3 closeout에서 canonical은 `w3_2b_roofer_repeatability_20260612_220747/run_2`로 잠겼고, 동일 Roofer 기본 파라미터의 반복성 확인용 별칭 관계로 기록되어 있다.",
        "- 반복성 기록 위치: `phases/p0-audit/docs/W3_2b_roofer_repeatability.md`, `phases/p0-audit/docs/W3_2b_roofer_repeatability_building_status.csv`.",
        "- Roofer 버전·파라미터: W2 versions/config와 W3 versions에 기록된 Roofer 1.0.0, val3dity 2.6.0, plane_detect_epsilon=0.3, plane_detect_min_points=15, complexity_factor=0.888.",
        "- 결과 변수 4종은 Roofer 산출 CityJSON attribute와 val3dity report에서 읽힌다. `roofer_ok/roof_surfaces>0`은 CityJSON LOD2.2 geometry 존재, val3dity는 생성 CityJSON 형식 유효성, `rf_roof_planes`와 `rf_rmse_lod22`는 Roofer가 입력 점군으로 만든 모델 내부 속성이다. P0 추출 코드는 `phases/p0-audit/scripts/08_roofer_w2.py`에서 CityJSON attributes를 읽어 status CSV에 쓴다. 외부 LoD2 참조나 이미지 투영 좌표를 다시 쓰는 단계는 없다.",
        "",
        "## 판정 필요 지점",
        "",
        "- 부유점 여유 3 m를 유지할지.",
        "- 라벨 프록시를 전체 점 대비로 둘지 ground 라벨 내부 비율로 둘지.",
        "- `none` 처리 행을 회귀에서 결측으로 둘지, 결측 자체를 설명변수로 둘지.",
        "- 회귀 사양에서 ref_invalid와 fallback clip_source를 어떻게 층화·제외·고정효과 처리할지.",
    ]
    return "\n".join(lines) + "\n"


def density_qa(rows: list[dict[str, object]]) -> dict[str, object]:
    vals = []
    outliers = []
    for r in rows:
        if r["arm"] != "raw_dense" or r["clip_source"] != "fallback_dim_footprint_clip":
            continue
        delta = float_or_none(r.get("status_density_delta"))
        sd = float_or_none(r.get("status_rf_pt_density"))
        if delta is None:
            continue
        vals.append(delta)
        thresh = max(5.0, 0.25 * abs(sd or 0.0))
        if abs(delta) > thresh:
            outliers.append(
                f"{r['building_id']}: delta={delta:.3f}, attr={float_or_none(r.get('pt_density_m2')):.3f}, status={sd:.3f}"
            )
    med, q1, q3 = base.median_iqr(vals)
    return {
        "n": len(vals),
        "median": med,
        "iqr": "none" if q1 is None else f"{q1:.4g}-{q3:.4g}",
        "outliers": outliers,
    }


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", default="docs/experiments/input-and-alignment/population_aux/tables/population_aux_v4.csv")
    ap.add_argument("--status", default="docs/building_reconstruction_status.csv")
    ap.add_argument("--footprints", default="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg")
    ap.add_argument("--lod2-gml-dir", default="phases/p0-audit/data/raw/lod2")
    ap.add_argument("--v1-csv", default="docs/archive/pointcloud_attributes/v1/tables/pointcloud_attributes_v1.csv")
    ap.add_argument("--out-csv", default="docs/archive/pointcloud_attributes/v1_1/tables/pointcloud_attributes_v1_1.csv")
    ap.add_argument("--out-report", default="docs/experiments/input-and-alignment/pointcloud_attributes/reports/W_pointcloud_attributes.md")
    ap.add_argument("--fig-dir", default="docs/figs/pointcloud_attributes_v1_1")
    ap.add_argument("--versions", default=f"phases/p2-gsjso/runs/{RUN_ID}/versions.txt")
    ap.add_argument("--grid-cell-m", type=float, default=0.5)
    ap.add_argument("--local-plane-radius-m", type=float, default=0.75)
    ap.add_argument("--local-plane-min-neighbors", type=int, default=10)
    ap.add_argument("--local-plane-max-cores", type=int, default=3000)
    ap.add_argument("--local-plane-max-neighbors", type=int, default=256)
    ap.add_argument("--m3c2-normal-radius-m", type=float, default=1.0)
    ap.add_argument("--m3c2-proj-radius-m", type=float, default=0.75)
    ap.add_argument("--m3c2-min-neighbors", type=int, default=8)
    ap.add_argument("--m3c2-max-cores", type=int, default=2500)
    ap.add_argument("--floater-margin-m", type=float, default=3.0)
    ap.add_argument("--label-proxy-roof-minus-m", type=float, default=1.0)
    return ap


def main() -> None:
    args = build_argparser().parse_args()
    repo = Path.cwd()
    base.GEOID_MED_M = HEIGHT_CONSTANT_M
    v1_fields, v1_by_key = read_v1_rows(repo / args.v1_csv)
    pop = base.read_population(repo / args.population)
    pop_set = set(pop)
    st_path, st_note = base.status_path(repo, repo / args.status)
    status = base.load_status(st_path)
    provenance = {"status_path": str(st_path.relative_to(repo)), "status_note": st_note}
    footprints = base.load_footprints(repo / args.footprints, pop_set)
    roofs = base.load_roof_surfaces(repo / args.lod2_gml_dir, pop_set)
    ref_invalid = base.load_ref_invalid(repo)

    fallbacks = {
        "raw_dense": FallbackSource(
            repo / SOURCE_DIM,
            "fallback_dim_footprint_clip",
            0.0,
            "canonical Roofer DIM classified LAZ w2_1 input; dim_v1_classified_z_minus0p174 as-is; EPSG:25832; reference comparisons use v1.14 zeta +45.760",
        ),
        "raw_acmp": FallbackSource(
            repo / SOURCE_ACMP,
            "fallback_fused_acmp_footprint_clip",
            HEIGHT_CONSTANT_M,
            f"fused ACMP classified LAZ orthometric +{HEIGHT_CONSTANT_M:.3f} m ({HEIGHT_CONSTANT_LABEL})",
        ),
        "raw_lidar": FallbackSource(
            repo / SOURCE_ALS,
            "fallback_als_footprint_clip",
            HEIGHT_CONSTANT_M,
            f"ALS classified LAZ orthometric +{HEIGHT_CONSTANT_M:.3f} m ({HEIGHT_CONSTANT_LABEL})",
        ),
    }

    rows: list[dict[str, object]] = []
    sens = {hc: {"floater_frac": [], "label_proxy_frac_all": [], "m3c2_mean_m": []} for hc in SENSITIVITY_CONSTANTS}
    b104_points: dict[str, base.ArmPoints] = {}
    b104_rows: dict[str, dict[str, object]] = {}

    for i, bid in enumerate(pop, 1):
        poly = footprints[bid]
        loaded = {arm: load_arm(repo, arm, bid, poly, fallbacks) for arm in ARMS}
        lidar_roof = loaded["raw_lidar"].points.xyz[loaded["raw_lidar"].points.cls == 6]
        lidar_roof_for_m3c2 = lidar_roof if len(lidar_roof) else None
        collect_sensitivity(bid, loaded, roofs.get(bid, []), args, sens)
        for arm in ARMS:
            row = base.metric_row(
                repo,
                bid,
                arm,
                poly,
                loaded[arm].points,
                lidar_roof_for_m3c2,
                roofs.get(bid, []),
                ref_invalid,
                status,
                args,
            )
            annotate_change(row, loaded[arm], v1_by_key)
            rows.append(row)
            if bid == "DEBY_LOD2_104586480" and arm in {"raw_dense", "raw_lidar"}:
                b104_points[arm] = loaded[arm].points
                z = loaded[arm].points.xyz[:, 2]
                ground_frac = float(np.mean(loaded[arm].points.cls == 2)) if len(loaded[arm].points.cls) else None
                row = dict(row)
                row["ground_label_frac_all"] = ground_frac
                if len(z):
                    row["z_p05"], row["z_p50"], row["z_p95"] = [float(x) for x in np.percentile(z, [5, 50, 95])]
                b104_rows[arm] = row
        if i % 25 == 0 or i == len(pop):
            print(f"[attr-v1.1] processed {i}/{len(pop)} buildings", flush=True)

    out_csv = repo / args.out_csv
    write_csv(out_csv, rows, v1_fields)
    fig_dir = repo / args.fig_dir
    base.plot_distributions(rows, fig_dir / "arm_distribution.png")
    base.plot_als_scatter(rows, fig_dir / "als_scatter.png")
    plot_104586480_topview(b104_points, b104_rows, footprints["DEBY_LOD2_104586480"], fig_dir / "ref_invalid_104586480_topview.png")

    fps = source_fingerprints(repo, st_path)
    acmp_4907019 = load_acmp_4907019(repo)
    report_path = repo / args.out_report
    old_report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    prefix = old_report.split("\n---\n\n# W pointcloud attributes v1.1", 1)[0].rstrip()
    section = build_v11_section(rows, sens, b104_rows, density_qa(rows), acmp_4907019, fps, provenance)
    report_path.write_text(prefix + "\n\n" + section, encoding="utf-8")
    write_versions(repo / args.versions, args, provenance, rows, fps)
    print(f"[done] rows={len(rows)} -> {args.out_csv}")


if __name__ == "__main__":
    main()
