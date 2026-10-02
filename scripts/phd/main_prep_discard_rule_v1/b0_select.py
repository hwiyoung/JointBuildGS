"""PHD-MAIN-PREP-DISCARD-RULE-v1 5.3: the nadir-including B0 conditions N13 / N8 / N2 (jointbuildgs:dev, CPU; rule fixed in
configs discard_v1.json 'b0_conditions' before any result).

  python b0_select.py

Pool = the COVER training views (prep step01/b0.json, 209 = 40 nadir + 169 oblique; nadir = tilt <= 20 degrees).
Number of nadir views = max(1, round(n x 40 / 209)) -> N13: 2, N8: 2, N2: 1; the rest oblique.
Greedy coverage of the target building's LoD2 patches (DEBY_LOD2_4959323) with the visibility pairs (patch, view, pixels > 0)
of the prep COVER stage-1 run (prior render, not MVS / residuals / judgments / GT): first the nadir views, then the oblique
views, each step the view adding the most not-yet-seen target patches (ties: name order). Each condition is selected on its
own (no nesting is imposed). Writes mvs_lists/B0_N13.json, B0_N8.json, B0_N2.json and b0_conditions.json (all seven
conditions with their views, counts of nadir / oblique, target-patch coverage). scientific_verdict: null."""
import json

import numpy as np

from common import DCFG, OUT, PREP, Views, jdump, log

TARGET = "DEBY_LOD2_4959323"


def main():
    b0 = json.loads((PREP / "step01/b0.json").read_text())
    conds = b0["conditions"]
    cover = conds["COVER"]["train"]
    V = Views()
    tilt = {n: V.tilt(n) for n in cover}
    nadir_max = float(DCFG["b0_conditions"]["nadir_including"]["pool"].split("tilt <= ")[1].split(" ")[0])
    S1 = PREP / "step03_b0cond/COVER/B0/LoD2"
    pairs = np.load(S1 / "unit_view_pairs.npz")
    U = np.load(S1 / "units.npz")
    tab = {r["ext"]: r for r in json.loads((PREP / "step02/B0/lod2_surfaces.json").read_text())["surfaces"]}
    ext = U["surf_ext"][U["loc_surface"]]
    target = np.array([tab[int(e)]["building"] == TARGET for e in ext])
    views = [str(v) for v in pairs["views"]]
    seen_by = {}
    for vi, loc, npx in zip(pairs["view"], pairs["loc"], pairs["npix"]):
        if npx > 0 and target[loc]:
            seen_by.setdefault(views[vi], set()).add(int(loc))
    n_target = int(target.sum())
    out = {}
    for name, n in (("N13", 13), ("N8", 8), ("N2", 2)):
        nn = max(1, int(round(n * 40 / 209)))
        pools = [sorted(v for v in cover if tilt[v] <= nadir_max), sorted(v for v in cover if tilt[v] > nadir_max)]
        chosen, covered = [], set()
        for pool, k in ((pools[0], nn), (pools[1], n - nn)):
            for _ in range(k):
                best = max((v for v in pool if v not in chosen), key=lambda v: (len(seen_by.get(v, set()) - covered), [-ord(c) for c in v]))
                chosen.append(best); covered |= seen_by.get(best, set())
        jdump(OUT / "mvs_lists" / f"B0_{name}.json", dict(train=sorted(chosen), condition=name))
        out[name] = dict(train=sorted(chosen), n=n, nadir=int(sum(tilt[v] <= nadir_max for v in chosen)), oblique=int(sum(tilt[v] > nadir_max for v in chosen)),
                         target_patches_seen=len(covered), target_patches=n_target, coverage=round(len(covered) / max(n_target, 1), 4),
                         order_of_selection=chosen)
        log(name, out[name]["nadir"], out[name]["oblique"], "coverage", out[name]["coverage"])
    allc = {}
    for k in ("A15", "A9", "A3", "COVER"):
        tr = conds[k]["train"]
        cov = set().union(*[seen_by.get(v, set()) for v in tr]) if tr else set()
        allc[k] = dict(train=tr, n=len(tr), nadir=int(sum(V.tilt(v) <= nadir_max for v in tr)), oblique=int(sum(V.tilt(v) > nadir_max for v in tr)),
                       target_patches_seen=len(cov), coverage=round(len(cov) / max(n_target, 1), 4), source="prep step01/b0.json")
    allc.update({k: {kk: vv for kk, vv in v.items()} for k, v in out.items()})
    jdump(OUT / "b0_conditions.json", dict(rule=__doc__.split("\n\n")[2], target=TARGET, conditions=allc, scientific_verdict=None))


if __name__ == "__main__":
    main()
