"""PHD-MAIN-STAGE0-v1 5.2: the nadir-including B0 conditions N13 / N8 / N2 re-selected with the rule of configs
stage0_v1.json 'b0_conditions_v2' (= decision request v1 'na' option 3, chosen 2026-10-06), written before any result
(jointbuildgs:dev, CPU).

  python b0_select_v2.py

Pool = the COVER training views (prep step01/b0.json; nadir = tilt <= 20 degrees). Target patches and their visibility = the
discard task's b0_select.py (LoD2 patches of DEBY_LOD2_4959323; visibility pairs (patch, view, pixels > 0) of the prep COVER
stage-1 run: prior render only, no MVS / residual / judgment / GT). Shared points = 3-D points of the 937-image sparse model
observed in both views; overlap = >= 29 shared points (the author A3 pair).
  1. start pair: the (nadir, oblique) pair with >= 29 shared points and the most target patches seen by either view
     (ties: lexicographic order of (nadir, oblique) names)
  2. then nadir views up to the condition's nadir count, then oblique views: candidates share >= 29 points with at least one
     view already chosen; take the one adding the most not-yet-seen target patches (ties: name order)
Writes mvs_lists/B0_<N>.json and b0_conditions_v2.json (the three conditions with their order of selection, shared points,
coverage; the author conditions and COVER for reference; the discard task's v1 selection for comparison). scientific_verdict: null."""
import json

import numpy as np

from common import DENSE, DR, OUT, PREP, SCFG, Views, jdump, log, read_images_bin

TARGET = "DEBY_LOD2_4959323"


def main():
    C = SCFG["b0_conditions_v2"]
    min_shared = 29
    b0 = json.loads((PREP / "step01/b0.json").read_text())
    conds = b0["conditions"]
    cover = conds["COVER"]["train"]
    V = Views()
    tilt = {n: V.tilt(n) for n in cover}
    ims = read_images_bin(DENSE / "sparse/images.bin", with_points=True)
    pts = {n: set(ims[n]["pids"][ims[n]["pids"] >= 0].tolist()) for n in cover}
    S1 = PREP / "step03_b0cond/COVER/B0/LoD2"
    pairs = np.load(S1 / "unit_view_pairs.npz"); U = np.load(S1 / "units.npz")
    tab = {r["ext"]: r for r in json.loads((PREP / "step02/B0/lod2_surfaces.json").read_text())["surfaces"]}
    target = np.array([tab[int(e)]["building"] == TARGET for e in U["surf_ext"][U["loc_surface"]]])
    views = [str(v) for v in pairs["views"]]
    seen = {}
    for vi, loc, npx in zip(pairs["view"], pairs["loc"], pairs["npix"]):
        if npx > 0 and target[loc]:
            seen.setdefault(views[vi], set()).add(int(loc))
    nt = int(target.sum())
    shared = lambda a, b: len(pts[a] & pts[b])
    nad = sorted(v for v in cover if tilt[v] <= 20.0); obl = sorted(v for v in cover if tilt[v] > 20.0)
    # 1. start pair
    best = None
    for a_ in nad:
        for b_ in obl:
            if shared(a_, b_) >= min_shared:
                key = (len(seen.get(a_, set()) | seen.get(b_, set())), [-ord(c) for c in a_ + b_])
                if best is None or key > best[0]:
                    best = (key, a_, b_)
    if best is None:
        raise SystemExit("no (nadir, oblique) pair shares >= 29 points")
    start = [best[1], best[2]]
    out = {}
    for name, spec in C["counts"].items():
        chosen = list(start); cov = seen.get(start[0], set()) | seen.get(start[1], set())
        steps = [dict(view=start[0], kind="nadir", start_pair=True, new_patches=len(seen.get(start[0], set())), shared_with_chosen=None),
                 dict(view=start[1], kind="oblique", start_pair=True, new_patches=len(cov) - len(seen.get(start[0], set())),
                      shared_with_chosen=shared(start[0], start[1]))]
        status = "ok"
        for pool, kname, want in ((nad, "nadir", spec["nadir"] - 1), (obl, "oblique", spec["oblique"] - 1)):
            for _ in range(want):
                cand = [v for v in pool if v not in chosen and max(shared(v, c) for c in chosen) >= min_shared]
                if not cand:
                    status = f"no connected {kname} candidate"; break
                v = max(cand, key=lambda x: (len(seen.get(x, set()) - cov), [-ord(c) for c in x]))
                steps.append(dict(view=v, kind=kname, start_pair=False, new_patches=len(seen.get(v, set()) - cov),
                                  shared_with_chosen=max(shared(v, c) for c in chosen)))
                chosen.append(v); cov |= seen.get(v, set())
        ss = [shared(x, y) for i, x in enumerate(chosen) for y in chosen[i + 1:]]
        out[name] = dict(train=sorted(chosen), n=len(chosen), nadir=int(sum(tilt[v] <= 20.0 for v in chosen)),
                         oblique=int(sum(tilt[v] > 20.0 for v in chosen)), target_patches_seen=len(cov), target_patches=nt,
                         coverage=round(len(cov) / max(nt, 1), 4), order_of_selection=steps, status=status,
                         min_pair_shared=min(ss) if ss else None, max_pair_shared=max(ss) if ss else None)
        jdump(OUT / "mvs_lists" / f"B0_{name}.json", dict(train=sorted(chosen), condition=name, rule="b0_conditions_v2"))
        log(name, status, out[name]["nadir"], out[name]["oblique"], "coverage", out[name]["coverage"])
    ref = {}
    for k in ("A15", "A9", "A3", "COVER"):
        tr = conds[k]["train"]
        cov = set().union(*[seen.get(v, set()) for v in tr]) if tr else set()
        ref[k] = dict(train=tr, n=len(tr), nadir=int(sum(V.tilt(v) <= 20.0 for v in tr)), oblique=int(sum(V.tilt(v) > 20.0 for v in tr)),
                      coverage=round(len(cov) / max(nt, 1), 4), source="prep step01/b0.json")
    v1 = json.loads((DR / "b0_conditions.json").read_text())["conditions"]
    jdump(OUT / "b0_conditions_v2.json", dict(rule=C["selection"], rule_source=C["rule_source"], min_shared=min_shared, target=TARGET,
                                              target_patches=nt, start_pair=dict(views=start, shared=shared(*start), coverage=round(best[0][0] / nt, 4)),
                                              conditions=out, reference=ref,
                                              v1_selection={k: dict(train=v1[k]["train"], coverage=v1[k]["coverage"]) for k in ("N13", "N8", "N2")},
                                              scientific_verdict=None))


if __name__ == "__main__":
    main()
