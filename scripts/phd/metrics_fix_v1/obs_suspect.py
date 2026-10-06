"""PHD-MAIN-METRICS-FIX-v1 4.5 (part 3): the GT-suspect flag (configs/phd/metrics_fix_v1/gt_suspect_rule_v1.json) and its effect
(jointbuildgs:dev, CPU).

  python obs_suspect.py flag       pre-training: gt_suspect / gt_suspect_evaluated added to every region v2 file; areas with
                                   and without the flagged patches per site x prior
  python obs_suspect.py effect     after the 4.8 spread bundle of the eight results: the error inflow rate of the observation-
                                   error region at B173nb_b10 with and without the flagged patches (main points, |W - GT| >= 0.2 m)
Writes /out/obs/suspect_areas.json, /out/obs/suspect_effect.json. scientific_verdict: null."""
import json
import sys

import numpy as np

from mf_common import OUT, SITES, jdump, log, owner_rows
from src.phd.metrics_v2 import lines

RULE = json.loads((__import__("pathlib").Path("/repo/configs/phd/metrics_fix_v1/gt_suspect_rule_v1.json")).read_text())
V = RULE["values"]


def flag():
    A = np.load(OUT / "obs/appearance_patches.npz")
    Uat = np.load(OUT / "obs/uls_attributes.npz")
    areas = {}
    for site in SITES:
        nr = Uat[f"{site}_number_of_returns"]
        for prior in ("LoD2", "ALS"):
            f = OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz"
            R = dict(np.load(f))
            n_p = len(R["code_ext_v2"])
            up = np.ones(n_p, bool) if site.startswith("B0") else np.zeros(n_p, bool)
            tot = np.zeros(n_p)
            mul = np.zeros(n_p)
            for name, pt, pa, va, kd in owner_rows(site, prior, up):
                if name != "gt_points":
                    continue
                m = (kd == 1) & (nr[pt] >= 0)
                np.add.at(tot, pa[m], 1)
                np.add.at(mul, pa[m], (nr[pt[m]] > 1).astype(float))
            pre = f"{site}_{prior}_"
            patch = A[pre + "patch"]
            slope = A[pre + "slope"]
            adj = (np.nan_to_num(A[pre + "range"], nan=0.0) - V["cell_m"] * np.sqrt(2) * np.tan(np.radians(np.minimum(slope, V["slope_cap_deg"])))) > V["double_layer_m"]
            mlt = (mul[patch] / np.maximum(tot[patch], 1)) >= V["multi_return_share"]
            sus = np.zeros(n_p, bool)
            ev = np.zeros(n_p, bool)
            ev[patch] = tot[patch] > 0
            sus[patch] = (adj | mlt) & ev[patch]
            R["gt_suspect"] = sus
            R["gt_suspect_evaluated"] = ev
            np.savez_compressed(f, **R)
            c = R["code_ext_v2"]
            area = R["area"]
            e = {}
            for cc in (2, 3):
                m = (c == cc) & (R["kind"] == 1) & R["in_eval"]
                e[str(cc)] = dict(patches=int(m.sum()), area_m2=round(float(area[m].sum()), 1), flagged=int((m & sus).sum()),
                                  flagged_area_m2=round(float(area[m & sus].sum()), 1), area_without_m2=round(float(area[m & ~sus].sum()), 1),
                                  flagged_share=round(float(sus[m].mean()), 4) if m.any() else None)
            areas[f"{site}/{prior}"] = e
            log(site, prior, e)
    jdump(OUT / "obs/suspect_areas.json", dict(rule=RULE["rule"], areas=areas, scientific_verdict=None))


def effect():
    out = {}
    for prior in ("LoD2", "ALS"):
        R = np.load(OUT / "regions_v2" / f"regions_ext_v2_B173nb_b10_{prior}.npz")
        rws = np.load(__import__("pathlib").Path("/mt") / "defs" / f"rows_{prior}.npz")
        sus = R["gt_suspect"][rws["patch"]]
        for res in (f"b1_{prior}", f"b2_{prior}", f"surface_{prior}", f"samepath_{prior}"):
            rr = np.load(OUT / "metrics" / f"{res}_rows.npz")
            cls, code, sW = rr["cls"], rr["code_v2"], rr["sW"]
            main = np.abs(sW) >= 0.2
            m3 = (code == 3) & main
            out[res] = dict(with_flagged=lines.shares(cls[m3]), without_flagged=lines.shares(cls[m3 & ~sus]), flagged_only=lines.shares(cls[m3 & sus]),
                            points_flagged_share=round(float(sus[m3].mean()), 4) if m3.any() else None)
            log(res, out[res]["with_flagged"]["spread"], out[res]["without_flagged"]["spread"], out[res]["flagged_only"]["spread"])
    jdump(OUT / "obs/suspect_effect.json", dict(rule=RULE["rule"], region="observation error (code 3, v2), B173nb_b10, main points (|W - GT| >= 0.2 m)",
                                                effect=out, scientific_verdict=None))


if __name__ == "__main__":
    {"flag": flag, "effect": effect}[sys.argv[1]]()
