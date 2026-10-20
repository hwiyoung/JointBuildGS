"""PHD-MAIN-B0REF-v1 일 3 (jointbuildgs:dev, CPU): nearest-point distances in the raw comparison frame.

  python s3_dist.py query <target> [...]   GeoGS points in the evaluation range -> nearest point of <target> (a crop; '+'-joined
                                           names = the union, e.g. uls_nadir+fill_v120)  -> /b0/dist/geogs__<target>.npz (d, idx)
  python s3_dist.py reverse                the raw ULS wall points (space, all returns) -> nearest GeoGS point -> /b0/dist/uls_nadir_wall__geogs.npz
  python s3_dist.py misalign               per LoD2 wall face, 0.5 m (s, z) cells, median outward distance GeoGS - raw ULS
  python s3_dist.py rgb <target>           colour of the pairs within 2 cm (GeoGS 8 bit; LAS 16 bit -> >> 8)
  python s3_dist.py tables                 -> /docs/tables/t3_*.md|json
Targets 'single' = the raw ULS single returns, 'uls_nadir_t2first' / 'uls_nadir_t2mean' = the 2 cm thinnings. Rows of table 3: config
distances.rows. [이 요청에서 냄] scientific_verdict: null."""
import json
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

from b0_common import B0, CFG, DOCS, jdump, jl, load_crop, log, lod2_faces, now

BINS = CFG["distances"]["bins_m"]
HB = CFG["wall_selection"]["space"]["height_bins_m"]
LAB = {"uls_nadir": "원래 드론 LiDAR 모든 반사", "single": "원래 드론 LiDAR 단일 반사", "uls_nadir_t2first": "드론 LiDAR 2 cm 솎음(첫 점)",
       "uls_nadir_t2mean": "드론 LiDAR 2 cm 솎음(칸 평균)", "uls_manual": "수동 비행 판 1.1.0", "uls_manual_v120": "수동 비행 판 1.2.0",
       "fill_v120": "수동 비행 5 mm 처리본 판 1.2.0", "fill_v110": "수동 비행 5 mm 처리본 판 1.1.0", "photogrammetry": "드론 영상 점군",
       "uls_nadir+fill_v120": "연직 비행 + 5 mm 처리본 판 1.2.0", "uls_nadir+uls_manual_v120": "연직 비행 + 수동 비행 판 1.2.0",
       "uls_nadir+fill_v110": "연직 비행 + 5 mm 처리본 판 1.1.0"}


def target_points(name):
    parts = []
    for nm in name.split("+"):
        if nm == "single":
            C = load_crop("uls_nadir"); S = np.load(B0 / "sel/uls_nadir.npz")
            parts.append(C["xyz"][S["rclass"] == 0])
        else:
            parts.append(load_crop(nm)["xyz"])
    return np.concatenate(parts) if len(parts) > 1 else parts[0]


def geogs_rows():
    S = np.load(B0 / "sel/geogs.npz")
    ev = S["ev"]
    h = S["wall_h"]
    R = {"all": ev, "roof": S["roof_any"], "wall": S["wall_any"]}
    for lo, hi in HB:
        R[f"wall_h{lo}_{hi}"] = S["wall_any"] & (h >= lo) & (h < hi)
    R["other"] = ev & ~S["roof_any"] & ~S["wall_any"]
    return S, ev, R


def query(name):
    t0 = time.time()
    G = load_crop("geogs")["xyz"]
    S, ev, _ = geogs_rows()
    T = target_points(name)
    log(name, "tree", len(T))
    d, i = cKDTree(T).query(G[ev], workers=8)
    np.savez(B0 / "dist" / f"geogs__{name}.npz", d=d.astype(np.float32), idx=i.astype(np.int64), ev_rows=np.nonzero(ev)[0])
    log(name, "done", f"{time.time() - t0:.0f}s", float(np.median(d)))
    return dict(target=name, target_points=int(len(T)), seconds=round(time.time() - t0, 1))


