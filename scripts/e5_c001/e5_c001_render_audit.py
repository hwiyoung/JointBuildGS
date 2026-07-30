#!/usr/bin/env python3
"""C001 checkpoint render/floater audit.

This is a diagnostic-only pass:
  * no training
  * no formal pointcloudification/readout/reassembly
  * checkpoint inference and existing artifacts only

It writes docs tables, docs/figs assets, a markdown report, and a run versions file.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
import pandas as pd
import torch
from scipy.spatial import cKDTree
from skimage.metrics import structural_similarity
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stage2.dataloader import ColmapDataset  # noqa: E402
from src.stage2.model import GaussianModel2D  # noqa: E402
from src.stage2.renderer import render, render_semantic  # noqa: E402


SHIFT_UTM = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
GRID_SIZE_M = 0.5
CONFIG_CONSTANTS = {
    "w_distort": 0.0,
    "prune_opa": 0.005,
    "seed_protect": True,
    "sh_degree": 3,
    "w_depth": 0.03,
    "readout": "semantic-TSDF minobs3 / voxel0.05 / alpha0.5 / SOR",
}
TARGET_CASES = ["DEBY_LOD2_4907184", "DEBY_LOD2_60098", "DEBY_LOD2_8568391"]


@dataclass
class Footprint:
    building_id: str
    rings: list[np.ndarray]
    paths: list[MplPath]
    bbox: tuple[float, float, float, float]
    area_m2: float
    grid_total_cells: int


def sha256_file(path: Path, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def run_text(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostic metadata only
        return f"ERROR:{type(exc).__name__}:{exc}"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    ap.add_argument("--runs-root", default="results/tum_transfer/e5_pilot/C001/runs")
    ap.add_argument("--data-root", default="results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20")
    ap.add_argument("--readout-root", default="results/tum_transfer/e5_pilot/C001/readout")
    ap.add_argument("--seed-root", default="results/tum_transfer/e5_pilot/C001/seeds")
    ap.add_argument("--readout-setting", default=None, help="Optional setting filter for readout_fingerprints.csv rows.")
    ap.add_argument("--footprints", default="phases/p0-audit/data/work/footprints/lod2_ground_plan.geojson")
    ap.add_argument("--train-fingerprints", default="phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/train_fingerprints.csv")
    ap.add_argument("--readout-fingerprints", default="phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/readout_fingerprints.csv")
    ap.add_argument("--gsdiag-snapshot-dir", default="phases/p2-gsjso/runs/e5_c001/20260707_e5_c001_gsdiag/snapshots")
    ap.add_argument("--lowtex-v5", default="docs/experiments/input-and-alignment/lowtex_v5/tables/lowtex_v5.csv")
    ap.add_argument("--projection-zeta", default="docs/experiments/input-and-alignment/projection_zeta_ls/tables/projection_zeta_ls.csv")
    ap.add_argument("--out-run", default="phases/p2-gsjso/runs/e5_c001/20260708_e5_c001_render_audit")
    ap.add_argument("--fig-dir", default="docs/figs/e5_c001_render")
    ap.add_argument("--doc-path", default="docs/experiments/evaluation/e5_c001_render/reports/W_E5_C001_렌더플로터점검.md")
    ap.add_argument("--docs-prefix", default="docs/e5_c001_render", help="Prefix for CSV outputs before _eval_metrics.csv, etc.")
    ap.add_argument("--max-render-views", type=int, default=4)
    ap.add_argument("--max-depth-coverage-views", type=int, default=0, help="0 means all frames.")
    ap.add_argument("--max-offsurface-sample", type=int, default=200000)
    ap.add_argument("--device", default="cuda")
    return ap.parse_args()


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_ply_xyz_ascii(path: Path) -> np.ndarray:
    n = None
    header_lines = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            header_lines += 1
            if line.startswith("element vertex"):
                n = int(line.split()[-1])
            if line.strip() == "end_header":
                break
    if n is None:
        raise ValueError(f"Cannot find vertex count in {path}")
    arr = np.loadtxt(path, skiprows=header_lines, max_rows=n, dtype=np.float32, usecols=(0, 1, 2))
    return arr.reshape(-1, 3)


def load_footprints(path: Path, building_ids: Iterable[str], grid_totals: dict[str, int], areas: dict[str, float]) -> dict[str, Footprint]:
    wanted = set(building_ids)
    data = json.loads(path.read_text(encoding="utf-8"))
    by_id: dict[str, list[np.ndarray]] = {bid: [] for bid in wanted}
    for feat in data["features"]:
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
        by_id[bid].extend(rings)
    fps: dict[str, Footprint] = {}
    for bid, rings in by_id.items():
        if not rings:
            continue
        xy = np.concatenate(rings, axis=0)
        bbox = (float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max()))
        paths = [MplPath(r[:, :2], closed=True) for r in rings]
        fps[bid] = Footprint(
            building_id=bid,
            rings=[r[:, :2] for r in rings],
            paths=paths,
            bbox=bbox,
            area_m2=float(areas.get(bid, 0.0)),
            grid_total_cells=int(grid_totals.get(bid, max(1, round(float(areas.get(bid, 0.0)) / (GRID_SIZE_M**2))))),
        )
    return fps


def make_model_from_state(state: dict[str, torch.Tensor], device: torch.device) -> GaussianModel2D:
    model = GaussianModel2D.__new__(GaussianModel2D)
    torch.nn.Module.__init__(model)
    n_sh = int(state["sh0"].shape[1] + state["shN"].shape[1])
    sh_degree = int(round(math.sqrt(n_sh) - 1))
    model.sh_degree = sh_degree
    model.max_sh_degree = sh_degree
    model.active_sh_degree = sh_degree
    model.num_classes = int(state.get("sem_logits", torch.empty(0, 4)).shape[-1])
    for key in ["means", "quats", "log_scales", "opacities_raw", "sh0", "shN", "sem_logits"]:
        if key in state:
            param = torch.nn.Parameter(state[key].to(device).float(), requires_grad=False)
            setattr(model, key, param)
    model.eval()
    return model


def load_event_scalars(run_dir: Path) -> dict[str, float]:
    tb_files = sorted((run_dir / "tb").glob("events.out.tfevents*"))
    out: dict[str, float] = {}
    if not tb_files:
        return out
    acc = EventAccumulator(str(tb_files[-1]), size_guidance={"scalars": 0})
    acc.Reload()
    tags = set(acc.Tags().get("scalars", []))
    for tag in ["eval/psnr", "eval/depth_mae", "eval/normal_cos", "loss/distort", "metric/psnr_train"]:
        if tag not in tags:
            continue
        ev = acc.Scalars(tag)
        if ev:
            out[tag.replace("/", "_")] = float(ev[-1].value)
    return out


def psnr_np(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a - b) ** 2))
    return 20.0 * math.log10(1.0) - 10.0 * math.log10(max(mse, 1e-10))


def ssim_np(a: np.ndarray, b: np.ndarray) -> float:
    h, w = a.shape[:2]
    # Full-size SSIM is expensive; deterministic subsampling preserves the audit direction.
    stride = max(1, min(h, w) // 640)
    aa = np.ascontiguousarray(a[::stride, ::stride])
    bb = np.ascontiguousarray(b[::stride, ::stride])
    return float(structural_similarity(aa, bb, channel_axis=-1, data_range=1.0))


def depth_metrics(pred: np.ndarray, gt: np.ndarray, gt_mask: np.ndarray, alpha: np.ndarray | None = None) -> dict[str, float]:
    pm = np.isfinite(pred) & (pred > 0) & (pred < 500)
    if alpha is not None:
        pm &= alpha > 0.5
    valid = gt_mask & pm
    if int(valid.sum()) == 0:
        return {
            "depth_mae_m": float("nan"),
            "depth_rmse_m": float("nan"),
            "depth_valid_overlap_frac": 0.0,
            "depth_pred_valid_frac_on_mvs": float(pm[gt_mask].mean()) if int(gt_mask.sum()) else float("nan"),
        }
    err = pred[valid] - gt[valid]
    return {
        "depth_mae_m": float(np.abs(err).mean()),
        "depth_rmse_m": float(np.sqrt(np.mean(err**2))),
        "depth_valid_overlap_frac": float(valid.mean()),
        "depth_pred_valid_frac_on_mvs": float(pm[gt_mask].mean()) if int(gt_mask.sum()) else float("nan"),
    }


class CoverageGrid:
    def __init__(self, footprints: dict[str, Footprint]):
        self.footprints = footprints
        self.cells: dict[str, set[tuple[int, int]]] = {bid: set() for bid in footprints}

    def add_points(self, points_utm: np.ndarray) -> None:
        if points_utm.size == 0:
            return
        xy = points_utm[:, :2]
        for bid, fp in self.footprints.items():
            x0, y0, x1, y1 = fp.bbox
            m = (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)
            if not np.any(m):
                continue
            cand = xy[m]
            inside = np.zeros(cand.shape[0], dtype=bool)
            for path in fp.paths:
                inside |= path.contains_points(cand)
            if not np.any(inside):
                continue
            pts = cand[inside]
            ix = np.floor((pts[:, 0] - x0) / GRID_SIZE_M).astype(np.int64)
            iy = np.floor((pts[:, 1] - y0) / GRID_SIZE_M).astype(np.int64)
            self.cells[bid].update(zip(ix.tolist(), iy.tolist()))

    def rows(self, source_run: str, stage: str) -> list[dict[str, object]]:
        rows = []
        for bid, fp in self.footprints.items():
            occupied = len(self.cells[bid])
            total = max(1, fp.grid_total_cells)
            rows.append(
                {
                    "source_run": source_run,
                    "stage": stage,
                    "building_id": bid,
                    "occupied_cells": occupied,
                    "grid_total_cells": total,
                    "coverage_frac": min(1.0, occupied / total),
                }
            )
        return rows


def render_backproject_points(
    out: dict[str, torch.Tensor],
    sem_logits: torch.Tensor | None,
    b: dict[str, object],
    alpha_threshold: float = 0.5,
) -> np.ndarray:
    alpha = out["alpha"].detach()
    depth = out["depth_median"].detach()
    keep = (alpha > alpha_threshold) & torch.isfinite(depth) & (depth > 0) & (depth < 500)
    if sem_logits is not None:
        cls = sem_logits.argmax(dim=-1)
        keep &= cls == 1
    if int(keep.sum().item()) == 0:
        return np.empty((0, 3), dtype=np.float64)
    device = depth.device
    H, W = depth.shape
    v, u = torch.nonzero(keep, as_tuple=True)
    d = depth[v, u]
    K = b["K"].to(device)
    ud = (u.float() - K[0, 2]) / K[0, 0]
    vd = (v.float() - K[1, 2]) / K[1, 1]
    Xc = torch.stack([ud * d, vd * d, d], dim=1)
    w2c = b["w2c"].to(device)
    R = w2c[:3, :3]
    t = w2c[:3, 3]
    Xw = (Xc - t) @ R
    P_utm = Xw.detach().cpu().numpy().astype(np.float64) + SHIFT_UTM
    return P_utm


def summarize_floater_metrics(
    run_name: str,
    arm: str,
    replicate: str,
    state: dict[str, torch.Tensor],
    seed_tree: cKDTree | None,
    sample_n: int,
) -> dict[str, object]:
    with torch.no_grad():
        means = state["means"].detach().cpu().numpy().astype(np.float32)
        op = torch.sigmoid(state["opacities_raw"].detach().cpu().float()).numpy()
        scales = torch.exp(state["log_scales"].detach().cpu().float()).numpy()
    inplane_min = np.minimum(scales[:, 0], scales[:, 1]).clip(1e-8, None)
    inplane_max = np.maximum(scales[:, 0], scales[:, 1])
    inplane_ratio = inplane_max / inplane_min
    rng = np.random.default_rng(20260708)
    if seed_tree is not None and means.shape[0] > 0:
        idx = np.arange(means.shape[0])
        if means.shape[0] > sample_n:
            idx = rng.choice(idx, size=sample_n, replace=False)
        d, _ = seed_tree.query(means[idx], k=1, workers=-1)
        off_1m = float(np.mean(d > 1.0))
        off_2m = float(np.mean(d > 2.0))
        seed_dist_p50 = float(np.percentile(d, 50))
        seed_dist_p90 = float(np.percentile(d, 90))
    else:
        off_1m = off_2m = seed_dist_p50 = seed_dist_p90 = float("nan")
    return {
        "run_name": run_name,
        "arm": arm,
        "replicate": replicate,
        "n_gaussians": int(means.shape[0]),
        "opacity_p05": float(np.percentile(op, 5)),
        "opacity_p50": float(np.percentile(op, 50)),
        "opacity_p95": float(np.percentile(op, 95)),
        "opacity_below_prune005_frac": float(np.mean(op < CONFIG_CONSTANTS["prune_opa"])),
        "inplane_ratio_p50": float(np.percentile(inplane_ratio, 50)),
        "inplane_ratio_p95": float(np.percentile(inplane_ratio, 95)),
        "elongated_ratio_gt10_frac": float(np.mean(inplane_ratio > 10.0)),
        "elongated_ratio_gt20_frac": float(np.mean(inplane_ratio > 20.0)),
        "scale_inplane_p95_m": float(np.percentile(inplane_max, 95)),
        "seed_distance_p50_m": seed_dist_p50,
        "seed_distance_p90_m": seed_dist_p90,
        "off_seed_gt1m_proxy_frac": off_1m,
        "off_seed_gt2m_proxy_frac": off_2m,
    }


def extract_depth_supervision_coverage(ds: ColmapDataset, max_views: int) -> pd.DataFrame:
    rows = []
    n = len(ds) if max_views <= 0 else min(len(ds), max_views)
    for i in range(n):
        b = ds[i]
        if "semantic" not in b or "depth_mask" not in b:
            continue
        sem = b["semantic"].numpy()
        dmask = b["depth_mask"].numpy().astype(bool)
        roof = sem == 1
        if int(roof.sum()) == 0:
            continue
        rows.append(
            {
                "view_idx": i,
                "image_name": ds.frames[i].name,
                "roof_pixels": int(roof.sum()),
                "mvs_depth_valid_roof_pixels": int((roof & dmask).sum()),
                "mvs_depth_valid_roof_frac": float((roof & dmask).sum() / max(1, roof.sum())),
                "mvs_depth_valid_all_frac": float(dmask.mean()),
            }
        )
    return pd.DataFrame(rows)


def select_target_view_indices(ds: ColmapDataset, lowtex_path: Path, projection_path: Path) -> list[int]:
    name_to_idx = {fr.name: i for i, fr in enumerate(ds.frames)}
    names: list[str] = []
    if lowtex_path.exists():
        lowtex = pd.read_csv(lowtex_path)
        if {"building_id", "lowtex_v5_view"}.issubset(lowtex.columns):
            names.extend(
                lowtex.loc[lowtex["building_id"].isin(TARGET_CASES), "lowtex_v5_view"]
                .dropna()
                .astype(str)
                .tolist()
            )
    if projection_path.exists():
        projection = pd.read_csv(projection_path)
        if {"building_id", "view"}.issubset(projection.columns):
            names.extend(
                projection.loc[projection["building_id"].isin(TARGET_CASES), "view"]
                .dropna()
                .astype(str)
                .tolist()
            )
    idxs: list[int] = []
    seen: set[int] = set()
    for name in names:
        idx = name_to_idx.get(name)
        if idx is None or idx in seen:
            continue
        idxs.append(idx)
        seen.add(idx)
    return idxs


def coverage_from_npz(npz_path: Path, footprints: dict[str, Footprint], source_run: str) -> list[dict[str, object]]:
    z = np.load(npz_path)
    rows = []
    for key, cls_key, stage in [
        ("P_utm", "P_class", "tsdf_minobs_voxel_pre_sor"),
        ("P_utm_clean", "P_class_clean", "tsdf_minobs_voxel_post_sor"),
    ]:
        if key not in z.files:
            continue
        pts = z[key]
        if cls_key in z.files:
            cls = z[cls_key]
            pts = pts[cls == 1]
        cov = CoverageGrid(footprints)
        cov.add_points(pts)
        rows.extend(cov.rows(source_run, stage))
    return rows


def infer_cause_table(
    render_df: pd.DataFrame,
    cov_df: pd.DataFrame,
    floater_df: pd.DataFrame,
    depth_cov_df: pd.DataFrame,
    condition_df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    if not cov_df.empty:
        piv = cov_df.pivot_table(index=["source_run", "building_id"], columns="stage", values="coverage_frac", aggfunc="mean").reset_index()
        for col in ["render_depth_backproj_sample_pre_readout", "tsdf_minobs_voxel_pre_sor", "tsdf_minobs_voxel_post_sor"]:
            if col not in piv:
                piv[col] = np.nan
        piv["drop_render_to_minobs"] = piv["render_depth_backproj_sample_pre_readout"] - piv["tsdf_minobs_voxel_pre_sor"]
        piv["drop_minobs_to_sor"] = piv["tsdf_minobs_voxel_pre_sor"] - piv["tsdf_minobs_voxel_post_sor"]
        rows.append(
            {
                "failure_axis": "coverage_collapse",
                "candidate_cause": "readout_minobs_sor_discard",
                "evidence_metric": "mean(drop_render_to_minobs + drop_minobs_to_sor)",
                "value": float((piv["drop_render_to_minobs"].fillna(0) + piv["drop_minobs_to_sor"].fillna(0)).mean()),
                "observation": "positive means sampled render support exceeds retained TSDF/SOR footprint coverage",
            }
        )
        rows.append(
            {
                "failure_axis": "coverage_collapse",
                "candidate_cause": "render_depth_support_absent",
                "evidence_metric": "mean(render_depth_backproj_sample_pre_readout coverage)",
                "value": float(piv["render_depth_backproj_sample_pre_readout"].mean()),
                "observation": "low sampled pre-readout footprint coverage means the checkpoint render already supplies little roof support",
            }
        )
    if not depth_cov_df.empty:
        rows.append(
            {
                "failure_axis": "coverage_collapse",
                "candidate_cause": "mvs_depth_no_signal_texture_proxy",
                "evidence_metric": "median MVS valid fraction on semantic roof pixels",
                "value": float(depth_cov_df["mvs_depth_valid_roof_frac"].median()),
                "observation": "low roof valid-mask coverage means depth supervision was sparse on roof pixels",
            }
        )
    if not floater_df.empty:
        rows.append(
            {
                "failure_axis": "coverage_collapse_or_flattening",
                "candidate_cause": "floater_or_degenerate_gaussians",
                "evidence_metric": "mean off-seed>1m proxy + elongated>10 fraction",
                "value": float((floater_df["off_seed_gt1m_proxy_frac"].fillna(0) + floater_df["elongated_ratio_gt10_frac"].fillna(0)).mean()),
                "observation": "seed-distance proxy is not surface truth; it flags drift away from initialization support",
            }
        )
    if not render_df.empty:
        sh = render_df.pivot_table(index=["run_name", "view_idx"], columns="sh_degree", values=["psnr", "depth_mae_m"], aggfunc="mean")
        if (("psnr", 0) in sh.columns) and (("psnr", 3) in sh.columns):
            psnr_drop = (sh[("psnr", 3)] - sh[("psnr", 0)]).mean()
        else:
            psnr_drop = float("nan")
        if (("depth_mae_m", 0) in sh.columns) and (("depth_mae_m", 3) in sh.columns):
            depth_delta = (sh[("depth_mae_m", 3)] - sh[("depth_mae_m", 0)]).mean()
        else:
            depth_delta = float("nan")
        rows.append(
            {
                "failure_axis": "flattening_or_depth_error",
                "candidate_cause": "sh_view_dependent_absorption",
                "evidence_metric": "mean PSNR gain SH3-SH0; depth MAE delta SH3-SH0",
                "value": float(psnr_drop) if np.isfinite(psnr_drop) else float("nan"),
                "observation": f"depth_mae_delta_sh3_minus_sh0={depth_delta:.4f}; large PSNR gain with non-improved depth suggests appearance absorbs error",
            }
        )
        rows.append(
            {
                "failure_axis": "flattening_or_depth_error",
                "candidate_cause": "render_depth_itself",
                "evidence_metric": "mean SH3 depth MAE vs MVS valid pixels",
                "value": float(render_df[render_df["sh_degree"] == 3]["depth_mae_m"].mean()),
                "observation": "MVS depth is a baseline signal, not final geometric truth",
            }
        )
    if not condition_df.empty:
        lowtex = condition_df[condition_df["building_id"].isin(TARGET_CASES)]
        rows.append(
            {
                "failure_axis": "condition_strata",
                "candidate_cause": "texture_observation_interaction",
                "evidence_metric": "target case rows available",
                "value": float(len(lowtex)),
                "observation": "4907184/60098/8568391 retained as named strata cases",
            }
        )
    return pd.DataFrame(rows)


def write_csvs_to_snapshots(docs_csvs: list[Path], snapshot_dir: Path) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for p in docs_csvs:
        if p.exists():
            (snapshot_dir / p.name).write_bytes(p.read_bytes())


def md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 12, floatfmt: str = ".4f") -> str:
    if df.empty:
        return "_데이터 없음_"
    sub = df.loc[:, [c for c in cols if c in df.columns]].head(max_rows).copy()
    headers = list(sub.columns)
    if not headers:
        return "_데이터 없음_"

    def fmt(v: object) -> str:
        if pd.isna(v):
            return ""
        if isinstance(v, (float, np.floating)):
            return format(float(v), floatfmt)
        return str(v).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in sub.iterrows():
        lines.append("| " + " | ".join(fmt(row[h]) for h in headers) + " |")
    return "\n".join(lines)


def build_report(
    repo: Path,
    out_doc: Path,
    fig_dir: Path,
    out_run: Path,
    inventory: dict[str, object],
    render_df: pd.DataFrame,
    floater_df: pd.DataFrame,
    depth_cov_df: pd.DataFrame,
    readout_cov_df: pd.DataFrame,
    condition_df: pd.DataFrame,
    cause_df: pd.DataFrame,
) -> None:
    def p(path: str) -> str:
        return f"`{path}`"

    render_eval_df = render_df[render_df["view_role"] == "test_eval"].copy() if (not render_df.empty and "view_role" in render_df.columns) else render_df
    sh_summary = pd.DataFrame()
    if not render_df.empty:
        sh_summary = (
            render_eval_df.groupby(["run_name", "sh_degree"], as_index=False)
            .agg(psnr=("psnr", "mean"), ssim=("ssim", "mean"), depth_mae_m=("depth_mae_m", "mean"), rend_dist_mean=("rend_dist_mean", "mean"))
            .sort_values(["run_name", "sh_degree"])
        )
    readout_summary = pd.DataFrame()
    if not readout_cov_df.empty:
        readout_summary = (
            readout_cov_df.groupby(["source_run", "stage"], as_index=False)
            .agg(coverage_frac=("coverage_frac", "mean"))
            .sort_values(["source_run", "stage"])
        )
    target_condition = condition_df[condition_df["building_id"].isin(TARGET_CASES)].copy()

    cause_line = "데이터 부족"
    if not cause_df.empty:
        render_support = cause_df.loc[cause_df["candidate_cause"] == "render_depth_support_absent", "value"]
        readout_drop = cause_df.loc[cause_df["candidate_cause"] == "readout_minobs_sor_discard", "value"]
        depth_mae = cause_df.loc[cause_df["candidate_cause"] == "render_depth_itself", "value"]
        parts = []
        if len(render_support) and np.isfinite(render_support.iloc[0]):
            parts.append(f"sample render footprint coverage mean={render_support.iloc[0]:.3f}")
        if len(readout_drop) and np.isfinite(readout_drop.iloc[0]):
            parts.append(f"render->TSDF/SOR drop mean={readout_drop.iloc[0]:.3f}")
        if len(depth_mae) and np.isfinite(depth_mae.iloc[0]):
            parts.append(f"SH3 depth MAE vs MVS={depth_mae.iloc[0]:.3f} m")
        cause_line = "; ".join(parts) if parts else "프록시 수치 산출됨"

    routing = []
    if not cause_df.empty:
        vals = {r["candidate_cause"]: r["value"] for _, r in cause_df.iterrows()}
        if vals.get("render_depth_itself", 0) and vals.get("render_depth_itself", 0) > 2.0:
            routing.append("depth 감독 강화 0.03->0.5(CityGaussianV2식) 후보")
        if vals.get("readout_minobs_sor_discard", 0) and vals.get("readout_minobs_sor_discard", 0) > 0.05:
            routing.append("readout minobs/SOR 완화 후보")
        if vals.get("floater_or_degenerate_gaussians", 0) and vals.get("floater_or_degenerate_gaussians", 0) > 0.15:
            routing.append("floater/elongation 제어 및 distortion 복원(scene-scale) 후보")
        if vals.get("sh_view_dependent_absorption", 0) and vals.get("sh_view_dependent_absorption", 0) > 0.5:
            routing.append("SH 제한 후보")
    if not routing:
        routing.append("③ ablation 후보는 원인 귀속표 수치와 함께 보류 관찰")

    text = f"""# W_E5_C001 렌더·플로터 점검

