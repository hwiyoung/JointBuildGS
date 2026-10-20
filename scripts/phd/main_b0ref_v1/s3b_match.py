"""PHD-MAIN-B0REF-v1 일 3·4 (결과를 본 뒤 더함): what the GeoGS points are in a matched source file. (jointbuildgs:dev, CPU)

  python s3b_match.py <source>   e.g. fill_v120   -> /b0/dist/match__<source>.json, /docs/tables/t4_match_<source>.md|json

After the distance table showed GeoGS points sitting on <source> points (median 0.03 mm), this reads, for the GeoGS points within 1 mm
of a <source> point: the GPS time of that point (UTC, date), its return class, per place (roof / wall / other). And the other way:
the <source> points in the evaluation range, roof space and wall space -> nearest GeoGS point (is every <source> point within the
2 cm spacing of a kept GeoGS point, as a minimum-distance subsampling would leave?). The GeoGS points farther than 1 mm: where they are
and their distance to the raw ULS nadir file. [이 요청에서 냄, 결과를 본 뒤 더함] scientific_verdict: null."""
import datetime as dt
import sys

import numpy as np
from scipy.spatial import cKDTree

from b0_common import B0, DOCS, jdump, load_crop, log, now

GPS0 = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)


def utc(t):
    return (GPS0 + dt.timedelta(seconds=float(t) + 1e9 - 18)).isoformat(timespec="seconds")


def place_masks(S, rows):
    h = S["wall_h"][rows]
    return {"all": np.ones(len(rows), bool), "roof": S["roof_any"][rows], "wall": S["wall_any"][rows],
            "wall_h0_3": S["wall_any"][rows] & (h < 3), "wall_h3_10": S["wall_any"][rows] & (h >= 3) & (h < 10),
            "wall_h10_1000": S["wall_any"][rows] & (h >= 10), "other": S["ev"][rows] & ~S["roof_any"][rows] & ~S["wall_any"][rows]}


