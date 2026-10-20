"""PHD-MAIN-FIXTEST-v1 6.1 / 6.2 (jointbuildgs:dev, CPU): per-view band-end maps w_p of fix A for one box and prior, made the way the
stage-0 export made the per-view tau maps the fork reads (scripts/phd/main_stage0_v1/s03_stage1_v6.py pass 3 --export-fork, the box
runs of run_51.sh: --mesh-sub /dr/s02_box --mvs /prep/mvs/box_<box> --fix-from /dr/s52/s03/<search region>):
  tau_px = tau_roof where the hit face is roof-like, tau_wall where wall-like (building faces), tau_roof elsewhere;
  map    = tau_px / max(f, 1e-3) on every hit pixel (f = conversion.factor: the residual direction to camera depth), NaN elsewhere.
The w map takes w_roof / w_wall in place of tau_roof / tau_wall (the airborne LiDAR wall takes the roof value as its tau does).
Check first: the same code with tau must give back every stored tau map of the training views bit for bit (else nothing is written).

  python w_maps.py <B0_b10|B173nb_b10|R1rep_b10> <LoD2|ALS> [--check-only]
w comes from /out/prep/w1/<search region>_<prior>.json (일 1). Outputs /out/prep/wmaps/<box>/<prior>/<view>.npy and summary.json.
scientific_verdict: null."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1")
sys.path.insert(0, "/repo")
from common import GRID_H, GRID_W, Views  # noqa: E402
from s03_stage1_v6 import Prior  # noqa: E402
from src.phd.prior_propagation_v6 import conversion as conv  # noqa: E402

DR, PREP, S0 = Path("/dr"), Path("/prep"), Path("/s0")
SEARCH = {"B0_b10": "B0", "B173nb_b10": "R2", "R1rep_b10": "R1"}


def maps_for(pr, sc, V, n):
    Dr = V.rays(n); C = V.C(n)
    t, tri = sc.cast(C, Dr)
    hit = tri >= 0
    idx = np.nonzero(hit.ravel())[0]
    trif = tri.ravel()[idx]
    d = Dr.reshape(-1, 3)[idx].astype(np.float64)
    nn = pr.n_used[trif]
    f = conv.factor(nn, d)
    bf = pr.bface_tri[trif]
    kind = conv.surface_kind(nn[:, 2])
    return idx, f, bf, kind


def one_map(idx, f, bf, kind, roof, wall):
    v_px = np.where(bf, np.where(kind == conv.KIND_ROOF, roof, wall), roof)
    tm = np.full(GRID_H * GRID_W, np.nan, np.float32)
    tm[idx] = (v_px / np.maximum(f, 1e-3)).astype(np.float32)
    return tm.reshape(GRID_H, GRID_W)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("box", choices=list(SEARCH)); ap.add_argument("prior", choices=["LoD2", "ALS"])
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--reading", choices=["L", "T"], default="L", help="the reading of the item-1 table whose w is used (w_decision_<reading>.json)")
    a = ap.parse_args()
    t0 = time.time()
    R = SEARCH[a.box]
    fs = json.loads((DR / "s52/s03" / R / a.prior / "summary.json").read_text())
    shift = np.asarray(fs["registration"]["shift_applied"], np.float64)
    tau_roof, tau_wall = float(fs["tolerance"]["roof"]["tau"]), float(fs["tolerance"]["wall"]["tau"])
    fi = json.loads((S0 / "fork_inputs/s61" / a.box / "fork_inputs.json").read_text())[a.prior]
    if not (np.isclose(fi["tau_roof"], tau_roof, rtol=0, atol=0) and np.isclose(fi["tau_wall"], tau_wall, rtol=0, atol=0)
            and np.array_equal(np.asarray(fi["shift"], np.float64), shift)):
        raise RuntimeError(f"fork inputs {fi} differ from the fixed values {tau_roof} {tau_wall} {shift.tolist()}")
    w_roof = w_wall = None
    if not a.check_only:
        wd = json.loads(Path(f"/out/prep/w_decision_{a.reading}.json").read_text())["cases"][f"{a.box}/{a.prior}"]
        w_roof = float(wd["w_roof"])
        w_wall = float(wd["w_wall"]) if a.prior == "LoD2" else w_roof
    views = json.loads((PREP / "step06/box_views.json").read_text())["views"][a.box]["train"]
    mvs = PREP / "mvs" / f"box_{a.box}"
    views = [n for n in views if (mvs / "stereo/depth_maps" / f"{n}.geometric.bin").exists()]
    tau_dir = S0 / "s61/export" / a.box / a.prior / "tau"
    stems = sorted(p.stem for p in tau_dir.glob("*.npy"))
    if sorted(n.rsplit(".", 1)[0] for n in views) != stems:
        raise RuntimeError(f"views {len(views)} and stored tau maps {len(stems)} differ")
    V = Views()
    pr = Prior(DR / "s02_box" / a.box, a.prior)
    pr.shift = shift
    sc, _ = pr.scene()
    out = Path("/out/prep/wmaps" if a.reading == "L" else "/out/prep/wmaps_T") / a.box / a.prior
    out.mkdir(parents=True, exist_ok=True)
    rep = dict(task_id="PHD-MAIN-FIXTEST-v1", box=a.box, prior=a.prior, search_region=R, reading=a.reading, shift=shift.tolist(), tau_roof=tau_roof, tau_wall=tau_wall,
               w_roof=w_roof, w_wall=w_wall, views=len(views), rule=__doc__.split("\n\n")[0], tau_maps_equal=0, tau_maps_differ=[],
               narrowed_pixels=0, prior_pixels=0, sha256={}, scientific_verdict=None)
    bad = []
    for n in views:
        stem = n.rsplit(".", 1)[0]
        idx, f, bf, kind = maps_for(pr, sc, V, n)
        tm = one_map(idx, f, bf, kind, tau_roof, tau_wall)
        ref = np.load(tau_dir / f"{stem}.npy")
        same = ref.shape == tm.shape and np.array_equal(np.isnan(ref), np.isnan(tm)) and np.array_equal(ref[~np.isnan(ref)].view(np.uint32), tm[~np.isnan(tm)].view(np.uint32))
        if same:
            rep["tau_maps_equal"] += 1
        else:
            bad.append(stem)
        if not a.check_only:
            wm = one_map(idx, f, bf, kind, w_roof, w_wall)
            fin = np.isfinite(wm)
            rep["prior_pixels"] += int(fin.sum()); rep["narrowed_pixels"] += int((wm[fin] < tm[fin]).sum())
            np.save(out / f"{stem}.npy", wm)
    rep["tau_maps_differ"] = bad
    if bad:
        for p in out.glob("*.npy"):
            p.unlink()
        rep["written"] = False
        (out / "summary.json").write_text(json.dumps(rep, indent=1))
        raise SystemExit(f"tau maps not reproduced bit for bit in {len(bad)} views: nothing written")
    rep["written"] = not a.check_only
    if not a.check_only:
        rep["sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.npy"))[:3]}
        rep["sha256_note"] = "first three files only"
    rep["seconds"] = round(time.time() - t0, 1)
    (out / ("summary.json" if not a.check_only else "check_tau.json")).write_text(json.dumps(rep, indent=1))
    print("[w_maps]", a.box, a.prior, "tau maps equal", rep["tau_maps_equal"], "/", len(views), "written", rep["written"], "w", w_roof, w_wall,
          "narrowed", rep["narrowed_pixels"], "/", rep["prior_pixels"], f"{rep['seconds']}s", flush=True)


if __name__ == "__main__":
    main()
