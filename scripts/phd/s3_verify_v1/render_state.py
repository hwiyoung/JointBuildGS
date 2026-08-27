#!/usr/bin/env python3
"""S3 render state from the s1+s2 bundle (shared by stages 3a-3d).

The bundle (s1_planes + s2_cells/s2_faces/s2_seeds) is the ONLY input for the
gaussian state (verification-page data contract); cameras/photos come from the
sealed base (real: real_scene.load_real_scene unchanged with skip_images off;
synthetic: the x0 GT-gaussian-render path of arrgs_train.run()).

Render factors (methodology §2.1 r16 — every gaussian is a derived quantity):
  mu     = plane origin(P⁰⊕δ) + frozen S2 seed uv   (follows the plane)
  R      = plane pose [e1, e2, n]
  scale  = (size_m, size_m, EPS_Z)                   (S2 frozen constant)
  alpha  = |o_a − o_b| ∈ {0,1}                       (s2_faces.initial_real; no free alpha)
  color  = the only per-gaussian free variable       (3a: constant neutral gray)
δ is wired as a render factor from the start: d_eff = d⁰ + n⁰·δ on prior-source
planes, so positions are differentiable in δ even while δ is held at 0.
No densification/pruning ever (lifetime rule 1): the seed set is immutable.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, REPO / "scripts/p2/arrgs_v1"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from arrgs_model import _rotmat_to_quat, EPS_Z  # noqa: E402


def load_bundle_state(run_dir):
    """Bundle files -> numpy state: plane table (unique face (n,d)), faces, seeds."""
    run_dir = Path(run_dir)
    s1 = json.load(open(run_dir / "s1_planes.json"))
    faces = json.load(open(run_dir / "s2_faces.json"))["faces"]
    cells = json.load(open(run_dir / "s2_cells.json"))["cells"]
    seeds_doc = json.load(open(run_dir / "s2_seeds.json"))
    src_of = {p["plane_id"]: p["source"] for p in s1["planes"]}

    key2j, plane_n, plane_d, plane_sources, plane_s1 = {}, [], [], [], []
    face_plane = np.empty(len(faces), dtype=np.int64)
    face_alpha = np.empty(len(faces), dtype=np.float32)
    face_area = np.empty(len(faces), dtype=np.float64)
    fid2idx = {}
    for fi, f in enumerate(faces):
        key = (tuple(f["n"]), f["d"])
        j = key2j.get(key)
        if j is None:
            j = key2j[key] = len(plane_n)
            plane_n.append(f["n"])
            plane_d.append(f["d"])
            plane_sources.append(set())
            plane_s1.append(set())
        if f["domain"] is not None:
            plane_sources[j].add("domain")
        for q in f["s1_plane_ids"]:
            plane_sources[j].add(src_of[q])
            plane_s1[j].add(q)
        face_plane[fi] = j
        face_alpha[fi] = 1.0 if f["initial_real"] else 0.0
        face_area[fi] = f["area_m2"]
        fid2idx[f["face_id"]] = fi

    seeds = seeds_doc["seeds"]
    return {
        "faces": faces, "cells": cells,
        "grid": seeds_doc["grid"],
        "plane_n": np.asarray(plane_n, dtype=np.float64),
        "plane_d": np.asarray(plane_d, dtype=np.float64),
        "plane_sources": [sorted(s) for s in plane_sources],
        "plane_s1_ids": [sorted(s) for s in plane_s1],
        "face_plane": face_plane, "face_alpha": face_alpha,
        "face_area": face_area,
        "face_ids": [f["face_id"] for f in faces],
        "seed_uv": np.asarray([s["uv"] for s in seeds], dtype=np.float64),
        "seed_mu0": np.asarray([s["mu"] for s in seeds], dtype=np.float64),
        "seed_face": np.asarray([fid2idx[s["face_id"]] for s in seeds],
                                dtype=np.int64),
    }


class S3RenderState:
    """Torch leaves {plane_n_raw, plane_d, delta, colors} + frozen buffers.

    Only leaves receive gradients; a stage unfreezes a group by giving it an
    optimizer (3a gives none — one backward records wiring evidence only)."""

    def __init__(self, st, s3cfg, device="cuda"):
        self.device = device
        n0 = st["plane_n"] / np.linalg.norm(st["plane_n"], axis=1, keepdims=True)
        scope_srcs = set(s3cfg["delta_sources"])
        scope = np.asarray(
            [1.0 if (set(srcs) & scope_srcs) else 0.0
             for srcs in st["plane_sources"]], dtype=np.float32)
        t32 = lambda a, dt=torch.float32: torch.tensor(a, dtype=dt, device=device)
        # leaves (all frozen in 3a: no optimizer, gradients only recorded)
        self.plane_n_raw = t32(n0).requires_grad_(True)
        self.plane_d = t32(st["plane_d"]).requires_grad_(True)
        self.delta = torch.zeros(3, device=device, requires_grad=True)
        n_seed = len(st["seed_uv"])
        gray = float(s3cfg["color_gray"])
        self.colors = torch.full((n_seed, 3), gray, device=device,
                                 requires_grad=True)
        # frozen buffers
        ref = np.where(np.abs(n0[:, 0:1]) < 0.9,
                       np.tile([1.0, 0, 0], (len(n0), 1)),
                       np.tile([0.0, 1, 0], (len(n0), 1)))
        self.ref = t32(ref)
        self.delta_dir = t32(n0)              # δ shifts along n⁰ (§1.3 d_eff)
        self.scope = t32(scope)               # 1 = prior-source plane
        self.uv = t32(st["seed_uv"])
        seed_face = torch.tensor(st["seed_face"], dtype=torch.long, device=device)
        self.seed_face = seed_face
        self.g_plane = torch.tensor(st["face_plane"], dtype=torch.long,
                                    device=device)[seed_face]
        self.alpha_g = t32(st["face_alpha"])[seed_face]
        size_m = float(st["grid"]["size_m"])
        s2 = torch.full((n_seed, 2), size_m, device=device)
        self.scales = torch.cat([s2, torch.full((n_seed, 1), EPS_Z,
                                                device=device)], dim=-1)
        self.n_seeds = n_seed
        self.n_planes = len(n0)
        self.n_scope_planes = int(scope.sum())

    def gaussians(self):
        """(means, quats, scales, alphas, colors) — recomputed per call so a
        fresh graph exists for each backward chunk (leaves accumulate)."""
        n = F.normalize(self.plane_n_raw, dim=-1)
        e1 = F.normalize(self.ref - (self.ref * n).sum(-1, keepdim=True) * n,
                         dim=-1)
        e2 = torch.cross(n, e1, dim=-1)
        d_eff = self.plane_d + self.scope * (self.delta_dir @ self.delta)
        origin = n * d_eff[:, None]
        j = self.g_plane
        means = origin[j] + self.uv[:, :1] * e1[j] + self.uv[:, 1:2] * e2[j]
        quats = _rotmat_to_quat(torch.stack([e1, e2, n], dim=-1))[j]
        return means, quats, self.scales, self.alpha_g, self.colors

    def grad_norms(self):
        def nrm(*ts):
            s = sum(float((t.grad ** 2).sum()) for t in ts if t.grad is not None)
            return float(np.sqrt(s))
        return {"delta": nrm(self.delta),
                "planes": nrm(self.plane_n_raw, self.plane_d),
                "colors": nrm(self.colors)}


def state_checksums(state, keys=None):
    """sha256 over the raw bytes of every tensor EXCEPT the colors leaf —
    stages 3b-3d assert byte-identity of their frozen groups before/after
    training; `keys` restricts to a subset for cheap per-step checks."""
    tensors = {"plane_n_raw": state.plane_n_raw, "plane_d": state.plane_d,
               "delta": state.delta, "uv": state.uv,
               "seed_face": state.seed_face, "alpha_g": state.alpha_g,
               "scales": state.scales, "g_plane": state.g_plane,
               "scope": state.scope, "delta_dir": state.delta_dir,
               "ref": state.ref}
    if keys is not None:
        tensors = {k: tensors[k] for k in keys}
    return {k: hashlib.sha256(t.detach().cpu().numpy().tobytes()).hexdigest()
            for k, t in tensors.items()}


def photo_l1_backward(state, views):
    """Per-step training pass shared by 3b-3d: fresh assembly graph per view,
    masked photo L1, (photo/V).backward() accumulating into ALL leaves (the
    stage's optimizer decides which group actually moves). No CPU image
    copies — same loss math as build_s3a_bundle.render_views(with_grad)."""
    from arrgs_train import render_gaussians
    viewmats, Ks = views["viewmats"], views["Ks"]
    W, H, bg, targets = views["W"], views["H"], views["bg"], views["targets"]
    mask_t = views.get("masks_t")
    if mask_t is None:
        mask_t = torch.tensor(views["masks"], device=targets.device)
    V = viewmats.shape[0]
    vals = []
    for ci in range(V):
        means, quats, scales, alphas, colors = state.gaussians()
        rgb = render_gaussians(means, quats, scales, alphas, colors,
                               viewmats[ci:ci + 1], Ks[ci:ci + 1],
                               W, H, bg)[0]
        m = mask_t[ci]
        photo = ((rgb - targets[ci]).abs()[m].mean() if m.any()
                 else rgb.sum() * 0)
        (photo / V).backward()
        vals.append(float(photo))
    return float(np.mean(vals))


def color_stats(colors):
    """Color-differentiation timelapse metrics (3b+ checkpoint rows):
    mean_saturation = mean(max(RGB)-min(RGB)) per gaussian,
    color_var = across-gaussian variance averaged over channels."""
    with torch.no_grad():
        c = colors.detach()
        sat = float((c.max(dim=1).values - c.min(dim=1).values).mean())
        var = float(c.var(dim=0, unbiased=False).mean())
    return {"mean_saturation": round(sat, 6), "color_var": round(var, 8)}


def write_render_tiles(tile_dir, row, tile_max_px, residual_vmax,
                       with_photo=False):
    """3a tile encoding reused for step snapshots: render.png + residual.png
    (photo.png only on demand — 3b+ steps reuse the 3a photo tiles, viewer
    references them). Returns the full-res residual (mean |photo-render|)."""
    from PIL import Image
    tile_dir = Path(tile_dir)
    tile_dir.mkdir(parents=True, exist_ok=True)
    H, W = row["target"].shape[:2]
    sc = min(1.0, tile_max_px / max(W, H))
    size = (int(round(W * sc)), int(round(H * sc)))
    res = np.abs(row["target"] - row["render"]).mean(axis=-1)
    items = [("render", (row["render"] * 255).astype(np.uint8), "RGB"),
             ("residual", (np.clip(res / residual_vmax, 0, 1) * 255)
              .astype(np.uint8), "L")]
    if with_photo:
        items.insert(0, ("photo", (row["target"] * 255).astype(np.uint8),
                         "RGB"))
    for name, arr, mode in items:
        Image.fromarray(arr, mode).resize(size, Image.LANCZOS).save(
            tile_dir / f"{name}.png")
    return res


def anchor_terms(st):
    """§2.2 with o frozen at o_state, P=P⁰, δ=0 (3a constants, recorded).

    cell anchor  Σ_k w_k·C_k(o_k), C_k = −[o·log t + (1−o)·log(1−t)], w=1
    plane anchor Σ_p w_p·ρ(P_p ⊖ (P⁰_p ⊕ δ)) = 0 exactly at P=P⁰, δ=0
    area         λ_a · Σ_f area(f)·|o_a−o_b|  (λ_a applied by caller)"""
    o = np.asarray([c["o_state"] for c in st["cells"]], dtype=np.float64)
    t = np.asarray([c["t"] for c in st["cells"]], dtype=np.float64)
    c_k = -(o * np.log(t) + (1 - o) * np.log(1 - t))
    area_gate = float((st["face_area"] * st["face_alpha"]).sum())
    return {"anchor_cell": float(c_k.sum()), "anchor_plane": 0.0,
            "area_gate_m2": area_gate}


# δ-injection bundle names -> xreal_run.scene_for kwargs (e.g. {"bk": "B022",
# "dz": 0.5}). Orchestrators (build_s3c_bundle) register their runs here before
# calling the stage writers; empty registry == exact previous behaviour.
INJECTED_SCENES = {}


def real_views(run_name, s3cfg):
    """Sealed-base cameras/photos via the legacy scene loader, unmodified.
    Selection = real_scene.load_real_scene camera scoring (footprint-prism
    projected hull area, top max_views, depth 15-180 m, 12% center margin).
    Injected runs (INJECTED_SCENES) resolve through scene_for(base, dz=..)
    — cameras/photos stay the sealed base; only the ALS-derived scene fields
    (planes/footprint-prism extent) carry the injection."""
    from real_scene import load_real_scene, FULLSCENE_IMAGES, quat_to_R  # noqa: F401
    from xreal_run import scene_for
    inj_args = INJECTED_SCENES.get(run_name)
    scene = scene_for(**inj_args) if inj_args else scene_for(run_name)
    scene["max_views"] = int(s3cfg["n_views"])
    scene["image_scale"] = float(s3cfg["image_scale"])
    rs = load_real_scene(scene, device="cuda")
    viewmats = rs["viewmats"].cpu().numpy()
    Ks = rs["Ks"].cpu().numpy()
    fp = np.asarray(rs["footprint"])
    center = np.array([fp[:, 0].mean(), fp[:, 1].mean(),
                       (rs["ground_z"] + rs["top_z"]) / 2])
    rows = []
    for i, nm in enumerate(rs["view_names"]):
        z = float((viewmats[i][:3, :3] @ center + viewmats[i][:3, 3])[2])
        rows.append({
            "view_id": Path(nm).stem,
            "image_ref": str(FULLSCENE_IMAGES / nm),
            "width": rs["W"], "height": rs["H"],
            "px_per_m": round(float(Ks[i][0, 0]) / max(z, 1e-6), 2),
            "K": np.round(Ks[i], 4).tolist(),
            "R": np.round(viewmats[i][:3, :3], 8).tolist(),
            "t": np.round(viewmats[i][:3, 3], 6).tolist(),
        })
    # 3a render bg: legacy 0.5 gray == neutral-gray color -> zero-contrast
    # silhouettes (geometry gradients collapse to float noise). Declared bg.
    bg = torch.tensor([float(v) for v in s3cfg["bg_rgb"]],
                      device=rs["targets"].device)
    return {
        "rows": rows,
        "selection_rule": (
            "scripts/p2/arrgs_v1/real_scene.py load_real_scene camera scoring, "
            "reused unmodified (skip_images off): footprint-prism projected "
            "convex-hull area ranking, top max_views(=n_views), camera depth "
            "15-180 m, principal-point 12% margin; sealed full-scene COLMAP "
            "sparse + images (Gate-S0 lineage), viewer-local frame; "
            f"image_scale {scene['image_scale']}"),
        "targets": rs["targets"], "masks": rs["masks"],
        "viewmats": rs["viewmats"], "Ks": rs["Ks"],
        "W": rs["W"], "H": rs["H"], "bg": bg,
        "bg_rgb": [float(v) for v in s3cfg["bg_rgb"]],
    }


def synth_views(s3cfg, device="cuda"):
    """x0 path reused (arrgs_train.run synthetic branch): GT-gaussian renders
    from the fixed camera ring ARE the photos."""
    import synthetic as syn
    from arrgs_train import render_gaussians, normals_to_quats, project_mask
    g_means, g_normals, g_colors, _inside, fp, spacing = syn.gt_gaussians("gable")
    ground_z, top_z = 0.0, 13.0  # arrgs_train.run() synthetic constants
    viewmats_np, Ks_np = syn.camera_ring(center=(10, 6, 4),
                                         rings=s3cfg.get("synth_rings"))
    W, H = syn.W, syn.H
    means = torch.tensor(g_means, dtype=torch.float32, device=device)
    quats = normals_to_quats(torch.tensor(g_normals, dtype=torch.float32,
                                          device=device))
    scales = torch.full((len(g_means), 3), spacing * 0.7, device=device)
    scales[:, 2] = 1e-3
    alphas = torch.full((len(g_means),), 0.95, device=device)
    colors = torch.tensor(g_colors, dtype=torch.float32, device=device)
    viewmats = torch.tensor(viewmats_np, dtype=torch.float32, device=device)
    Ks = torch.tensor(Ks_np, dtype=torch.float32, device=device)
    bg = torch.tensor([0.55, 0.65, 0.78], device=device)
    with torch.no_grad():
        targets = render_gaussians(means, quats, scales, alphas, colors,
                                   viewmats, Ks, W, H, bg)
    masks = np.stack([project_mask(fp, ground_z, top_z, viewmats_np[i],
                                   Ks_np[i], W, H)
                      for i in range(len(viewmats_np))])
    rows = []
    for i in range(len(viewmats_np)):
        rows.append({
            "view_id": f"ring{i:02d}",
            "image_ref": "synthetic:x0 GT-gaussian render (no photo file)",
            "width": W, "height": H, "px_per_m": None,
            "K": np.round(Ks_np[i], 4).tolist(),
            "R": np.round(viewmats_np[i][:3, :3], 8).tolist(),
            "t": np.round(viewmats_np[i][:3, 3], 6).tolist(),
        })
    return {
        "rows": rows,
        "selection_rule": (
            "scripts/p2/arrgs_v1/arrgs_train.py run() synthetic branch reused: "
            "targets = GT-gaussian renders (synthetic.gt_gaussians 'gable') "
            "from synthetic.camera_ring center=(10,6,4) default rings "
            "(high+medium), masks = footprint-prism project_mask"),
        "targets": targets, "masks": masks,
        "viewmats": viewmats, "Ks": Ks, "W": W, "H": H, "bg": bg,
        "bg_rgb": [0.55, 0.65, 0.78],  # target-consistent (x0 path)
    }
