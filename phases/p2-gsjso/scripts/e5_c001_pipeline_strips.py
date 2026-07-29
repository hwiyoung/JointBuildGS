#!/usr/bin/env python3
"""Build A-6 visual pipeline strips for E5 C001 S1 factor work."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import e5_c001_8way as eight  # noqa: E402
import e5_c001_s1_full_factor as factor  # noqa: E402


SHIFT_UTM = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
DATA_ROOT = REPO / "results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20"
FOOTPRINTS_GEOJSON = REPO / "phases/p0-audit/data/work/footprints/lod2_ground_plan.geojson"
FIG_DIR = REPO / "docs/figs/e5_c001_s1_full_factor/pipeline_strips"
CSV_STRIPS = REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_pipeline_strips.csv"
CSV_ISSUES = REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_pipeline_strips_issues.csv"
REPAIR_ROOT = REPO / "phases/p0-audit/runs/e5p_405_repair_20260709_C001"
TARGET_INITIAL = ["4907202", "4908168", "4907185", "4907184", "60098", "8568392"]
TARGET_FACTOR = ["4907202", "4908168", "4907185", "4907184"]
RNG = np.random.default_rng(20260709)


@dataclass(frozen=True)
class StripCondition:
    key: str
    label: str
    run_name: str
    ckpt: Path
    coverage_csv: Path
    metrics_csv: Path
    p0_run_id: str
    setting: str = "base"
    z_shift_to_reference_m: float = -45.7


def rel(path: Path | str | None) -> str:
    if path is None:
        return ""
    p = Path(path)
    for root in (REPO, Path("/workspace/JointBuildGS")):
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    text = str(p)
    prefix = "/workspace/JointBuildGS/"
    return text[len(prefix) :] if text.startswith(prefix) else text


def full_id(short: str) -> str:
    return short if short.startswith("DEBY_LOD2_") else f"DEBY_LOD2_{short}"


def short_id(bid: str) -> str:
    return bid.replace("DEBY_LOD2_", "")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not fields:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def append_issue(rows: list[dict[str, Any]], condition: str, building_id: str, message: str, path: Path | None = None) -> None:
    rows.append({"condition": condition, "building_id": building_id, "message": message, "path": rel(path)})


def num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(str(value).strip())
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def load_footprints(ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted = {full_id(x) for x in ids}
    payload = json.loads(FOOTPRINTS_GEOJSON.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in wanted:
            continue
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            rings = [np.asarray(geom["coordinates"][0], dtype=np.float64)]
        elif geom["type"] == "MultiPolygon":
            rings = [np.asarray(poly[0], dtype=np.float64) for poly in geom["coordinates"]]
        else:
            continue
        xy = np.concatenate([r[:, :2] for r in rings], axis=0)
        out[bid] = {
            "rings": [r[:, :2] for r in rings],
            "paths": [MplPath(r[:, :2], closed=True) for r in rings],
            "bbox": (float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max())),
        }
    return out


def polygon_exteriors(poly: Any) -> list[np.ndarray]:
    if poly is None or poly.is_empty:
        return []
    if poly.geom_type == "Polygon":
        return [np.asarray(poly.exterior.coords, dtype=float)]
    if poly.geom_type == "MultiPolygon":
        return [np.asarray(p.exterior.coords, dtype=float) for p in poly.geoms]
    return []


def plot_roof_polygons(ax: Any, surfaces: list[eight.RoofSurface], color: str, label: str, lw: float = 1.2) -> None:
    labelled = False
    for surf in surfaces:
        for ring in polygon_exteriors(surf.polygon):
            ax.plot(ring[:, 0], ring[:, 1], color=color, linewidth=lw, label=label if not labelled else None)
            labelled = True


def load_gaussians(ckpt: Path) -> dict[str, np.ndarray]:
    import torch

    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    state = payload["state_dict"]
    means = state["means"].detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
    opa = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
    return {"means": means, "opacity": opa}


def gaussian_indices(means: np.ndarray, fp: dict[str, Any], margin: float) -> np.ndarray:
    x0, y0, x1, y1 = fp["bbox"]
    return np.where((means[:, 0] >= x0 - margin) & (means[:, 0] <= x1 + margin) & (means[:, 1] >= y0 - margin) & (means[:, 1] <= y1 + margin))[0]


def gaussian_stats(means: np.ndarray, opacity: np.ndarray, fp: dict[str, Any]) -> dict[str, Any]:
    idx = gaussian_indices(means, fp, 2.0)
    if idx.size:
        cand = means[idx]
        inside = np.zeros(cand.shape[0], dtype=bool)
        for path in fp["paths"]:
            inside |= path.contains_points(cand[:, :2])
        idx = idx[inside]
    z = means[idx, 2] if idx.size else np.array([], dtype=float)
    op = opacity[idx] if idx.size else np.array([], dtype=float)
    return {
        "n_gaussians_in_footprint": int(idx.size),
        "gaussian_z_p50": float(np.quantile(z, 0.5)) if z.size else None,
        "gaussian_z_std": float(np.std(z)) if z.size else None,
        "gaussian_opacity_p50": float(np.quantile(op, 0.5)) if op.size else None,
    }


def make_model_from_state(state: dict[str, Any], device: Any) -> Any:
    import torch
    from src.stage2.model import GaussianModel2D

    model = GaussianModel2D.__new__(GaussianModel2D)
    torch.nn.Module.__init__(model)
    n_sh = int(state["sh0"].shape[1] + state["shN"].shape[1])
    sh_degree = int(round(math.sqrt(n_sh) - 1))
    model.sh_degree = sh_degree
    model.max_sh_degree = sh_degree
    model.active_sh_degree = sh_degree
    model.num_classes = int(state.get("sem_logits").shape[-1]) if "sem_logits" in state else 4
    for key in ["means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"]:
        if key in state:
            setattr(model, key, torch.nn.Parameter(state[key].to(device).float(), requires_grad=False))
    model.eval()
    return model


def project(points_local: np.ndarray, w2c: np.ndarray, K: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hom = np.concatenate([points_local, np.ones((len(points_local), 1), dtype=np.float64)], axis=1)
    cam = (w2c @ hom.T).T[:, :3]
    z = cam[:, 2]
    uvw = (K @ cam.T).T
    uv = uvw[:, :2] / np.maximum(uvw[:, 2:3], 1e-9)
    return uv, z


def reference_z(refs: list[eight.RoofSurface], fp: dict[str, Any]) -> float:
    vals = []
    for surf in refs:
        for ring in polygon_exteriors(surf.polygon):
            vals.extend(ring[:, 2].tolist() if ring.shape[1] > 2 else [])
        cx = (fp["bbox"][0] + fp["bbox"][2]) / 2.0
        cy = (fp["bbox"][1] + fp["bbox"][3]) / 2.0
        vals.append(float(surf.z_at(np.asarray([cx]), np.asarray([cy]))[0]))
    return float(np.median(vals)) if vals else 575.0


def select_view(ds: Any, fp: dict[str, Any], refs: list[eight.RoofSurface]) -> tuple[int, tuple[int, int, int, int]]:
    x0, y0, x1, y1 = fp["bbox"]
    z = reference_z(refs, fp)
    pts_utm = np.asarray([[x0, y0, z], [x0, y1, z], [x1, y1, z], [x1, y0, z], [(x0 + x1) / 2, (y0 + y1) / 2, z]], dtype=np.float64)
    pts_local = pts_utm - SHIFT_UTM
    best: tuple[float, int, tuple[int, int, int, int]] | None = None
    for i in range(len(ds)):
        batch = ds[i]
        H, W = int(batch["height"]), int(batch["width"])
        uv, depth = project(pts_local, batch["w2c"].numpy(), batch["K"].numpy())
        if np.count_nonzero(depth > 0) < 4:
            continue
        u0, v0 = np.nanmin(uv[:, 0]), np.nanmin(uv[:, 1])
        u1, v1 = np.nanmax(uv[:, 0]), np.nanmax(uv[:, 1])
        if u1 < 0 or v1 < 0 or u0 >= W or v0 >= H:
            continue
        area = max(0.0, min(u1, W - 1) - max(u0, 0)) * max(0.0, min(v1, H - 1) - max(v0, 0))
        if area <= 20:
            continue
        margin = 36
        crop = (max(0, int(u0) - margin), max(0, int(v0) - margin), min(W, int(u1) + margin), min(H, int(v1) + margin))
        score = area / max(1, (crop[2] - crop[0]) * (crop[3] - crop[1]))
        if best is None or score > best[0]:
            best = (score, i, crop)
    if best is None:
        batch = ds[10]
        H, W = int(batch["height"]), int(batch["width"])
        return 10, (W // 4, H // 4, 3 * W // 4, 3 * H // 4)
    return best[1], best[2]


def render_crop(condition: StripCondition, view_idx: int, crop: tuple[int, int, int, int], device_name: str, cache: dict[tuple[str, int], dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    key = (condition.key, view_idx)
    if key not in cache:
        import torch
        from src.stage2.dataloader import ColmapDataset
        from src.stage2.renderer import render

        ds = render_crop.dataset
        device = torch.device(device_name if device_name == "cpu" or torch.cuda.is_available() else "cpu")
        payload = torch.load(condition.ckpt, map_location="cpu", weights_only=False)
        model = make_model_from_state(payload["state_dict"], device)
        batch = ds[view_idx]
        with torch.no_grad():
            out = render(model, batch["w2c"].to(device), batch["K"].to(device), batch["width"], batch["height"], sh_degree=model.active_sh_degree, render_mode="RGB+ED")
        cache[key] = {
            "rgb": np.clip(out["rgb"].detach().cpu().numpy(), 0.0, 1.0),
            "depth": out["depth"].detach().cpu().numpy(),
            "alpha": out["alpha"].detach().cpu().numpy(),
        }
    x0, y0, x1, y1 = crop
    return {name: arr[y0:y1, x0:x1] for name, arr in cache[key].items()}


def coverage_counts(condition: StripCondition, building_id: str) -> dict[str, Any]:
    rows = read_csv(condition.coverage_csv)
    stages = {
        "voxel_all_pre_minobs": "pre",
        "minobs_post_gate_pre_sor": "minobs",
        "sor_post_clean": "sor",
    }
    out = {label: 0 for label in stages.values()}
    for row in rows:
        if row.get("setting", "base") != condition.setting or row.get("run_name") != condition.run_name or row.get("building_id") != building_id:
            continue
        label = stages.get(row.get("stage", ""))
        if label:
            out[label] = int(float(row.get("occupied_cells") or 0))
    metrics_path = REPO / "phases/p0-audit/runs" / condition.p0_run_id / condition.setting / "roofer" / condition.run_name / "run_1" / f"{building_id}_run_1_metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        out["final_fp_points"] = int(metrics.get("n_building_in_fp") or 0)
        out["classified_points"] = int(metrics.get("n_building") or 0)
    else:
        out["final_fp_points"] = 0
        out["classified_points"] = 0
    return out


def cityjson_path(condition: StripCondition) -> Path:
    repaired = REPAIR_ROOT / condition.p0_run_id / condition.setting / "cityjson" / f"{condition.run_name}_run_1.city.json"
    if repaired.exists():
        return repaired
    return REPO / "phases/p0-audit/runs" / condition.p0_run_id / condition.setting / "cityjson" / f"{condition.run_name}_run_1.city.json"


def status_for(condition: StripCondition, building_id: str) -> dict[str, str]:
    repaired = REPAIR_ROOT / condition.p0_run_id / condition.setting / "status" / f"{condition.run_name}_run_1.csv"
    raw = REPO / "phases/p0-audit/runs" / condition.p0_run_id / condition.setting / "status" / f"{condition.run_name}_run_1.csv"
    for path in [repaired, raw]:
        for row in read_csv(path):
            if row.get("building_id") == building_id:
                return row
    return {}


def plot_strip(
    condition: StripCondition,
    bid: str,
    fp: dict[str, Any],
    refs: list[eight.RoofSurface],
    pred: list[eight.RoofSurface],
    gauss: dict[str, np.ndarray],
    render: dict[str, np.ndarray] | None,
    counts: dict[str, Any],
    status: dict[str, str],
    out_path: Path,
) -> None:
    means = gauss["means"]
    opacity = gauss["opacity"]
    idx = gaussian_indices(means, fp, 20.0)
    if idx.size > 25000:
        idx = RNG.choice(idx, 25000, replace=False)
    pts = means[idx]
    op = opacity[idx]
    x0, y0, x1, y1 = fp["bbox"]
    horiz_axis = 0 if (x1 - x0) >= (y1 - y0) else 1
    hcoord = pts[:, horiz_axis] if len(pts) else np.array([])
    hlabel = "Easting" if horiz_axis == 0 else "Northing"

    fig, axes = plt.subplots(1, 6, figsize=(18.0, 3.4))
    if len(pts):
        sc = axes[0].scatter(pts[:, 0], pts[:, 1], c=op, s=1.5, cmap="viridis", vmin=0, vmax=max(0.12, float(np.quantile(op, 0.98))))
        fig.colorbar(sc, ax=axes[0], fraction=0.045, pad=0.01).ax.tick_params(labelsize=6)
    for ring in fp["rings"]:
        axes[0].plot(ring[:, 0], ring[:, 1], color="black", linewidth=1.0)
    plot_roof_polygons(axes[0], refs, "#e63946", "ref", lw=1.0)
    axes[0].set_title("Gaussian top")
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_xlim(x0 - 20, x1 + 20)
    axes[0].set_ylim(y0 - 20, y1 + 20)

    if len(pts):
        axes[1].scatter(hcoord, pts[:, 2], c=op, s=1.5, cmap="viridis", vmin=0, vmax=max(0.12, float(np.quantile(op, 0.98))))
    z_vals = []
    for surf in refs:
        z_vals.append(float(surf.z_at(np.asarray([(x0 + x1) / 2]), np.asarray([(y0 + y1) / 2]))[0]))
    if z_vals:
        axes[1].axhspan(min(z_vals) - 1.0, max(z_vals) + 1.0, color="#e63946", alpha=0.12)
    axes[1].set_title("Gaussian side")
    axes[1].set_xlabel(hlabel)
    axes[1].set_ylabel("z m")
    if len(pts):
        axes[1].set_ylim(np.nanpercentile(pts[:, 2], 1) - 3, np.nanpercentile(pts[:, 2], 99) + 3)

    if render is not None and render["rgb"].size:
        axes[2].imshow(render["rgb"])
        depth = render["depth"]
        valid = np.isfinite(depth) & (depth > 0)
        if np.any(valid):
            lo, hi = np.quantile(depth[valid], [0.05, 0.95])
            axes[3].imshow(depth, cmap="magma", vmin=lo, vmax=hi)
        else:
            axes[3].imshow(depth, cmap="magma")
    axes[2].set_title("GS RGB crop")
    axes[3].set_title("GS depth crop")
    axes[2].axis("off")
    axes[3].axis("off")

    labels = ["pre", "minobs", "sor", "fp pts"]
    vals = [counts.get("pre", 0), counts.get("minobs", 0), counts.get("sor", 0), counts.get("final_fp_points", 0)]
    axes[4].bar(np.arange(len(labels)), vals, color=["#577590", "#f3722c", "#43aa8b", "#277da1"])
    axes[4].set_xticks(np.arange(len(labels)))
    axes[4].set_xticklabels(labels, rotation=25, ha="right", fontsize=7)
    axes[4].set_title("Readout stages")
    axes[4].grid(axis="y", alpha=0.25)

    plot_roof_polygons(axes[5], refs, "#e63946", "ref", lw=1.4)
    plot_roof_polygons(axes[5], pred, "#277da1", "model", lw=1.2)
    for ring in fp["rings"]:
        axes[5].plot(ring[:, 0], ring[:, 1], color="black", linewidth=0.7, alpha=0.45)
    axes[5].set_title(f"Model vs ref\n{status.get('reason', '')}")
    axes[5].set_aspect("equal", adjustable="box")
    axes[5].set_xlim(x0 - 5, x1 + 5)
    axes[5].set_ylim(y0 - 5, y1 + 5)
    axes[5].legend(fontsize=6, loc="upper right")

    stats = gaussian_stats(means, opacity, fp)
    fig.suptitle(
        f"{short_id(bid)} | {condition.label} | n={stats['n_gaussians_in_footprint']} z50={stats['gaussian_z_p50'] if stats['gaussian_z_p50'] is not None else 'NA'}",
        fontsize=10,
    )
    for ax in axes:
        ax.tick_params(labelsize=7)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=170)
    plt.close(fig)


def initial_conditions() -> list[StripCondition]:
    return [
        StripCondition(
            "s1_dense",
            "S1 dense",
            "gs_e5_C001_s1_dense_r1",
            REPO / "results/tum_transfer/e5_3b_s1/C001/runs/gs_e5_C001_s1_dense_r1/ckpt/final.pt",
            REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_coverage.csv",
            REPO / "docs/experiments/e5_c001_3b_s1/tables/e5_c001_3b_s1_metrics.csv",
            "e5p_3b_s1_20260708_C001",
        ),
        StripCondition(
            "corrected_recheck_keepall_dense",
            "corrected recheck keepall dense",
            "gs_e5_C001_corrected_s1_preprune_keepall_dense_r1",
            REPO / "results/tum_transfer/e5_corrected_s1_recheck/C001/runs/gs_e5_C001_corrected_s1_preprune_keepall_dense_r1/ckpt/final.pt",
            REPO / "docs/experiments/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_preprune_coverage.csv",
            REPO / "docs/experiments/e5_c001_corrected_s1_recheck/tables/e5_c001_corrected_s1_recheck_building_8way.csv",
            "e5p_corrected_s1_recheck_20260709_C001",
        ),
    ]


def factor_conditions(weight: int | None) -> list[StripCondition]:
    w = factor.selected_w(weight)
    cells = [cell for cell in factor.cells_for_weight(w) if not cell.reuse]
    return [
        StripCondition(
            cell.key,
            cell.role,
            cell.run_name,
            factor.CKPT_ROOT / cell.run_name / "ckpt/final.pt",
            REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_coverage.csv",
            REPO / "docs/experiments/e5_c001_s1_full/tables/e5_c001_s1_full_building_8way.csv",
            factor.P0_RUN_ID,
        )
        for cell in cells
    ]


def run(args: argparse.Namespace) -> None:
    import torch
    from src.stage2.dataloader import ColmapDataset

    ids = TARGET_INITIAL if args.mode == "initial" else TARGET_FACTOR
    conditions = initial_conditions() if args.mode == "initial" else factor_conditions(args.weight)
    footprints = load_footprints(ids)
    refs_by_id = eight.parse_lod2_roofs(eight.LOD2_DIR, {full_id(x) for x in ids})
    ds = ColmapDataset(root=str(DATA_ROOT), downscale=args.downscale, load_depth=True, load_normal=False, load_semantic=False)
    render_crop.dataset = ds
    render_cache: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for condition in conditions:
        if not condition.ckpt.exists():
            append_issue(issues, condition.key, "", "checkpoint missing", condition.ckpt)
            continue
        gauss = load_gaussians(condition.ckpt)
        pred_by_id = eight.parse_cityjson_roofs(cityjson_path(condition), {full_id(x) for x in ids})
        pred_by_id = {bid: eight.shift_surface_z(surfs, condition.z_shift_to_reference_m) for bid, surfs in pred_by_id.items()}
        for sid in ids:
            bid = full_id(sid)
            fp = footprints.get(bid)
            refs = refs_by_id.get(bid, [])
            if fp is None or not refs:
                append_issue(issues, condition.key, bid, "footprint or reference missing")
                continue
            view_idx, crop = select_view(ds, fp, refs)
            rendered = None
            try:
                rendered = render_crop(condition, view_idx, crop, args.device, render_cache)
            except Exception as exc:  # noqa: BLE001
                append_issue(issues, condition.key, bid, f"render failed: {type(exc).__name__}: {exc}", condition.ckpt)
            counts = coverage_counts(condition, bid)
            status = status_for(condition, bid)
            out = FIG_DIR / f"{args.mode}_{short_id(bid)}_{condition.key}.png"
            plot_strip(condition, bid, fp, refs, pred_by_id.get(bid, []), gauss, rendered, counts, status, out)
            stats = gaussian_stats(gauss["means"], gauss["opacity"], fp)
            rows.append(
                {
                    "mode": args.mode,
                    "condition": condition.key,
                    "run_name": condition.run_name,
                    "building_id": bid,
                    "figure": rel(out),
                    "view_idx": view_idx,
                    "crop_xyxy": ",".join(str(v) for v in crop),
                    "ckpt": rel(condition.ckpt),
                    "cityjson": rel(cityjson_path(condition)),
                    "status_reason": status.get("reason", ""),
                    "has_lod22": status.get("has_lod22", ""),
                    "val3dity_valid": status.get("val3dity_valid", ""),
                    **{k: "" if v is None else v for k, v in stats.items()},
                    **{f"readout_{k}": v for k, v in counts.items()},
                }
            )
            print(json.dumps({"mode": args.mode, "condition": condition.key, "building_id": bid, "figure": rel(out)}, ensure_ascii=False), flush=True)
    previous = [] if args.mode == "initial" else [r for r in read_csv(CSV_STRIPS) if r.get("mode") != args.mode]
    write_csv(CSV_STRIPS, previous + rows)
    write_csv(CSV_ISSUES, issues, ["condition", "building_id", "message", "path"])
    torch.cuda.empty_cache() if torch.cuda.is_available() else None
    print(json.dumps({"strips": rel(CSV_STRIPS), "rows": len(rows), "issues": len(issues)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["initial", "factor"])
    parser.add_argument("--weight", type=int, default=None)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--downscale", type=float, default=0.35)
    return parser


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
