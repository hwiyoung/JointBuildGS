#!/usr/bin/env python3
"""S3b bundle writer — phd_s3_verify_s3b_v1 (stage 3b "color-only warm-up").

Geometry stays byte-frozen: the ONLY trained leaf is colors (A_g). Planes P,
delta, occupancy-derived alpha and the seed set are held and verified by
sha256 checksums before/after training (any mismatch aborts the run).
Backward still flows into EVERY leaf, so the per-group gradient norms of the
frozen groups are recorded each step — the observation "how geometry pressure
evolves while color converges". No densification/pruning (lifetime rule 1);
alpha = |o_a-o_b| in {0,1} stays derived (no free alpha).

Adds to runs/<name>/ (on top of s1+s2+s3a):
  s3_steps.jsonl                        3b rows appended (3a rows preserved)
  s3_tiles/s<step>/<view_id>/{render,residual}.png   checkpoints only
                                        (photo tiles stay the 3a ones)
  s3_face_residual_final.json           final-state residual, 3a approximation
  manifest.json                         stage -> s1+s2+s3a+s3b, s3b_def

Usage (container):
  bash scripts/p2/arrgs_v1/run_host.sh <gpu> \
      scripts/phd/s3_verify_v1/build_s3b_bundle.py [run ...]   # default: all
"""
from __future__ import annotations

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
for p in (HERE, REPO / "scripts/p2/arrgs_v1"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from render_state import (S3RenderState, anchor_terms, color_stats,  # noqa: E402
                          load_bundle_state, photo_l1_backward, real_views,
                          state_checksums, synth_views, write_render_tiles)
from build_s3a_bundle import face_residuals, render_views  # noqa: E402

CFG = json.load(open(REPO / "configs/phd/s3_verify_v1/s1_bundle_v1.json"))
S3 = CFG["s3"]
S3B = S3["b"]
S3B_SCHEMA = "phd_s3_verify_s3b_v1"
PLANE_KEYS = ("plane_n_raw", "plane_d", "delta")  # cheap per-step subset


def set_determinism(seed):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)
    return {
        "torch_manual_seed": seed, "numpy_seed": seed,
        "cudnn_deterministic": True, "cudnn_benchmark": False,
        "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"],
        "use_deterministic_algorithms": (
            "warn_only=True — gsplat rasterization backward uses atomic "
            "accumulation (order non-deterministic on GPU)"),
        "rerun_tolerance_jsonl": float(S3B["rerun_tolerance_jsonl"]),
    }


def median_psnr(views_psnr):
    vals = [v for v in views_psnr.values() if v is not None]
    return float(np.median(vals)) if vals else None


