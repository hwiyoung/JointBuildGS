#!/usr/bin/env python3
"""ARRGS S3+S4 model: planes + cell occupancy + plane-bound gaussians, one loss.

Variables (all torch, single Adam):
  plane_n_raw (J,3), plane_d (J,)       -- plane pose
  o_logit (K_free,)                     -- cell occupancy (sigmoid)
  u (N,2), log_s (N,2), rgb_raw (N,3), alpha_logit (N,)  -- gaussians in plane frames
  delta (3,)                            -- shared prior registration shift (optional)

Rendering: gsplat.rasterization with per-gaussian opacity multiplied by the
face visibility gate v_f = |o(cell_a) - o(cell_b)| (fixed cells contribute
constants). No CUDA fork: the gate is a plain autograd multiply.
"""
from __future__ import annotations

import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from shapely.geometry import Polygon, Point as ShPoint

EPS_Z = 1e-3


def _rotmat_to_quat(R):
    """(J,3,3) -> (J,4) wxyz, robust branchy conversion."""
    J = R.shape[0]
    q = torch.zeros(J, 4, device=R.device, dtype=R.dtype)
    tr = R[:, 0, 0] + R[:, 1, 1] + R[:, 2, 2]
    for j in range(J):  # J is small (<=64); loop is fine and safe
        m = R[j]
        t = tr[j]
        if t > 0:
            s = torch.sqrt(t + 1.0) * 2
            q[j, 0] = 0.25 * s
            q[j, 1] = (m[2, 1] - m[1, 2]) / s
            q[j, 2] = (m[0, 2] - m[2, 0]) / s
            q[j, 3] = (m[1, 0] - m[0, 1]) / s
        elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = torch.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
            q[j, 0] = (m[2, 1] - m[1, 2]) / s
            q[j, 1] = 0.25 * s
            q[j, 2] = (m[0, 1] + m[1, 0]) / s
            q[j, 3] = (m[0, 2] + m[2, 0]) / s
        elif m[1, 1] > m[2, 2]:
            s = torch.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
            q[j, 0] = (m[0, 2] - m[2, 0]) / s
            q[j, 1] = (m[0, 1] + m[1, 0]) / s
            q[j, 2] = 0.25 * s
            q[j, 3] = (m[1, 2] + m[2, 1]) / s
        else:
            s = torch.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
            q[j, 0] = (m[1, 0] - m[0, 1]) / s
            q[j, 1] = (m[0, 2] + m[2, 0]) / s
            q[j, 2] = (m[1, 2] + m[2, 1]) / s
            q[j, 3] = 0.25 * s
    return F.normalize(q, dim=-1)


