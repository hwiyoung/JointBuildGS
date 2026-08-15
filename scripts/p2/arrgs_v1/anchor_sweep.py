#!/usr/bin/env python3
"""S3+4 anchor experiment: L_occ_prior w-sweep (P2-ARRGS-ANCHOR-v1).

The v1 loss had no occupancy-prior term (o_init was initialization only, so
annealing could erase it -> hole punching). This sweep tests whether that
missing MAP anchor was the confound behind "global co-optimization rejected".

Pre-registered expectations (2026-08-15, scientific_verdict stays null):
  SYN gate (gable, proxy init = GT + 15% flip noise):
    w=0    -> v1 behaviour reproduced (plumbing check)
    w>=5   -> anchor freezes o_init INCLUDING its flip noise
              (occupancy_accuracy ~= 1 - proxy_flip ~= 0.85)
    mid w  -> render evidence corrects the noise while the anchor holds the
              rest: occupancy_accuracy >= 0.95. Fail -> fixed-scalar anchor
              cannot separate noise from signal even in synthetic.
  REAL triad (same proxy-f1 recipe for run and oracle, e1 crop, tau=0.5):
    exists w*: f1(B022,w*) >= 0.9 x f1(oracle B022)
           and f1(B036,w*) >= 0.9 x f1(oracle B036)
           and f1(B173,w*) >= 0.35 (photometric discretion survives on the
                                     changed building; oracle there is 0.077)
    No such w* -> fixed anchor insufficient; occlusion-context rendering and
    per-cell attenuation (occ_w) get promoted to primary causes.
  Metric semantics: proxy f1 is model-samples vs E1 crop cls6, both arms and
  oracle scored by the SAME recipe -- relative readout only; the sealed
  geometry_eval chain stays the official scorer for the chosen w.

Usage: anchor_sweep.py syn|real|all [only-run-name]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arrgs_train import run  # noqa: E402
from export_eval_points import sample_obj  # noqa: E402
from xreal_run import BUILDINGS, BASE as REAL_BASE, scene_for, OUT  # noqa: E402

ROOT = OUT / "P2-ARRGS-ANCHOR-v1"
ORACLE_RUNS = OUT / "P2-ARRGS-ORACLE-v1/runs"
E1_DIR = Path("/artifacts/JointBuildGS/phase-payloads/p2/e1_e6_roofer_ox_review_v1/"
              "P2-E1-E6-GATE5-DASHBOARD-v1/assets_roofer_input/E1")

# post-hoc grid extension (recorded): the first syn pass froze all flips at
# w>=0.05 -- the render-evidence gradient per cell is far weaker than guessed,
# so the transition region sits at smaller w. Grid now spans decades downward.
# second extension (recorded): w=0.001 still froze every flip -> probe the
# micro range to locate (or refute) the scalar transition before concluding.
W_GRID_SYN = [0.0, 0.00001, 0.00003, 0.0001, 0.0003,
              0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.25, 1.0, 5.0]
W_GRID_REAL = [0.0, 0.001, 0.005, 0.02, 0.1, 0.5, 5.0]
TAU = 0.5

_PLY_T = {"float": ("<f4", 4), "float32": ("<f4", 4), "double": ("<f8", 8),
          "uchar": ("u1", 1), "uint8": ("u1", 1), "int": ("<i4", 4),
          "uint": ("<u4", 4), "short": ("<i2", 2), "ushort": ("<u2", 2)}


def read_ply_xyz_cls(path):
    """Minimal binary_little_endian PLY reader -> (xyz, classification|None)."""
    with open(path, "rb") as f:
        head = b""
        while not head.endswith(b"end_header\n"):
            head += f.readline()
        n, props = 0, []
        for ln in head.decode().splitlines():
            t = ln.split()
            if t[:2] == ["element", "vertex"]:
                n = int(t[2])
            elif t and t[0] == "property":
                props.append((t[2], _PLY_T[t[1]][0]))
        rec = np.dtype(props)
        arr = np.frombuffer(f.read(n * rec.itemsize), dtype=rec, count=n)
    xyz = np.stack([arr["x"], arr["y"], arr["z"]], axis=1).astype(np.float64)
    cls = arr["classification"] if "classification" in arr.dtype.names else None
    return xyz, cls


def f1_proxy(model_xyz, ref_xyz, tau=TAU, cap=400_000, seed=0):
    """Bidirectional f1@tau, same recipe for every arm (relative use only)."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    def sub(a):
        return a[rng.choice(len(a), cap, replace=False)] if len(a) > cap else a
    m, r = sub(model_xyz), sub(ref_xyz)
    if len(m) == 0 or len(r) == 0:
        return {"f1": 0.0, "precision": 0.0, "completeness": 0.0}
    prec = float((cKDTree(r).query(m, k=1)[0] <= tau).mean())
    comp = float((cKDTree(m).query(r, k=1)[0] <= tau).mean())
    f1 = 2 * prec * comp / max(prec + comp, 1e-9)
    return {"f1": round(f1, 4), "precision": round(prec, 4),
            "completeness": round(comp, 4)}


