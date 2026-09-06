"""Run isolated, conditional P2 reconstruction comparisons in Docker."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

import cv2
import numpy as np
import torch
from scipy.spatial import cKDTree

from src.phd.p2_ab_v1.reconstruction import (
    SurfaceGaussians, View, appearance_metrics, estimate_frames, extract_surface,
    optimize, render_view, representative_rows, surface_guard, validate_handoff,
)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def load_views(path, xyz, config):
    data = json.loads(Path(path).read_text())
    rows = data["views"] if isinstance(data, dict) else data
    result = []
    provenance = []
    for row in rows:
        if row["role"] not in {"train", "eval", "reconstruction_train", "appearance_eval"}:
            continue
        role = "train" if row["role"] in {"train", "reconstruction_train"} else "eval"
        path = Path(row.get("path", row.get("image_path", "")))
        if not path.is_file():
            raise ValueError(f"Missing input image {path}")
        if sha(path) != row["sha256"]:
            raise ValueError(f"Image hash mismatch {path}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Cannot read image {path}")
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        K = np.asarray(row["K"], dtype=np.float64)
        R, t = np.asarray(row["R"]), np.asarray(row["t"])
        camera = xyz @ R.T + t
        projection = camera @ K.T
        uv = projection[:, :2] / projection[:, 2:]
        inside = (camera[:, 2] > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < image.shape[1])
        inside &= (uv[:, 1] >= 0) & (uv[:, 1] < image.shape[0])
        if inside.sum() < 10:
            provenance.append({"image_id": row["image_id"], "excluded": "fewer_than_10_projected_seeds"})
            continue
        lo = np.floor(uv[inside].min(0) - 12).astype(int)
        hi = np.ceil(uv[inside].max(0) + 13).astype(int)
        x0, y0 = max(0, lo[0]), max(0, lo[1])
        x1, y1 = min(image.shape[1], hi[0]), min(image.shape[0], hi[1])
        crop = image[y0:y1, x0:x1]
        factor = min(1.0, config["maximum_crop_dimension_px"] / max(crop.shape[:2]))
        width, height = max(16, int(round(crop.shape[1] * factor))), max(16, int(round(crop.shape[0] * factor)))
        crop = cv2.resize(crop, (width, height), interpolation=cv2.INTER_AREA)
        K[0, 2] -= x0
        K[1, 2] -= y0
        K[0] *= width / (x1 - x0)
        K[1] *= height / (y1 - y0)
        V = np.eye(4, dtype=np.float32)
        V[:3, :3], V[:3, 3] = R, t
        detail = {"image_id": row["image_id"], "role": role, "path": str(path),
                  "sha256": row["sha256"], "crop_xyxy": [int(x0), int(y0), int(x1), int(y1)],
                  "width": width, "height": height, "K": K.tolist(), "viewmat": V.tolist()}
        result.append(View(int(row["image_id"]), role,
                           torch.tensor(crop.astype(np.float32) / 255., device="cuda"),
                           torch.tensor(K, dtype=torch.float32, device="cuda"),
                           torch.tensor(V, dtype=torch.float32, device="cuda"), width, height, detail))
        provenance.append(detail)
    if not any(v.role == "train" for v in result) or not any(v.role == "eval" for v in result):
        raise ValueError("Separate training and evaluation views are required")
    return result, provenance


def texture_colors(xyz, views):
    samples = []
    for view in views:
        K = view.K.cpu().numpy()
        V = view.viewmat.cpu().numpy()
        camera = xyz @ V[:3, :3].T + V[:3, 3]
        projection = camera @ K.T
        uv = projection[:, :2] / projection[:, 2:]
        valid = (camera[:, 2] > 0) & (uv[:, 0] >= .5) & (uv[:, 0] < view.width - .5)
        valid &= (uv[:, 1] >= .5) & (uv[:, 1] < view.height - .5)
        color = np.full((len(xyz), 3), np.nan, dtype=np.float32)
        sampled = cv2.remap(view.image.cpu().numpy(), (uv[:, 0] - .5).astype(np.float32).reshape(-1, 1),
                            (uv[:, 1] - .5).astype(np.float32).reshape(-1, 1), cv2.INTER_LINEAR).reshape(-1, 3)
        color[valid] = sampled[valid]
        samples.append(color)
    samples = np.stack(samples)
    colors = np.nanmedian(samples, axis=0)
    missing = ~np.isfinite(colors).all(1)
    colors[missing] = .5
    return colors, {"seed_count": len(xyz), "no_train_rgb_seeds": int(missing.sum()),
                    "visibility": "projection_only; no independent current occlusion certificate"}


def select_geometry(common, rows, config):
    payload = np.load(common / "units.npz", allow_pickle=False)
    units_data = json.loads((common / "units.json").read_text())
    units = units_data["units"] if isinstance(units_data, dict) else units_data
    lookup = {row["unit_id"]: int(row.get("unit_index", i)) for i, row in enumerate(units)}
    xyzs, normals, groups, structure_groups, native_rows, sources, receipts = [], [], [], [], [], [], []
    for row in rows:
        uid = row["unit_id"]
        action = row.get("conditional_action", row.get("action", "ABSTAIN"))
        row = dict(row, conditional_action=action)
        if action == "ABSTAIN":
            receipts.append({"unit_id": uid, "action": action, "seed_count": 0})
            continue
        source = "mvs" if action == "IMAGE" else "als" if action == "PRIOR" else None
        selected = row.get("selected_geometry")
        if not isinstance(selected, dict):
            raise ValueError(f"Exact tested candidate geometry is required for {uid}, action={action}")
        selected_path = Path(selected["path"])
        if not selected_path.is_absolute():
            selected_path = Path(config["handoff_path"]).parent / selected_path
        candidate = np.load(selected_path, allow_pickle=False)
        exact = candidate[selected.get("index_key", "candidate_index")] == selected["index"]
        p = candidate[selected.get("xyz_key", "xyz")][exact].copy()
        p[:, 2] += float(selected.get("offset_z_m", 0.))
        n = candidate[selected.get("normals_key", "normals")][exact].copy()
        n[n[:, 2] < 0] *= -1
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        rr = candidate[f"{source}_tile_rows"][exact] if source else np.full(len(p), -1, dtype=np.int64)
        # A candidate is a specific tested source patch, or exact paired fusion.
        patch = np.full(len(p), int(selected["index"]), dtype=np.int64)
        source_name = source or "fusion"
        if len(p) < 3:
            receipts.append({"unit_id": uid, "action": action, "seed_count": 0, "excluded": "too_few_source_points"})
            continue
        # This is a conditional source-to-surfel representation of that unit;
        # a point-level judgment is not elevated to certified area authority.
        source_groups = lookup[uid] * 1000000 + patch.astype(np.int64)
        keep = representative_rows(p, source_groups, config["representation_spacing_m"])
        if len(keep) > config["maximum_seeds_per_unit"]:
            keep = keep[np.linspace(0, len(keep) - 1, config["maximum_seeds_per_unit"], dtype=int)]
        p, n, rr, local_group = p[keep], n[keep], rr[keep], source_groups[keep]
        counts = {g: int(np.sum(local_group == g)) for g in np.unique(local_group)}
        framed = np.array([counts[g] >= 3 for g in local_group])
        excluded_tangent_support = int((~framed).sum())
        p, n, rr, local_group = p[framed], n[framed], rr[framed], local_group[framed]
        if len(p) < 3:
            receipts.append({"unit_id": uid, "action": action, "seed_count": 0,
                             "excluded": "insufficient_within_patch_tangent_support"})
            continue
        xyzs.append(p)
        normals.append(n)
        groups.append(np.full(len(p), lookup[uid], dtype=np.int64))
        structure_groups.append(local_group)
        native_rows.append(rr)
        sources.append(np.full(len(p), source_name))
        receipts.append({"unit_id": uid, "unit_index": lookup[uid], "action": action, "source": source_name,
                         "seed_count": len(p), "native_points_before_representation": int(len(source_groups)),
                         "excluded_tangent_support": excluded_tangent_support,
                         "native_membership_scope": "exact_A_selected_candidate_then_representation_thinning",
                         "support_scope": row.get("support_scope", "sampled_points"),
                         "representation_status": "conditional_finite_footprint_not_certified_surface",
                         "conditional_displacement_budget_m": row.get("conditional_displacement_budget_m"),
                         "strict_current_use_action": row.get("strict_current_use_action", "ABSTAIN")})
    if not xyzs:
        return None, receipts
    return {"xyz": np.concatenate(xyzs).astype(np.float32), "normal": np.concatenate(normals).astype(np.float32),
            "unit_index": np.concatenate(groups),
            "structure_group": np.concatenate(structure_groups),
            "native_tile_row": np.concatenate(native_rows), "source": np.concatenate(sources)}, receipts


def main(config_path):
    start = time.monotonic()
    config_path = Path(config_path)
    cfg = json.loads(config_path.read_text())
    output = Path(cfg["output_root"])
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError("Output must be an empty separately mounted new directory")
    write_json(output / "STARTED.json", {"utc": datetime.now(timezone.utc).isoformat(), "scientific_verdict": None})
    try:
        torch.manual_seed(0)
        torch.set_num_threads(2)
        cv2.setNumThreads(1)
        common = Path(cfg["common_root"])
        handoff_path = Path(cfg["handoff_path"])
        rows = [json.loads(line) for line in handoff_path.read_text().splitlines() if line]
        rows = [row for row in rows if row["method"] == cfg["decision_method"] and row["condition"] == cfg["condition"]]
        if not rows or len({row["unit_id"] for row in rows}) != len(rows):
            raise ValueError("Expected exactly one handoff per selected method-condition unit")
        input_hashes = {str(p): sha(p) for p in [config_path, handoff_path, common / "sample_manifest.json",
                                                common / "units.json", common / "units.npz", common / "views.json"]}
        candidate_paths = {Path(row["selected_geometry"]["path"]) for row in rows if isinstance(row.get("selected_geometry"), dict)}
        for path in candidate_paths:
            path = path if path.is_absolute() else handoff_path.parent / path
            input_hashes[str(path)] = sha(path)
        seeds, receipts = select_geometry(common, rows, cfg)
        write_json(output / "handoff_receipt.json", {"method": cfg["decision_method"], "condition": cfg["condition"],
                   "units": receipts, "strict_accepted_units": sum(validate_handoff(r, certified=True) for r in rows),
                   "scientific_verdict": None})
        if seeds is None:
            write_json(output / "result.json", {"status": "ABSTAIN_NO_GEOMETRY", "units": receipts,
                                               "input_hashes": input_hashes, "scientific_verdict": None})
            return
        np.savez_compressed(output / "initial_source_seeds.npz", **seeds)
        xyz, group = seeds["xyz"], seeds["unit_index"]
        _, scale = estimate_frames(xyz, seeds["structure_group"])
        normal = seeds["normal"]
        common_points = np.load(common / "units.npz", allow_pickle=False)
        crop_geometry = np.concatenate((common_points["mvs_xyz"], common_points["als_xyz"]))
        views, provenance = load_views(common / "views.json", crop_geometry, cfg)
        train, evaluate = [v for v in views if v.role == "train"], [v for v in views if v.role == "eval"]
        colors, texture_status = texture_colors(xyz, train)
        write_json(output / "views.json", {"views": provenance, "texture_initialization": texture_status})
        summary = []
        for arm in cfg["arms"]:
            arm_start = time.monotonic()
            destination = output / arm
            destination.mkdir()
            model = SurfaceGaussians(xyz, normal, scale, colors, seeds["structure_group"], displacement_axis="scene_z")
            with torch.no_grad():
                initial = {v.image_id: {k: val.detach().clone() for k, val in render_view(model, v).items()
                                       if isinstance(val, torch.Tensor)} for v in evaluate}
            # Unvalidated budgets are never promoted from point evidence. The
            # fixture budget, if supplied, is a declared conditional solver test.
            supplied_budgets = [r.get("conditional_displacement_budget_m") for r in receipts if r.get("seed_count", 0) > 0]
            budget = min(supplied_budgets) if supplied_budgets and all(b is not None for b in supplied_budgets) else None
            if cfg.get("conditional_solver_fixture_depth_budget_m") is not None:
                raise ValueError("Solver fixture budgets must use the separate fixture driver")
            initial_surfaces = []
            for view in evaluate:
                before = initial[view.image_id]
                initial_surfaces.append(extract_surface(before, view, xyz, group))
                image = (before["rgb"].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
                cv2.imwrite(str(destination / f"initial_rgb_{view.image_id}.png"), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            np.savez_compressed(destination / "initial_extracted_surface.npz", **{
                key: np.concatenate([surface[key] for surface in initial_surfaces]) for key in initial_surfaces[0]})
            fitted = optimize(model, train, arm=arm, steps=cfg["steps"], warmup=cfg["warmup_steps"],
                              guard_depth_m=budget, lr_color=cfg["lr_color"], lr_geometry=cfg["lr_geometry"],
                              prior_weight=cfg["prior_weight"], progress=lambda r: print(arm, r, flush=True))
            torch.save(model.state_dict(), destination / "gaussians.pt")
            surfaces, metrics, guards = [], [], []
            with torch.no_grad():
                for view in evaluate:
                    current = render_view(model, view)
                    surfaces.append(extract_surface(current, view, xyz, group))
                    metrics.append(appearance_metrics(initial[view.image_id], current, view))
                    guards.append({"image_id": view.image_id, **surface_guard(initial[view.image_id], current,
                                   max_depth_m=budget or 0.)})
                    np.savez_compressed(destination / f"render_{view.image_id}.npz",
                        rgb=current["rgb"].cpu().numpy(), depth=current["depth"].cpu().numpy(),
                        alpha=current["alpha"].cpu().numpy(), normal=current["normal_render"].cpu().numpy())
                    for name, value in [("rgb", current["rgb"]), ("target", view.image)]:
                        image = (value.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
                        cv2.imwrite(str(destination / f"{name}_{view.image_id}.png"), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            combined = {key: np.concatenate([surface[key] for surface in surfaces]) for key in surfaces[0]}
            np.savez_compressed(destination / "extracted_surface.npz", **combined)
            np.savez_compressed(destination / "centers.npz", xyz=model.means.detach().cpu().numpy(),
                                unit_index=group, base_xyz=xyz, normal=normal)
            row = {"arm": arm, "decision_method": cfg["decision_method"], "condition": cfg["condition"],
                   "scope": "conditional_measured_handoff_representation_development",
                   "conditional_handoff_depth_budget_m": budget, "fixture_depth_budget_m": None,
                   "displacement_component": "SCENE_LOCAL_Z; coordinate component, not gravity",
                   "surface_points": len(combined["xyz"]),
                   "gaussians": len(xyz), "train_views": len(train), "eval_views": len(evaluate),
                   "appearance": metrics, "evaluation_surface_guard": guards, **fitted,
                   "runtime_seconds": time.monotonic() - arm_start, "scientific_verdict": None}
            write_json(destination / "metrics.json", row)
            summary.append(row)
            del model
            torch.cuda.empty_cache()
        write_json(output / "result.json", {"status": "CONDITIONAL_DEVELOPMENT_COMPLETE", "arms": summary,
                   "input_hashes": input_hashes, "units": receipts, "configuration": cfg,
                   "source_git_head": os.environ.get("JBGS_SOURCE_GIT_HEAD"),
                   "container_image_id": os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   "torch": torch.__version__, "gpu": torch.cuda.get_device_name(),
                   "runtime_seconds": time.monotonic() - start, "scientific_verdict": None})
    except Exception:
        write_json(output / "FAILED.json", {"error": traceback.format_exc(), "scientific_verdict": None})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    main(parser.parse_args().config)
