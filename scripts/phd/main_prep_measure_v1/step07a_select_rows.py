"""PHD-MAIN-PREP-MEASURE-v1 step 07a (jointbuildgs:dev, CPU): automatic candidates for the representative figure rows.

  python step07a_select_rows.py [--ranges R1 R2 ...] [--per-case 2] [--out figrows/spec_v1.json]

Rule (written before looking at any row): per range and case, the largest items of the case lists of step 05
(case 1: true-conflict area of a LoD2 face per type; case 2: surfaces with propagated judgments, one per outcome
'conflict carried right', 'agree carried right', 'mixed', 'carried wrong'; case 3: largest blobs (a), (b);
case 4: largest invisible cluster whose inherited prior is wrong / right; case 5: largest cluster with the prior in front /
behind and the largest absent-structure blob; case 8: largest 1-2 tau face). The row centre is the centroid of the item,
the section runs through it along the main axis of the item (PCA, 12-40 m), the view is the training view with the most
pixels on the item's units (unit_view_pairs). v1.1 (--photo-rule nadir-roof, 2026-10-04, after the user's review: the order
asks for a nadir photo crop): roof items take the nadir training view (tilt <= views.nadir_max_tilt_deg) with the most pixels
on the item among those holding its centre, falling back to the v1 view when there is none; wall items keep the v1 view,
because nadir views barely see walls. Readings of the rows are analyst judgment. scientific_verdict: null."""
import argparse
import csv
import json

import numpy as np
import scipy.ndimage as ndi

from common import CFG, GRID_H, GRID_W, OUT, Views, jdump
from src.phd.prior_propagation_v4 import rule


def rcsv(p):
    try:
        with open(p) as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def axis_line(P, cx, cy, lo=12.0, hi=40.0):
    if len(P) >= 3:
        Q = P - P.mean(0); w, v = np.linalg.eigh(Q.T @ Q); d = v[:, -1]
        L = float(np.clip(2.5 * np.sqrt(w[-1] / len(P)) * 2 + 6, lo, hi))
    else:
        d = np.array([1.0, 0.0]); L = lo
    return [[cx - d[0] * L / 2, cy - d[1] * L / 2], [cx + d[0] * L / 2, cy + d[1] * L / 2]]


def clusters(xy, cell=0.5, min_n=20):
    if len(xy) == 0:
        return []
    ij = np.floor(xy / cell).astype(np.int64); ij -= ij.min(0)
    M = np.zeros(ij.max(0) + 1, np.int32); np.add.at(M, (ij[:, 0], ij[:, 1]), 1)
    lab, nb = ndi.label(M > 0, structure=np.ones((3, 3)))
    pl = lab[ij[:, 0], ij[:, 1]]
    cnt = np.bincount(pl, minlength=nb + 1)
    order = np.argsort(-cnt[1:]) + 1
    return [np.nonzero(pl == k)[0] for k in order if cnt[k] >= min_n]


