"""PHD-MAIN-PHOTOFIG-v1 [결과를 본 뒤 더함] an extra place for figure 3, chosen from the region file and the camera geometry only (as
p0_places.py): the R1 LoD2 face (roofs included) with the most prior-error missing patches (code 13) in the evaluation range; a tie goes
to the face with the larger area in the range. Added after the locked wall 49 showed no past-shape inflow in any result.
  python p1_extra.py -> /pf/prep/places_after.json   scientific_verdict: null"""
import numpy as np

import p0_places as P0
from pf_common import PF, jdump, now


def main():
    site, prior = "R1rep_b10", "LoD2"
    R = P0.region(site, prior); U = P0.store(site, prior)
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool); se = R["surf_ext"].astype(int); kind = R["kind"].astype(int)
    m = ev & (code == 13)
    u, c = np.unique(se[m], return_counts=True)
    area = {int(e): float(R["area"][ev & (se == e)].sum()) for e in u}
    best = max(zip(u.tolist(), c.tolist()), key=lambda t: (t[1], area[int(t[0])]))
    ext = int(best[0])
    mp = np.nonzero(m & (se == ext))[0]
    P = P0.patch_corners(U, mp)
    k = int(np.bincount(kind[mp]).argmax())
    if k == 1:
        ph, sc = P0.score_views(site, prior, P, "vertical")
        sec = P0.section_roof(R["centre"][mp][:, :2].astype(np.float64))
    else:
        out = P0.wall_place(site, ext); ph, sc, sec = out["photo"], out["photo_search"], out["section"]
    rec = dict(fig3_extra2=dict(site=site, prior=prior, ext=ext, kind=k, code13=int(len(mp)), ties=[dict(ext=int(a), code13=int(b), area_m2=area[int(a)]) for a, b in zip(u, c)],
                                photo=(dict(P0.info_view(ph["view"]), score=ph) if ph and "view" in ph and k == 1 else ph), photo_search=sc, section=sec,
                                place_rule=__doc__.split("\n\n")[0], added="결과를 본 뒤 더함"), made=now(), scientific_verdict=None)
    jdump(PF / "prep/places_after.json", rec)
    print(ext, len(mp), rec["fig3_extra2"]["ties"], (rec["fig3_extra2"]["photo"] or {}).get("view"))


if __name__ == "__main__":
    main()
