#!/usr/bin/env python3
"""S3c bundle writer — phd_s3_verify_s3c_v1 (stage 3c "δ thaw", injection-
recovery test) + full-pipeline orchestration for the δ-injected runs.

Trained leaves: δ (ONE global translation vector, methodology §1.3 — no
rotation) + colors (warm-started from the 3b artifact s3b_colors.f16.bin).
Planes P, occupancy-derived alpha and the seed set stay byte-frozen (sha256
before/after; per-step plane subset check). No free alpha, no densify/prune.

OPTIMIZED OBJECTIVE = photo only. anchor(cell)/area are constant diagnostics;
anchor_plane is recorded as a Σ|n⁰·δ̂| diagnostic but NOT backpropped: δ itself
has no anchor (§2.2), and the plane anchor's target is P⁰⊕δ — with planes
frozen at P⁰ in 3c it would reduce to a |δ̂|-proportional penalty that unjustly
suppresses injection recovery (it operates correctly from 3d, where planes
follow). Backward still flows into every leaf, so frozen-group gradient
pressure is recorded each step.

Injected runs (config injected_runs, e.g. B022_DZ050 = B022 + dz 0.5 m): the
ALS prior bytes are shifted through the legacy X3 route (xreal_run.scene_for
dz -> real_scene inject_delta_z_m + s1r delta_shift on E7 prior planes), the
bundle writer shifts the identical E7 crop it serializes, and the full
S1->S2->3a->3b pipeline is run through the EXISTING writers before 3c — the
injection flows into plane statements and o_init pillars together (honest
path). Expected δ̂ = −[0,0,dz] (sign convention: d_eff = d⁰+n⁰·δ translates
prior planes by +δ, so recovery counteracts the applied shift).

Adds to runs/<name>/ (on top of s1+s2+s3a+s3b):
  s3_steps.jsonl                        3c rows appended (3a+3b rows preserved)
  s3_tiles/s3c_s<step>/<view_id>/{render,residual}.png   checkpoints only
                                        (no collision with 3b s<step>/ dirs)
  s3_face_residual_s3c_final.json       final-state residual (3a null rule)
  manifest.json                         stage -> s1+s2+s3a+s3b+s3c, s3c_def
                                        (+ injection block on injected runs)

Usage (container):
  bash scripts/p2/arrgs_v1/run_host.sh <gpu> \
      scripts/phd/s3_verify_v1/build_s3c_bundle.py [run ...]
  default: config runs + injected_runs. An injected run missing its
  s1..s3b bundle is built first (S1->S2->3a->3b), then 3c runs.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, REPO / "scripts/p2/arrgs_v1", REPO / "scripts/p2/journal1_phase_a_v1"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import render_state  # noqa: E402
from render_state import (S3RenderState, anchor_terms, color_stats,  # noqa: E402
                          load_bundle_state, photo_l1_backward, real_views,
                          state_checksums, synth_views, write_render_tiles)
import build_s1_bundle as s1b  # noqa: E402
import build_s2_bundle as s2b  # noqa: E402
import build_s3a_bundle as s3a  # noqa: E402
import build_s3b_bundle as s3b  # noqa: E402
from build_s3a_bundle import face_residuals, render_views  # noqa: E402

CFG = s1b.CFG
S3 = CFG["s3"]
S3B = S3["b"]
S3C = S3["c"]
INJECTED = CFG.get("injected_runs", {})
S3C_SCHEMA = "phd_s3_verify_s3c_v1"
PLANE_KEYS = ("plane_n_raw", "plane_d")  # cheap per-step frozen subset

OBJECTIVE_NOTE = (
    "optimized objective = photo only. anchor(cell)/area are constant "
    "diagnostics (o frozen); anchor_plane is recorded as sum_{p in delta-"
    "scope} |n0_p . delta_hat| (m, w=1, angle term 0) but NOT backpropped: "
    "delta itself has no anchor (methodology 2.2), and the plane anchor's "
    "target is P0(+)delta — with planes frozen at P0 in 3c it reduces to a "
    "|delta_hat|-proportional penalty that would unjustly suppress injection "
    "recovery; it operates correctly from 3d where planes follow.")


def register_injected_scenes():
    for name, spec in INJECTED.items():
        render_state.INJECTED_SCENES[name] = {"bk": spec["base"],
                                              "dz": float(spec["dz"])}


# ---------------------------------------------------------------- injected S1
def build_injected_s1(name, base, dz, out_root, gravity, lod2_faces):
    """s1b.build_real mirrored for a δ-injected scene: planes come from
    load_real_scene with inject_delta_z_m (E7 prior planes shifted by the
    legacy X3 route), and the SAME shift is applied to the E7 crop bytes this
    writer serializes as source==1 — so o_init pillars judge the shifted
    prior. Cameras are untouched (skip_images bundle path)."""
    from real_scene import A2_CROPS, VIEWER_SHIFT, load_real_scene
    from xreal_run import BUILDINGS, E2_DIR, scene_for
    from bundle_io import read_ply_points, thin_stride
    inj = [0.0, 0.0, float(dz)]
    scene = scene_for(base, dz=float(dz))
    scene["skip_images"] = True
    sc = load_real_scene(scene, device=None)
    assert sc["inject"] == inj, sc["inject"]
    bkey, sid = BUILDINGS[base]["bkey"], BUILDINGS[base]["stable_id"]
    mvs_xyz, mvs_rgb, _ = read_ply_points(Path(E2_DIR) / f"{bkey}.points.ply")
    als_xyz, als_rgb, _ = read_ply_points(A2_CROPS / "E7" / f"{bkey}.points.ply")
    als_xyz = als_xyz + np.asarray(inj)  # same route as real_scene L208-209
    if mvs_rgb is None or not mvs_rgb.any():
        mvs_rgb = np.full((len(mvs_xyz), 3), 180, dtype=np.uint8)
    if als_rgb is None or not als_rgb.any():
        als_rgb = np.full((len(als_xyz), 3), 120, dtype=np.uint8)
    xyz = np.concatenate([mvs_xyz, als_xyz])
    rgb = np.concatenate([mvs_rgb, als_rgb]).astype(np.uint8)
    src = np.concatenate([np.zeros(len(mvs_xyz), np.uint8),
                          np.ones(len(als_xyz), np.uint8)])
    keep, stride = thin_stride(len(xyz), CFG["thin_max_points"])
    entries = s1b.expand_planes(sc["planes"], sc["footprint"],
                                sc["ground_z"], sc["top_z"])
    injection = {
        "delta_applied": inj,
        "route": ("als_bytes(scene_for dz) — xreal_run.scene_for(base, dz) -> "
                  "real_scene.load_real_scene inject_delta_z_m: ALS crop bytes "
                  "+[0,0,dz] (L208-209) and s1r.candidates_from_roofer "
                  "delta_shift on the E7 prior planes/supports (L120-125); "
                  "this writer applies the identical shift to the E7 crop it "
                  "serializes as source==1, so plane statements AND o_init "
                  "pillars carry the injection together (honest path)"),
        "base_run": base,
        "expected_delta_hat": [0.0, 0.0, -float(dz)],
        "sign_convention": (
            "d_eff = d0 + n0*delta (render_state, methodology 1.3): delta "
            "translates prior-source planes by +delta. The injection "
            "translated the prior world by +delta_applied while photos show "
            "the unshifted world, so photo-consistent recovery is delta_hat "
            "-> -delta_applied (the direction that CANCELS the injection)."),
    }
    s1b.write_run(
        out_root / "runs" / name,
        name=name, s1_mode=sc["s1_mode"],
        dataset={"kind": "real", "bkey": bkey, "stable_id": sid,
                 "injected_from": base},
        crs="EPSG:25832", local_offset=VIEWER_SHIFT.tolist(),
        xyz=xyz[keep], rgb=rgb[keep], src=src[keep],
        entries=entries,
        gt_faces=s1b.gt_faces_from_lod2(lod2_faces.get(sid, [])),
        fp_xy=sc["footprint"], ground_z=sc["ground_z"], top_z=sc["top_z"],
        gravity=gravity, stride=stride, n_orig=len(xyz),
        extra_manifest={"injection": injection})
    return {"name": name, "out_dir": out_root / "runs" / name,
            "dataset_kind": "real",
            "planes": [p for p in sc["planes"]
                       if s1b.SOURCE_MAP[p["source"]] not in s1b.EXCLUDE_SOURCES],
            "entries": entries, "fp_xy": np.asarray(sc["footprint"]),
            "ground_z": sc["ground_z"], "top_z": sc["top_z"],
            "xyz": xyz[keep], "src": src[keep],
            "stride": stride, "n_als_orig": len(als_xyz)}


def injection_s1_checks(name, base, dz, out_root):
    """Numeric receipt: did the prior planes really move by n·[0,0,dz], and
    how did o_init respond vs the base bundle? Written into
    manifest.injection.s1_checks (base bundle must exist)."""
    rd_i, rd_b = out_root / "runs" / name, out_root / "runs" / base
    pi = [p for p in json.load(open(rd_i / "s1_planes.json"))["planes"]
          if p["source"] == "prior"]
    pb = [p for p in json.load(open(rd_b / "s1_planes.json"))["planes"]
          if p["source"] == "prior"]
    shift_errs = None
    if len(pi) == len(pb):
        errs = []
        for a, b in zip(pi, pb):  # E7 order is preserved by the shift route
            na, nb = np.asarray(a["n"]), np.asarray(b["n"])
            assert float(np.abs(na - nb).max()) <= 1e-5, (a["plane_id"], b["plane_id"])
            errs.append(abs((a["d"] - b["d"]) - float(na[2]) * dz))
        shift_errs = {"n_prior_planes": len(pi),
                      "max_abs_err_m": round(float(np.max(errs)), 6),
                      "expected_dd": "n_z*dz per plane"}
    ci = json.load(open(rd_i / "s2_cells.json"))["cells"]
    cb = json.load(open(rd_b / "s2_cells.json"))["cells"]
    zs_i = [c["surf"]["z_surf"] for c in ci if c["surf"]["z_surf"] is not None]
    zs_b = [c["surf"]["z_surf"] for c in cb if c["surf"]["z_surf"] is not None]
    checks = {
        "prior_plane_d_shift": shift_errs,
        "prior_plane_counts": {"base": len(pb), "injected": len(pi)},
        "o_init": {
            "mean_z_surf_base": round(float(np.mean(zs_b)), 4),
            "mean_z_surf_injected": round(float(np.mean(zs_i)), 4),
            "mean_z_surf_diff": round(float(np.mean(zs_i) - np.mean(zs_b)), 4),
            "note": ("arrangements differ (shifted planes/top_z), so cells do "
                     "not correspond 1:1; mean pillar z_surf shows the bytes-"
                     "level shift, on-cell counts show the o_init response"),
            "on_cells_base": sum(c["o_state"] for c in cb),
            "cells_base": len(cb),
            "on_cells_injected": sum(c["o_state"] for c in ci),
            "cells_injected": len(ci)}}
    man = json.load(open(rd_i / "manifest.json"))
    man["injection"]["s1_checks"] = checks
    json.dump(man, open(rd_i / "manifest.json", "w"), indent=1)
    print(f"[s3c-inject-check] {name}: {json.dumps(checks)}", flush=True)
    return checks


def ensure_injected_pipeline(name, out_root):
    """S1->S2->3a->3b for an injected run through the existing writers
    (regeneration order constraint 3a->3b respected); no-op when present."""
    spec = INJECTED[name]
    out_dir = out_root / "runs" / name
    mp = out_dir / "manifest.json"
    if mp.is_file():
        stage = json.load(open(mp))["stage"]
        if stage in ("s1+s2+s3a+s3b", "s1+s2+s3a+s3b+s3c"):
            return
        raise AssertionError(
            f"{name}: partial bundle at stage {stage} — delete the run dir to "
            "rebuild the injected pipeline from S1")
    base, dz = spec["base"], float(spec["dz"])
    print(f"[s3c-pipeline] {name}: building S1->S2->3a->3b "
          f"(base {base}, dz {dz})", flush=True)
    gravity, lod2_faces = s1b.real_context([base])
    ctx = build_injected_s1(name, base, dz, out_root, gravity, lod2_faces)
    s2b.build_s2(ctx)
    print(f"[s2-verify] {json.dumps(s2b.verify_run(ctx))}", flush=True)
    injection_s1_checks(name, base, dz, out_root)
    s3a.build_s3a(name, out_root)
    s3b.build_s3b(name, out_root)


# ------------------------------------------------------------------ stage 3c
def build_s3c(name, out_root):
    t0 = time.time()
    out_dir = Path(out_root) / "runs" / name
    manifest = json.load(open(out_dir / "manifest.json"))
    assert manifest["stage"] in ("s1+s2+s3a+s3b", "s1+s2+s3a+s3b+s3c"), \
        manifest["stage"]

    det = s3b.set_determinism(int(S3C["seed"]))
    det["rerun_tolerance_jsonl"] = float(S3C["rerun_tolerance_jsonl"])
    st = load_bundle_state(out_dir)
    n_seeds = len(st["seed_uv"])
    assert n_seeds == manifest["counts"]["seeds"], (
        f"seed count {n_seeds} != manifest {manifest['counts']['seeds']}")

    state = S3RenderState(st, S3, device="cuda")
    # colors warm-start from the 3b artifact (integrity-checked)
    art = manifest["s3b_def"]["colors_artifact"]
    colors_f16 = np.fromfile(out_dir / art["file"], dtype=np.float16)
    assert hashlib.sha256(colors_f16.tobytes()).hexdigest() == art["sha256"], \
        "3b colors artifact sha mismatch"
    colors0 = colors_f16.reshape(n_seeds, 3).astype(np.float32)
    with torch.no_grad():
        state.colors.copy_(torch.tensor(colors0, device=state.colors.device))

    sums0 = state_checksums(state)
    frozen_keys = sorted(k for k in sums0 if k != "delta")  # delta thaws
    assert np.isin(state.alpha_g.cpu().numpy(), (0.0, 1.0)).all(), \
        "alpha not binary"
    assert bool((state.delta.detach() == 0).all()), "delta not starting at 0"
    scope0 = state.n_scope_planes == 0

    views = (synth_views(S3) if name == "SYNTH_GABLE"
             else real_views(name, S3))
    views["masks_t"] = torch.tensor(views["masks"],
                                    device=views["targets"].device)

    steps = int(S3C["steps"])
    ckpts = sorted(set(int(c) for c in S3C["checkpoints"]) | {0, steps})
    assert all(0 <= c <= steps for c in ckpts), ckpts
    lr_delta = float(S3C["lr_delta"])
    lr_rgb = float(S3B["lr_rgb"])  # contract: 3b value, no new registration
    opt = torch.optim.Adam([{"params": [state.colors], "lr": lr_rgb},
                            {"params": [state.delta], "lr": lr_delta}])

    lam_a = float(S3["lambda_area"])
    terms = anchor_terms(st)
    anchor_const = terms["anchor_cell"]
    area_const = lam_a * terms["area_gate_m2"]
    # |n0·δ̂| summed over δ-scope planes (diagnostic; see OBJECTIVE_NOTE)
    nd_scope = (state.delta_dir * state.scope[:, None]).detach()

    leaves = (state.plane_n_raw, state.plane_d, state.delta, state.colors)
    rows_3c, psnr_by_ckpt = [], {}
    final_rows = final_residuals = None
    for k in range(steps + 1):
        for t in leaves:
            t.grad = None
        if k in ckpts:
            vrows = render_views(state, views, with_grad=True)
            photo = float(np.mean([r["photo_l1"] for r in vrows]))
        else:
            vrows = None
            photo = photo_l1_backward(state, views)
        gn = state.grad_norms()
        assert all(np.isfinite(v) for v in gn.values()), gn
        with torch.no_grad():
            dh = [float(v) for v in state.delta.detach().cpu()]
            anchor_plane = float((nd_scope @ state.delta.detach()).abs().sum())
        sums_k = state_checksums(state, keys=PLANE_KEYS)
        planes_frozen = all(sums_k[q] == sums0[q] for q in PLANE_KEYS)
        assert planes_frozen, f"plane group moved at {k}"
        row = {
            "step": k, "stage": "3c",
            "losses": {"photo": round(photo, 6),
                       "anchor": round(anchor_const, 6),
                       "area": round(area_const, 6),
                       "anchor_plane": round(anchor_plane, 6),
                       "total_recorded": round(photo + anchor_const
                                               + area_const + anchor_plane, 6)},
            "grad_norms": {q: float(f"{v:.6g}") for q, v in gn.items()},
            "delta_hat": [round(v, 6) for v in dh],
            "param_step_norms": {"delta": 0.0, "planes": 0.0, "colors": 0.0},
            "invariants": {"planes_frozen": planes_frozen,
                           "alpha_binary": True, "n_seeds": n_seeds},
        }
        if k in ckpts:
            views_psnr = {m["view_id"]: (round(r["psnr"], 3)
                                         if r["psnr"] is not None else None)
                          for r, m in zip(vrows, views["rows"])}
            row["views_psnr"] = views_psnr
            row["color_stats"] = color_stats(state.colors)
            psnr_by_ckpt[k] = views_psnr
            residuals = [write_render_tiles(
                out_dir / "s3_tiles" / f"s3c_s{k}" / m["view_id"], r,
                int(S3["tile_max_px"]), float(S3["residual_vmax"]))
                for r, m in zip(vrows, views["rows"])]
            if k == steps:
                final_rows, final_residuals = vrows, residuals
        if k < steps:  # final row = post-training evaluation, no update
            before_c = state.colors.detach().clone()
            before_d = state.delta.detach().clone()
            opt.step()
            with torch.no_grad():
                state.colors.clamp_(0.0, 1.0)
                dn_c = float(torch.linalg.vector_norm(
                    state.colors.detach() - before_c))
                dn_d = float(torch.linalg.vector_norm(
                    state.delta.detach() - before_d))
            row["param_step_norms"]["colors"] = float(f"{dn_c:.6g}")
            row["param_step_norms"]["delta"] = float(f"{dn_d:.6g}")
        rows_3c.append(row)

    sums1 = state_checksums(state)
    frozen_ok = all(sums1[q] == sums0[q] for q in frozen_keys)
    assert frozen_ok, {q: (sums0[q], sums1[q])
                       for q in frozen_keys if sums0[q] != sums1[q]}
    assert np.isin(state.alpha_g.cpu().numpy(), (0.0, 1.0)).all(), \
        "alpha not binary after training"
    delta_final = [float(v) for v in state.delta.detach().cpu()]
    if scope0:  # zero grad -> zero Adam step: δ must not have moved at all
        assert sums1["delta"] == sums0["delta"] and \
            all(v == 0.0 for v in delta_final), delta_final

    def _med(d):
        vals = [v for v in d.values() if v is not None]
        return float(np.median(vals)) if vals else None
    med0, medf = _med(psnr_by_ckpt[0]), _med(psnr_by_ckpt[steps])
    assert med0 is not None and medf is not None

    injection = manifest.get("injection")
    recovery = None
    if injection:
        exp = np.asarray(injection["expected_delta_hat"], dtype=np.float64)
        err = np.asarray(delta_final) - exp
        recovery = {"expected_delta_hat": injection["expected_delta_hat"],
                    "delta_hat_final": [round(v, 4) for v in delta_final],
                    "residual_m": [round(float(v), 4) for v in err],
                    "abs_residual_z_m": round(abs(float(err[2])), 4),
                    "abs_residual_norm_m": round(float(np.linalg.norm(err)), 4)}

    # append 3c rows; preserve 3a+3b rows byte-exact, drop stale 3c rows
    kept = [ln.rstrip("\n") for ln in open(out_dir / "s3_steps.jsonl")
            if ln.strip() and json.loads(ln).get("stage") != "3c"]
    stages = [json.loads(ln)["stage"] for ln in kept]
    assert stages and stages[0] == "3a" and "3b" in stages, "3a/3b rows missing"
    with open(out_dir / "s3_steps.jsonl", "w") as f:
        for ln in kept:
            f.write(ln + "\n")
        for row in rows_3c:
            f.write(json.dumps(row) + "\n")

    per_face, n_sampled = face_residuals(st, state, views, final_rows,
                                         final_residuals, S3["face_residual"])
    fr3a = json.load(open(out_dir / "s3_face_residual.json"))
    json.dump({"step": steps, "stage": "3c", "method": fr3a["method"],
               "n_views": len(final_rows), "faces_sampled": n_sampled,
               "per_face": per_face},
              open(out_dir / "s3_face_residual_s3c_final.json", "w"))

    manifest["stage"] = "s1+s2+s3a+s3b+s3c"
    manifest["s3c_schema"] = S3C_SCHEMA
    manifest["s3c_def"] = {
        "stage": "3c", "trained": ["delta", "colors"],
        "objective": "photo",
        "objective_note": OBJECTIVE_NOTE,
        "optimizer": "adam (torch.optim.Adam, default betas 0.9/0.999 eps 1e-8)",
        "lr_delta": lr_delta,
        "lr_delta_source": ("s3.c new registration (proposal 1e-2): legacy "
                            "arrgs_train.py L295 lr.get('delta', 2e-3) is a "
                            "5000-iter joint-loop value; 1e-2 sizes the Adam-"
                            "normalized step for the 300-step budget "
                            "(0.5 m / 1e-2 ~ 50 steps minimum)"),
        "lr_rgb": lr_rgb,
        "lr_rgb_source": "s3.b lr_rgb reused (3b value, no new registration)",
        "steps": steps, "rows": len(rows_3c), "checkpoints": ckpts,
        "row_semantics": ("row k = losses/grad_norms/delta_hat at the "
                          "pre-update state of step k; param_step_norms = the "
                          "update applied at step k (final row is evaluation "
                          "only, all 0.0); total_recorded = photo + anchor + "
                          "area + anchor_plane is a RECORDED sum only — the "
                          "optimized objective is photo alone"),
        "anchor_plane_diag": ("sum_{p in delta-scope} |n0_p . delta_hat| (m) "
                              "— methodology 2.2 rho offset residual with P "
                              "frozen at P0, w=1, angle term 0; diagnostic "
                              "only, never backpropped in 3c"),
        "delta_parameterization": ("one global translation vector "
                                   "(methodology 1.3, no rotation); "
                                   "d_eff = d0 + n0*delta on delta-scope "
                                   "planes only"),
        "delta_scope_planes": state.n_scope_planes,
        "delta_sources": S3["delta_sources"],
        "delta_hat_final": [round(v, 6) for v in delta_final],
        "colors_warmstart": {"file": art["file"], "sha256": art["sha256"],
                             "verified": True},
        "frozen": frozen_keys, "frozen_checksum_ok": bool(frozen_ok),
        "frozen_checksums_sha256": {q: sums1[q] for q in frozen_keys},
        "color_projection": "clamp [0,1] after each Adam step (3b rule)",
        "densify_prune": "never (lifetime rule 1)",
        "alpha": "|o_a-o_b| in {0,1} from s2_faces.initial_real (no free alpha)",
        "tile_dirs": "s3_tiles/s3c_s<step>/ (no collision with 3b s<step>/)",
        "psnr_median": {"step0": round(med0, 3), "final": round(medf, 3)},
        "determinism": det,
    }
    if scope0:
        manifest["s3c_def"]["scope0_note"] = (
            "delta scope is 0 planes — photo gradient on delta is exactly 0, "
            "Adam step is 0, delta stays [0,0,0] (negative record)")
    if recovery:
        manifest["s3c_def"]["injection_recovery"] = recovery
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=1)

    # self checks: tiles exist, 3c steps monotonic in the file
    tiles_ok = all((out_dir / "s3_tiles" / f"s3c_s{k}" / m["view_id"]
                    / f"{n}.png").is_file()
                   for k in ckpts for m in views["rows"]
                   for n in ("render", "residual"))
    assert tiles_ok, "missing 3c tiles"
    seq = [json.loads(ln)["step"] for ln in open(out_dir / "s3_steps.jsonl")
           if json.loads(ln).get("stage") == "3c"]
    assert seq == list(range(steps + 1)), "3c steps not monotonic"

    dh0, dhf = rows_3c[0]["delta_hat"], rows_3c[-1]["delta_hat"]
    print(f"[s3c] {name}: steps {steps} scope {state.n_scope_planes} | "
          f"photo {rows_3c[0]['losses']['photo']} -> "
          f"{rows_3c[-1]['losses']['photo']} | psnr med {med0:.2f} -> "
          f"{medf:.2f} | delta {dh0} -> {dhf}"
          + (f" | recovery {json.dumps(recovery)}" if recovery else "")
          + f" | frozen_ok {frozen_ok} | {time.time()-t0:.0f}s", flush=True)
    return {"name": name, "steps": steps, "scope": state.n_scope_planes,
            "photo": (rows_3c[0]["losses"]["photo"],
                      rows_3c[-1]["losses"]["photo"]),
            "psnr_median": (med0, medf), "delta_hat_final": delta_final,
            "recovery": recovery, "frozen_checksum_ok": frozen_ok}


def main():
    register_injected_scenes()
    runs = sys.argv[1:] or (list(CFG["runs"]) + list(INJECTED))
    out_root = Path(CFG["out_root"])
    for r in runs:
        if r in INJECTED:
            ensure_injected_pipeline(r, out_root)
        build_s3c(r, out_root)


if __name__ == "__main__":
    main()
