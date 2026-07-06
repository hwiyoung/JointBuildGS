#!/usr/bin/env python3
"""Prepare E5 pilot block candidates.

This is an A-stage, no-training helper. It enumerates spatially compact blocks
outside the existing GS train/eval stage, attaches the preregistered lens
columns, writes a candidate CSV and a map, and records a phase-local run
fingerprint. CRS is EPSG:25832 throughout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon


REPO = Path(__file__).resolve().parents[3]
W2_RUN = REPO / "phases/p0-audit/runs/w2_1_roofer_default_20260612_152729"
REF_MISMATCH = {"DEBY_LOD2_42364663", "DEBY_LOD2_104586480"}
WORLD_SHIFT = (690953.0, 5336071.0, 604.0)
SOURCE_PATHS = {
    "sparse": REPO / "phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt",
    "dense": REPO / "phases/p0-audit/data/work/mvs/dim/dim_v1.laz",
    "acmp": REPO / "results/tum_transfer/mob_analysis/p0c_step2/acmp_aoi_utm.laz",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def as_float(value: str | None) -> float | None:
    if value in (None, "", "none", "None"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def median(values: Iterable[float | None]) -> str:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return ""
    return f"{statistics.median(vals):.3f}"


def count_join(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return ";".join(f"{k}:{counter[k]}" for k in sorted(counter))


def normalize_bid(value: str) -> str:
    value = str(value)
    return value if value.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{value}"


def polygon_rings(geometry: dict) -> list[list[tuple[float, float]]]:
    if geometry.get("type") == "Polygon":
        return [[(float(x), float(y)) for x, y in geometry["coordinates"][0]]]
    if geometry.get("type") == "MultiPolygon":
        return [[(float(x), float(y)) for x, y in poly[0]] for poly in geometry["coordinates"]]
    return []


def ring_centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    if len(ring) < 3:
        return (0.0, 0.0)
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    pts = ring if ring[0] == ring[-1] else [*ring, ring[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area2) < 1e-9:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    return (cx / (3.0 * area2), cy / (3.0 * area2))


def load_footprints(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text())
    out: dict[str, dict] = {}
    for ft in data["features"]:
        bid = str(ft["properties"]["building_id"])
        rings = polygon_rings(ft["geometry"])
        coords = [p for ring in rings for p in ring]
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        # Properties already contain the footprint area. Use the largest part
        # centroid when a building appears once, and merge by bbox if repeated.
        centroid = ring_centroid(max(rings, key=len)) if rings else (sum(xs) / len(xs), sum(ys) / len(ys))
        row = {
            "rings": rings,
            "centroid": centroid,
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
            "area_m2": float(ft["properties"].get("area_m2") or 0.0),
        }
        if bid not in out:
            out[bid] = row
        else:
            old = out[bid]
            ox0, oy0, ox1, oy1 = old["bbox"]
            x0, y0, x1, y1 = row["bbox"]
            old["rings"].extend(rings)
            old["bbox"] = (min(ox0, x0), min(oy0, y0), max(ox1, x1), max(oy1, y1))
            old["area_m2"] += row["area_m2"]
            old["centroid"] = ((old["bbox"][0] + old["bbox"][2]) / 2.0, (old["bbox"][1] + old["bbox"][3]) / 2.0)
    return out


def unique_stage_bids(paths: list[Path]) -> set[str]:
    out: set[str] = set()
    for path in paths:
        for row in read_csv(path):
            out.add(normalize_bid(row["bid"]))
    return out


def source_bounds() -> dict[str, dict[str, object]]:
    bounds: dict[str, dict[str, object]] = {}
    sparse = SOURCE_PATHS["sparse"]
    if sparse.exists():
        xs: list[float] = []
        ys: list[float] = []
        with sparse.open() as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                xs.append(float(parts[1]) + WORLD_SHIFT[0])
                ys.append(float(parts[2]) + WORLD_SHIFT[1])
        bounds["sparse"] = {
            "exists": True,
            "bounds": (min(xs), min(ys), max(xs), max(ys)) if xs else None,
            "points": len(xs),
            "path": sparse,
        }
    else:
        bounds["sparse"] = {"exists": False, "bounds": None, "points": 0, "path": sparse}

    try:
        import laspy
    except Exception:
        laspy = None

    for name in ("dense", "acmp"):
        path = SOURCE_PATHS[name]
        if path.exists() and laspy is not None:
            las = laspy.open(path)
            hdr = las.header
            b = (float(hdr.x_min), float(hdr.y_min), float(hdr.x_max), float(hdr.y_max))
            bounds[name] = {"exists": True, "bounds": b, "points": int(hdr.point_count), "path": path}
            las.close()
        else:
            bounds[name] = {"exists": path.exists(), "bounds": None, "points": 0, "path": path}
    return bounds


def bbox_union(bids: Iterable[str], footprints: dict[str, dict]) -> tuple[float, float, float, float]:
    boxes = [footprints[b]["bbox"] for b in bids]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def bbox_inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float] | None) -> bool:
    if outer is None:
        return False
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def enumerate_candidates(
    footprints: dict[str, dict],
    outside_stage: set[str],
    dense_success: set[str],
    dense_fail: dict[str, dict[str, str]],
    manual: dict[str, dict[str, str]],
    aux: dict[str, dict[str, str]],
    src: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    raw: dict[tuple[str, ...], dict[str, object]] = {}
    valid = [b for b in footprints if b in outside_stage]
    for seed in valid:
        sx, sy = footprints[seed]["centroid"]
        neigh = sorted(
            valid,
            key=lambda b: (footprints[b]["centroid"][0] - sx) ** 2 + (footprints[b]["centroid"][1] - sy) ** 2,
        )
        for k in range(15, 31):
            bids = tuple(sorted(neigh[:k]))
            if bids in raw:
                continue
            success_count = sum(b in dense_success for b in bids)
            failure_count = sum(b in dense_fail for b in bids)
            if success_count < 10 or failure_count < 2:
                continue
            x0, y0, x1, y1 = bbox_union(bids, footprints)
            compact = math.hypot(x1 - x0, y1 - y0)
            failure_buckets = Counter(dense_fail[b]["bucket"] for b in bids if b in dense_fail)
            failure_reasons = Counter(dense_fail[b]["reason"] for b in bids if b in dense_fail)
            manual_labels = Counter(manual[b]["label"] for b in bids if b in manual)
            ref_ids = sorted(set(bids) & REF_MISMATCH)
            src_flags = {}
            for name, info in src.items():
                src_flags[f"seed_{name}_source"] = "present" if info["exists"] else "missing"
                src_flags[f"seed_{name}_clip_possible"] = "yes" if bbox_inside((x0, y0, x1, y1), info["bounds"]) else "no"
            dense_no_points = sum(dense_fail.get(b, {}).get("reason") == "pointcloud_unusable_no_points" for b in bids)
            dense_no_planes = sum(dense_fail.get(b, {}).get("reason") == "pointcloud_unusable_no_planes" for b in bids)
            dense_assembly = sum(dense_fail.get(b, {}).get("bucket") == "2_assembly" for b in bids)
            raw[bids] = {
                "building_ids": ";".join(bids),
                "n_buildings": len(bids),
                "dense_success_count": success_count,
                "dense_failure_count": failure_count,
                "dense_no_points_count": dense_no_points,
                "dense_no_planes_count": dense_no_planes,
                "dense_assembly_failure_count": dense_assembly,
                "failure_bucket_counts": count_join(failure_buckets),
                "failure_reason_counts": count_join(failure_reasons),
                "manual_review_count": sum(b in manual for b in bids),
                "manual_label_counts": count_join(manual_labels),
                "ref_mismatch_ids": ";".join(ref_ids),
                "n_views_nadir_median": median(as_float(aux.get(b, {}).get("n_views_nadir")) for b in bids),
                "n_views_total_median": median(as_float(aux.get(b, {}).get("n_views_total")) for b in bids),
                "frac_views_incidence_le60_median": median(
                    as_float(aux.get(b, {}).get("frac_views_incidence_le60")) for b in bids
                ),
                "recon_score_median_median": median(as_float(aux.get(b, {}).get("recon_score_median")) for b in bids),
                "roof_lowtex_v5_median": median(as_float(aux.get(b, {}).get("roof_lowtex_v5")) for b in bids),
                "bbox_minx": f"{x0:.3f}",
                "bbox_miny": f"{y0:.3f}",
                "bbox_maxx": f"{x1:.3f}",
                "bbox_maxy": f"{y1:.3f}",
                "compactness_diag_m": f"{compact:.3f}",
                "existing_stage_overlap_count": 0,
                **src_flags,
                "_score": (
                    1 if ref_ids else 0,
                    0 if dense_no_points > 0 else 1,
                    compact,
                    -failure_count,
                    -success_count,
                    len(bids),
                ),
                "_bids": bids,
            }
    out = sorted(raw.values(), key=lambda r: r["_score"])
    for i, row in enumerate(out, 1):
        row["candidate_id"] = f"C{i:03d}"
        row["rank"] = i
        row["recommended"] = "yes" if i == 1 else "no"
        row["recommendation_note"] = (
            "ref-mismatch excluded; includes dense no-points lens; compact among rule-satisfying blocks"
            if i == 1
            else ""
        )
    return out


def draw_map(
    path: Path,
    footprints: dict[str, dict],
    stage_bids: set[str],
    candidates: list[dict[str, object]],
) -> None:
    rec = candidates[0] if candidates else None
    rec_bids = set(rec["_bids"]) if rec else set()
    top_bids: set[str] = set()
    for cand in candidates[:10]:
        top_bids.update(cand["_bids"])

    fig, ax = plt.subplots(figsize=(10, 9), dpi=180)
    for bid, ft in footprints.items():
        if bid in rec_bids:
            face = "#f2a65a"
            edge = "#9a4f00"
            lw = 0.7
            alpha = 0.78
        elif bid in top_bids:
            face = "#f7d8ae"
            edge = "#c78b3b"
            lw = 0.35
            alpha = 0.45
        elif bid in stage_bids:
            face = "#7aa6c2"
            edge = "#456980"
            lw = 0.25
            alpha = 0.38
        else:
            face = "#d7d7d7"
            edge = "#9c9c9c"
            lw = 0.18
            alpha = 0.45
        for ring in ft["rings"]:
            ax.add_patch(MplPolygon(ring, closed=True, facecolor=face, edgecolor=edge, linewidth=lw, alpha=alpha))

    if rec:
        x0 = float(rec["bbox_minx"])
        y0 = float(rec["bbox_miny"])
        x1 = float(rec["bbox_maxx"])
        y1 = float(rec["bbox_maxy"])
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color="#b63100", linewidth=2.0)
        ax.text(x0, y1 + 5, f"recommended {rec['candidate_id']}", color="#8a2500", fontsize=9)

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("EPSG:25832 X (m)")
    ax.set_ylabel("EPSG:25832 Y (m)")
    ax.set_title("E5 pilot block candidates: outside existing GS stage")
    ax.grid(True, color="#eeeeee", linewidth=0.5)
    ax.autoscale()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_summary(
    path: Path,
    candidates: list[dict[str, object]],
    stage_bids: set[str],
    outside_count: int,
    src: dict[str, dict[str, object]],
    run_id: str,
) -> None:
    rec = candidates[0] if candidates else None
    lines = [
        "# E5 Pilot Block Candidates (A1)",
        "",
        "- CRS: EPSG:25832",
        f"- Run fingerprint: `phases/p2-gsjso/runs/{run_id}/versions.txt`",
        f"- Existing GS stage exclusion: {len(stage_bids)} buildings (D4 make-or-break + D12 71-stage union)",
        f"- Buildings outside stage: {outside_count}",
        f"- Rule-satisfying candidate blocks: {len(candidates)}",
        "",
        "## Seed Source Availability",
        "",
        "| seed source | file | source points | xy bounds | global status |",
        "|---|---:|---:|---|---|",
    ]
    for name in ("sparse", "dense", "acmp"):
        info = src[name]
        b = info["bounds"]
        btxt = "" if b is None else f"{b[0]:.1f},{b[1]:.1f} to {b[2]:.1f},{b[3]:.1f}"
        status = "present" if info["exists"] else "missing"
        lines.append(f"| {name} | `{Path(info['path']).relative_to(REPO)}` | {info['points']} | {btxt} | {status} |")
    lines.extend(
        [
            "",
            "## Recommended Candidate",
            "",
        ]
    )
    if rec:
        lines.extend(
            [
                f"- Candidate: `{rec['candidate_id']}`",
                f"- Buildings: {rec['n_buildings']}",
                f"- Dense success/failure: {rec['dense_success_count']} / {rec['dense_failure_count']}",
                f"- Dense no-points/no-planes/assembly: {rec['dense_no_points_count']} / {rec['dense_no_planes_count']} / {rec['dense_assembly_failure_count']}",
                f"- Manual labels: {rec['manual_label_counts'] or 'none'}",
                f"- Ref-mismatch IDs: {rec['ref_mismatch_ids'] or 'none'}",
                f"- Note: {rec['recommendation_note']}",
                "",
                "## Cost Estimate For Decision",
                "",
                "| item | estimate | basis |",
                "|---|---:|---|",
                "| GS learning runs | 6 | three seed sources x two random seeds |",
                "| GPU time | 6 x 4-8 h | prior D4-style 30k-iter full-scene runs; block clipping may reduce IO but not yet benchmarked |",
                "| GPU count | 1-2 | prior D4 dense/acmp used two GPUs in parallel; sparse can run independently |",
                "| read-out + assembly | <1 h per learned run | TSDF read-out + Roofer per block is lower cost than training |",
                "",
                "Observation only: this is cost material for the human A-stage decision, not a gate verdict.",
            ]
        )
    else:
        lines.append("No candidate satisfies the preregistered block rule.")
    path.write_text("\n".join(lines) + "\n")


def write_versions(path: Path, run_id: str, source_files: list[Path], candidate_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id={run_id}",
        "task=e5p-prep A1 pilot block candidate enumeration",
        f"created_at={datetime.now().isoformat(timespec='seconds')}",
        f"branch={git(['branch', '--show-current'])}",
        f"head={git(['rev-parse', 'HEAD'])}",
        "crs=EPSG:25832",
        "docker_image=jointbuildgs-p0-tools:t0",
        f"script=phases/p2-gsjso/scripts/e5_pilot_prep.py sha256={sha256(Path(__file__))}",
        f"candidate_count={candidate_count}",
        "",
        "inputs:",
    ]
    for src in source_files:
        if src.exists():
            lines.append(f"- {src.relative_to(REPO)} sha256={sha256(src)}")
        else:
            lines.append(f"- {src.relative_to(REPO)} MISSING")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=datetime.now().strftime("e5p_prep_%Y%m%d_%H%M%S"))
    ap.add_argument("--candidate-csv", default="docs/e5_pilot_block_candidates.csv")
    ap.add_argument("--map-png", default="docs/figs/e5_pilot_block_candidates.png")
    ap.add_argument("--summary-md", default="docs/e5_pilot_block_candidates_summary.md")
    args = ap.parse_args()

    footprint_path = REPO / "results/tum_transfer/analysis/footprints_aoi.geojson"
    aux_path = REPO / "docs/population_aux_v4.csv"
    manual_path = REPO / "docs/manual_review_judgments.csv"
    d12_path = REPO / "results/tum_transfer/mob/overseg_lever/d12_buckets.csv"
    d4_eval = REPO / "results/tum_transfer/mob/eval_d4_gssem.csv"
    d12_eval = REPO / "results/tum_transfer/mob/eval_d12_gssem.csv"
    status_path = W2_RUN / "building_reconstruction_status.csv"

    footprints = load_footprints(footprint_path)
    stage_bids = unique_stage_bids([d4_eval, d12_eval])
    outside_stage = set(footprints) - stage_bids

    dim_status = {
        row["building_id"]: row for row in read_csv(status_path) if row["input"] == "DIM"
    }
    dense_fail = {normalize_bid(row["bid"]): row for row in read_csv(d12_path)}
    dense_success = {
        bid for bid, row in dim_status.items() if row.get("has_lod22") == "True" and bid not in dense_fail
    }
    manual = {row["building_id"]: row for row in read_csv(manual_path)}
    aux = {row["building_id"]: row for row in read_csv(aux_path)}
    src = source_bounds()

    candidates = enumerate_candidates(footprints, outside_stage, dense_success, dense_fail, manual, aux, src)
    if not candidates:
        print("no candidates satisfy the rule", flush=True)
        return 2

    fieldnames = [
        "candidate_id",
        "rank",
        "recommended",
        "recommendation_note",
        "n_buildings",
        "dense_success_count",
        "dense_failure_count",
        "dense_no_points_count",
        "dense_no_planes_count",
        "dense_assembly_failure_count",
        "failure_bucket_counts",
        "failure_reason_counts",
        "manual_review_count",
        "manual_label_counts",
        "ref_mismatch_ids",
        "n_views_nadir_median",
        "n_views_total_median",
        "frac_views_incidence_le60_median",
        "recon_score_median_median",
        "roof_lowtex_v5_median",
        "bbox_minx",
        "bbox_miny",
        "bbox_maxx",
        "bbox_maxy",
        "compactness_diag_m",
        "existing_stage_overlap_count",
        "seed_sparse_source",
        "seed_sparse_clip_possible",
        "seed_dense_source",
        "seed_dense_clip_possible",
        "seed_acmp_source",
        "seed_acmp_clip_possible",
        "building_ids",
    ]
    public_rows = [{k: row.get(k, "") for k in fieldnames} for row in candidates]
    write_csv(REPO / args.candidate_csv, public_rows, fieldnames)
    draw_map(REPO / args.map_png, footprints, stage_bids, candidates)
    write_summary(REPO / args.summary_md, candidates, stage_bids, len(outside_stage), src, args.run_id)
    write_versions(
        REPO / f"phases/p2-gsjso/runs/{args.run_id}/versions.txt",
        args.run_id,
        [footprint_path, aux_path, manual_path, d12_path, d4_eval, d12_eval, status_path, Path(__file__)],
        len(candidates),
    )
    print(f"candidate_csv={args.candidate_csv}")
    print(f"map_png={args.map_png}")
    print(f"summary_md={args.summary_md}")
    print(f"run_versions=phases/p2-gsjso/runs/{args.run_id}/versions.txt")
    print(f"candidate_count={len(candidates)}")
    print(f"recommended={candidates[0]['candidate_id']} n={candidates[0]['n_buildings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