## 시작 전 확인

- 브랜치/HEAD: `{inventory['branch']}` / `{inventory['head']}`.
- C001 재고: checkpoint {inventory['n_ckpt']}개, 기존 RGB render {inventory['n_existing_renders']}개, MVS depth map {inventory['n_mvs_depth_maps']}개, semantic mask {inventory['n_semantic_masks']}개, readout NPZ {inventory['n_readout_npz']}개.
- D4 상수 재사용: `w_distort=0`, `prune_opa=0.005`, `seed_protect=true`, `sh_degree=3`, `w_depth=0.03`, `readout=minobs3/voxel0.05/alpha0.5/SOR`.
- 수행 범위: 체크포인트 추론 + 기존 산출 재측정. 학습 0, 정식 재점군화 0, 재조립 0, 판정 0.
- 좌표: footprint/readout coverage는 EPSG:25832, GS-local은 `local + [690953, 5336071, 604]`.

## 한계

- C001 18동·2씨드·체크포인트 추론만의 진단이다. "지금 왜 무너지나"의 관찰이며, "고치면 되나"는 ③ 재학습 ablation 대상이다.
- SH 낮춤과 readout 전 backprojection은 진단 프록시다. 원 readout 파이프라인과 동일한 전체뷰 TSDF가 아니라 test split 샘플 + target 대표 view 렌더에서 산출했다.
- LoD2 참조 depth map 파일은 재고에서 확인되지 않았다. B의 깊이 비교는 MVS/ACMP depth valid pixel 대비로 축소했다.
- 영상 텍스처는 기존 C001 video-layer 프록시를 사용했고, 가림은 정밀 분리하지 않았다.
- MVS/ACMP depth와 ACMP 성공은 목표 기준선·메커니즘 단서이며 정답은 아니다.

