"""PHD-CH6-SUPPORT-v1 task 4: buildings whose prior is offset differently from the rest of the range after the scene-wide
registration (jointbuildgs:dev, CPU; definitions = configs ch6_support_v1.json 'task4_region_offset', written before any result).

  python t4_offset.py

Per range (7) and prior: the task-5 mask-on v6 run (the range's own registration applied) and its labels. Roof-like support
patches in range, not excluded, finite MVS value, grouped by the footprint containing the patch centre. Per building with
>= 10 m2 of such roof: area-weighted median m_b and NMAD s_b of r = MVS - prior (patch medians); candidate |m_b| > s_b (the
method's vertical-bias rule). GT check on the labelled roof patches: g_b, sg_b (GT - prior), MVS - GT. Classes: real change
(survey list or |g_b| > 2 m), prior offset case (GT confirms with the same sign), image-side offset (GT does not confirm),
no GT. Effect flag |m_b| >= tau. Supplement (LoD2, recorded only): robust horizontal translation from the wall residuals.
For the confirmed cases: the released patches whose |GT - prior - g_b| <= tau (false conflicts of the offset).
Writes /out/t4/{buildings.csv, candidates.csv, summary.json, cases.json} and /out/t4/figs/offset_<range>_<prior>.png.
scientific_verdict: null."""
import csv
import json
from pathlib import Path

import numpy as np

from ch6_common import CCFG, DR, OUT, RANGES, RNGDEF, footprint_index, jdump, labels_of, log, rule, setup_fonts, xy_to_uv

T4 = CCFG["task4_region_offset"]
O = OUT / "t4"; (O / "figs").mkdir(parents=True, exist_ok=True)
CHANGE_IDS = ("4959326", "4907510", "4907508", "4907207")
MIN_AREA = float(T4["min_roof_area_m2"])


def wmed(x, w):
    o = np.argsort(x); x = x[o]; w = w[o]
    c = np.cumsum(w)
    return float(x[np.searchsorted(c, 0.5 * c[-1])])


def wnmad(x, w, m):
    return 1.4826 * wmed(np.abs(x - m), w)


def huber_shift(N, r, w, it=30):
    """robust 2D translation t with r ~ N t (N [n, 2] horizontal outward normals)."""
    t = np.zeros(2)
    for _ in range(it):
        e = r - N @ t
        s = max(1.4826 * np.median(np.abs(e - np.median(e))), 1e-3)
        k = 1.345 * s
        ww = w * np.where(np.abs(e) <= k, 1.0, k / np.maximum(np.abs(e), 1e-12))
        A = (N * ww[:, None]).T @ N; b = (N * ww[:, None]).T @ r
        try:
            t_new = np.linalg.solve(A + 1e-9 * np.eye(2), b)
        except np.linalg.LinAlgError:
            return None, None
        if np.linalg.norm(t_new - t) < 1e-5:
            t = t_new; break
        t = t_new
    e = r - N @ t
    return t, 1.4826 * float(np.median(np.abs(e - np.median(e))))