def reverse():
    t0 = time.time()
    G = load_crop("geogs")["xyz"]; U = load_crop("uls_nadir")["xyz"]
    S = np.load(B0 / "sel/uls_nadir.npz")
    w = S["wall_any"]
    d, _ = cKDTree(G).query(U[w], workers=8)
    np.savez(B0 / "dist/uls_nadir_wall__geogs.npz", d=d.astype(np.float32), rows=np.nonzero(w)[0], h=S["wall_h"][w], rclass=S["rclass"][w])
    log("reverse done", len(d), f"{time.time() - t0:.0f}s")


def nmad(x):
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else None


def misalign():
    faces = {f["ext"]: f for f in lod2_faces() if f["kind"] == 2}
    Sg = np.load(B0 / "sel/geogs.npz"); Su = np.load(B0 / "sel/uls_nadir.npz")
    out = []
    allc = []
    for e, f in faces.items():
        def cells(S):
            m = S["wall_face"] == e
            s, z, d = S["wall_s"][m].astype(np.float64), S["wall_h"][m].astype(np.float64), S["wall_d"][m].astype(np.float64)
            if not len(s):
                return {}
            key = np.floor(s / 0.5).astype(np.int64) * 100000 + np.floor(z / 0.5).astype(np.int64)
            o = np.argsort(key, kind="stable"); key, d = key[o], d[o]
            u, st, c = np.unique(key, return_index=True, return_counts=True)
            return {int(k): float(np.median(d[a:a + n])) for k, a, n in zip(u, st, c) if n >= 3}
        cg, cu = cells(Sg), cells(Su)
        both = sorted(set(cg) & set(cu))
        diff = np.array([cg[k] - cu[k] for k in both])
        allc.append(diff)
        out.append(dict(ext=e, cells_geogs=len(cg), cells_uls=len(cu), cells_both=len(both),
                        median_diff_m=float(np.median(diff)) if len(diff) else None, nmad_m=nmad(diff),
                        p05_m=float(np.percentile(diff, 5)) if len(diff) else None, p95_m=float(np.percentile(diff, 95)) if len(diff) else None,
                        median_d_geogs_m=float(np.median(list(cg.values()))) if cg else None, median_d_uls_m=float(np.median(list(cu.values()))) if cu else None))
    a = np.concatenate(allc)
    rec = dict(faces=out, all=dict(cells_both=int(len(a)), median_diff_m=float(np.median(a)), nmad_m=nmad(a)),
               rule=CFG["distances"]["misalignment"], made=now(), scientific_verdict=None)
    jdump(B0 / "dist/misalign.json", rec)
    log("misalign", rec["all"])


def rgb(name):
    G = load_crop("geogs")
    z = np.load(B0 / "dist" / f"geogs__{name}.npz")
    T = load_crop(name)
    if "red" not in T:
        return
    gi = z["ev_rows"]; m = z["d"] <= 0.02
    g = np.column_stack([G[c][gi[m]] for c in ("red", "green", "blue")]).astype(np.int64)
    t = np.column_stack([T[c][z["idx"][m]] for c in ("red", "green", "blue")]).astype(np.float64)
    if t.max() > 255:
        t = np.floor(t / 256.0)
    t = t.astype(np.int64)
    dd = np.abs(g - t)
    ex = z["d"] <= 1e-3
    rec = dict(target=name, pairs_within_2cm=int(m.sum()), share_all_three_equal=float(np.mean((dd == 0).all(1))),
               share_each_channel_equal=[float(np.mean(dd[:, k] == 0)) for k in range(3)],
               abs_diff_median=[float(np.median(dd[:, k])) for k in range(3)], abs_diff_p95=[float(np.percentile(dd[:, k], 95)) for k in range(3)],
               mean_diff_geogs_minus_target=[float(np.mean(g[:, k] - t[:, k])) for k in range(3)], pairs_within_1mm=int(ex.sum()),
               note="LAS 16-bit colour divided by 256 (DJI Terra writes 8-bit values x 256; 0..65280)", made=now(), scientific_verdict=None)
    jdump(B0 / "dist" / f"rgb__{name}.json", rec)
    log("rgb", name, rec["share_all_three_equal"], rec["abs_diff_median"])