def main(src):
    z = np.load(B0 / "dist" / f"geogs__{src}.npz")
    d = z["d"].astype(np.float64); idx = z["idx"]; rows = z["ev_rows"]
    Sg = np.load(B0 / "sel/geogs.npz")
    T = load_crop(src)
    M = place_masks(Sg, rows)
    hit = d <= 1e-3
    rc_src = np.full(len(T["xyz"]), -1, np.int8)
    if "return_number" in T:
        from b0_common import return_class
        rc_src = return_class(T["return_number"], T["number_of_returns"])
    out = dict(source=src, geogs_points=int(len(d)), within_1mm=int(hit.sum()), within_0_1mm=int((d <= 1e-4).sum()),
               distance_quantiles_mm={q: float(np.percentile(d, q) * 1e3) for q in (1, 5, 25, 50, 75, 95, 99)}, places={})
    for k, m in M.items():
        mh = m & hit
        e = dict(n=int(m.sum()), within_1mm=int(mh.sum()), share_within_1mm=float(mh.sum() / max(m.sum(), 1)))
        if "gps_time" in T and mh.any():
            g = T["gps_time"][idx[mh]]
            e.update(gps_utc_min=utc(g.min()), gps_utc_max=utc(g.max()), gps_utc_p01=utc(np.percentile(g, 1)), gps_utc_p99=utc(np.percentile(g, 99)))
        if mh.any():
            c = rc_src[idx[mh]]
            e["return_class_share"] = {nm: float(np.mean(c == v)) for nm, v in (("single", 0), ("first_of_many", 1), ("middle", 2), ("last", 3), ("none", -1))}
        out["places"][k] = e
    # GPS time histogram (10-minute bins) of the matched points
    if "gps_time" in T:
        g = T["gps_time"][idx[hit]]
        mins = np.floor((g - g.min()) / 600).astype(int)
        u, c = np.unique(mins, return_counts=True)
        out["gps_10min_bins"] = [dict(start_utc=utc(g.min() + 600 * int(a)), points=int(b)) for a, b in zip(u, c)]
    # unmatched GeoGS points: where, and how far from the raw ULS nadir
    zn = np.load(B0 / "dist/geogs__uls_nadir.npz")
    assert np.array_equal(zn["ev_rows"], rows)
    um = ~hit
    out["unmatched"] = dict(n=int(um.sum()), by_place={k: int((m & um).sum()) for k, m in M.items()},
                            dist_to_uls_nadir_median_m=float(np.median(zn["d"][um])) if um.any() else None,
                            dist_to_uls_nadir_share_le_1mm=float(np.mean(zn["d"][um] <= 1e-3)) if um.any() else None,
                            dist_to_src_median_m=float(np.median(d[um])) if um.any() else None)
    # the other way: source points -> nearest GeoGS point
    Ss = np.load(B0 / "sel" / f"{src}.npz")
    G = load_crop("geogs")["xyz"]
    tree = cKDTree(G)
    rev = {}
    for k, m in (("eval", Ss["ev"]), ("roof", Ss["roof_any"]), ("wall", Ss["wall_any"])):
        dd = tree.query(T["xyz"][m], workers=8)[0]
        rev[k] = dict(n=int(m.sum()), share_le_1mm=float(np.mean(dd <= 1e-3)), share_le_2cm=float(np.mean(dd <= 0.02)),
                      share_le_2cm_plus=float(np.mean(dd <= 0.0201)), median_m=float(np.median(dd)), p99_m=float(np.percentile(dd, 99)),
                      share_gt_10cm=float(np.mean(dd > 0.1)))
    out["source_to_geogs"] = rev
    out["made"] = now(); out["scientific_verdict"] = None
    jdump(B0 / "dist" / f"match__{src}.json", out)
    jdump(DOCS / "tables" / f"t4_match_{src}.json", out)
    lab = {"all": "전체", "roof": "지붕", "wall": "벽", "wall_h0_3": "벽 0~3 m", "wall_h3_10": "벽 3~10 m", "wall_h10_1000": "벽 10 m 위", "other": "그 밖"}
    L = [f"# 표 4. GeoGS 점과 {src}의 점: 1 mm 안의 짝 [이 요청에서 냄, 결과를 본 뒤 더함]", "",
         f"- GeoGS 점(평가 범위) {out['geogs_points']:,} 가운데 1 mm 안 {out['within_1mm']:,} ({out['within_1mm']/out['geogs_points']*100:.2f} %), 0.1 mm 안 {out['within_0_1mm']:,}. 거리 분위(mm): " +
         ", ".join(f"{q} % {v:.3f}" for q, v in out["distance_quantiles_mm"].items()), "",
         "| 곳 | GeoGS 점 | 1 mm 안 | 몫 | 짝의 GPS 시각(UTC, 처음 ~ 끝) | 짝의 반사 종류: 단일 · 처음 · 가운데 · 마지막 |", "|---|---:|---:|---:|---|---|"]
    for k, e in out["places"].items():
        rcs = e.get("return_class_share", {})
        L.append(f"| {lab[k]} | {e['n']:,} | {e['within_1mm']:,} | {e['share_within_1mm']*100:.2f} % | {e.get('gps_utc_min', '')} ~ {e.get('gps_utc_max', '')} | " +
                 " · ".join(f"{rcs.get(n, 0)*100:.1f} %" for n in ("single", "first_of_many", "middle", "last")) + " |")
    u = out["unmatched"]
    L += ["", f"- 1 mm 밖의 GeoGS 점 {u['n']:,}: 곳별 " + ", ".join(f"{lab[k]} {v:,}" for k, v in u["by_place"].items()) +
          (f"; 그 점에서 {src}까지 중앙값 {u['dist_to_src_median_m']*1e3:.1f} mm, 원래 드론 LiDAR(연직)까지 중앙값 {u['dist_to_uls_nadir_median_m']*1e3:.1f} mm(1 mm 안 {u['dist_to_uls_nadir_share_le_1mm']*100:.1f} %)." if u["n"] else ".")]
    if "gps_10min_bins" in out:
        L += ["", "짝의 GPS 시각(10분 칸, UTC): " + ", ".join(f"{b['start_utc'][11:16]} {b['points']:,}" for b in out["gps_10min_bins"])]
    L += ["", f"거꾸로: {src}의 점에서 GeoGS 점군의 가장 가까운 점까지", "", "| 곳 | 점 | 1 mm 안 | 2 cm 안 | 중앙값 (mm) | 99 분위 (mm) | 10 cm 넘음 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k, e in rev.items():
        L.append(f"| {dict(eval='평가 범위', roof='지붕', wall='벽')[k]} | {e['n']:,} | {e['share_le_1mm']*100:.1f} % | {e['share_le_2cm']*100:.1f} % | {e['median_m']*1e3:.1f} | {e['p99_m']*1e3:.1f} | {e['share_gt_10cm']*100:.2f} % |")
    (DOCS / "tables" / f"t4_match_{src}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)