## 산출 파일

- 표: {p('docs/experiments/evaluation/e5_c001_render/tables/e5_c001_render_eval_metrics.csv')}, {p('docs/experiments/evaluation/e5_c001_render/tables/e5_c001_render_floater_metrics.csv')}, {p('docs/experiments/evaluation/e5_c001_render/tables/e5_c001_render_depth_supervision.csv')}, {p('docs/experiments/evaluation/e5_c001_render/tables/e5_c001_render_readout_coverage.csv')}, {p('docs/experiments/evaluation/e5_c001_render/tables/e5_c001_render_condition_strata.csv')}, {p('docs/experiments/evaluation/e5_c001_render/tables/e5_c001_render_cause_attribution.csv')}.
- 그림: {p(rel(repo, fig_dir))}/.
- run 기록: {p(rel(repo, out_run / 'versions.txt'))}.

## A. 렌더 품질

기존 TensorBoard final eval과 동일한 test split 앞 {inventory['max_render_views']}뷰를 재렌더했다. SSIM은 동일 뷰에서 deterministic subsampling으로 계산했다. readout 전 coverage 프록시에는 target 대표 view {inventory['n_target_extra_views']}개를 추가했다.

{md_table(sh_summary, ['run_name', 'sh_degree', 'psnr', 'ssim', 'depth_mae_m', 'rend_dist_mean'], 24)}