def build_s3b(name, out_root):
    t0 = time.time()
    out_dir = Path(out_root) / "runs" / name
    manifest = json.load(open(out_dir / "manifest.json"))
    assert manifest["stage"] in ("s1+s2+s3a", "s1+s2+s3a+s3b"), manifest["stage"]

    det = set_determinism(int(S3B["seed"]))
    st = load_bundle_state(out_dir)
    n_seeds = len(st["seed_uv"])
    assert n_seeds == manifest["counts"]["seeds"], (
        f"seed count {n_seeds} != manifest {manifest['counts']['seeds']}")

    state = S3RenderState(st, S3, device="cuda")
    sums0 = state_checksums(state)
    assert np.isin(state.alpha_g.cpu().numpy(), (0.0, 1.0)).all(), \
        "alpha not binary"

    views = (synth_views(S3) if name == "SYNTH_GABLE"
             else real_views(name, S3))
    views["masks_t"] = torch.tensor(views["masks"],
                                    device=views["targets"].device)

    steps = int(S3B["steps"])
    ckpts = sorted(set(int(c) for c in S3B["checkpoints"]) | {0, steps})
    assert all(0 <= c <= steps for c in ckpts), ckpts
    lr = float(S3B["lr_rgb"])
    opt = torch.optim.Adam([{"params": [state.colors], "lr": lr}])

    lam_a = float(S3["lambda_area"])
    terms = anchor_terms(st)
    anchor_const = terms["anchor_cell"] + terms["anchor_plane"]
    area_const = lam_a * terms["area_gate_m2"]

    leaves = (state.plane_n_raw, state.plane_d, state.delta, state.colors)
    rows_3b, psnr_by_ckpt = [], {}
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
        sums_k = state_checksums(state, keys=PLANE_KEYS)
        planes_frozen = all(sums_k[q] == sums0[q] for q in PLANE_KEYS[:2])
        delta_frozen = (sums_k["delta"] == sums0["delta"]
                        and bool((state.delta.detach() == 0).all()))
        assert planes_frozen and delta_frozen, f"frozen group moved at {k}"
        row = {
            "step": k, "stage": "3b",
            "losses": {"photo": round(photo, 6),
                       "anchor": round(anchor_const, 6),
                       "area": round(area_const, 6),
                       "total": round(photo + anchor_const + area_const, 6)},
            "grad_norms": {q: float(f"{v:.6g}") for q, v in gn.items()},
            "param_step_norms": {"delta": 0.0, "planes": 0.0, "colors": 0.0},
            "invariants": {"delta_frozen": delta_frozen,
                           "planes_frozen": planes_frozen,
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
                out_dir / "s3_tiles" / f"s{k}" / m["view_id"], r,
                int(S3["tile_max_px"]), float(S3["residual_vmax"]))
                for r, m in zip(vrows, views["rows"])]
            if k == steps:
                final_rows, final_residuals = vrows, residuals
        if k < steps:  # final row = post-training evaluation, no update
            before = state.colors.detach().clone()
            opt.step()
            with torch.no_grad():
                state.colors.clamp_(0.0, 1.0)
                dn = float(torch.linalg.vector_norm(
                    state.colors.detach() - before))
            row["param_step_norms"]["colors"] = float(f"{dn:.6g}")
        rows_3b.append(row)

    sums1 = state_checksums(state)
    frozen_ok = (sums1 == sums0)
    assert frozen_ok, {q: (sums0[q], sums1[q])
                       for q in sums0 if sums0[q] != sums1[q]}
    assert np.isin(state.alpha_g.cpu().numpy(), (0.0, 1.0)).all(), \
        "alpha not binary after training"

    med0, medf = (median_psnr(psnr_by_ckpt[0]),
                  median_psnr(psnr_by_ckpt[steps]))
    assert med0 is not None and medf is not None and medf > med0, \
        f"PSNR median did not improve: {med0} -> {medf}"

    # append 3b rows; preserve 3a rows byte-exact, drop stale 3b rows (rerun)
    kept = [ln.rstrip("\n") for ln in open(out_dir / "s3_steps.jsonl")
            if ln.strip() and json.loads(ln).get("stage") != "3b"]
    assert kept and json.loads(kept[0])["stage"] == "3a", "3a row missing"
    with open(out_dir / "s3_steps.jsonl", "w") as f:
        for ln in kept:
            f.write(ln + "\n")
        for row in rows_3b:
            f.write(json.dumps(row) + "\n")

    per_face, n_sampled = face_residuals(st, state, views, final_rows,
                                         final_residuals, S3["face_residual"])
    fr3a = json.load(open(out_dir / "s3_face_residual.json"))
    json.dump({"step": steps, "stage": "3b", "method": fr3a["method"],
               "n_views": len(final_rows), "faces_sampled": n_sampled,
               "per_face": per_face},
              open(out_dir / "s3_face_residual_final.json", "w"))

    manifest["stage"] = "s1+s2+s3a+s3b"
    manifest["s3b_schema"] = S3B_SCHEMA
    manifest["s3b_def"] = {
        "stage": "3b", "trained": ["colors"],
        "optimizer": "adam (torch.optim.Adam, default betas 0.9/0.999 eps 1e-8)",
        "lr": lr,
        "lr_source": ("scripts/p2/arrgs_v1/arrgs_train.py L291 "
                      "lr.get('rgb', 2.5e-2); optimizer L296 "
                      "torch.optim.Adam(param_groups)"),
        "steps": steps, "rows": len(rows_3b), "checkpoints": ckpts,
        "row_semantics": ("row k = losses/grad_norms at the pre-update state "
                          "of step k; param_step_norms = the update applied "
                          "at step k (final row is evaluation only, "
                          "colors 0.0)"),
        "frozen": sorted(sums0), "frozen_checksum_ok": bool(frozen_ok),
        "frozen_checksums_sha256": sums1,
        "color_projection": ("clamp [0,1] after each Adam step — legacy "
                             "trains pre-sigmoid rgb_raw; here colors are "
                             "the direct 3a leaf (3a compat), Adam's "
                             "per-parameter scaling absorbs the "
                             "parameterization difference"),
        "densify_prune": "never (lifetime rule 1)",
        "alpha": "|o_a-o_b| in {0,1} from s2_faces.initial_real (no free alpha)",
        "color_stats_def": ("mean_saturation = mean(max(RGB)-min(RGB)) per "
                            "gaussian; color_var = across-gaussian variance "
                            "averaged over channels"),
        "psnr_median": {"step0": round(med0, 3), "final": round(medf, 3)},
        "determinism": det,
    }
    json.dump(manifest, open(out_dir / "manifest.json", "w"), indent=1)

    # self checks: tiles exist, 3b steps strictly monotonic in the file
    tiles_ok = all((out_dir / "s3_tiles" / f"s{k}" / m["view_id"] / f"{n}.png")
                   .is_file()
                   for k in ckpts for m in views["rows"]
                   for n in ("render", "residual"))
    assert tiles_ok, "missing 3b tiles"
    seq = [json.loads(ln)["step"] for ln in open(out_dir / "s3_steps.jsonl")
           if json.loads(ln).get("stage") == "3b"]
    assert seq == list(range(steps + 1)), "3b steps not monotonic"

    cs0, csf = rows_3b[0]["color_stats"], rows_3b[-1]["color_stats"]
    print(f"[s3b] {name}: steps {steps} views {len(views['rows'])} "
          f"seeds {n_seeds} | photo {rows_3b[0]['losses']['photo']} -> "
          f"{rows_3b[-1]['losses']['photo']} | psnr med {med0:.2f} -> "
          f"{medf:.2f} | sat {cs0['mean_saturation']:.4f} -> "
          f"{csf['mean_saturation']:.4f} var {cs0['color_var']:.6f} -> "
          f"{csf['color_var']:.6f} | frozen_ok {frozen_ok} | "
          f"faces sampled {n_sampled}/{len(st['face_ids'])} | "
          f"{time.time()-t0:.0f}s", flush=True)
    return {"name": name, "steps": steps,
            "photo": (rows_3b[0]["losses"]["photo"],
                      rows_3b[-1]["losses"]["photo"]),
            "psnr_median": (med0, medf), "frozen_checksum_ok": frozen_ok}


def main():
    runs = sys.argv[1:] or CFG["runs"]
    out_root = Path(CFG["out_root"])
    for r in runs:
        build_s3b(r, out_root)


if __name__ == "__main__":
    main()