def seed_faces(arr, target_total=6000, min_spacing=0.30, planes=None,
               uniform=False):
    """Grid-seed gaussians on renderable faces. Returns dict of numpy arrays.

    Skips faces whose both sides are fixed-empty (v==0 forever). When `planes`
    carry support regions (S1R), facets outside their plane's support get no
    seeds (pierce-facet cull), and the budget is weighted toward facets on the
    initial solid|empty boundary (|Δo_init|). `uniform=True` disables both
    (v1 behaviour — the seeding ablation control)."""
    from shapely.prepared import prep as _prep
    sup_map = {}
    if planes and not uniform:
        for p in planes:
            if p.get("support"):
                polys = [Polygon(r) for r in p["support"] if len(r) >= 3]
                polys = [q for q in polys if q.is_valid and q.area > 0.2]
                if polys:
                    from shapely.ops import unary_union
                    sup_map[p["id"]] = _prep(unary_union(polys))
    cells = arr["cells"]
    fixed = [c["fixed"] for c in cells]

    def o0(ci):
        if ci < 0 or fixed[ci] == 0.0:
            return 0.0
        return cells[ci].get("o_init", 0.5)

    seeds = []          # (x,y,z) world
    seed_face = []      # face index
    face_keep = []      # indices of renderable faces
    face_w = {}
    total_area = 0.0
    for fi, f in enumerate(arr["faces"]):
        a, b = f["cell_a"], f["cell_b"]
        fa = fixed[a] if a >= 0 else 0.0
        fb = fixed[b] if b >= 0 else 0.0
        if fa == 0.0 and fb == 0.0:
            continue
        if sup_map:
            pid = f["plane_id"]
            if pid in sup_map:
                cen = np.asarray(f["poly3d"]).mean(axis=0)
                if not sup_map[pid].contains(ShPoint(cen[0], cen[1])):
                    continue  # pierce facet outside the plane's support
            elif not pid.startswith("domain:"):
                pass  # plane without support info: keep (fallback planes)
        w = 1.0
        if not uniform:
            gate0 = abs(o0(a) - o0(b))
            w = 0.25 + 2.75 * min(1.0, gate0 / 0.6)  # boundary-weighted budget
        face_keep.append(fi)
        face_w[fi] = w
        total_area += f["area"] * w
    for fi in face_keep:
        f = arr["faces"][fi]
        poly3d = np.asarray(f["poly3d"])
        n = np.asarray(f["n"]); d = f["d"]
        # shared plane frame (same convention as arrangement.plane_frame)
        ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0.0, 1, 0])
        e1 = ref - np.dot(ref, n) * n; e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1)
        origin = n * d
        uv = np.stack([(poly3d - origin) @ e1, (poly3d - origin) @ e2], axis=1)
        poly = Polygon(uv)
        # spacing from (weighted) area budget
        share = max(f["area"] * face_w.get(fi, 1.0) / max(total_area, 1e-6), 1e-4)
        n_target = max(6, int(target_total * share))
        spacing = max(min_spacing, math.sqrt(f["area"] / n_target))
        minx, miny, maxx, maxy = poly.bounds
        xs = np.arange(minx + spacing / 2, maxx, spacing)
        ys = np.arange(miny + spacing / 2, maxy, spacing)
        pts = []
        for x in xs:
            for y in ys:
                if poly.contains(ShPoint(x, y)):
                    pts.append((x, y))
        if not pts:
            c = poly.centroid
            pts = [(c.x, c.y)]
        for (x, y) in pts:
            world = origin + x * e1 + y * e2
            seeds.append(world)
            seed_face.append(fi)
    xyz = np.asarray(seeds)
    face_idx = np.asarray(seed_face, dtype=np.int64)
    if len(xyz) > 2.2 * target_total:  # per-face minimums can blow the budget
        stride = int(np.ceil(len(xyz) / (2.2 * target_total)))
        xyz, face_idx = xyz[::stride], face_idx[::stride]
    return {"xyz": xyz, "face_idx": face_idx,
            "renderable_faces": np.asarray(face_keep, dtype=np.int64)}