## B. 렌더 깊이 품질

MVS depth valid pixel에서 expected/median depth를 비교했다. LoD2 참조 depth map은 재고에 없어서 직접 비교하지 않았다.

{md_table(render_df[render_df['sh_degree'] == 3] if not render_df.empty else render_df, ['run_name', 'view_role', 'view_idx', 'image_name', 'psnr', 'ssim', 'depth_mae_m', 'depth_rmse_m', 'depth_pred_valid_frac_on_mvs', 'rend_dist_mean'], 24)}

## C. 플로터·퇴화 정량

off-surface는 정답 표면 거리가 아니라 arm별 seed point cloud에 대한 center-distance 프록시다.

{md_table(floater_df, ['run_name', 'n_gaussians', 'opacity_p50', 'opacity_below_prune005_frac', 'inplane_ratio_p95', 'elongated_ratio_gt10_frac', 'seed_distance_p90_m', 'off_seed_gt1m_proxy_frac'], 12)}

## D. depth 감독 커버리지

semantic roof pixel 중 COLMAP MVS depth mask가 유효한 비율이다.

{md_table(depth_cov_df.describe(percentiles=[0.1, 0.5, 0.9]).reset_index() if not depth_cov_df.empty else depth_cov_df, ['index', 'roof_pixels', 'mvs_depth_valid_roof_pixels', 'mvs_depth_valid_roof_frac', 'mvs_depth_valid_all_frac'], 12)}

