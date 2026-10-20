"""PHD-MAIN-FIXTEST-v1 9.1-4 (판 A의 기제, A8): the band shares of the rendered depth at iteration 30,000 (jointbuildgs:dev, CPU; run_step_ft.sh).
Stage 2's fine ruler (bands_s2.py) on the training views with the band edges of this task: per pixel |D - P| against w_p, tau_p, 2 tau_p,
4 tau_p -> shares in [0, w), [w, tau), [tau, 2 tau), [2 tau, 4 tau), >= 4 tau.
  D  = the result's dump model/dump/iteration_30000/<view>_depth.npy
  P  = the prior depth of the view (stage-0 fork inputs maps/prior_<prior>), tau_p = maps/tau_<prior>, w_p = this task's w maps of the reading
  pixels: prior pixels with a rendered depth whose patch judgment is agree (unit_judgment 1 of the patch the pixel sees, from the r16-default
          dry init: patch maps lm_<view> and locations.npz) -- 'agree pixels'; recorded too: every pixel with g_p > 0 (stage 2's selection)
          and the agree pixels of support-agreement patches (region code 2)
  python band_w.py <site> <prior> <reading L|T> <result ...>    (results: prop_<prior>_s0, prop_<prior>_s1, fixA_<prior>_s0, ...)
Writes /ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1/mech/bands_<site>_<prior>_<reading>.json (results already in the file are kept; the
results given are counted again). scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S0 = Path("/s0")
S1 = Path("/out")
EDGES = ("w", "tau", "2tau", "4tau")
NAMES = ("lt_w", "w_tau", "tau_2tau", "2tau_4tau", "ge_4tau")


def run_dir(site, res):
    if res.startswith("fix"):
        return FTP / "runs" / site / res
    if site == "B173nb_b10" and res.startswith("prop_"):
        prior = "LoD2" if "LoD2" in res else "ALS"
        return S0 / "stage0" / f"b{1 if res.endswith('s0') else 2}_{prior}"
    if res.startswith("nojudge_"):
        return PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1/runs" / site / res
    if res.startswith("abl_band_"):
        return PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1/runs" / site / res
    return S1 / "stage1" / site / res


def main():
    site, prior, rd = sys.argv[1], sys.argv[2], sys.argv[3]
    results = sys.argv[4:]
    I = S0 / "fork_inputs/s61" / site / "maps"
    Wd = FTP / "prep" / ("wmaps" if rd == "L" else "wmaps_T") / site / prior
    dry = FTP / "checks/dry" / f"r16d_{site}_{prior}" / "model/monitor"
    L = np.load(dry / "locations.npz")
    jl = L["unit_judgment"]
    G = np.load(dry / "gate_check.npz")
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    code = R["code_ext_v3"]
    if len(code) != len(jl):
        raise RuntimeError("region rows != patches")
    views = sorted(k[3:] for k in G.files if k.startswith("lm_"))
    dst = FTP / "mech" / f"bands_{site}_{prior}_{rd}.json"
    old = json.loads(dst.read_text()) if dst.exists() else None      # results counted before stay; the ones given are (re)counted
    out = dict(site=site, prior=prior, reading=rd, w_maps=str(Wd), views=len(views), selection=dict(
        agree="prior pixels with a rendered depth whose patch judgment (unit_judgment) is agree, r16-default dry init",
        g1="every prior pixel with a rendered depth and g_p > 0 (stage 2's bands selection)", agree_c2="agree pixels of region code 2 patches"), results=dict(old["results"]) if old else {})
    for res in results:
        Rd = run_dir(site, res) / "model/dump/iteration_30000"
        acc = {k: np.zeros(5, np.int64) for k in ("agree", "g1", "agree_c2")}
        missing = 0
        for v in views:
            f = Rd / f"{v}_depth.npy"
            if not f.exists():
                missing += 1
                continue
            D = np.load(f).astype(np.float64)
            P = np.load(I / f"prior_{prior}" / f"{v}.npy").astype(np.float64)
            T = np.load(I / f"tau_{prior}" / f"{v}.npy").astype(np.float64)
            W = np.load(Wd / f"{v}.npy").astype(np.float64)
            lm = G[f"lm_{v}"].astype(np.int64)
            g = G[f"g_{v}"].astype(bool)
            ok = np.isfinite(P) & (P > 0) & np.isfinite(T) & np.isfinite(D) & (D > 0) & np.isfinite(W)
            loc = lm >= 0
            ag = np.zeros(lm.shape, bool); ag[loc] = jl[lm[loc]] == 1
            c2 = np.zeros(lm.shape, bool); c2[loc] = code[lm[loc]] == 2
            a = np.abs(D - P)
            b = np.select([a < W, a < T, a < 2 * T, a < 4 * T], [0, 1, 2, 3], 4)
            for k, m in (("agree", ok & ag), ("g1", ok & g), ("agree_c2", ok & ag & c2)):
                acc[k] += np.bincount(b[m], minlength=5)
        out["results"][res] = dict(dump=str(Rd), views_missing=missing,
                                   **{k: dict(n=int(c.sum()), shares={nm: float(c[i] / max(c.sum(), 1)) for i, nm in enumerate(NAMES)}) for k, c in acc.items()})
        print(res, json.dumps({k: [round(100 * x, 2) for x in v["shares"].values()] for k, v in out["results"][res].items() if isinstance(v, dict) and "shares" in v}), flush=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