def stats(d):
    if not len(d):
        return dict(n=0)
    o = dict(n=int(len(d)))
    for k, v in BINS.items():
        o[k] = float(np.mean(d > v)) if k.startswith("gt") else float(np.mean(d <= v))
    o["median_m"] = float(np.median(d)); o["p95_m"] = float(np.percentile(d, 95))
    return o


ROWLAB = {"all": "전체(평가 범위)", "roof": "지붕", "wall": "벽(공간으로 고름)", "wall_h0_3": "벽 0~3 m", "wall_h3_10": "벽 3~10 m",
          "wall_h10_1000": "벽 10 m 위", "other": "그 밖"}


def table_rows(name):
    z = np.load(B0 / "dist" / f"geogs__{name}.npz")
    S, ev, R = geogs_rows()
    d = z["d"].astype(np.float64)
    out = {}
    for k, m in R.items():
        out[k] = stats(d[m[ev]])
    return out


def md_table(title, rows_by_key, note=None):
    L = [title, ""] + ([note, ""] if note else [])
    L += ["| 줄 | 점 | 1 mm 안 | 5 mm 안 | 1 cm 안 | 2 cm 안 | 5 cm 안 | 10 cm 안 | 50 cm 넘음 | 중앙값 (mm) | 95 분위 (mm) |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, q in rows_by_key.items():
        if not q.get("n"):
            L.append(f"| {ROWLAB.get(k, k)} | 0 | | | | | | | | | |"); continue
        L.append(f"| {ROWLAB.get(k, k)} | {q['n']:,} | " + " | ".join(f"{q[b]*100:.1f} %" for b in BINS) +
                 f" | {q['median_m']*1e3:.1f} | {q['p95_m']*1e3:.1f} |")
    return L


def tables():
    done = sorted(p.stem.split("__", 1)[1] for p in (B0 / "dist").glob("geogs__*.npz"))
    allrec = {}
    order = ["uls_nadir", "single", "uls_nadir_t2first", "uls_nadir_t2mean"] + [n for n in done if n not in ("uls_nadir", "single", "uls_nadir_t2first", "uls_nadir_t2mean")]
    L = ["# 표 3. GeoGS 점에서 다른 점군의 가장 가까운 점까지의 거리 [이 요청에서 냄]", "",
         "- GeoGS 점 = 평가 범위 안 전부. 두 점군 모두 정리 전, 비교 좌표. 줄의 곳은 GeoGS 점의 자리(지붕 공간, 벽 공간, 벽 높이 = 그 벽면의 가장 낮은 점에서).", ""]
    for n in order:
        if n not in done:
            continue
        allrec[n] = table_rows(n)
        L += md_table(f"## 표 3 · {LAB.get(n, n)}까지", allrec[n]) + [""]
    jdump(DOCS / "tables/t3_dist.json", dict(targets=allrec, labels={n: LAB.get(n, n) for n in allrec}, bins=BINS, made=now(), scientific_verdict=None))
    (DOCS / "tables/t3_dist.md").write_text("\n".join(L) + "\n")
    rp = B0 / "dist/uls_nadir_wall__geogs.npz"
    if rp.exists():
        z = np.load(rp)
        d, h, rc = z["d"].astype(np.float64), z["h"], z["rclass"]
        rr = {"wall": stats(d)}
        for lo, hi in HB:
            rr[f"wall_h{lo}_{hi}"] = stats(d[(h >= lo) & (h < hi)])
        rr["single"] = stats(d[rc == 0]); rr["multi"] = stats(d[rc > 0])
        jdump(DOCS / "tables/t3b_reverse.json", dict(rows=rr, made=now(), scientific_verdict=None))
        ROWLAB.update(single="벽, 단일 반사", multi="벽, 여러 반사")
        (DOCS / "tables/t3b_reverse.md").write_text("\n".join(md_table("# 표 3b. 거꾸로: 공간으로 고른 원래 드론 LiDAR 벽 점에서 GeoGS 점군의 가장 가까운 점까지 [이 요청에서 냄]", rr)) + "\n")
    mp = B0 / "dist/misalign.json"
    if mp.exists():
        M = jl(mp)
        F = {f["ext"]: f for f in jl(B0 / "prep/faces.json")["faces"]}
        L = ["# 표 3c. 두 자료의 벽 어긋남: 벽면마다 0.5 m 칸의 바깥 법선 방향 거리 중앙값의 차(GeoGS − 원래 드론 LiDAR) [이 요청에서 냄]", "",
             "- 칸 = 벽면 위 (면을 따라, 높이) 0.5 m 칸, 두 점군 모두 3점 이상인 칸만. 거리 = 공간으로 고른 점의 바깥 법선 방향 거리(LoD2 면에서).", "",
             "| 면 | 향한 쪽 | 넓이 (m²) | 함께 덮는 칸 | GeoGS만 칸 수 | 드론 LiDAR만 칸 수 | 차의 중앙값 (mm) | NMAD (mm) | 5~95 분위 (mm) | GeoGS 거리 중앙값 (mm) | 드론 LiDAR 거리 중앙값 (mm) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
        for r in sorted(M["faces"], key=lambda r: -F[r["ext"]]["area_space_in_eval_m2"]):
            if not r["cells_both"]:
                L.append(f"| {r['ext']} | {F[r['ext']]['facing']} | {F[r['ext']]['area_space_in_eval_m2']:,.1f} | 0 | {r['cells_geogs']} | {r['cells_uls']} | | | | | |"); continue
            L.append(f"| {r['ext']} | {F[r['ext']]['facing']} | {F[r['ext']]['area_space_in_eval_m2']:,.1f} | {r['cells_both']:,} | {r['cells_geogs'] - r['cells_both']:,} | {r['cells_uls'] - r['cells_both']:,} | "
                     f"{r['median_diff_m']*1e3:+.1f} | {r['nmad_m']*1e3:.1f} | {r['p05_m']*1e3:+.0f} ~ {r['p95_m']*1e3:+.0f} | {r['median_d_geogs_m']*1e3:+.0f} | {r['median_d_uls_m']*1e3:+.0f} |")
        a = M["all"]
        L += ["", f"- 모든 벽면: 함께 덮는 칸 {a['cells_both']:,}, 차의 중앙값 {a['median_diff_m']*1e3:+.1f} mm, NMAD {a['nmad_m']*1e3:.1f} mm."]
        (DOCS / "tables/t3c_misalign.md").write_text("\n".join(L) + "\n")
        jdump(DOCS / "tables/t3c_misalign.json", M)
    rg = sorted((B0 / "dist").glob("rgb__*.json"))
    if rg:
        L = ["# 표 3d. 색: 거리 2 cm 안의 짝에서 [이 요청에서 냄]", "", "- 세기는 GeoGS 점군에 없다. LAS 색(16 bit)은 256으로 나눔.", "",
             "| 자료 | 2 cm 안 짝 | 세 값 모두 같음 | R·G·B 같음 | 차의 절댓값 중앙값 (R·G·B) | 95 분위 | 평균 차 GeoGS − 자료 |", "|---|---:|---:|---|---|---|---|"]
        recs = {}
        for p in rg:
            r = jl(p); recs[r["target"]] = r
            L.append(f"| {LAB.get(r['target'], r['target'])} | {r['pairs_within_2cm']:,} | {r['share_all_three_equal']*100:.1f} % | " +
                     " · ".join(f"{x*100:.1f} %" for x in r["share_each_channel_equal"]) + " | " + " · ".join(f"{x:.0f}" for x in r["abs_diff_median"]) +
                     " | " + " · ".join(f"{x:.0f}" for x in r["abs_diff_p95"]) + " | " + " · ".join(f"{x:+.1f}" for x in r["mean_diff_geogs_minus_target"]) + " |")
        (DOCS / "tables/t3d_rgb.md").write_text("\n".join(L) + "\n")
        jdump(DOCS / "tables/t3d_rgb.json", recs)
    print("tables", done)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "query":
        log_ = []
        for n in sys.argv[2:]:
            log_.append(query(n))
        p = B0 / "dist/query_log.json"
        old = jl(p) if p.exists() else []
        jdump(p, old + [dict(e, made=now()) for e in log_])
    elif cmd == "reverse":
        reverse()
    elif cmd == "misalign":
        misalign()
    elif cmd == "rgb":
        for n in sys.argv[2:]:
            rgb(n)
    elif cmd == "tables":
        tables()
