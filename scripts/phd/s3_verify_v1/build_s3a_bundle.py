#!/usr/bin/env python3
"""S3a bundle writer — phd_s3_verify_s3a_v1 (stage 3a "render-only").

ZERO optimization steps: the S2 state (bundle-only input, render_state.py) is
rendered against sealed-base photos with gsplat, and ONE backward pass records
per-variable-group gradient norms (delta / planes / colors) as wiring evidence
— no parameter is updated. δ is wired as a render factor and held at 0;
alpha = |Δo| ∈ {0,1} is derived (no free alpha); color is constant neutral
gray; no densification/pruning.

Adds to runs/<name>/: s3_views.json, s3_steps.jsonl (step 0 row),
s3_tiles/<view_id>/{photo,render,residual}.png, s3_face_residual.json,
manifest stage -> s1+s2+s3a.

Usage (container):
  bash scripts/p2/arrgs_v1/run_host.sh <gpu> \
      scripts/phd/s3_verify_v1/build_s3a_bundle.py [run ...]   # default: all
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, REPO / "scripts/p2/arrgs_v1"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from render_state import (S3RenderState, anchor_terms, load_bundle_state,  # noqa: E402
                          real_views, synth_views)

CFG = json.load(open(REPO / "configs/phd/s3_verify_v1/s1_bundle_v1.json"))
S3 = CFG["s3"]
S3_SCHEMA = "phd_s3_verify_s3a_v1"


def render_views(state, views, with_grad):
    """Per-view render (fresh assembly graph per view); backward accumulates
    photo/V into the leaves when with_grad. Returns per-view CPU results."""
    from arrgs_train import render_gaussians
    viewmats, Ks = views["viewmats"], views["Ks"]
    W, H, bg = views["W"], views["H"], views["bg"]
    targets = views["targets"]
    mask_t = torch.tensor(views["masks"], device=targets.device)
    V = viewmats.shape[0]
    out_rows = []
    for ci in range(V):
        with torch.enable_grad() if with_grad else torch.no_grad():
            means, quats, scales, alphas, colors = state.gaussians()
            rgb, dep, ralpha = render_gaussians(
                means, quats, scales, alphas, colors,
                viewmats[ci:ci + 1], Ks[ci:ci + 1], W, H, bg, with_depth=True)
            rgb, dep, ralpha = rgb[0], dep[0], ralpha[0]
            m = mask_t[ci]
            photo = (rgb - targets[ci]).abs()[m].mean() if m.any() else rgb.sum() * 0
            if with_grad:
                (photo / V).backward()
        with torch.no_grad():
            mse = float(((rgb - targets[ci])[m] ** 2).mean()) if m.any() else None
            out_rows.append({
                "photo_l1": float(photo),
                "psnr": (float(-10 * np.log10(mse + 1e-10))
                         if mse is not None else None),
                "render": rgb.detach().clamp(0, 1).cpu().numpy(),
                "target": targets[ci].clamp(0, 1).cpu().numpy(),
                "depth": dep.detach().cpu().numpy(),
                "ralpha": ralpha.detach().cpu().numpy(),
                "mask": views["masks"][ci],
            })
    return out_rows


def write_tiles(out_dir, view_id, row, tile_max_px, residual_vmax):
    from PIL import Image
    d = out_dir / "s3_tiles" / view_id
    d.mkdir(parents=True, exist_ok=True)
    H, W = row["target"].shape[:2]
    sc = min(1.0, tile_max_px / max(W, H))
    size = (int(round(W * sc)), int(round(H * sc)))
    res = np.abs(row["target"] - row["render"]).mean(axis=-1)
    for name, arr, mode in (
            ("photo", (row["target"] * 255).astype(np.uint8), "RGB"),
            ("render", (row["render"] * 255).astype(np.uint8), "RGB"),
            ("residual", (np.clip(res / residual_vmax, 0, 1) * 255)
             .astype(np.uint8), "L")):
        Image.fromarray(arr, mode).resize(size, Image.LANCZOS).save(
            d / f"{name}.png")
    return res


def face_residuals(st, state, views, rows, residuals, fr_cfg):
    """Seed-projection approximation: per view, project every seed mu into the
    image, sample |photo-render| (RGB mean) at the nearest pixel inside the
    footprint mask, keep seeds passing the rendered-depth visibility gate,
    and average per face. No exact polygon rasterization, no exact occlusion."""
    with torch.no_grad():
        mu = state.gaussians()[0].detach().cpu().numpy().astype(np.float64)
    seed_face = st["seed_face"]
    viewmats = views["viewmats"].cpu().numpy()
    Ks = views["Ks"].cpu().numpy()
    W, H = views["W"], views["H"]
    tol = float(fr_cfg["visibility_depth_tol_m"])
    a_bg = float(fr_cfg["alpha_visible_below"])
    f_sum = np.zeros(len(st["face_ids"]))
    f_cnt = np.zeros(len(st["face_ids"]), dtype=np.int64)
    for ci, row in enumerate(rows):
        R, t = viewmats[ci][:3, :3], viewmats[ci][:3, 3]
        Xc = mu @ R.T + t
        z = Xc[:, 2]
        ok = z > 0.1
        uvw = Xc[ok] @ Ks[ci].T
        px = np.round(uvw[:, 0] / uvw[:, 2] - 0.5).astype(np.int64)
        py = np.round(uvw[:, 1] / uvw[:, 2] - 0.5).astype(np.int64)
        inside = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        idx = np.nonzero(ok)[0][inside]
        px, py = px[inside], py[inside]
        keep = row["mask"][py, px]
        vis = (row["ralpha"][py, px] < a_bg) | \
              (z[idx] <= row["depth"][py, px] + tol)
        sel = keep & vis
        np.add.at(f_sum, seed_face[idx[sel]], residuals[ci][py[sel], px[sel]])
        np.add.at(f_cnt, seed_face[idx[sel]], 1)
    per_face = {}
    for fi, fid in enumerate(st["face_ids"]):
        per_face[fid] = (round(float(f_sum[fi] / f_cnt[fi]), 4)
                         if f_cnt[fi] else None)
    return per_face, int((f_cnt > 0).sum())


def build_s3a(name, out_root):
    t0 = time.time()
    out_dir = Path(out_root) / "runs" / name
    manifest = json.load(open(out_dir / "manifest.json"))
    assert manifest["stage"].startswith("s1+s2"), manifest["stage"]

    st = load_bundle_state(out_dir)
    n_seeds = len(st["seed_uv"])
    assert n_seeds == manifest["counts"]["seeds"], (
        f"seed count {n_seeds} != manifest {manifest['counts']['seeds']}")

    state = S3RenderState(st, S3, device="cuda")
    with torch.no_grad():
        mu_dev = float(np.abs(state.gaussians()[0].cpu().numpy()
                              - st["seed_mu0"]).max())
        alpha_np = state.alpha_g.cpu().numpy()
    assert np.isin(alpha_np, (0.0, 1.0)).all(), "alpha not binary"
    assert mu_dev < 2e-3, f"mu reconstruction dev {mu_dev}"

    views = (synth_views(S3) if name == "SYNTH_GABLE"
             else real_views(name, S3))
    rows = render_views(state, views, with_grad=True)
    grad_norms = state.grad_norms()
    assert all(np.isfinite(v) for v in grad_norms.values()), grad_norms

    lam_a = float(S3["lambda_area"])
    terms = anchor_terms(st)
    photo = float(np.mean([r["photo_l1"] for r in rows]))
    area = lam_a * terms["area_gate_m2"]
    losses = {
        "photo": round(photo, 6),
        "anchor": round(terms["anchor_cell"], 6),
        "anchor_plane": round(terms["anchor_plane"], 6),
        "area": round(area, 6),
        "total": round(photo + terms["anchor_cell"] + terms["anchor_plane"]
                       + area, 6),
    }

    residuals, views_psnr, views_l1 = [], {}, {}
    for row, meta in zip(rows, views["rows"]):
        residuals.append(write_tiles(out_dir, meta["view_id"], row,
                                     int(S3["tile_max_px"]),
                                     float(S3["residual_vmax"])))
        views_psnr[meta["view_id"]] = (round(row["psnr"], 3)
                                       if row["psnr"] is not None else None)
        views_l1[meta["view_id"]] = round(row["photo_l1"], 6)
    per_face, n_sampled = face_residuals(st, state, views, rows, residuals,
                                         S3["face_residual"])

    json.dump({"selection_rule": views["selection_rule"],
               "views": views["rows"]},
              open(out_dir / "s3_views.json", "w"))
    step = {
        "step": 0, "stage": "3a",
        "losses": losses,
        "grad_norms": {k: float(f"{v:.6g}") for k, v in grad_norms.items()},
        "delta_hat": [0.0, 0.0, 0.0],
        "invariants": {"n_seeds": n_seeds, "alpha_binary": True,
                       "delta_frozen": True},
        "param_step_norm": 0.0,
        "views_psnr": views_psnr,
        "views_photo_l1": views_l1,
    }
    with open(out_dir / "s3_steps.jsonl", "w") as f:
        f.write(json.dumps(step) + "\n")
    json.dump({
        "method": ("seed-projection sampling — per view every S2 seed mu is "
                   "projected to its nearest pixel; sample = mean|photo-render|"
                   " over RGB inside the footprint mask; occlusion is "
                   "approximate: a seed counts as visible when rendered "
                   f"coverage < {S3['face_residual']['alpha_visible_below']} "
                   "(background) or seed camera-depth <= rendered expected "
                   f"depth + {S3['face_residual']['visibility_depth_tol_m']} m."
                   " No exact polygon rasterization; gate-0 faces are sampled "
                   "through the same rule (null = never visible/sampled)"),
        "n_views": len(rows), "faces_sampled": n_sampled,
        "per_face": per_face},
        open(out_dir / "s3_face_residual.json", "w"))

    manifest["stage"] = "s1+s2+s3a"
    manifest["s3_schema"] = S3_SCHEMA
    manifest["s3_def"] = {
        "stage": "3a", "optimizer": "none", "renderer": "gsplat",
        "backward_passes": 1,
        "delta_wired": True, "delta_value": [0.0, 0.0, 0.0],
        "delta_sources": S3["delta_sources"],
        "delta_scope_planes": state.n_scope_planes,
        "color": "neutral-gray", "color_value": float(S3["color_gray"]),
        "alpha": "|o_a-o_b| in {0,1} from s2_faces.initial_real (no free alpha)",
        "n_views": len(rows),
        "bg_rgb": views["bg_rgb"],
        "bg_note": ("real: config bg_rgb (legacy 0.5 gray == neutral-gray "
                    "color suppressed silhouette gradients); synth: "
                    "target-consistent x0 bg"),
        "image": {"width": views["W"], "height": views["H"],
                  "scale": (float(S3["image_scale"])
                            if name != "SYNTH_GABLE" else 1.0)},
        "lambda_area": lam_a,
        "lambda_area_note": S3["lambda_area_note"],
        "planes_render": state.n_planes,
        "mu_recon_max_dev_m": round(mu_dev, 6),
        "view_selection": views["selection_rule"],
    }
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=1)

    tiles_ok = all((out_dir / "s3_tiles" / m["view_id"] / f"{k}.png").is_file()
                   for m in views["rows"]
                   for k in ("photo", "render", "residual"))
    assert tiles_ok, "missing tiles"
    psnr_vals = [v for v in views_psnr.values() if v is not None]
    print(f"[s3a] {name}: views {len(rows)} seeds {n_seeds} "
          f"planes {state.n_planes} (delta-scope {state.n_scope_planes}) | "
          f"photo {losses['photo']} anchor {losses['anchor']} "
          f"area {losses['area']} | grad {step['grad_norms']} | "
          f"psnr {min(psnr_vals):.2f}..{max(psnr_vals):.2f} | "
          f"faces sampled {n_sampled}/{len(st['face_ids'])} | "
          f"mu_dev {mu_dev:.2e} | {time.time()-t0:.0f}s", flush=True)
    return {"name": name, "views": len(rows), "losses": losses,
            "grad_norms": step["grad_norms"], "views_psnr": views_psnr}


def main():
    runs = sys.argv[1:] or CFG["runs"]
    out_root = Path(CFG["out_root"])
    for r in runs:
        build_s3a(r, out_root)


if __name__ == "__main__":
    main()
