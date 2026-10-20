"""PHD-MAIN-PHOTOFIG-v1 [사용자가 더 요청함, 10-20 22시 뒤] places of figures 7 and 8, chosen from the region file, the patch store and the
camera geometry only (as p0_places.py and p1_extra.py); no result file is opened. The two cases were asked for after the fix-test final
report showed their unit values (B173 주변 LoD2 결측 지키기 inflow 20.75 -> 27.49 %, R1 LoD2 폭 좁히기 기록 셈 recall 50.77 -> 63.62 %).
  fig7  B173 주변 LoD2: the face (roofs included) with the most prior-error missing patches (code 13) in the evaluation range.
  fig8  R1 LoD2: the face (roofs included) with the most prior-right missing patches (code 4) in the evaluation range.
A tie goes to the face with the larger area in the range. Photo and section: wall -> p0_places.wall_place (all missing patches of the face);
roof -> the most-pixel vertical training image of the chosen code's patches and a vertical section along their long axis (p1_extra.py).
  python p2_more.py -> /pf/prep/places_more.json   scientific_verdict: null"""
import numpy as np

import p0_places as P0
from pf_common import PF, jdump, now

CASES = {"fig7": ("B173nb_b10", "LoD2", 13), "fig8": ("R1rep_b10", "LoD2", 4)}


def place(site, prior, want, ext=None):
    """ext given (p3_after_more.py): that face; otherwise the face with the most patches of code `want`."""
    R = P0.region(site, prior); U = P0.store(site, prior)
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool); se = R["surf_ext"].astype(int); kind = R["kind"].astype(int)
    m = ev & (code == want)
    u, c = np.unique(se[m], return_counts=True)
    area = {int(e): float(R["area"][ev & (se == e)].sum()) for e in u}
    ranked = sorted(zip(u.tolist(), c.tolist()), key=lambda t: (-t[1], -area[int(t[0])]))
    ext = int(ranked[0][0]) if ext is None else int(ext)
    mp = np.nonzero(m & (se == ext))[0]
    allm = np.nonzero(ev & (se == ext) & np.isin(code, [4, 13]))[0]
    k = int(np.bincount(kind[mp]).argmax())
    if k == 1:
        ph, sc = P0.score_views(site, prior, P0.patch_corners(U, mp), "vertical")
        sec = P0.section_roof(R["centre"][mp][:, :2].astype(np.float64))
        photo = dict(P0.info_view(ph["view"]), score=ph) if ph else None
    else:
        out = P0.wall_place(site, ext, prior); photo, sc, sec = out["photo"], out["photo_search"], out["section"]
    return dict(site=site, prior=prior, ext=ext, kind=k, chosen_code=want, chosen_code_patches=int(len(mp)), missing=int(len(allm)),
                code4=int((code[allm] == 4).sum()), code13=int((code[allm] == 13).sum()),
                top_faces=[dict(ext=int(a), patches=int(b), area_m2=area[int(a)]) for a, b in ranked[:8]],
                photo=photo, photo_search=sc, section=sec)


def main():
    rule = __doc__.split("\n\n")[0]
    rec = dict(made=now(), scientific_verdict=None, place_rule=rule, added="사용자가 더 요청함(고친 판 시험 최종 보고의 단위 값을 본 뒤). 자리는 결과 파일을 열지 않고 고름")
    for key, (site, prior, want) in CASES.items():
        rec[key] = place(site, prior, want)
        p = rec[key]
        print(key, site, p["ext"], "kind", p["kind"], "code", want, p["chosen_code_patches"], "missing", p["missing"], (p["photo"] or {}).get("view"), p["top_faces"][:3])
    jdump(PF / "prep/places_more.json", rec)


if __name__ == "__main__":
    main()