def best_view(pairs, units, X0=None, Vw=None, margin=80, max_tilt=None):
    """the view with the most pixels on the item's units among the views whose image holds the item centre (margin px);
    max_tilt: only views whose tilt is at most this (nadir views)."""
    m = np.isin(pairs["loc"], units)
    if not m.any():
        return None
    s = np.bincount(pairs["view"][m], weights=pairs["npix"][m], minlength=len(pairs["views"]))
    for i in np.argsort(-s):
        if s[i] <= 0:
            break
        n = str(pairs["views"][i])
        if max_tilt is not None and Vw.tilt(n) > max_tilt:
            continue
        if X0 is None:
            return n
        u, v, z = Vw.project(n, np.asarray(X0, float).reshape(1, 3))
        if z[0] > 0 and margin <= u[0] < GRID_W - margin and margin <= v[0] < GRID_H - margin:
            return n
    return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ranges", nargs="*", default=["R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"])
    ap.add_argument("--per-case", type=int, default=2); ap.add_argument("--out", default="figrows/spec_v1.json")
    ap.add_argument("--stage1-sub", default="step03"); ap.add_argument("--gt-sub", default="step04"); ap.add_argument("--cases-sub", default="step05")
    ap.add_argument("--photo-rule", default="best", choices=["best", "nadir-roof"], help="v1 = best; v1.1 = nadir-roof")
    ap.add_argument("--split", action="store_true", help="also write one spec per range (<out stem>_<range>.json)")
    a = ap.parse_args()
    rows = []
    Vw = Views()
    nadir_max = float(CFG["views"]["nadir_max_tilt_deg"])
    for rid in a.ranges:
        for prior in ("LoD2", "ALS"):
            S1 = OUT / a.stage1_sub / rid / prior
            U = dict(np.load(S1 / "units.npz")); G = dict(np.load(OUT / a.gt_sub / rid / f"labels_{prior}.npz"))
            pairs = dict(np.load(S1 / "unit_view_pairs.npz"))
            ext = U["surf_ext"][U["loc_surface"]]; C = U["loc_center"]; lab = G["label"]; st, J = U["state"], U["J"]
            ok = U["loc_in_range"] & ~G["excluded"]
            C5 = OUT / a.cases_sub / rid

            nrm_u = np.cross(U["loc_t1"], U["loc_t2"])

            def add(case, tag, units, title, note=""):
                if len(units) == 0:
                    return
                P = C[units, :2]
                k0 = units[int(np.argmin(((P - P.mean(0)) ** 2).sum(1)))]     # medoid: a unit of the item nearest to its mean
                cx, cy, cz = C[k0]
                wall = np.mean(U["loc_kind"][units] == 2) > 0.5
                if wall:   # walls: the section crosses the wall along its horizontal normal
                    nh = nrm_u[units, :2].mean(0); nh = nh / max(np.linalg.norm(nh), 1e-9)
                    line = [[cx - 8 * nh[0], cy - 8 * nh[1]], [cx + 8 * nh[0], cy + 8 * nh[1]]]
                else:
                    line = axis_line(P, cx, cy)
                view, photo = best_view(pairs, units, C[k0], Vw), "best"
                if a.photo_rule == "nadir-roof":
                    if wall:
                        photo = "best (wall: nadir views barely see walls)"
                    else:
                        vn = best_view(pairs, units, C[k0], Vw, max_tilt=nadir_max)
                        view, photo = (vn, "nadir") if vn else (view, "best (no nadir view holds the item)")
                if view is None:
                    photo = "most nadir view holding the centre (step 07): no training view sees the item"
                rows.append(dict(tid=f"c{case}_{rid}_{prior}_{tag}", case=case, range=rid, prior=prior, centre=[float(cx), float(cy)],
                                 z=float(cz), half_m=float(np.clip(np.ptp(P, axis=0).max() / 2 + 6, 10, 30)), wall=bool(wall),
                                 line=line, view=view, photo=photo, units=int(len(units)), title=title, note=note))
            # case 1 (LoD2 faces by type)
            if prior == "LoD2":
                T = np.load(C5 / "case1_unit_types_LoD2.npz"); typ = T["type"]
                for t in ["curved", "wall position", "eave", "rooftop structure"]:
                    m = ok & (typ == t)
                    if not m.any():
                        continue
                    e_cnt = np.bincount(np.searchsorted(np.unique(ext[m]), ext[m]))
                    faces = np.unique(ext[m])[np.argsort(-e_cnt)][: a.per_case]
                    for k, e in enumerate(faces):
                        u = np.nonzero(m & (ext == e))[0]
                        add(1, f"{t.replace(' ', '')}{k}", u, f"경우 1 표현 차이 — {rid} LoD2 면 {int(e)} ({t}), 참 충돌 {len(u)}패치")
                bi = T["bin"]
                m8 = ok & (bi == 1)
                if m8.any():
                    e_cnt = np.bincount(np.searchsorted(np.unique(ext[m8]), ext[m8]))
                    for k, e in enumerate(np.unique(ext[m8])[np.argsort(-e_cnt)][: a.per_case]):
                        u = np.nonzero(m8 & (ext == e))[0]
                        add(8, f"face{k}", u, f"경우 8 허용 오차 경계(1~2배) — {rid} LoD2 면 {int(e)}, {len(u)}패치")
            # case 2 (propagation outcomes)
            M = np.load(C5 / f"case2_missing_{prior}.npz"); mu = M["unit"]
            outcomes = [("conflict_right", (J[mu] == rule.J_CONFLICT) & (lab[mu] == 1), "충돌이 옮겨 가 맞은 곳"),
                        ("agree_right", (J[mu] == rule.J_AGREE) & (lab[mu] == 0), "일치가 옮겨 가 맞은 곳"),
                        ("mixed", (J[mu] == rule.J_MIXED), "혼재로 남은 곳"),
                        ("wrong", ((J[mu] == rule.J_AGREE) & (lab[mu] == 1)) | ((J[mu] == rule.J_CONFLICT) & (lab[mu] == 0)), "옮겨 간 판정이 틀린 곳")]
            for tag, sel, ttl in outcomes:
                u = mu[sel & ok[mu]]
                if len(u) == 0:
                    continue
                es, cnt = np.unique(ext[u], return_counts=True)
                for k, e in enumerate(es[np.argsort(-cnt)][:1]):
                    uu = u[ext[u] == e]
                    add(2, f"{tag}{k}", uu, f"경우 2 판정의 전파 — {rid} {prior} 표면 {int(e)}: {ttl} {len(uu)}패치")
            # case 4 (invisible)
            for tag, lv, ttl in (("wrong", 1, "이어받으면 틀림(참 충돌)"), ("right", 0, "이어받으면 맞음(참 일치)")):
                u = np.nonzero(ok & (st == rule.ST_INVISIBLE) & (lab == lv))[0]
                cl = clusters(C[u, :2])
                for k, ci in enumerate(cl[:1]):
                    add(4, f"{tag}{k}", u[ci], f"경우 4 못 본 곳 — {rid} {prior}: {ttl} {len(ci)}패치")
            # case 5 (direction)
            F5 = np.load(C5 / f"case5_units_{prior}.npz")
            for tag, idx, ttl in (("front", F5["front"], "사전 정보가 앞(지붕 위·벽 바깥)"), ("behind", F5["behind"], "사전 정보가 뒤")):
                cl = clusters(C[idx, :2])
                for k, ci in enumerate(cl[:1]):
                    add(5, f"{tag}{k}", idx[ci], f"경우 5 변화의 방향 — {rid} {prior}: {ttl} {len(ci)}패치")
            ab = rcsv(C5 / f"case5_absent_{prior}.csv")
            for k, r in enumerate(ab[:1]):
                cx, cy = float(r["x"]), float(r["y"])
                rows.append(dict(tid=f"c5_{rid}_{prior}_absent{k}", case=5, range=rid, prior=prior, centre=[cx, cy], z=float(r["z"]),
                                 half_m=float(np.clip(np.sqrt(float(r["area_m2"])) / 2 + 8, 10, 30)), line=[[cx - 12, cy], [cx + 12, cy]], view=None, photo="most nadir view holding the centre (step 07)",
                                 units=0, title=f"경우 5 사전 정보에 없는 구조 — {rid} {prior}: 덩어리 {float(r['area_m2']):.0f} m², 높이 {float(r['median_height_above_m']):.1f} m"))
        # case 3 (image errors; LoD2 render)
        for kk, ttl in (("a", "신뢰도 1인데 틀린 MVS"), ("b", "신뢰도 0으로 걸러진 틀린 깊이")):
            bl = rcsv(OUT / a.cases_sub / rid / f"case3_blobs_{kk}.csv")
            for k, r in enumerate(bl[: a.per_case]):
                cx, cy = float(r["x"]), float(r["y"])
                rows.append(dict(tid=f"c3_{rid}_{kk}{k}", case=3, range=rid, prior="LoD2", centre=[cx, cy], z=float(r["z"]),
                                 half_m=float(np.clip(np.sqrt(float(r["area_m2"])) / 2 + 8, 10, 25)), line=[[cx - 10, cy], [cx + 10, cy]], view=None, photo="most nadir view holding the centre (step 07)",
                                 units=0, title=f"경우 3 영상이 틀린 곳 ({kk}) — {rid}: {ttl}, 덩어리 {float(r['area_m2']):.0f} m², 오차 중앙값 {float(r['median_err_m']):.2f} m"))
    (OUT / a.out).parent.mkdir(parents=True, exist_ok=True)
    rule_txt = __doc__.split("Rule")[1].split("scientific_verdict")[0].strip()
    jdump(OUT / a.out, dict(rule=rule_txt, photo_rule=a.photo_rule, rows=rows))
    if a.split:
        for rid in a.ranges:
            jdump(OUT / a.out.replace(".json", f"_{rid}.json"), dict(rule=rule_txt, photo_rule=a.photo_rule, rows=[r for r in rows if r["range"] == rid]))
    print("rows", len(rows), {c: sum(r["case"] == c for r in rows) for c in (1, 2, 3, 4, 5, 8)},
          "photo", {p: sum(r.get("photo", "") == p for r in rows) for p in sorted({r.get("photo", "") for r in rows})})


if __name__ == "__main__":
    main()