class ArrgsModel(nn.Module):
    def __init__(self, arr, planes, seeds, device="cuda", enable_delta=False,
                 init_scale_mult=0.7):
        super().__init__()
        self.device = device
        self.arr = arr
        self.planes_meta = planes  # list of dicts (id, n, d, source, prior)
        cells = arr["cells"]
        faces = arr["faces"]

        # --- plane parameters ---
        pid_list = [p["id"] for p in planes]
        self.pid_index = {pid: j for j, pid in enumerate(pid_list)}
        n0 = np.asarray([p["n"] for p in planes], dtype=np.float64)
        n0 /= np.linalg.norm(n0, axis=1, keepdims=True)
        d0 = np.asarray([p["d"] for p in planes], dtype=np.float64)
        self.plane_n_raw = nn.Parameter(torch.tensor(n0, dtype=torch.float32))
        self.plane_d = nn.Parameter(torch.tensor(d0, dtype=torch.float32))
        self.register_buffer("n_init", torch.tensor(n0, dtype=torch.float32))
        self.register_buffer("d_init", torch.tensor(d0, dtype=torch.float32))
        # fixed per-plane reference vectors for the frame (chosen at init)
        ref = np.where(np.abs(n0[:, 0:1]) < 0.9,
                       np.tile([1.0, 0, 0], (len(planes), 1)),
                       np.tile([0.0, 1, 0], (len(planes), 1)))
        self.register_buffer("ref", torch.tensor(ref, dtype=torch.float32))
        # prior targets (subset of planes)
        prior_rows = [(j, p["prior"]) for j, p in enumerate(planes) if p.get("prior")]
        self.prior_j = torch.tensor([r[0] for r in prior_rows], dtype=torch.long)
        if prior_rows:
            pn = np.asarray([r[1]["n0"] for r in prior_rows], dtype=np.float64)
            pn /= np.linalg.norm(pn, axis=1, keepdims=True)
            self.register_buffer("prior_n0", torch.tensor(pn, dtype=torch.float32))
            self.register_buffer("prior_d0", torch.tensor(
                [r[1]["d0"] for r in prior_rows], dtype=torch.float32))
            self.register_buffer("prior_w", torch.tensor(
                [r[1].get("w", 1.0) for r in prior_rows], dtype=torch.float32))
        self.delta = nn.Parameter(torch.zeros(3), requires_grad=enable_delta)

        # --- occupancy ---
        self.free_cells = [c["idx"] for c in cells if c["fixed"] is None]
        self.free_index = {ci: k for k, ci in enumerate(self.free_cells)}
        o_init = np.asarray([c.get("o_init", 0.5) for c in cells])
        logits = np.log(np.clip(o_init, 1e-3, 1 - 1e-3) / np.clip(1 - o_init, 1e-3, 1))
        self.o_logit = nn.Parameter(torch.tensor(
            [logits[ci] for ci in self.free_cells], dtype=torch.float32))
        # persistent anchor target: the same o_init the logits start from.
        # Init alone exerts no force after step 1; the anchor keeps pulling.
        self.register_buffer("o_init_free", torch.tensor(
            [o_init[ci] for ci in self.free_cells], dtype=torch.float32))
        # per-cell anchor trust (conflict attenuation hook; 1.0 = full trust)
        self.register_buffer("occ_w", torch.ones(len(self.free_cells)))
        # per-face endpoint gather tables (renderable faces only)
        rf = seeds["renderable_faces"]
        self.rf = rf
        def cell_terms(side_key):
            idx, const = [], []
            for fi in rf:
                c = faces[fi][side_key]
                if c >= 0 and cells[c]["fixed"] is None:
                    idx.append(self.free_index[c]); const.append(-1.0)
                else:
                    idx.append(0)
                    const.append(0.0 if (c < 0 or cells[c]["fixed"] == 0.0) else 1.0)
            return (torch.tensor(idx, dtype=torch.long),
                    torch.tensor(const, dtype=torch.float32))
        self.register_buffer("fa_idx", cell_terms("cell_a")[0])
        self.register_buffer("fa_const", cell_terms("cell_a")[1])
        self.register_buffer("fb_idx", cell_terms("cell_b")[0])
        self.register_buffer("fb_const", cell_terms("cell_b")[1])
        # map arrangement face idx -> renderable slot
        self.face_slot = {int(fi): s for s, fi in enumerate(rf)}

        # --- gaussians ---
        xyz = seeds["xyz"]
        face_idx = seeds["face_idx"]
        g_plane = []
        for fi in face_idx:
            pid = faces[fi]["plane_id"]
            g_plane.append(self.pid_index.get(pid, -1))
        g_plane = np.asarray(g_plane)
        # domain-boundary gaussians (plane -1): bind to a virtual frozen plane slot
        self.register_buffer("g_plane", torch.tensor(g_plane, dtype=torch.long))
        self.register_buffer("g_face_slot", torch.tensor(
            [self.face_slot[int(fi)] for fi in face_idx], dtype=torch.long))
        # anchor per plane: centroid of its seeds (falls back to n*d)
        anchors = np.zeros((len(planes), 3))
        for j in range(len(planes)):
            m = g_plane == j
            anchors[j] = xyz[m].mean(axis=0) if m.any() else n0[j] * d0[j]
        self.register_buffer("anchor", torch.tensor(anchors, dtype=torch.float32))
        # init u in init frame
        e1_0, e2_0, _ = self._frames_np(n0)
        u = np.zeros((len(xyz), 2))
        m = g_plane >= 0
        rel = xyz[m] - anchors[g_plane[m]]
        u[m, 0] = np.einsum("ij,ij->i", rel, e1_0[g_plane[m]])
        u[m, 1] = np.einsum("ij,ij->i", rel, e2_0[g_plane[m]])
        self.u = nn.Parameter(torch.tensor(u, dtype=torch.float32))
        # domain gaussians keep absolute positions
        self.register_buffer("g_abs", torch.tensor(xyz, dtype=torch.float32))
        spacing0 = np.full(len(xyz), 0.4)
        self.log_s = nn.Parameter(torch.log(torch.tensor(
            spacing0 * init_scale_mult, dtype=torch.float32))[:, None].repeat(1, 2))
        self.rgb_raw = nn.Parameter(torch.zeros(len(xyz), 3))
        self.alpha_logit = nn.Parameter(torch.full((len(xyz),), 0.85))

    def _frames_np(self, n):
        ref = np.where(np.abs(n[:, 0:1]) < 0.9,
                       np.tile([1.0, 0, 0], (len(n), 1)),
                       np.tile([0.0, 1, 0], (len(n), 1)))
        e1 = ref - (ref * n).sum(1, keepdims=True) * n
        e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
        e2 = np.cross(n, e1)
        return e1, e2, ref

    def plane_frames(self):
        n = F.normalize(self.plane_n_raw, dim=-1)
        e1 = self.ref - (self.ref * n).sum(-1, keepdim=True) * n
        e1 = F.normalize(e1, dim=-1)
        e2 = torch.cross(n, e1, dim=-1)
        # origin: anchor projected onto current plane
        off = (n * self.anchor).sum(-1) - self.plane_d
        origin = self.anchor - off[:, None] * n
        return n, e1, e2, origin

    def occupancy(self):
        return torch.sigmoid(self.o_logit)

    def face_gate(self):
        """v per renderable face slot."""
        o = self.occupancy()
        oa = torch.where(self.fa_const < 0, o[self.fa_idx], self.fa_const)
        ob = torch.where(self.fb_const < 0, o[self.fb_idx], self.fb_const)
        return (oa - ob).abs(), oa, ob

    def gaussians(self):
        n, e1, e2, origin = self.plane_frames()
        j = self.g_plane.clamp(min=0)
        means = origin[j] + self.u[:, :1] * e1[j] + self.u[:, 1:2] * e2[j]
        # domain-boundary gaussians stay absolute
        dom = (self.g_plane < 0)[:, None]
        means = torch.where(dom, self.g_abs, means)
        R = torch.stack([e1, e2, n], dim=-1)  # (J,3,3) columns
        quats = _rotmat_to_quat(R)[j]
        s = torch.exp(self.log_s).clamp(1e-3, 5.0)
        scales = torch.cat([s, torch.full_like(s[:, :1], EPS_Z)], dim=-1)
        v, _, _ = self.face_gate()
        v_g = v[self.g_face_slot]
        alphas = torch.sigmoid(self.alpha_logit) * v_g
        colors = torch.sigmoid(self.rgb_raw)
        return means, quats, scales, alphas, colors

    def prior_loss(self, huber_m=0.5, huber_deg=10.0):
        if len(self.prior_j) == 0:
            return torch.zeros((), device=self.plane_d.device)
        n = F.normalize(self.plane_n_raw, dim=-1)[self.prior_j]
        d = self.plane_d[self.prior_j]
        cos = (n * self.prior_n0).sum(-1).clamp(-1, 1)
        # smooth angle proxy: |n - n0| ~ angle in rad for small angles.
        # (acos has an infinite gradient at cos=1 — the init point — and NaN'd
        # the whole graph on the first backward; sqrt(2(1-cos)+eps) is smooth.)
        ang = torch.rad2deg(torch.sqrt(2.0 * (1.0 - cos) + 1e-8))
        d_target = self.prior_d0 + (self.prior_n0 * self.delta[None, :]).sum(-1)
        r_ang = F.huber_loss(ang, torch.zeros_like(ang), delta=huber_deg,
                             reduction="none") / huber_deg
        r_d = F.huber_loss(d, d_target, delta=huber_m, reduction="none") / huber_m
        return (self.prior_w * (r_ang + r_d)).mean()

    def binarization_loss(self):
        o = self.occupancy()
        return (o * (1 - o)).mean()

    def occ_prior_loss(self):
        """Occupancy anchor: weighted BCE(o, o_init) over free cells.

        The MAP prior term the v1 loss lacked — o_init entered only as
        initialization, so annealing could erase it (hole punching). Soft
        targets are intentional: BCE against o_init=0.75 has its minimum at
        0.75, i.e. the anchor encodes trust, not a hard copy."""
        o = self.occupancy().clamp(1e-4, 1 - 1e-4)
        t = self.o_init_free
        bce = -(t * torch.log(o) + (1 - t) * torch.log(1 - o))
        return (self.occ_w * bce).mean()

    def snapshot_state(self):
        with torch.no_grad():
            n = F.normalize(self.plane_n_raw, dim=-1)
            cosi = (n * F.normalize(self.n_init, dim=-1)).sum(-1).clamp(-1, 1)
            v, oa, ob = self.face_gate()
            o = self.occupancy()
            out = {
                "o": o.cpu().tolist(),
                "free_cells": list(self.free_cells),
                "planes": [{
                    "id": p["id"], "source": p.get("source", ""),
                    "n": n[j].cpu().tolist(), "d": float(self.plane_d[j]),
                    "dn_deg": float(torch.rad2deg(torch.acos(cosi[j]))),
                    "dd_m": float(self.plane_d[j] - self.d_init[j]),
                } for j, p in enumerate(self.planes_meta)],
                "delta_hat": self.delta.detach().cpu().tolist(),
                "face_v": v.cpu().tolist(),
                "renderable_faces": [int(x) for x in self.rf],
            }
        return out
