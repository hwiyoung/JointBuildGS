#!/usr/bin/env python3
"""ARRGS S3+S4 trainer + S5 serializer.

One Adam loop over {planes, occupancy, gaussians, delta}; snapshots at a fixed
iteration schedule (occupancy, plane deltas, losses, gate-health probe, render
vs target panels); at the end hardens occupancy, rebuilds the arrangement at
final plane poses, and serializes the B-rep (OBJ + semantics + evidence card)
plus metrics.json.

Usage: python arrgs_train.py --config cfg.json  (paths inside config)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrangement import build_arrangement, label_cells_by_solid  # noqa: E402
from arrgs_model import ArrgsModel, seed_faces, _rotmat_to_quat  # noqa: E402

DEFAULT_SNAPSHOTS = [0, 50, 100, 250, 500, 1000, 2000, 3500, 5000]


def render_gaussians(means, quats, scales, alphas, colors, viewmats, Ks, W, H, bg,
                     with_depth=False):
    from gsplat import rasterization
    mode = "RGB+ED" if with_depth else "RGB"
    out, ralpha, _ = rasterization(
        means, quats, scales, alphas, colors,
        viewmats, Ks, W, H, render_mode=mode,
        backgrounds=bg.expand(viewmats.shape[0], 3),
        near_plane=0.05, radius_clip=0.1)
    if with_depth:
        return out[..., :3], out[..., 3], ralpha[..., 0]
    return out  # (C,H,W,3)


def normals_to_quats(normals):
    n = F.normalize(normals, dim=-1)
    ref = torch.where(n[:, 0:1].abs() < 0.9,
                      torch.tensor([[1.0, 0, 0]], device=n.device),
                      torch.tensor([[0.0, 1, 0]], device=n.device)).expand_as(n)
    e1 = F.normalize(ref - (ref * n).sum(-1, keepdim=True) * n, dim=-1)
    e2 = torch.cross(n, e1, dim=-1)
    R = torch.stack([e1, e2, n], dim=-1)
    return _rotmat_to_quat(R)


def project_mask(footprint_xy, ground_z, top_z, viewmat, K, W, H, buffer_scale=1.10):
    """Fill polygon mask of the footprint prism projection."""
    fp = np.asarray(footprint_xy, dtype=np.float64)
    c = fp.mean(axis=0)
    fp = c + (fp - c) * buffer_scale
    corners = np.concatenate([np.c_[fp, np.full(len(fp), ground_z)],
                              np.c_[fp, np.full(len(fp), top_z)]])
    Xc = (viewmat[:3, :3] @ corners.T).T + viewmat[:3, 3]
    valid = Xc[:, 2] > 0.1
    if valid.sum() < 3:
        return np.zeros((H, W), dtype=bool)
    uv = (K @ (Xc[valid] / Xc[valid, 2:3]).T).T[:, :2]
    from scipy.spatial import ConvexHull
    try:
        hull = ConvexHull(uv)
    except Exception:
        return np.zeros((H, W), dtype=bool)
    poly = [tuple(p) for p in uv[hull.vertices]]
    img = Image.new("1", (W, H), 0)
    ImageDraw.Draw(img).polygon(poly, fill=1)
    return np.array(img, dtype=bool)


def _to_png(t):
    return Image.fromarray((t.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8))


def side_by_side(render, target, path, scale=0.5):
    a, b = _to_png(render), _to_png(target)
    w, h = int(a.width * scale), int(a.height * scale)
    a, b = a.resize((w, h)), b.resize((w, h))
    canvas = Image.new("RGB", (w * 2 + 4, h), (30, 30, 30))
    canvas.paste(a, (0, 0)); canvas.paste(b, (w + 4, 0))
    canvas.save(path)


def classify_face(f, ground_z):
    nz = abs(f["n"][2])
    zc = np.asarray(f["poly3d"])[:, 2].mean()
    if f["plane_id"] == "domain:z-" or (nz > 0.7 and zc < ground_z + 0.5):
        return "ground"
    if nz < 0.35:
        return "wall"
    return "roof"


def solid_boundary_faces(arr, o_hard):
    """Faces between solid and empty after hardening (incl. domain boundary)."""
    cells = arr["cells"]
    out = []
    for f in arr["faces"]:
        a, b = f["cell_a"], f["cell_b"]
        oa = o_hard[a] if a >= 0 else 0.0
        ob = o_hard[b] if b >= 0 else 0.0
        if abs(oa - ob) > 0.5:
            out.append((f, oa > 0.5))
    return out


def export_obj(faces_solid, path, ground_z):
    verts, groups = [], {"roof": [], "wall": [], "ground": []}
    for f, solid_is_a in faces_solid:
        poly = np.asarray(f["poly3d"])
        # outward normal: from solid cell to empty side
        flip = not solid_is_a  # cell_a is the below(n·x<=d) side
        idxs = []
        for p in poly:
            verts.append(p)
            idxs.append(len(verts))
        if flip:
            idxs = idxs[::-1]
        groups[classify_face(f, ground_z)].append(idxs)
    with open(path, "w") as fh:
        fh.write("# ARRGS S5 B-rep\n")
        for v in verts:
            fh.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        for cls, polys in groups.items():
            fh.write(f"g {cls}\n")
            for idxs in polys:
                for k in range(1, len(idxs) - 1):  # fan triangulation
                    fh.write(f"f {idxs[0]} {idxs[k]} {idxs[k+1]}\n")
    return {cls: len(p) for cls, p in groups.items()}


def map_occupancy(old_arr, new_arr, o_old):
    """Transfer hardened occupancy to rebuilt arrangement by centroid containment."""
    old_cells = old_arr["cells"]
    o_new = []
    for c in new_arr["cells"]:
        if c["fixed"] == 0.0:
            o_new.append(0.0)
            continue
        p = np.asarray(c["centroid"])
        val, best_d = 0.0, 1e18
        for oc, ov in zip(old_cells, o_old):
            d = np.linalg.norm(np.asarray(oc["centroid"]) - p)
            if d < best_d:
                best_d, val = d, ov if oc["fixed"] is None else 0.0
        o_new.append(val)
    return o_new


def run(cfg):
    device = "cuda"
    out_dir = Path(cfg["out_dir"])
    (out_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    torch.manual_seed(cfg.get("seed", 0))
    np.random.seed(cfg.get("seed", 0))

    # ---------------- scene ----------------
    scene = cfg["scene"]
    if scene["type"] == "synthetic":
        import synthetic as syn
        g_means, g_normals, g_colors, inside_fn, fp, spacing = syn.gt_gaussians(scene["kind"])
        planes, fp = syn.candidate_planes(scene["kind"], perturb=scene.get("perturb", 0.0))
        gt_planes, _ = syn.candidate_planes(scene["kind"], perturb=0.0)
        ground_z, top_z = 0.0, 13.0
        viewmats_np, Ks_np = syn.camera_ring(center=(10, 6, 4),
                                             rings=scene.get("rings"))
        W, H = syn.W, syn.H
        means = torch.tensor(g_means, dtype=torch.float32, device=device)
        quats = normals_to_quats(torch.tensor(g_normals, dtype=torch.float32, device=device))
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
        masks = np.stack([project_mask(fp, ground_z, top_z, viewmats_np[i], Ks_np[i], W, H)
                          for i in range(len(viewmats_np))])
        gt_inside = inside_fn
    elif scene["type"] == "real":
        from real_scene import load_real_scene
        rs = load_real_scene(scene, device)
        planes, fp, ground_z, top_z = rs["planes"], rs["footprint"], rs["ground_z"], rs["top_z"]
        gt_planes = None
        targets, masks = rs["targets"], rs["masks"]
        viewmats, Ks = rs["viewmats"], rs["Ks"]
        viewmats_np, Ks_np = viewmats.cpu().numpy(), Ks.cpu().numpy()
        W, H = rs["W"], rs["H"]
        bg = rs["bg"]
        gt_inside = None
        o_init_fn = rs.get("o_init_fn")
    else:
        raise ValueError(scene["type"])

    # optional prior delta injection (X3): shift prior targets east by delta_xy
    dx = float(cfg.get("inject_delta_east_m", 0.0))
    dz = float(cfg.get("inject_delta_z_m", 0.0))
    if dx or dz:
        shift = np.array([dx, 0.0, dz])
        for p in planes:
            if p.get("prior"):
                n0 = np.asarray(p["prior"]["n0"])
                p["prior"]["d0"] = float(p["prior"]["d0"] + n0 @ shift)
                p["n"], p["d"] = p["prior"]["n0"], p["prior"]["d0"]  # init at shifted prior

    # ---------------- S1/S2 ----------------
    t0 = time.time()
    json.dump({"planes": planes, "footprint": np.asarray(fp).tolist(),
               "ground_z": ground_z, "top_z": top_z},
              open(out_dir / "s1_candidates.json", "w"))
    arr = build_arrangement(planes, fp, ground_z, top_z,
                            margin=cfg.get("domain_margin", 1.5))
    # occupancy init: below any roof-ish candidate -> leaning solid
    roofish = [(np.asarray(p["n"]), p["d"]) for p in planes
               if abs(p["n"][2]) > 0.3 and p["source"] != "footprint"]
    o_init_mode = cfg.get("o_init", "heuristic")
    real_o_init = scene["type"] == "real" and "o_init_fn" in dir() and o_init_fn is not None
    for c in arr["cells"]:
        if c["fixed"] is not None:
            continue
        if o_init_mode == "sym":
            c["o_init"] = 0.5
        elif real_o_init:
            c["o_init"] = float(o_init_fn(np.asarray(c["centroid"])))  # ALS solid proxy
        elif o_init_mode == "proxy" and gt_inside is not None:
            # synthetic analog of the real ALS-solid init: GT label + flip noise
            rng_flip = np.random.default_rng(hash(tuple(np.round(c["centroid"], 2))) % 2**31)
            lab = gt_inside(np.asarray(c["centroid"]))
            if rng_flip.random() < cfg.get("proxy_flip", 0.15):
                lab = not lab
            c["o_init"] = 0.75 if lab else 0.25
        else:
            below = any(np.asarray(c["centroid"]) @ n - d < 0 for n, d in roofish)
            c["o_init"] = 0.7 if below else 0.25
    if gt_inside is not None:
        gt_labels = label_cells_by_solid(arr, gt_inside)
    else:
        gt_labels = None
    seeds = seed_faces(arr, target_total=cfg.get("gaussians", 6000))
    json.dump({"cells": arr["cells"], "faces": [
        {k: f[k] for k in ("plane_id", "cell_a", "cell_b", "n", "d", "poly3d", "area")}
        for f in arr["faces"]],
        "seed_count": int(len(seeds["xyz"])),
        "renderable_faces": seeds["renderable_faces"].tolist(),
        "gt_labels": gt_labels},
        open(out_dir / "s2_arrangement.json", "w"))
    print(f"[arrgs] cells={len(arr['cells'])} faces={len(arr['faces'])} "
          f"seeds={len(seeds['xyz'])} ({time.time()-t0:.1f}s)", flush=True)

    # ---------------- model/opt ----------------
    model = ArrgsModel(arr, planes, seeds, device=device,
                       enable_delta=bool(cfg.get("enable_delta", False))).to(device)
    lr = cfg.get("lr", {})
    param_groups = [
        {"params": [model.plane_n_raw], "lr": lr.get("plane_n", 1e-3)},
        {"params": [model.plane_d], "lr": lr.get("plane_d", 5e-3)},
        {"params": [model.o_logit], "lr": lr.get("o", 5e-2)},
        {"params": [model.u], "lr": lr.get("u", 2e-3)},
        {"params": [model.log_s], "lr": lr.get("s", 5e-3)},
        {"params": [model.rgb_raw], "lr": lr.get("rgb", 2.5e-2)},
        {"params": [model.alpha_logit], "lr": lr.get("alpha", 5e-2)},
    ]
    if cfg.get("enable_delta"):
        param_groups.append({"params": [model.delta], "lr": lr.get("delta", 2e-3)})
    opt = torch.optim.Adam(param_groups)

    iters = cfg.get("iters", 5000)
    lam = cfg.get("lambda", {})
    lam_photo = lam.get("photo", 1.0)
    lam_prior = lam.get("prior", 0.05)
    lam_bin_max = lam.get("bin", 1.0)
    lam_u = lam.get("u_reg", 1e-3)
    anneal = cfg.get("anneal", True)
    warm = int(iters * cfg.get("anneal_warm", 0.35))
    full = int(iters * cfg.get("anneal_full", 0.85))

    mask_t = torch.tensor(masks, device=device)
    depth_t = None
    if scene["type"] == "real" and rs.get("depth_targets") is not None:
        depth_t = rs["depth_targets"]  # (C,H,W), 0 = invalid
    lam_depth = lam.get("depth", 0.5) if depth_t is not None else 0.0
    C = targets.shape[0]
    holdout = max(1, C // 8) if cfg.get("holdout", True) else 0
    train_cams = list(range(C - holdout))
    eval_cams = list(range(C - holdout, C)) if holdout else train_cams[:2]
    snap_iters = sorted(set(cfg.get("snapshots", DEFAULT_SNAPSHOTS) + [iters]))
    snap_views = eval_cams[:2] if holdout else [0, C // 2]
    u_init = model.u.detach().clone()
    batch = cfg.get("cam_batch", 4)
    ema = {}
    gate_probe = []

    def lam_bin(i):
        if not anneal:
            return 0.0
        if i < warm:
            return 0.0
        return lam_bin_max * min(1.0, (i - warm) / max(1, full - warm))

    def psnr_all(cams):
        with torch.no_grad():
            means_, quats_, scales_, alphas_, colors_ = model.gaussians()
            vals = []
            for ci in cams:
                out = render_gaussians(means_, quats_, scales_, alphas_, colors_,
                                       viewmats[ci:ci + 1], Ks[ci:ci + 1], W, H, bg)[0]
                m = mask_t[ci]
                if m.sum() == 0:
                    continue
                mse = ((out - targets[ci])[m] ** 2).mean()
                vals.append(float(-10 * torch.log10(mse + 1e-10)))
            return float(np.mean(vals)) if vals else 0.0

    print(f"[arrgs] train {iters} iters, {len(train_cams)} train cams, "
          f"{len(eval_cams)} eval cams", flush=True)
    for it in range(iters + 1):
        cams = np.random.choice(train_cams, size=min(batch, len(train_cams)),
                                replace=False)
        means_, quats_, scales_, alphas_, colors_ = model.gaussians()
        m = mask_t[cams]
        if depth_t is not None:
            out, dep, ralpha = render_gaussians(means_, quats_, scales_, alphas_,
                                                colors_, viewmats[cams], Ks[cams],
                                                W, H, bg, with_depth=True)
            dt = depth_t[cams]
            md = m & (dt > 0.5)
            # occluder disambiguation: MVS depth says where the surface really
            # is along each masked ray — phantom cells above/below it pay here
            loss_depth = ((dep - dt).abs().clamp(max=8.0) * ralpha)[md].mean() / 4.0 \
                if md.any() else torch.zeros((), device=device)
        else:
            out = render_gaussians(means_, quats_, scales_, alphas_, colors_,
                                   viewmats[cams], Ks[cams], W, H, bg)
            loss_depth = torch.zeros((), device=device)
        photo = (out - targets[cams]).abs()[m.unsqueeze(-1).expand_as(out)].mean()
        loss_bin = model.binarization_loss()
        loss_prior = model.prior_loss()
        loss_u = ((model.u - u_init) ** 2).mean()
        loss = (lam_photo * photo + lam_depth * loss_depth + lam_bin(it) * loss_bin
                + lam_prior * loss_prior + lam_u * loss_u)
        opt.zero_grad(set_to_none=False)
        loss.backward()
        for k, v in (("photo", photo), ("depth", loss_depth), ("bin", loss_bin),
                     ("prior", loss_prior), ("u", loss_u), ("total", loss)):
            ema[k] = 0.95 * ema.get(k, float(v)) + 0.05 * float(v)
        if it in snap_iters:
            og = model.o_logit.grad
            gate = {"iter": it,
                    "grad_nonzero_frac": float((og.abs() > 1e-10).float().mean()) if og is not None else 0.0,
                    "grad_mean_abs": float(og.abs().mean()) if og is not None else 0.0}
            gate_probe.append(gate)
            snap = model.snapshot_state()
            snap.update({"iter": it, "losses": {k: round(v, 6) for k, v in ema.items()},
                         "lambda_bin": lam_bin(it), "gate": gate,
                         "psnr_eval": psnr_all(eval_cams)})
            json.dump(snap, open(out_dir / "snapshots" / f"iter_{it:06d}.json", "w"))
            with torch.no_grad():
                mm, qq, ss, aa, cc = model.gaussians()
                for vi in snap_views:
                    r = render_gaussians(mm, qq, ss, aa, cc, viewmats[vi:vi + 1],
                                         Ks[vi:vi + 1], W, H, bg)[0]
                    side_by_side(r, targets[vi],
                                 out_dir / "snapshots" / f"render_v{vi}_{it:06d}.png")
            print(f"[arrgs] it={it} loss={ema['total']:.4f} photo={ema['photo']:.4f} "
                  f"bin={ema['bin']:.4f} psnr={snap['psnr_eval']:.2f} "
                  f"gate_nz={gate['grad_nonzero_frac']:.2f}", flush=True)
        opt.step()

    # ---------------- S5 ----------------
    with torch.no_grad():
        o_free = model.occupancy().cpu().numpy()
    o_all = np.zeros(len(arr["cells"]))
    for k, ci in enumerate(model.free_cells):
        o_all[ci] = o_free[k]
    o_hard = (o_all > 0.5).astype(float)
    # rebuild arrangement at final plane poses for exact geometry
    with torch.no_grad():
        n_fin = F.normalize(model.plane_n_raw, dim=-1).cpu().numpy()
        d_fin = model.plane_d.cpu().numpy()
    planes_fin = []
    for j, p in enumerate(planes):
        q = dict(p)
        q["n"], q["d"] = n_fin[j].tolist(), float(d_fin[j])
        planes_fin.append(q)
    arr_fin = build_arrangement(planes_fin, fp, ground_z, top_z,
                                margin=cfg.get("domain_margin", 1.5))
    o_fin = map_occupancy(arr, arr_fin, o_hard)
    faces_solid = solid_boundary_faces(arr_fin, [1.0 if (c["fixed"] is None and o_fin[i] > 0.5) else 0.0
                                                 for i, c in enumerate(arr_fin["cells"])])
    group_counts = export_obj(faces_solid, out_dir / "s5_brep.obj", ground_z)

    # evidence card per final face
    with torch.no_grad():
        v_slot, oa_s, ob_s = model.face_gate()
        alpha_final = torch.sigmoid(model.alpha_logit).cpu().numpy()
    face_support = {}
    for gi, slot in enumerate(model.g_face_slot.cpu().numpy()):
        face_support.setdefault(int(slot), []).append(alpha_final[gi])
    evidence = []
    for s, fi in enumerate(seeds["renderable_faces"]):
        f = arr["faces"][fi]
        pid = f["plane_id"]
        pm = next((p for p in planes if p["id"] == pid), None)
        sup = face_support.get(s, [])
        evidence.append({
            "face": int(fi), "plane_id": pid,
            "source": pm["source"] if pm else "domain",
            "class": classify_face(f, ground_z),
            "area": f["area"], "v_final": float(v_slot[s]),
            "o_a": float(oa_s[s]), "o_b": float(ob_s[s]),
            "photo_support_proxy": float(np.mean(sup)) if sup else 0.0,
            "has_prior": bool(pm and pm.get("prior")),
        })
    json.dump(evidence, open(out_dir / "s5_evidence.json", "w"))

    # ---------------- metrics ----------------
    metrics = {
        "iters": iters, "wall_s": round(time.time() - t0, 1),
        "cells": len(arr["cells"]), "free_cells": len(model.free_cells),
        "faces": len(arr["faces"]), "gaussians": int(len(seeds["xyz"])),
        "group_counts": group_counts,
        "psnr_eval_final": psnr_all(eval_cams),
        "o_decision": float(np.median(2 * np.abs(o_free - 0.5))),
        "o_undecided": int(((o_free > 0.3) & (o_free < 0.7)).sum()),
        "gate_probe": gate_probe,
        "delta_hat": model.delta.detach().cpu().tolist(),
        "inject_delta": [dx, 0.0, dz],
    }
    if gt_labels is not None:
        free = [i for i, c in enumerate(arr["cells"]) if c["fixed"] is None]
        acc = float(np.mean([(o_all[i] > 0.5) == (gt_labels[i] > 0.5) for i in free]))
        metrics["occupancy_accuracy"] = acc
        # ghost/missing internal faces (exclude domain boundary)
        ghost = missing = 0
        with torch.no_grad():
            v_np = v_slot.cpu().numpy()
        for s, fi in enumerate(seeds["renderable_faces"]):
            f = arr["faces"][fi]
            a, b = f["cell_a"], f["cell_b"]
            if b < 0 or f["plane_id"].startswith("domain:"):
                continue
            ga = gt_labels[a] if arr["cells"][a]["fixed"] is None else 0.0
            gb = gt_labels[b] if arr["cells"][b]["fixed"] is None else 0.0
            gt_v = abs(ga - gb)
            if gt_v < 0.5 and v_np[s] > 0.05:
                ghost += 1
            if gt_v > 0.5 and v_np[s] < 0.5:
                missing += 1
        metrics["ghost_faces"] = ghost
        metrics["missing_faces"] = missing
    if gt_planes is not None:
        errs = []
        for p_gt in gt_planes:
            if p_gt["source"] != "gt":
                continue
            j = model.pid_index.get(p_gt["id"])
            if j is None:
                continue
            cos = float(np.clip(n_fin[j] @ (np.asarray(p_gt["n"]) /
                                            np.linalg.norm(p_gt["n"])), -1, 1))
            errs.append({"id": p_gt["id"],
                         "ang_deg": float(np.degrees(np.arccos(cos))),
                         "d_err_m": float(abs(d_fin[j] - p_gt["d"]))})
        metrics["plane_recovery"] = errs
    json.dump(metrics, open(out_dir / "metrics.json", "w"), indent=1)
    json.dump({"config": cfg, "scientific_verdict": None},
              open(out_dir / "run.json", "w"), indent=1)
    print("[arrgs] done:", json.dumps({k: metrics[k] for k in
          ("occupancy_accuracy", "ghost_faces", "missing_faces", "psnr_eval_final",
           "o_undecided") if k in metrics}), flush=True)
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    run(json.load(open(args.config)))
