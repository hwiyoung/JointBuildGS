"""PHD-MAIN-PHOTOFIG-v1 [결과를 본 뒤 더함] an extra place for figure 7: the locked wall 99 showed the same past-shape inflow in every result
(51.5 %, 103 rows), while the unit inflow of B173 주변 LoD2 rose from 20.75 % (the method's two-seed mean) to 27.49 % (결측 지키기).
Extra place = the B173 주변 LoD2 face where the past-shape inflow rows rose the most from the two-seed mean to 결측 지키기 (rows = S1/defs
rows of code 13, thinned, |s_W| >= 0.2 m; inflow = the result's class 'cls' 1 or 2, as f3_r1.py and the fix-test area_b.py); a tie goes to
the face with more such rows. Photo and section from the face's code-13 patches as p2_more.py. The per-face table of the rise is kept.
  python p3_after_more.py -> /pf/prep/places_after_more.json   scientific_verdict: null"""
import numpy as np

import p0_places as P0
import p2_more
from pf_common import FT, PF, S1, jdump, now

SITE, PRIOR = "B173nb_b10", "LoD2"
RUNS = {"지금 방법 씨앗 0": S1 / "metrics" / SITE / "prop_LoD2_s0__LoD2_rows.npz", "지금 방법 씨앗 1": S1 / "metrics" / SITE / "prop_LoD2_s1__LoD2_rows.npz",
        "결측 지키기": FT / "metrics" / SITE / "fixB_LoD2_s0__LoD2_rows.npz"}


def main():
    R = P0.region(SITE, PRIOR); se = R["surf_ext"].astype(int); kind = R["kind"].astype(int)
    rows = np.load(S1 / "defs" / SITE / f"rows_{PRIOR}.npz")
    sel = (rows["code"] == 13) & rows["thin"].astype(bool) & (np.abs(rows["sW"].astype(np.float64)) >= 0.2)
    face = se[rows["patch"][sel].astype(np.int64)]
    inf = {k: np.isin(np.load(f)["cls"][sel], (1, 2)) for k, f in RUNS.items()}
    tab = []
    for e in np.unique(face):
        m = face == e
        n0, n1, nb = (int(inf[k][m].sum()) for k in RUNS)
        tab.append(dict(ext=int(e), kind=int(np.bincount(kind[rows["patch"][sel][m].astype(np.int64)]).argmax()), rows=int(m.sum()),
                        inflow_rows_method_s0=n0, inflow_rows_method_s1=n1, inflow_rows_fix=nb, rise_rows=nb - (n0 + n1) / 2))
    tab.sort(key=lambda r: (-r["rise_rows"], -r["rows"]))
    ext = tab[0]["ext"]
    # on the chosen face: the GT-to-prior distance |s_W| of the rows and the four classes of each result (src/phd/metrics_v3/lines.py:
    # windows of half width min(0.5, 0.5 |s_W|) around the GT and around the prior; 0 GT side, 1 wrong side, 2 both, 3 neither)
    mf = face == ext
    sw = np.abs(rows["sW"][sel][mf].astype(np.float64))
    names = {0: "참값 쪽", 1: "사전 정보 쪽", 2: "둘 다", 3: "둘 다 아님"}
    classes = {}
    for k, f in RUNS.items():
        cl = np.load(f)["cls"][sel][mf]
        classes[k] = {names[c]: int((cl == c).sum()) for c in range(4)}
    for k, f in (("판정만 끈 방법", RUNS["결측 지키기"].parents[4] / "main_stage3_v1/PHD-MAIN-STAGE3-v1/metrics" / SITE / "nojudge_LoD2_s0__LoD2_rows.npz"),):
        cl = np.load(f)["cls"][sel][mf]
        classes[k] = {names[c]: int((cl == c).sum()) for c in range(4)}
    face_rows = dict(rows=int(mf.sum()), abs_sW_median_m=float(np.median(sw)), abs_sW_p10_p90_m=[float(np.percentile(sw, 10)), float(np.percentile(sw, 90))],
                     window_half_width_median_m=float(np.median(np.minimum(0.5, 0.5 * sw))), classes=classes)
    print("face rows", face_rows)
    rec = dict(fig7_extra=dict(p2_more.place(SITE, PRIOR, 13, ext=ext), face_rise_table=tab, total_rows=int(sel.sum()), chosen_face_rows=face_rows,
                               total_rise_rows=float(sum(r["rise_rows"] for r in tab)), place_rule=__doc__.split("\n\n")[0], added="결과를 본 뒤 더함"),
               made=now(), scientific_verdict=None)
    jdump(PF / "prep/places_after_more.json", rec)
    for r in tab[:8]:
        print(r)
    print("total", rec["fig7_extra"]["total_rows"], rec["fig7_extra"]["total_rise_rows"], "photo", (rec["fig7_extra"]["photo"] or {}).get("view"))


if __name__ == "__main__":
    main()