def score_run(run_dir, bkey):
    obj = Path(run_dir) / "s5_brep.obj"
    ref = E1_DIR / f"{bkey}.points.ply"
    if not obj.is_file() or not ref.is_file():
        return None
    xyz, cls = sample_obj(obj)
    ref_xyz, ref_cls = read_ply_xyz_cls(ref)
    if ref_cls is not None:
        ref_xyz = ref_xyz[ref_cls == 6]
    return f1_proxy(xyz[cls == 6], ref_xyz)


def oracle_scores():
    out = {}
    for bk, meta in BUILDINGS.items():
        idx = bk  # oracle runs are named by B-idx
        d = ORACLE_RUNS / idx
        s = score_run(d, meta["bkey"]) if d.is_dir() else None
        out[bk] = s
    return out


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    only = sys.argv[2] if len(sys.argv) > 2 else None
    (ROOT / "runs").mkdir(parents=True, exist_ok=True)
    summary_path = ROOT / "anchor_summary.json"
    summary = json.load(open(summary_path)) if summary_path.is_file() else {}

    def tag(w):  # unified w-notation: w0, w1e-05, w0.005, w5 (dirs renamed 2026-08-16)
        return "w0" if w == 0 else f"w{w:g}"

    runs = []
    if which in ("syn", "all"):
        for w in W_GRID_SYN:
            runs.append((f"gable_{tag(w)}", {
                "scene": {"type": "synthetic", "kind": "gable"},
                "o_init": "proxy", "iters": 4000, "gaussians": 6000,
                "lambda": {"occ_prior": w}}, None))
    if which in ("real", "all"):
        for bk in ("B022", "B036", "B173"):
            for w in W_GRID_REAL:
                cfg = dict(REAL_BASE)
                cfg["scene"] = scene_for(bk)
                cfg["lambda"] = {"occ_prior": w}
                runs.append((f"{bk}_{tag(w)}", cfg, bk))

    for name, cfg, bk in runs:
        if only and not name.startswith(only):
            continue
        if (ROOT / "runs" / name / "metrics.json").is_file():
            print(f"[anchor] skip done: {name}", flush=True)
            continue
        cfg = dict(cfg)
        cfg["out_dir"] = str(ROOT / "runs" / name)
        print(f"[anchor] ===== {name} (w={cfg['lambda']['occ_prior']}) =====",
              flush=True)
        try:
            m = run(cfg)
            row = {k: m.get(k) for k in (
                "occupancy_accuracy", "ghost_faces", "missing_faces",
                "psnr_eval_final", "o_undecided", "occ_final",
                "lambda_occ_prior", "wall_s")}
            if bk:
                row["f1_proxy_e1"] = score_run(cfg["out_dir"], BUILDINGS[bk]["bkey"])
            summary[name] = row
        except Exception as e:  # keep the grid going; failures are data
            import traceback
            traceback.print_exc()
            summary[name] = {"error": str(e)}
        json.dump(summary, open(summary_path, "w"), indent=1, default=str)

    # ---- verdict block (recomputed from whatever rows exist) ----
    verdict = {"oracle_f1_proxy": oracle_scores() if which != "syn" else None}
    syn = {k: v for k, v in summary.items() if k.startswith("gable_")}
    if syn:
        accs = {k: v.get("occupancy_accuracy") for k, v in syn.items()}
        mids = [accs.get(f"gable_{tag(w)}") for w in W_GRID_SYN if 0 < w < 5.0]
        verdict["SYN"] = {
            "acc_by_w": accs,
            "w0_reproduces_v1": accs.get(f"gable_{tag(0)}") is not None,
            "freeze_keeps_noise": (accs.get(f"gable_{tag(5.0)}") or 0) <= 0.92,
            "mid_w_corrects_noise": any((a or 0) >= 0.95 for a in mids),
        }
    if which != "syn":
        orc = verdict["oracle_f1_proxy"]
        joint = {}
        for w in W_GRID_REAL:
            f = {bk: (summary.get(f"{bk}_{tag(w)}", {}).get("f1_proxy_e1") or {}
                      ).get("f1") for bk in ("B022", "B036", "B173")}
            gates = {bk: round(0.9 * orc[bk]["f1"], 3) if orc.get(bk) else None
                     for bk in ("B022", "B036")}
            ok_unchanged = all(
                f[bk] is not None and gates[bk] is not None and
                f[bk] >= gates[bk] for bk in ("B022", "B036"))
            ok_changed = f["B173"] is not None and f["B173"] >= 0.35
            joint[tag(w)] = {"f1": f, "hold_gate_0.9xORACLE": gates,
                             "discretion_gate": 0.35,
                             "unchanged_hold": ok_unchanged,
                             "changed_discretion": ok_changed,
                             "joint_pass": ok_unchanged and ok_changed}
        verdict["REAL"] = joint
        verdict["exists_joint_w"] = any(v["joint_pass"] for v in joint.values())
    summary["_verdict"] = verdict
    json.dump(summary, open(summary_path, "w"), indent=1, default=str)
    print("[anchor] verdict ->", json.dumps(verdict, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