## E. readout 귀속

`render_depth_backproj_sample_pre_readout`는 체크포인트 샘플 렌더에서 alpha>0.5·semantic roof 픽셀을 backprojection한 프록시다. `tsdf_minobs_voxel_pre_sor`와 `tsdf_minobs_voxel_post_sor`는 기존 readout NPZ에서 재측정했다.

{md_table(readout_summary, ['source_run', 'stage', 'coverage_frac'], 24)}

## F. SH 흡수

동일 checkpoint에서 SH degree 0/1/3을 비교했다. PSNR이 SH와 함께 오르지만 depth MAE가 같이 개선되지 않는 경우는 시점-의존 색이 geometry 오차를 흡수한 프록시로만 본다.

{md_table(sh_summary, ['run_name', 'sh_degree', 'psnr', 'ssim', 'depth_mae_m'], 24)}

## G. 조건 층화

대표 조건 3건을 기존 C001 GS 진단 지표와 이번 readout coverage 재측정에 붙였다.

{md_table(target_condition, ['building_id', 'texture_class', 'texture_sufficient_proxy', 'n_views_nadir', 'raw_dense_success', 'acmp_success', 'mechanism_bucket', 'gs_median_clean_coverage', 'gs_median_render_backproj_coverage'], 12)}

## 원인 귀속표

