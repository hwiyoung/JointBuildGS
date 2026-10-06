"""PHD-MAIN-METRICS-FIX-v1 4.5 (part 2): candidate 'GT suspect' rules compared on pre-training data only (jointbuildgs:dev,
CPU). No training result is read; the rule chosen from this table is written to configs/phd/metrics_fix_v1/
gt_suspect_rule_v1.json before its effect on the trainings is computed.

  python obs_rule.py

Per roof-like patch of codes 2 and 3 (regions v2, both priors, four sites), from obs/appearance_patches.npz and the ULS
attributes of its owned GT points (ULS label-source rows):
  double   the GT height range in the patch's 0.25 m cell > 0.3 m (two layers: e.g. glass and what lies under it)
  multi    >= 5 % of the patch's GT points come from pulses with more than one return (the laser went through)
  ring     some 0.5 m cell within 1 m holds no GT point or is excluded
  double_adj  double with the range a plane of the prior face's slope makes over the cell diagonal (0.354 m x tan theta) taken off
              (added after the first table: on steep faces the plain test fires for support agreement too, as the trial's edge band did)
candidates: double, multi, ring, double AND multi, double OR multi, double_adj, double_adj OR multi. For each: the flagged share of code 3 and of code 2 per
site x prior and slope class, and the contrast (share in 3 - share in 2). Writes /out/obs/rule_candidates.json / .md.
scientific_verdict: null."""
import json

import numpy as np

from mf_common import OUT, SITES, jdump, owner_rows, Timer

CANDS = ["double", "multi", "ring", "double_and_multi", "double_or_multi", "double_adj", "double_adj_or_multi"]


def main():
    T = Timer()
    A = np.load(OUT / "obs/appearance_patches.npz")
    U = np.load(OUT / "obs/uls_attributes.npz")
    res, md = {}, []
    md.append("| 지역 · 사전 정보 · 경사 | 패치 (지지 일치 / 관측 오류) | " + " | ".join(CANDS) + " |")
    md.append("|---|---|" + "---|" * len(CANDS))
    agg = {c: [] for c in CANDS}
    for site in SITES:
        nr = U[f"{site}_number_of_returns"]
        for prior in ("LoD2", "ALS"):
            R = np.load(OUT / "regions_v2" / f"regions_ext_v2_{site}_{prior}.npz")
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
            code = A[pre + "code"]
            slope = A[pre + "slope"]
            dbl = np.nan_to_num(A[pre + "range"], nan=0.0) > 0.3
            mlt = (mul[patch] / np.maximum(tot[patch], 1)) >= 0.05
            rng = A[pre + "ring_missing"] > 0
            adj = (np.nan_to_num(A[pre + "range"], nan=0.0) - 0.25 * np.sqrt(2) * np.tan(np.radians(np.minimum(slope, 80.0)))) > 0.3
            flags = dict(double=dbl, multi=mlt, ring=rng, double_and_multi=dbl & mlt, double_or_multi=dbl | mlt, double_adj=adj, double_adj_or_multi=adj | mlt)
            e = {}
            for nm, sm in (("gentle_le17", slope <= 17), ("steep_gt17", slope > 17), ("all", np.ones(len(slope), bool))):
                row = {}
                for c in CANDS:
                    f = flags[c]
                    s3 = float(f[sm & (code == 3)].mean()) if (sm & (code == 3)).any() else None
                    s2 = float(f[sm & (code == 2)].mean()) if (sm & (code == 2)).any() else None
                    row[c] = dict(share_3=None if s3 is None else round(s3, 4), share_2=None if s2 is None else round(s2, 4),
                                  contrast=None if (s3 is None or s2 is None) else round(s3 - s2, 4))
                    if nm == "all" and s3 is not None and s2 is not None:
                        agg[c].append((s3, s2))
                e[nm] = dict(patches_2=int((sm & (code == 2)).sum()), patches_3=int((sm & (code == 3)).sum()), rules=row)
                md.append(f"| {site} · {prior} · {nm} | {e[nm]['patches_2']:,} / {e[nm]['patches_3']:,} | "
                          + " | ".join("—" if row[c]["share_3"] is None or row[c]["share_2"] is None else f"{100 * row[c]['share_3']:.0f} / {100 * row[c]['share_2']:.0f}" for c in CANDS) + " |")
            res[f"{site}/{prior}"] = e
    summ = {c: dict(mean_share_3=round(float(np.mean([a for a, b in v])), 4), mean_share_2=round(float(np.mean([b for a, b in v])), 4),
                    mean_contrast=round(float(np.mean([a - b for a, b in v])), 4)) for c, v in agg.items()}
    md.append("\n| 후보 | 관측 오류 영역에서 표시되는 몫 (평균) | 지지 일치 영역에서 표시되는 몫 (평균) | 차이 |")
    md.append("|---|---|---|---|")
    for c, s in summ.items():
        md.append(f"| {c} | {100 * s['mean_share_3']:.1f} % | {100 * s['mean_share_2']:.1f} % | {100 * s['mean_contrast']:+.1f} %p |")
    jdump(OUT / "obs/rule_candidates.json", dict(candidates=CANDS, per_site=res, summary=summ, seconds=T.mark("all"), scientific_verdict=None))
    (OUT / "obs/rule_candidates.md").write_text("(칸 = 관측 오류 영역 / 지지 일치 영역에서 표시되는 패치의 몫, %)\n\n" + "\n".join(md) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
