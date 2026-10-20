"""PHD-MAIN-FIXTEST-v1 9.1-5 (판 B의 기제, B5) (jointbuildgs:dev, CPU; run_step_ft.sh). In the evaluation range, the missing patches whose
reading fix B changed (item 2: own_depth_changed of the fix-B dry init, previous judgment conflict or mixed), split by the previous judgment
and the region code:
  wrongly released  previous conflict, code 4 (the prior was right)  -> R(0.2 m) of their GT rows (the new distance metric: rows' unsigned
                    distance to the result mesh, dist npz r_d / r_patch)
  rightly released  previous conflict, code 13 (the prior was wrong)  -> past-shape inflow of their GT rows (metrics_s1.spread's rule: thinned
                    rows with |s_W| >= 0.2 m, inflow = wrong side + both of the four-way classes 'cls' of the result's metrics rows)
  mixed             previous mixed, code 4 and code 13 apart (the same two values)
Per group: patches, area (m2), GT rows (all thinned rows / those used). Results: the method's two seeds (prop_<prior>_s0, _s1), fix B, A + B
where trained, and the judgment-only-off method (nojudge_<prior>_s0) as a reference.
  python mech_b.py
Writes /ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1/mech/mech_b.json. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S1 = Path("/out")
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
SD = PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
CASES = [(s, p) for s in ("B0_b10", "B173nb_b10", "R1rep_b10") for p in ("LoD2", "ALS")]


def metrics_rows(site, prior, res):
    for base in (FTP / "metrics", S3 / "metrics", S1 / "metrics"):
        f = base / site / f"{res}__{prior}_rows.npz"
        if f.exists():
            return f
    return None


def dist_file(site, prior, res):
    for base in (FTP / "dist", SD / "dist"):
        f = base / f"{site}_{prior}__{res}.npz"
        if f.exists():
            return f
    return None


def main():
    out = {}
    for site, prior in CASES:
        dry = FTP / "checks/dry" / f"r16B_{site}_{prior}" / "model/monitor/locations.npz"
        if not dry.exists():
            continue
        L = np.load(dry)
        chg, jb = L["own_depth_changed"].astype(bool), L["judgment_before_own_depth"]
        R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
        code, ev, area = R["code_ext_v3"], R["in_eval"].astype(bool), R["area"].astype(np.float64)
        rows = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
        r_pa, r_code, r_thin, r_sW = rows["patch"].astype(np.int64), rows["code"], rows["thin"].astype(bool), rows["sW"].astype(np.float64)
        groups = {"wrong_release_c4": chg & ev & (jb == 0) & (code == 4), "right_release_c13": chg & ev & (jb == 0) & (code == 13),
                  "mixed_c4": chg & ev & (jb == 2) & (code == 4), "mixed_c13": chg & ev & (jb == 2) & (code == 13)}
        res_list = [f"prop_{prior}_s0", f"prop_{prior}_s1", f"fixB_{prior}_s0", f"fixAB_{prior}_s0", f"nojudge_{prior}_s0"]
        e = {}
        def on(mask, pa):
            o = np.zeros(len(pa), bool)
            ok = pa >= 0
            o[ok] = mask[pa[ok]]
            return o
        for g, m in groups.items():
            rr = on(m, r_pa) & r_thin
            e[g] = dict(patches=int(m.sum()), area_m2=float(area[m].sum()), rows_thinned=int(rr.sum()),
                        rows_main=int((rr & (np.abs(r_sW) >= 0.2)).sum()), values={})
            for res in res_list:
                v = {}
                if g.endswith("c4"):
                    f = dist_file(site, prior, res)
                    if f is None:
                        continue
                    z = np.load(f)
                    sel = on(m, z["r_patch"].astype(np.int64))
                    d = z["r_d"][sel].astype(np.float64)
                    v = dict(R_0_2=float((d <= 0.2).mean()) if len(d) else None, n=int(len(d)), source=str(f).replace(str(PH), "PH"))
                else:
                    f = metrics_rows(site, prior, res)
                    if f is None:
                        continue
                    cls = np.load(f)["cls"]
                    sel = rr & (np.abs(r_sW) >= 0.2)
                    c = cls[sel]
                    v = dict(inflow=float(np.isin(c, (1, 2)).mean()) if len(c) else None, gt_side=float((c == 0).mean()) if len(c) else None,
                             neither=float((c == 3).mean()) if len(c) else None, n=int(len(c)), source=str(f).replace(str(PH), "PH").replace("/out", "S1"))
                e[g]["values"][res] = v
        out[f"{site}/{prior}"] = e
    d = FTP / "mech"
    d.mkdir(parents=True, exist_ok=True)
    (d / "mech_b.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", rule=__doc__.split("\n\n")[0], cases=out, scientific_verdict=None), indent=1))
    print(json.dumps({k: {g: (v["patches"], {r: (round(100 * (x.get("R_0_2") if x.get("R_0_2") is not None else (x.get("inflow") or float("nan"))), 1), x.get("n"))
                                                 for r, x in v["values"].items()}) for g, v in e.items()} for k, e in out.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