{md_table(cause_df, ['failure_axis', 'candidate_cause', 'evidence_metric', 'value', 'observation'], 12)}

판별 한 줄(판정 아님): 커버리지 붕괴는 {cause_line}로 관찰된다.

## ③ 라우팅 후보

{chr(10).join(f'- {x}' for x in routing)}

## 인용·근거

- `docs/experiments/joint-optimization/w_d4/reports/W_D4_손실config_감사.md`, `docs/W_D4config감사_분석·②연결_20260707.md`, `docs/W_문헌검증_GS기하_foundation·가중·평가_20260707.md`.
- 2DGS: arXiv 2403.17888 (<https://arxiv.org/abs/2403.17888>), depth distortion/normal consistency가 geometry regularization으로 제시됨.
- CityGaussianV2: arXiv 2411.00771 (<https://arxiv.org/abs/2411.00771>), large-scale reconstruction에서 depth regression과 geometry accuracy 이슈를 다룸.
- AlignGS: arXiv 2510.07839 (<https://arxiv.org/abs/2510.07839>), semantic priors를 geometry regularizer로 쓰는 sparse-view reconstruction 방향.

재확인: 학습 0 · 정식 재조립 0 · 판정 0.
"""
    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text(text, encoding="utf-8")


def make_figures(fig_dir: Path, render_df: pd.DataFrame, floater_df: pd.DataFrame, readout_cov_df: pd.DataFrame) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)

    if not floater_df.empty:
        fig, ax = plt.subplots(figsize=(9, 4.8))
        x = np.arange(len(floater_df))
        ax.bar(x - 0.18, floater_df["opacity_below_prune005_frac"], width=0.36, label="opacity < 0.005")
        ax.bar(x + 0.18, floater_df["elongated_ratio_gt10_frac"], width=0.36, label="in-plane ratio > 10")
        ax.set_xticks(x)
        ax.set_xticklabels(floater_df["run_name"], rotation=30, ha="right")
        ax.set_ylabel("fraction")
        ax.set_title("Floater / Degenerate Proxy")
        ax.legend()
        fig.tight_layout()
        fig.savefig(fig_dir / "floater_distribution.png", dpi=180)
        plt.close(fig)

    if not render_df.empty:
        sh3 = render_df[render_df["sh_degree"] == 3]
        fig, ax = plt.subplots(figsize=(9, 4.8))
        for run_name, g in sh3.groupby("run_name"):
            ax.scatter(g["depth_mae_m"], g["psnr"], label=run_name, s=36)
        ax.set_xlabel("Depth MAE vs MVS (m)")
        ax.set_ylabel("RGB PSNR")
        ax.set_title("Render Depth vs MVS")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(fig_dir / "render_depth_vs_mvs.png", dpi=180)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 4.8))
        base = render_df[render_df["view_role"] == "test_eval"] if "view_role" in render_df.columns else render_df
        sh = base.groupby(["run_name", "sh_degree"], as_index=False).agg(psnr=("psnr", "mean"), depth_mae_m=("depth_mae_m", "mean"))
        for run_name, g in sh.groupby("run_name"):
            ax.plot(g["sh_degree"], g["psnr"], marker="o", label=f"{run_name} PSNR")
        ax.set_xlabel("SH degree")
        ax.set_ylabel("PSNR")
        ax.set_title("SH Comparison")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(fig_dir / "sh_comparison.png", dpi=180)
        plt.close(fig)

    if not readout_cov_df.empty:
        stage_order = ["render_depth_backproj_sample_pre_readout", "tsdf_minobs_voxel_pre_sor", "tsdf_minobs_voxel_post_sor"]
        piv = (
            readout_cov_df.groupby(["source_run", "stage"], as_index=False)
            .agg(coverage_frac=("coverage_frac", "mean"))
            .pivot(index="source_run", columns="stage", values="coverage_frac")
            .reindex(columns=stage_order)
        )
        fig, ax = plt.subplots(figsize=(10, 5))
        piv.plot(kind="bar", ax=ax)
        ax.set_ylabel("mean footprint coverage")
        ax.set_title("Readout Pre/Post Coverage")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(fig_dir / "readout_prepost_coverage.png", dpi=180)
        plt.close(fig)

        target = readout_cov_df[readout_cov_df["building_id"].isin(TARGET_CASES)]
        if not target.empty:
            piv2 = target.pivot_table(index="building_id", columns="stage", values="coverage_frac", aggfunc="median").reindex(columns=stage_order)
            fig, ax = plt.subplots(figsize=(8, 4.8))
            piv2.plot(kind="bar", ax=ax)
            ax.set_ylabel("median coverage")
            ax.set_title("Flattening / Coverage Location Cases")
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(fig_dir / "flattening_location_cases.png", dpi=180)
            plt.close(fig)


def write_versions(out_run: Path, inventory: dict[str, object], docs_csvs: list[Path], fig_dir: Path, doc_path: Path) -> None:
    out_run.mkdir(parents=True, exist_ok=True)
    lines = [
        "# W_E5_C001 render/floater audit versions",
        f"created_local={pd.Timestamp.now(tz='Asia/Seoul').isoformat()}",
        f"branch={inventory['branch']}",
        f"head={inventory['head']}",
        f"docker_image=jointbuildgs:dev",
        f"script=scripts/e5_c001/e5_c001_render_audit.py",
        f"data_root={inventory['data_root']}",
        f"runs_root={inventory['runs_root']}",
        f"readout_root={inventory['readout_root']}",
        f"max_render_views={inventory['max_render_views']}",
        f"render_views_total={inventory.get('n_render_views_total')}",
        f"target_extra_views={inventory.get('n_target_extra_views')}",
        "training=0",
        "formal_pointcloudification=0",
        "formal_reassembly=0",
        "verdict=0",
        "config_constants=" + json.dumps(CONFIG_CONSTANTS, ensure_ascii=False, sort_keys=True),
        "",
        "inputs:",
    ]
    for item in inventory.get("input_hashes", []):
        lines.append(f"- {item['path']} sha256={item['sha256']}")
    lines += ["", "outputs:"]
    for p in docs_csvs:
        lines.append(f"- {p}")
    lines.append(f"- {doc_path}")
    for p in sorted(fig_dir.glob("*.png")):
        lines.append(f"- {p}")
    (out_run / "versions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    os.chdir(repo)
    runs_root = repo / args.runs_root
    data_root = repo / args.data_root
    readout_root = repo / args.readout_root
    seed_root = repo / args.seed_root
    out_run = repo / args.out_run
    snapshot_dir = out_run / "snapshots"
    fig_dir = repo / args.fig_dir
    doc_path = repo / args.doc_path
    gsdiag_dir = repo / args.gsdiag_snapshot_dir

    train_fp = pd.read_csv(repo / args.train_fingerprints)
    readout_fp = pd.read_csv(repo / args.readout_fingerprints)
    video_df = pd.read_csv(gsdiag_dir / "e5_c001_gsdiag_video_layer.csv")
    pc_df = pd.read_csv(gsdiag_dir / "e5_c001_gsdiag_pointcloud_metrics.csv")

    building_ids = list(video_df["building_id"].dropna().astype(str))
    base = pc_df.drop_duplicates("building_id").set_index("building_id")
    grid_totals = base["grid_total_cells"].to_dict()
    areas = base["footprint_area_m2"].to_dict()
    footprints = load_footprints(repo / args.footprints, building_ids, grid_totals, areas)

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        print("[warn] CUDA unavailable; rendering on CPU will be slow.", file=sys.stderr)

    ds = ColmapDataset(data_root, downscale=1.0, load_depth=True, load_normal=False, load_semantic=True)
    test_idx = [i for i in range(len(ds)) if i % 10 == 9][: args.max_render_views]
    target_extra_idx = select_target_view_indices(ds, repo / args.lowtex_v5, repo / args.projection_zeta)
    render_idx = list(test_idx)
    for idx in target_extra_idx:
        if idx not in render_idx:
            render_idx.append(idx)
    view_roles = {idx: "test_eval" for idx in test_idx}
    for idx in render_idx:
        view_roles.setdefault(idx, "target_case_proxy")
    depth_cov_df = extract_depth_supervision_coverage(ds, args.max_depth_coverage_views)

    inventory = {
        "branch": run_text(["git", "branch", "--show-current"]),
        "head": run_text(["git", "rev-parse", "HEAD"]),
        "runs_root": rel(repo, runs_root),
        "data_root": rel(repo, data_root),
        "readout_root": rel(repo, readout_root),
        "n_ckpt": len(list(runs_root.glob("*/ckpt/final.pt"))),
        "n_existing_renders": len(list(runs_root.glob("*/renders/*_rgb.png"))),
        "n_mvs_depth_maps": len(list((data_root / "stereo" / "depth_maps").glob("*.bin"))),
        "n_semantic_masks": len(list((data_root / "semantic").glob("*.png"))),
        "n_readout_npz": len(list(readout_root.glob("*/tsdf_gssem.npz"))),
        "max_render_views": args.max_render_views,
        "n_render_views_total": len(render_idx),
        "n_target_extra_views": len([idx for idx in render_idx if view_roles[idx] == "target_case_proxy"]),
    }
    input_hashes = []
    for p in [
        repo / args.train_fingerprints,
        repo / args.readout_fingerprints,
        gsdiag_dir / "e5_c001_gsdiag_video_layer.csv",
        repo / args.lowtex_v5,
        repo / args.projection_zeta,
    ]:
        if p.exists():
            input_hashes.append({"path": rel(repo, p), "sha256": sha256_file(p)})
    inventory["input_hashes"] = input_hashes

    seed_trees: dict[str, cKDTree] = {}
    for arm in ["sparse", "dense", "acmp"]:
        seed_path = seed_root / f"seed_{arm}_C001_buf20.ply"
        if seed_path.exists():
            seed_trees[arm] = cKDTree(read_ply_xyz_ascii(seed_path))

    render_rows = []
    floater_rows = []
    coverage_rows = []
    event_rows = []

    for _, row in train_fp.iterrows():
        run_name = row["run_name"]
        arm = row["arm"]
        replicate = row["replicate"]
        run_dir = repo / str(row["ckpt"]).replace("/ckpt/final.pt", "")
        ckpt_path = repo / row["ckpt"]
        print(f"[run] {run_name}", flush=True)
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        state = ckpt["state_dict"]
        event = {"run_name": run_name, "arm": arm, "replicate": replicate}
        event.update(load_event_scalars(run_dir))
        event_rows.append(event)
        floater_rows.append(summarize_floater_metrics(run_name, arm, replicate, state, seed_trees.get(arm), args.max_offsurface_sample))
        model = make_model_from_state(state, device)
        backproj_cov = CoverageGrid(footprints)
        with torch.no_grad():
            for idx in render_idx:
                b = ds[idx]
                rgb_gt = b["rgb"].numpy()
                gt_depth = b["depth"].numpy()
                gt_mask = b["depth_mask"].numpy().astype(bool)
                w2c = b["w2c"].to(device)
                K = b["K"].to(device)
                H, W = b["height"], b["width"]
                sem_logits = None
                rendered_for_backproj = None
                for sh_degree in [0, 1, 3]:
                    out = render(model, w2c, K, W, H, sh_degree=sh_degree, render_mode="RGB+ED")
                    rgb = out["rgb"].clamp(0, 1).detach().cpu().numpy()
                    dep = out["depth"].detach().cpu().numpy()
                    alpha = out["alpha"].detach().cpu().numpy()
                    dm = depth_metrics(dep, gt_depth, gt_mask, alpha)
                    render_rows.append(
                        {
                            "run_name": run_name,
                            "arm": arm,
                            "replicate": replicate,
                            "view_idx": idx,
                            "view_role": view_roles[idx],
                            "image_name": ds.frames[idx].name,
                            "sh_degree": sh_degree,
                            "psnr": psnr_np(rgb, rgb_gt),
                            "ssim": ssim_np(rgb, rgb_gt),
                            **dm,
                            "alpha_gt05_frac": float(np.mean(alpha > 0.5)),
                            "rend_dist_mean": float(out["distort"][out["alpha"] > 0.5].mean().detach().cpu().item()) if int((out["alpha"] > 0.5).sum().item()) else float("nan"),
                        }
                    )
                    if sh_degree == 3:
                        rendered_for_backproj = out
                try:
                    sem_logits = render_semantic(model, w2c, K, W, H, sem_detach_geometry=True)
                except Exception as exc:
                    print(f"[warn] semantic render failed for {run_name} view={idx}: {exc}", file=sys.stderr)
                    sem_logits = None
                if rendered_for_backproj is not None:
                    pts = render_backproject_points(rendered_for_backproj, sem_logits, b)
                    backproj_cov.add_points(pts)
        coverage_rows.extend(backproj_cov.rows(run_name, "render_depth_backproj_sample_pre_readout"))

        # Release GPU memory between runs.
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    for _, row in readout_fp.iterrows():
        if args.readout_setting and str(row.get("setting", "")) != args.readout_setting:
            continue
        source_run = row["run_name"]
        npz_path = repo / row["tsdf_npz"]
        if npz_path.exists():
            coverage_rows.extend(coverage_from_npz(npz_path, footprints, source_run))

    render_df = pd.DataFrame(render_rows)
    event_df = pd.DataFrame(event_rows)
    if not event_df.empty:
        render_df = render_df.merge(event_df, on=["run_name", "arm", "replicate"], how="left")
    floater_df = pd.DataFrame(floater_rows)
    readout_cov_df = pd.DataFrame(coverage_rows)

    # Condition table: existing video layer + existing GS clean coverage + new coverage stages.
    gs_clean = pc_df[pc_df["source_run"].str.startswith("gs_", na=False)].groupby("building_id", as_index=False).agg(
        gs_median_clean_coverage=("coverage_frac", "median"),
        gs_min_clean_coverage=("coverage_frac", "min"),
        gs_max_clean_coverage=("coverage_frac", "max"),
    )
    render_cov = readout_cov_df[readout_cov_df["stage"] == "render_depth_backproj_sample_pre_readout"].groupby("building_id", as_index=False).agg(
        gs_median_render_backproj_coverage=("coverage_frac", "median"),
    )
    condition_df = video_df.merge(gs_clean, on="building_id", how="left").merge(render_cov, on="building_id", how="left")

    cause_df = infer_cause_table(render_df, readout_cov_df, floater_df, depth_cov_df, condition_df)

    csv_prefix = repo / args.docs_prefix
    docs_csvs = [
        csv_prefix.with_name(csv_prefix.name + "_eval_metrics.csv"),
        csv_prefix.with_name(csv_prefix.name + "_floater_metrics.csv"),
        csv_prefix.with_name(csv_prefix.name + "_depth_supervision.csv"),
        csv_prefix.with_name(csv_prefix.name + "_readout_coverage.csv"),
        csv_prefix.with_name(csv_prefix.name + "_condition_strata.csv"),
        csv_prefix.with_name(csv_prefix.name + "_cause_attribution.csv"),
    ]
    render_df.to_csv(docs_csvs[0], index=False)
    floater_df.to_csv(docs_csvs[1], index=False)
    depth_cov_df.to_csv(docs_csvs[2], index=False)
    readout_cov_df.to_csv(docs_csvs[3], index=False)
    condition_df.to_csv(docs_csvs[4], index=False)
    cause_df.to_csv(docs_csvs[5], index=False)
    write_csvs_to_snapshots(docs_csvs, snapshot_dir)
    make_figures(fig_dir, render_df, floater_df, readout_cov_df)
    build_report(repo, doc_path, fig_dir, out_run, inventory, render_df, floater_df, depth_cov_df, readout_cov_df, condition_df, cause_df)
    write_versions(out_run, inventory, docs_csvs, fig_dir, doc_path)

    print(f"[done] report={rel(repo, doc_path)} figs={rel(repo, fig_dir)} versions={rel(repo, out_run / 'versions.txt')}")


if __name__ == "__main__":
    main()