def main():
    rows, summ, cases = [], {}, []
    plt = setup_fonts()
    for rid in RANGES:
        for prior in ("LoD2", "ALS"):
            run = OUT / "t5/s03" / rid / prior
            U = np.load(run / "units.npz")
            sm = json.loads((run / "summary.json").read_text())
            tau_roof = float(sm["tolerance"]["roof"]["tau"])
            lab, med, tau, ex = labels_of(OUT / "t5/gt" / rid, prior, rid)
            xy = U["loc_center"][:, :2].astype(np.float64); area = U["loc_area"].astype(np.float64)
            fp, names = footprint_index(DR / "s02" / rid / "footprints.json", xy)
            r = -U["mvs_r_med"].astype(np.float64)
            base = U["loc_in_range"].astype(bool) & ~ex & (fp >= 0)
            roof = base & (U["loc_kind"] == 1)
            use = roof & (U["state"] == rule.ST_SUPPORT) & np.isfinite(r)
            gtu = roof & (lab >= 0)
            # wall normals (LoD2) for the horizontal supplement
            if prior == "LoD2":
                S = json.loads((DR / "s02" / rid / "lod2_surfaces.json").read_text())["surfaces"]
                nrm = {s["ext"]: np.asarray(s["normal"], np.float64) for s in S}
                ext = U["surf_ext"][U["loc_surface"]]
                Nw = np.array([nrm.get(int(e), np.full(3, np.nan)) for e in ext])
                hn = Nw[:, :2] / np.maximum(np.linalg.norm(Nw[:, :2], axis=1, keepdims=True), 1e-9)
                wall = base & (U["loc_kind"] == 2) & (U["state"] == rule.ST_SUPPORT) & np.isfinite(r) & np.isfinite(hn).all(1)
            rel = U["J_loc"] == rule.J_CONFLICT
            nb = 0
            mb_map = {}
            for bi in np.unique(fp[use]):
                m = use & (fp == bi)
                a = float(area[m].sum())
                if a < MIN_AREA:
                    continue
                nb += 1
                mb = wmed(r[m], area[m]); sb = wnmad(r[m], area[m], mb)
                g = gtu & (fp == bi)
                ga = float(area[g].sum())
                if ga >= MIN_AREA:
                    gb = wmed(med[g], area[g]); sgb = wnmad(med[g], area[g], gb)
                    both = m & g
                    db = wmed(r[both] - med[both], area[both]) if area[both].sum() > 0 else np.nan
                else:
                    gb = sgb = db = np.nan
                cand = abs(mb) > sb
                name = names[bi]
                if not cand:
                    cls = ""
                elif any(c in name for c in CHANGE_IDS) or (np.isfinite(gb) and abs(gb) > 2.0):
                    cls = "real_change"
                elif not np.isfinite(gb):
                    cls = "no_gt"
                elif abs(gb) > sgb and np.sign(gb) == np.sign(mb):
                    cls = "prior_offset_case"
                else:
                    cls = "image_side_offset"
                row = dict(range=rid, prior=prior, building=name, roof_area_m2=round(a, 1), patches=int(m.sum()), m_b=round(mb, 4), s_b=round(sb, 4),
                           ratio_m_over_s=round(abs(mb) / max(sb, 1e-6), 3), tau_roof=round(tau_roof, 4), m_over_tau=round(abs(mb) / tau_roof, 3),
                           effect=bool(abs(mb) >= tau_roof), candidate=bool(cand), gt_area_m2=round(ga, 1),
                           g_b=round(gb, 4) if np.isfinite(gb) else "", sg_b=round(sgb, 4) if np.isfinite(sgb) else "",
                           mvs_minus_gt=round(db, 4) if np.isfinite(db) else "", cls=cls)
                if prior == "LoD2":
                    w = wall & (fp == bi)
                    if w.sum() >= 20:
                        Nh = hn[w]; ev = np.linalg.eigvalsh(Nh.T @ Nh / len(Nh))
                        t, nm = huber_shift(Nh, r[w], area[w])
                        row.update(h_walls=int(w.sum()), h_min_eig=round(float(ev[0]), 3),
                                   h_shift=round(float(np.linalg.norm(t)), 4) if t is not None else "", h_nmad_after=round(nm, 4) if nm is not None else "",
                                   h_flag=bool(t is not None and ev[0] >= 0.1 and np.linalg.norm(t) > nm))
                if cls == "prior_offset_case":
                    allb = U["loc_in_range"].astype(bool) & ~ex & (fp == bi) & (lab >= 0)
                    fc = allb & rel & (np.abs(med - gb) <= tau)
                    cases.append(dict(range=rid, prior=prior, building=name, g_b=round(gb, 4), m_b=round(mb, 4), tau_roof=round(tau_roof, 4),
                                      patches=int(allb.sum()), released=int((allb & rel).sum()), released_area_m2=round(float(area[allb & rel].sum()), 2),
                                      false_conflicts=int(fc.sum()), false_conflict_area_m2=round(float(area[fc].sum()), 2),
                                      true_wrong_after_offset=int((allb & (np.abs(med - gb) > tau)).sum())))
                rows.append(row); mb_map[bi] = (mb, sb, cls)
            summ[f"{rid}/{prior}"] = dict(buildings=nb, candidates=int(sum(1 for v in mb_map.values() if v[2])),
                                          by_class={c: int(sum(1 for v in mb_map.values() if v[2] == c)) for c in ("real_change", "prior_offset_case", "image_side_offset", "no_gt")},
                                          tau_roof=round(tau_roof, 4), shift=[round(x, 4) for x in sm["registration"]["shift_applied"]])
            log(rid, prior, summ[f"{rid}/{prior}"])
            # map: footprints coloured by m_b (clipped at 2 tau), candidates outlined
            F = json.loads((DR / "s02" / rid / "footprints.json").read_text())
            F = F["footprints"] if isinstance(F, dict) else F
            fig, ax = plt.subplots(figsize=(8.5, 7.2), constrained_layout=True)
            import matplotlib.colors as mcolors
            from matplotlib.cm import ScalarMappable
            norm = mcolors.TwoSlopeNorm(vmin=-2 * tau_roof, vcenter=0.0, vmax=2 * tau_roof)
            cmap = plt.get_cmap("RdBu_r")
            for bi, f in enumerate(F):
                ring = xy_to_uv(np.asarray(f["ring_local"], np.float64))
                if bi in mb_map:
                    mb, sb, cls = mb_map[bi]
                    ax.fill(ring[:, 0], ring[:, 1], color=cmap(norm(np.clip(mb, -2 * tau_roof, 2 * tau_roof))), lw=0)
                    ax.plot(ring[:, 0], ring[:, 1], color="k", lw=2.2 if cls else 0.4)
                    if cls:
                        c = ring.mean(0)
                        ax.text(c[0], c[1], {"real_change": "변화", "prior_offset_case": "사례", "image_side_offset": "영상", "no_gt": "참값 없음"}[cls],
                                ha="center", va="center", fontsize=8, bbox=dict(fc="white", ec="none", alpha=0.75, pad=1))
                else:
                    ax.fill(ring[:, 0], ring[:, 1], color="#dddddd", lw=0)
                    ax.plot(ring[:, 0], ring[:, 1], color="#999999", lw=0.3)
            pol = xy_to_uv(np.asarray(RNGDEF[rid]["polygon_local"], np.float64))
            ax.plot(np.r_[pol[:, 0], pol[0, 0]], np.r_[pol[:, 1], pol[0, 1]], "k--", lw=0.8)
            ax.set_aspect("equal"); ax.set_xlabel("u (m)"); ax.set_ylabel("v (m)")
            ax.set_title(f"{rid} · {'LoD2' if prior == 'LoD2' else '항공 LiDAR'}: 건물별 남은 치우침 (MVS − 사전 정보 중앙값), τ = {tau_roof:.2f} m")
            fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=0.7, label="m (중앙값, 2τ에서 자름)")
            fig.savefig(O / "figs" / f"offset_{rid}_{prior}.png", dpi=130); plt.close(fig)
    # deduplicate (first range wins)
    seen = set()
    for r_ in rows:
        k = (r_["prior"], r_["building"])
        r_["primary"] = k not in seen
        seen.add(k)
    keys = sorted({k for r_ in rows for k in r_}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    with open(O / "buildings.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    cand = [r_ for r_ in rows if r_["candidate"] and r_["primary"]]
    with open(O / "candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(sorted(cand, key=lambda x: -x["m_over_tau"]))
    tot = {}
    for prior in ("LoD2", "ALS"):
        P_ = [r_ for r_ in rows if r_["prior"] == prior and r_["primary"]]
        tot[prior] = dict(buildings=len(P_), candidates=sum(r_["candidate"] for r_ in P_),
                          by_class={c: sum(r_["cls"] == c for r_ in P_) for c in ("real_change", "prior_offset_case", "image_side_offset", "no_gt")},
                          candidates_with_effect=sum(r_["candidate"] and r_["effect"] for r_ in P_),
                          cases_with_effect=sum(r_["cls"] == "prior_offset_case" and r_["effect"] for r_ in P_),
                          horizontal_flags=sum(bool(r_.get("h_flag")) for r_ in P_))
    jdump(O / "summary.json", dict(definitions=T4, per_run=summ, total=tot, scientific_verdict=None))
    jdump(O / "cases.json", dict(cases=cases, scientific_verdict=None))
    print("t4 done", tot)


if __name__ == "__main__":
    main()
