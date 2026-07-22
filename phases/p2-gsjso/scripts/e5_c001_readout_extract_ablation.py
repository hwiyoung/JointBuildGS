#!/usr/bin/env python3
"""E5 C001 ③a readout-ablation extractor.

This is a task-scoped variant of ``tum_mob_tsdf_extract.py``.  It keeps the
checkpoint/render path unchanged, but exposes readout-only switches needed for
the C001 ablation: min-observation gate, voxel size, and SOR strength/off.

Frame: GS local + [690953, 5336071, 604] -> EPSG:25832.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, "/workspace/JointBuildGS")

from gsplat import rasterization_2dgs
from pilot_1wave_readout_lineage import (
    CONDITION_ARMS,
    FULL_STATE_CHECKPOINT_FORMAT,
    LINEAGE_SCHEMA,
    canonical_repo_path,
    sha256_file,
    validate_full_state_binding,
)
from src.stage2.colmap_io import read_cameras_bin, read_images_bin


REPO = "/workspace/JointBuildGS"
DENSE = f"{REPO}/phases/p0-audit/data/work/mvs/colmap_dense"
SHIFT = np.array([690953.0, 5336071.0, 604.0], dtype=np.float64)
C001_SHORT_IDS = [
    "108247349",
    "108247350",
    "108247351",
    "4907184",
    "4907185",
    "4907186",
    "4907188",
    "4907194",
    "4907195",
    "4907198",
    "4907199",
    "4907202",
    "4908168",
    "4908178",
    "4908179",
    "60098",
    "8568391",
    "8568392",
]
KC = 4
OFF = 1 << 20
MUL = 1 << 21
ROOF = 1
WALL = 2
_STEP_RE = re.compile(r"^step_(\d{6,})\.pt$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--downscale", type=float, default=1.0)
    ap.add_argument("--voxel", type=float, default=0.05)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--min-obs", type=int, default=3)
    ap.add_argument("--sor", choices=["on", "off"], default="on")
    ap.add_argument("--sor-std", type=float, default=2.0)
    ap.add_argument("--sor-neighbors", type=int, default=20)
    ap.add_argument("--buffer", type=float, default=15.0)
    ap.add_argument("--geojson", default=f"{REPO}/results/tum_transfer/analysis/footprints_aoi.geojson")
    ap.add_argument("--data-root", default=DENSE)
    ap.add_argument("--max-views", type=int, default=0)
    ap.add_argument("--sh-degree", type=int, default=3)
    ap.add_argument("--targets", nargs="*", default=None)
    ap.add_argument("--no-sem", action="store_true")
    ap.add_argument("--coverage-csv", default=None)
    ap.add_argument("--metrics-json", default=None)
    ap.add_argument("--provenance-json", default=None)
    ap.add_argument("--condition", choices=tuple(CONDITION_ARMS), default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--checkpoint-step", type=int, default=None)
    ap.add_argument("--full-state-manifest", default=None)
    ap.add_argument("--coverage-grid", type=float, default=0.5)
    return ap.parse_args()


def _canonical_condition_seed(checkpoint_path: Path) -> tuple[str | None, int | None]:
    """Infer only the canonical ``runs/<condition>/seed_<seed>/ckpt`` layout."""

    parts = checkpoint_path.resolve().parts
    if len(parts) < 4 or parts[-2] != "ckpt" or not parts[-3].startswith("seed_"):
        return None, None
    condition = parts[-4]
    try:
        seed = int(parts[-3].removeprefix("seed_"))
    except ValueError:
        return None, None
    if condition not in CONDITION_ARMS:
        return None, None
    return condition, seed


def _checkpoint_identity(
    checkpoint_path: Path,
    payload: Mapping[str, Any],
    *,
    condition: str | None,
    seed: int | None,
    checkpoint_step: int | None,
    full_state_manifest: str | None,
) -> tuple[Mapping[str, torch.Tensor], dict[str, Any]]:
    """Return a model state and immutable provenance for both checkpoint formats."""

    inferred_condition, inferred_seed = _canonical_condition_seed(checkpoint_path)
    condition_id = condition or inferred_condition
    resolved_seed = seed if seed is not None else inferred_seed
    if condition_id is None or resolved_seed is None:
        raise RuntimeError(
            "checkpoint condition/seed are not canonical; pass --condition and --seed"
        )
    if condition is not None and inferred_condition is not None and condition != inferred_condition:
        raise RuntimeError(
            f"checkpoint path/--condition mismatch: {inferred_condition} != {condition}"
        )
    if seed is not None and inferred_seed is not None and int(seed) != inferred_seed:
        raise RuntimeError(f"checkpoint path/--seed mismatch: {inferred_seed} != {seed}")

    checkpoint_path = checkpoint_path.resolve()
    checkpoint_sha = sha256_file(checkpoint_path)
    if payload.get("checkpoint_format") == FULL_STATE_CHECKPOINT_FORMAT:
        model = payload.get("model")
        if not isinstance(model, Mapping) or not isinstance(model.get("state_dict"), Mapping):
            raise RuntimeError("full-state checkpoint lacks model.state_dict")
        completed_steps = int(payload.get("completed_steps", -1))
        if checkpoint_step is not None and int(checkpoint_step) != completed_steps:
            raise RuntimeError(
                f"checkpoint payload/--checkpoint-step mismatch: "
                f"{completed_steps} != {checkpoint_step}"
            )
        manifest_path = (
            Path(full_state_manifest)
            if full_state_manifest
            else checkpoint_path.parent.parent / "full_state_manifest.json"
        )
        lineage = validate_full_state_binding(
            checkpoint_path=checkpoint_path,
            checkpoint_sha256=checkpoint_sha,
            completed_steps=completed_steps,
            condition_id=condition_id,
            seed=int(resolved_seed),
            manifest_path=manifest_path,
            checkpoint_binding_sha256=payload.get("binding_sha256"),
        )
        return model["state_dict"], lineage

    state_dict = payload.get("state_dict")
    if not isinstance(state_dict, Mapping):
        raise RuntimeError(
            "unsupported checkpoint: expected full-state model.state_dict or legacy state_dict"
        )
    match = _STEP_RE.fullmatch(checkpoint_path.name)
    payload_step = payload.get("it")
    completed_steps = (
        int(checkpoint_step)
        if checkpoint_step is not None
        else int(payload_step)
        if payload_step is not None
        else int(match.group(1))
        if match is not None
        else -1
    )
    if completed_steps < 0:
        raise RuntimeError("legacy checkpoint step is unknown; pass --checkpoint-step")
    if payload_step is not None and int(payload_step) != completed_steps:
        raise RuntimeError(
            f"legacy checkpoint payload/step mismatch: {payload_step} != {completed_steps}"
        )
    lineage = {
        "schema": LINEAGE_SCHEMA,
        "condition_id": condition_id,
        "seed": int(resolved_seed),
        "checkpoint": {
            "format": "legacy_state_dict",
            "path": canonical_repo_path(checkpoint_path),
            "sha256": checkpoint_sha,
            "completed_steps": completed_steps,
            "step_semantics": "legacy_iteration",
        },
        "full_state_manifest": None,
        "training_config": None,
        "verified_full_state": False,
        "eligible_20k_full_state": False,
    }
    return state_dict, lineage


def _write_provenance(
    args: argparse.Namespace,
    *,
    lineage: Mapping[str, Any],
    point_count: int,
) -> Path:
    output = Path(args.out).resolve()
    path = (
        Path(args.provenance_json).resolve()
        if args.provenance_json
        else Path(f"{output}.provenance.json")
    )
    payload = {
        "schema": "jointbuildgs.pilot_1wave.readout_extraction.v1",
        "state": "complete",
        "output_npz": {
            "path": str(output),
            "sha256": sha256_file(output),
            "point_count": int(point_count),
        },
        "readout_lineage": dict(lineage),
        "geometry_only": bool(args.no_sem),
        "crs": "EPSG:25832",
        "reference_inputs": {
            "groundsurface_xy_footprint": str(Path(args.geojson).resolve()),
            "lod2_z": False,
            "roofsurface": False,
            "semantic_class": False,
            "als": False,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def target_ids(short_ids: list[str] | None) -> list[str]:
    return [f"DEBY_LOD2_{sid}" for sid in (short_ids or C001_SHORT_IDS)]


def load_footprints(path: str, target_short_ids: list[str] | None) -> tuple[dict[str, np.ndarray], list[list[float]]]:
    ids = set(target_ids(target_short_ids))
    payload = json.load(open(path, encoding="utf-8"))
    rings: dict[str, np.ndarray] = {}
    boxes: list[list[float]] = []
    for feat in payload["features"]:
        bid = feat.get("properties", {}).get("building_id")
        if bid not in ids:
            continue
        geom = feat["geometry"]
        coords = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
        ring = np.asarray(coords, dtype=np.float64)[:, :2]
        rings[bid] = ring
        x0, y0 = ring[:, 0].min(), ring[:, 1].min()
        x1, y1 = ring[:, 0].max(), ring[:, 1].max()
        boxes.append([x0 - SHIFT[0], y0 - SHIFT[1], x1 - SHIFT[0], y1 - SHIFT[1]])
    missing = sorted(ids - set(rings))
    if missing:
        raise RuntimeError(f"missing target footprints: {missing}")
    return rings, boxes


def points_in_poly(points: np.ndarray, ring: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return np.zeros(0, dtype=bool)
    x = points[:, 0]
    y = points[:, 1]
    xv = ring[:, 0]
    yv = ring[:, 1]
    inside = np.zeros(len(points), dtype=bool)
    j = len(ring) - 1
    for i in range(len(ring)):
        cond = ((yv[i] > y) != (yv[j] > y)) & (x < (xv[j] - xv[i]) * (y - yv[i]) / ((yv[j] - yv[i]) + 1e-12) + xv[i])
        inside ^= cond
        j = i
    return inside


def footprint_grid(ring: np.ndarray, spacing: float) -> np.ndarray:
    minx, miny = ring.min(axis=0)
    maxx, maxy = ring.max(axis=0)
    xs = np.arange(minx + spacing / 2.0, maxx, spacing)
    ys = np.arange(miny + spacing / 2.0, maxy, spacing)
    if xs.size == 0 or ys.size == 0:
        c = ring.mean(axis=0, keepdims=True)
        return c
    xx, yy = np.meshgrid(xs, ys)
    pts = np.column_stack([xx.ravel(), yy.ravel()])
    mask = points_in_poly(pts, ring)
    if not np.any(mask):
        return ring.mean(axis=0, keepdims=True)
    return pts[mask]


def coverage_rows(points: np.ndarray, classes: np.ndarray | None, footprints: dict[str, np.ndarray], stage: str, spacing: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if classes is not None and len(classes) == len(points):
        mask = (classes == ROOF) | (classes == WALL)
        use = points[mask]
    else:
        use = points
    for bid, ring in footprints.items():
        grid = footprint_grid(ring, spacing)
        if len(grid) == 0:
            rows.append({"stage": stage, "building_id": bid, "occupied_cells": 0, "grid_total_cells": 0, "coverage_frac": ""})
            continue
        cell_xy = np.floor(grid / spacing).astype(np.int64)
        total = len({(int(a), int(b)) for a, b in cell_xy})
        if len(use) == 0:
            occupied = 0
        else:
            in_fp = points_in_poly(use[:, :2], ring)
            q = np.floor(use[in_fp, :2] / spacing).astype(np.int64)
            grid_set = {(int(a), int(b)) for a, b in cell_xy}
            occupied = len({(int(a), int(b)) for a, b in q if (int(a), int(b)) in grid_set})
        frac = min(1.0, occupied / total) if total else 0.0
        rows.append(
            {
                "stage": stage,
                "building_id": bid,
                "occupied_cells": occupied,
                "grid_total_cells": total,
                "coverage_frac": frac,
            }
        )
    return rows


def decode_keys(keys: torch.Tensor, voxel: float) -> np.ndarray:
    k = keys.detach().cpu().numpy().astype(np.int64, copy=True)
    iz = (k % MUL) - OFF
    k //= MUL
    iy = (k % MUL) - OFF
    ix = (k // MUL) - OFF
    local = (np.stack([ix, iy, iz], axis=1).astype(np.float64) + 0.5) * voxel
    return local + SHIFT


def write_csv(path: str | None, rows: list[dict[str, Any]]) -> None:
    if path is None:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    dev = "cuda"
    target_short_ids = args.targets if getattr(args, "targets", None) else C001_SHORT_IDS
    footprints, boxes = load_footprints(args.geojson, target_short_ids)
    print(f"[boxes] {len(boxes)} target footprint boxes")

    checkpoint_path = Path(args.ckpt).resolve()
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, Mapping):
        raise RuntimeError("checkpoint payload must be a mapping")
    sd, readout_lineage = _checkpoint_identity(
        checkpoint_path,
        ckpt,
        condition=args.condition,
        seed=args.seed,
        checkpoint_step=args.checkpoint_step,
        full_state_manifest=args.full_state_manifest,
    )
    del ckpt
    readout_lineage = {
        **readout_lineage,
        "geometry_only": bool(args.no_sem),
    }
    means = sd["means"].to(dev)
    quats = sd["quats"].to(dev)
    scales = torch.exp(sd["log_scales"]).to(dev)
    opac = torch.sigmoid(sd["opacities_raw"]).to(dev).ravel()
    colors = torch.cat([sd["sh0"], sd["shN"]], dim=1).to(dev)
    sem = sd.get("sem_logits")
    do_sem = (sem is not None) and (not args.no_sem)
    if do_sem:
        sem = sem.to(dev)
        sem = sem.unsqueeze(0) if sem.ndim == 2 else sem
        print(f"[sem] GS-semantic feature pass ON (K={sem.shape[-1]})")
    else:
        print("[sem] GS-semantic OFF")
    print(
        f"[model] N={means.shape[0]} ckpt={args.ckpt} "
        f"condition={readout_lineage['condition_id']} "
        f"seed={readout_lineage['seed']} "
        f"step={readout_lineage['checkpoint']['completed_steps']}"
    )

    data_root = Path(args.data_root)
    sparse_dir = data_root / "sparse"
    if (sparse_dir / "0" / "cameras.bin").exists():
        sparse_dir = sparse_dir / "0"
    cams = read_cameras_bin(sparse_dir / "cameras.bin")
    imgs = list(read_images_bin(sparse_dir / "images.bin").values())
    if args.max_views:
        imgs = imgs[: args.max_views]

    keylist: list[torch.Tensor] = []
    clslist: list[torch.Tensor] = []

    def add_keys(points: torch.Tensor, cls: torch.Tensor | None = None) -> None:
        q = torch.floor(points / args.voxel).to(torch.int64) + OFF
        k = (q[:, 0] * MUL + q[:, 1]) * MUL + q[:, 2]
        if cls is None:
            keylist.append(torch.unique(k).cpu())
            return
        uk_v, inv_v = torch.unique(k, return_inverse=True)
        hist = torch.zeros((uk_v.shape[0], KC), device=points.device)
        hist.index_add_(0, inv_v, torch.nn.functional.one_hot(cls, KC).float())
        keylist.append(uk_v.cpu())
        clslist.append(hist.argmax(1).to(torch.int64).cpu())

    n_surf = 0
    zlo, zhi = -120.0, 80.0
    for i, image in enumerate(imgs):
        cam = cams[image.camera_id]
        k0 = cam.K()
        w0, h0 = cam.width, cam.height
        scale = 1.0 / args.downscale
        width, height = int(round(w0 * scale)), int(round(h0 * scale))
        k_mat = k0.copy()
        k_mat[:2, :] *= scale
        kt = torch.tensor(k_mat, dtype=torch.float32, device=dev)
        uu, vv = np.meshgrid(np.arange(width), np.arange(height))
        uu = uu.ravel()
        vv = vv.ravel()
        ud = torch.tensor((uu - k_mat[0, 2]) / k_mat[0, 0], dtype=torch.float32, device=dev)
        vd = torch.tensor((vv - k_mat[1, 2]) / k_mat[1, 1], dtype=torch.float32, device=dev)
        r_mat = torch.tensor(image.R(), dtype=torch.float32, device=dev)
        t_vec = torch.tensor(image.tvec, dtype=torch.float32, device=dev)
        viewmat = torch.eye(4, device=dev)
        viewmat[:3, :3] = r_mat
        viewmat[:3, 3] = t_vec
        with torch.no_grad():
            out = rasterization_2dgs(
                means=means,
                quats=quats,
                scales=scales,
                opacities=opac,
                colors=colors,
                viewmats=viewmat.unsqueeze(0),
                Ks=kt.unsqueeze(0),
                width=width,
                height=height,
                near_plane=0.01,
                far_plane=1e10,
                render_mode="RGB+ED",
                depth_mode="expected",
                sh_degree=args.sh_degree,
            )
            cls_pix = None
            if do_sem:
                fout = rasterization_2dgs(
                    means=means,
                    quats=quats,
                    scales=scales,
                    opacities=opac,
                    colors=sem,
                    viewmats=viewmat.unsqueeze(0),
                    Ks=kt.unsqueeze(0),
                    width=width,
                    height=height,
                    near_plane=0.01,
                    far_plane=1e10,
                    render_mode="RGB",
                    sh_degree=None,
                )
                cls_pix = fout[0][0].reshape(-1, sem.shape[-1]).argmax(-1)
        alpha = out[1][0, ..., 0].reshape(-1)
        median_depth = out[5][0, ..., 0].reshape(-1)
        mask = (alpha > args.alpha) & (median_depth > 0) & (median_depth < 500)
        if mask.sum() == 0:
            continue
        depth = median_depth[mask]
        xc = ud[mask] * depth
        yc = vd[mask] * depth
        x_cam = torch.stack([xc, yc, depth], dim=1)
        x_world = (x_cam - t_vec) @ r_mat
        sel = (x_world[:, 2] >= zlo) & (x_world[:, 2] <= zhi)
        inbox = torch.zeros_like(sel)
        for bx in boxes:
            inbox |= (x_world[:, 0] >= bx[0]) & (x_world[:, 0] <= bx[2]) & (x_world[:, 1] >= bx[1]) & (x_world[:, 1] <= bx[3])
        keep = sel & inbox
        x_world = x_world[keep]
        if len(x_world):
            if do_sem and cls_pix is not None:
                add_keys(x_world, cls_pix[mask][keep])
            else:
                add_keys(x_world)
            n_surf += len(x_world)
        if (i + 1) % 200 == 0:
            print(f"  view {i + 1}/{len(imgs)}", flush=True)

    if not keylist:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        empty = np.empty((0, 3), dtype=np.float64)
        np.savez(
            args.out,
            P_utm=empty,
            P_utm_clean=empty,
            voxel=args.voxel,
            downscale=args.downscale,
            readout_lineage_json=np.array(
                json.dumps(
                    readout_lineage,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            ),
        )
        write_csv(args.coverage_csv, [])
        provenance_path = _write_provenance(
            args, lineage=readout_lineage, point_count=0
        )
        if args.metrics_json:
            Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.metrics_json).write_text(
                json.dumps(
                    {
                        "surf_backproj": 0,
                        "fused_all": 0,
                        "readout_lineage": readout_lineage,
                        "provenance_json": str(provenance_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
        print(f"[done] no points -> {args.out} provenance={provenance_path}")
        return

    all_keys = torch.cat(keylist)
    if do_sem:
        all_classes = torch.cat(clslist)
        uk_all, inv_all = torch.unique(all_keys, return_inverse=True)
        counts = torch.bincount(inv_all, minlength=uk_all.shape[0])
        hist = torch.zeros((uk_all.shape[0], KC))
        hist.index_add_(0, inv_all, torch.nn.functional.one_hot(all_classes, KC).float())
        classes_all = hist.argmax(1)
        keep = counts >= args.min_obs
        uk = uk_all[keep]
        classes = classes_all[keep]
    else:
        uk_all, counts = torch.unique(all_keys, return_counts=True)
        classes_all = None
        keep = counts >= args.min_obs
        uk = uk_all[keep]
        classes = None
    print(f"[consensus] min_obs={args.min_obs}: kept {len(uk)}/{len(uk_all)} voxels")

    p_all = decode_keys(uk_all, args.voxel)
    p_utm = decode_keys(uk, args.voxel)
    p_class_all = classes_all.numpy().astype(np.int32) if classes_all is not None else None
    p_class = classes.numpy().astype(np.int32) if classes is not None else None
    p_utm_clean = p_utm
    p_class_clean = p_class
    sor_status = "off"
    if args.sor == "on":
        try:
            import open3d as o3d

            pc = o3d.geometry.PointCloud()
            pc.points = o3d.utility.Vector3dVector(p_utm)
            pc2, ind = pc.remove_statistical_outlier(nb_neighbors=args.sor_neighbors, std_ratio=args.sor_std)
            p_utm_clean = np.asarray(pc2.points)
            if p_class is not None:
                p_class_clean = p_class[np.asarray(ind, dtype=np.int64)]
            sor_status = "on"
            print(f"[sor] std={args.sor_std} kept {len(p_utm_clean)}/{len(p_utm)}")
        except Exception as exc:  # noqa: BLE001 - preserve extraction even if Open3D fails.
            print("[sor] skipped:", repr(exc))
            sor_status = f"error:{exc!r}"
    else:
        print("[sor] off")

    coverage: list[dict[str, Any]] = []
    coverage.extend(coverage_rows(p_all, p_class_all, footprints, "voxel_all_pre_minobs", args.coverage_grid))
    coverage.extend(coverage_rows(p_utm, p_class, footprints, "minobs_post_gate_pre_sor", args.coverage_grid))
    coverage.extend(coverage_rows(p_utm_clean, p_class_clean, footprints, "sor_post_clean", args.coverage_grid))
    write_csv(args.coverage_csv, coverage)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    save = {
        "P_utm": p_utm,
        "P_utm_clean": p_utm_clean,
        "voxel": args.voxel,
        "downscale": args.downscale,
        "min_obs": args.min_obs,
        "alpha": args.alpha,
        "sor": np.array(args.sor),
        "sor_std": args.sor_std,
        "sor_neighbors": args.sor_neighbors,
        "readout_lineage_json": np.array(
            json.dumps(
                readout_lineage,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        ),
    }
    if p_class is not None:
        save.update(
            {
                "P_class": p_class,
                "P_class_clean": p_class_clean,
                "class_names": np.array(["BG", "Roof", "Wall", "Terrain"]),
            }
        )
        uniq, cnt = np.unique(p_class_clean, return_counts=True)
        names = ["BG", "Roof", "Wall", "Terrain"]
        print("[sem] fused class dist:", {names[int(a)]: int(b) for a, b in zip(uniq, cnt)})
    np.savez(args.out, **save)

    metrics = {
        "surf_backproj": int(n_surf),
        "fused_all": int(len(uk_all)),
        "minobs_kept": int(len(p_utm)),
        "sor_kept": int(len(p_utm_clean)),
        "minobs": int(args.min_obs),
        "voxel": float(args.voxel),
        "alpha": float(args.alpha),
        "sor": args.sor,
        "sor_status": sor_status,
        "sor_std": float(args.sor_std),
        "sor_neighbors": int(args.sor_neighbors),
    }
    provenance_path = _write_provenance(
        args, lineage=readout_lineage, point_count=len(p_utm_clean)
    )
    metrics["readout_lineage"] = readout_lineage
    metrics["provenance_json"] = str(provenance_path)
    if args.metrics_json:
        Path(args.metrics_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.metrics_json).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[done] surf_backproj={n_surf} fused={len(p_utm)} "
        f"clean={len(p_utm_clean)} -> {args.out} provenance={provenance_path}"
    )


if __name__ == "__main__":
    main()
