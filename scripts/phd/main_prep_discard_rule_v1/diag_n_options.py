"""PHD-MAIN-PREP-DISCARD-RULE-v1 diagnostic for the pending decision on the nadir-including B0 conditions (nothing applied):
what the two proposed rule changes would select, with the same greedy coverage of the target building.
  option 2: N2 only -- the second (oblique) view must share >= 29 sparse points (the author A3 pair) with the first
  option 3: N13 / N8 / N2 -- every new view must share >= 29 sparse points with at least one view already chosen
Shared points = 3-D points of the 937-image sparse model observed in both views. Writes diag/n_options.json.
scientific_verdict: null."""
import json

import numpy as np

from common import DENSE, OUT, PREP, Views, jdump, log, read_images_bin

MIN_SHARED = 29


def main():
    b0 = json.loads((PREP / "step01/b0.json").read_text())
    cover = b0["conditions"]["COVER"]["train"]
    V = Views()
    ims = read_images_bin(DENSE / "sparse/images.bin", with_points=True)
    pts = {n: set(r["pids"][r["pids"] >= 0].tolist()) for n, r in ims.items()}
    tilt = {n: V.tilt(n) for n in cover}
    sel = json.loads((OUT / "b0_conditions.json").read_text())["conditions"]
    S1 = PREP / "step03_b0cond/COVER/B0/LoD2"
    pairs = np.load(S1 / "unit_view_pairs.npz"); U = np.load(S1 / "units.npz")
    tab = {r["ext"]: r for r in json.loads((PREP / "step02/B0/lod2_surfaces.json").read_text())["surfaces"]}
    target = np.array([tab[int(e)]["building"] == "DEBY_LOD2_4959323" for e in U["surf_ext"][U["loc_surface"]]])
    views = [str(v) for v in pairs["views"]]
    seen = {}
    for vi, loc, npx in zip(pairs["view"], pairs["loc"], pairs["npix"]):
        if npx > 0 and target[loc]:
            seen.setdefault(views[vi], set()).add(int(loc))
    nt = int(target.sum())
    shared = lambda a, b: len(pts[a] & pts[b])

    def greedy(n, constrained):
        nn = max(1, int(round(n * 40 / 209)))
        pools = [sorted(v for v in cover if tilt[v] <= 20), sorted(v for v in cover if tilt[v] > 20)]
        chosen, cov = [], set()
        for pool, k in ((pools[0], nn), (pools[1], n - nn)):
            for _ in range(k):
                cand = [v for v in pool if v not in chosen and (not constrained or not chosen or max(shared(v, c) for c in chosen) >= MIN_SHARED)]
                if not cand:
                    return chosen, cov, "no candidate"
                best = max(cand, key=lambda v: (len(seen.get(v, set()) - cov), [-ord(ch) for ch in v]))
                chosen.append(best); cov |= seen.get(best, set())
        return chosen, cov, "ok"

    out = dict(current={k: dict(views=sel[k]["train"], coverage=sel[k]["coverage"],
                                min_pair_shared=min((shared(a, b) for i, a in enumerate(sel[k]["train"]) for b in sel[k]["train"][i + 1:]), default=None))
                        for k in ("N13", "N8", "N2")})
    a3 = b0["conditions"]["A3"]["train"]
    out["author_A3_shared"] = shared(a3[0], a3[1]) if len(a3) == 2 and all(v in pts for v in a3) else None
    o2 = {}
    first = sel["N2"]["order_of_selection"][0]
    cand = [v for v in cover if tilt[v] > 20 and shared(first, v) >= MIN_SHARED]
    if cand:
        cov0 = seen.get(first, set())
        best = max(cand, key=lambda v: (len(seen.get(v, set()) - cov0), [-ord(ch) for ch in v]))
        o2["N2"] = dict(views=sorted([first, best]), coverage=round(len(cov0 | seen.get(best, set())) / nt, 4), shared=shared(first, best))
    out["option2"] = o2
    # option 2b: the (nadir, oblique) pair sharing >= MIN_SHARED points with the largest target coverage (joint choice)
    nad = [v for v in cover if tilt[v] <= 20]; obl = [v for v in cover if tilt[v] > 20]
    best = None
    for a_ in nad:
        for b_ in obl:
            if shared(a_, b_) >= MIN_SHARED:
                c_ = len(seen.get(a_, set()) | seen.get(b_, set()))
                if best is None or c_ > best[0]:
                    best = (c_, a_, b_)
    out["option2b"] = dict(views=[best[1], best[2]], coverage=round(best[0] / nt, 4), shared=shared(best[1], best[2])) if best else None
    out["first_nadir_connected_obliques"] = sum(shared(first, v) >= MIN_SHARED for v in obl)
    o3 = {}
    for k, n in (("N13", 13), ("N8", 8), ("N2", 2)):
        ch, cov, status = greedy(n, True)
        o3[k] = dict(views=sorted(ch), coverage=round(len(cov) / nt, 4), status=status, same_as_current=sorted(ch) == sorted(sel[k]["train"]))
    out["option3"] = o3
    jdump(OUT / "diag/n_options.json", dict(rule=__doc__.split("\n\n")[0], min_shared=MIN_SHARED, **out, scientific_verdict=None))
    log(json.dumps({k: (v.get("coverage"), v.get("same_as_current")) for k, v in o3.items()}), "option2", o2.get("N2", {}).get("coverage"))


if __name__ == "__main__":
    main()
