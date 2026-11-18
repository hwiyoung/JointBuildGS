"""PHD-MAIN-JUDGEABL-v1 5절 캠퍼스 판: 결합(기존 4)을 WIDEN0 캠퍼스 MVS 로 JC 151동 전체에 (학습 없음, CPU). FA_CFG=judgeabl_v1_fusion_campus.json.
  python fa_campus.py prepare   -> /res/campus/groups/<묶음>/{lod2_mesh,als_mesh}.npz, range.json, views.json; /res/campus/sites.json
  python fa_campus.py link      -> /res/campus/fusion_campus_<prior>.npz (JC 패치 차례: region, target_h, covered, group), link_summary.json
묶음: 탐색 지역마다 하나(그 지역 건물), none 건물은 첫 타일마다 하나. 묶음의 메시 = 그 건물들의 타일과 이웃 타일(8방)의 WIDEN0 타일 메시
  LoD2: 건물 이름마다 한 번만(처음 나온 타일의 것; 타일 메시는 걸친 건물을 통째로 담음), ALS: 타일 core(100 m)에 무게중심이 든 삼각형만(겹침 없앰)
이동(정합) = JC 패치와 같은 값: LoD2 0, ALS = 묶음 건물의 탐색 지역 als_shift_m (none 0). WIDEN0 타일 정합 값은 쓰지 않음(설정에 까닭).
격자 = 묶음의 JC 패치 중심(두 사전 정보) 사각형 + 10 m. 학습 영상 = WIDEN0 학습 819장 가운데 묶음 패치 중심 표본(최대 5000)이 25개 이상 화면에 드는 것.
참값 읽지 않음. scientific_verdict: null."""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

import fa_common as FC
from fa_common import M

W = Path("/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2")
JC = Path("/ph/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2")
JP = Path("/ph/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1")
OUT = FC.RES
ORIGIN = np.array([690953.0, 5336071.0])
REGS = ["SW", "R1", "R2", "R3E", "R4", "R5", "B0"]


def tile_xy(t):
    a, b = t.split("_"); return int(a), int(b)


def neighbours(tiles, have):
    out = set()
    for t in tiles:
        a, b = tile_xy(t)
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                q = f"{a + da}_{b + db}"
                if q in have: out.add(q)
    return sorted(out)


def groups():
    B = [r for r in json.loads((JC / "stage0/buildings.json").read_text())["rows"] if r["in_scope"]]
    g = defaultdict(list)
    for r in B:
        key = f"C_{r['search_region']}" if r["search_region"] != "none" else f"C_none_{sorted(r['tiles'])[0]}"
        g[key].append(r)
    return g


def merge_lod2(tiles):
    Vs, Fs, ts, tt, tb, names, off, soff = [], [], [], [], [], [], 0, 0
    seen = set()
    for t in tiles:
        z = np.load(W / "holdout/internal/prior_tiles" / t / "lod2_mesh.npz")
        bn = [str(x) for x in z["building_names"]]
        for b, nm in enumerate(bn):
            if nm in seen: continue
            seen.add(nm)
            sel = np.nonzero(z["tri_building"] == b)[0]
            if not len(sel): continue
            F = z["F"][sel]; u, inv = np.unique(F, return_inverse=True)
            Vs.append(z["V"][u]); Fs.append(inv.reshape(-1, 3) + off); off += len(u)
            ts.append(z["tri_surface"][sel] + soff); tt.append(z["tri_type"][sel]); tb.append(np.full(len(sel), len(names))); names.append(nm)
        soff += int(z["tri_surface"].max()) + 1
    return dict(V=np.concatenate(Vs), F=np.concatenate(Fs), tri_surface=np.concatenate(ts), tri_type=np.concatenate(tt), tri_building=np.concatenate(tb),
                building_names=np.array(names))


def merge_als(tiles, tinfo):
    Vs, Fs, bt, ts, off, soff = [], [], [], [], 0, 0
    for t in tiles:
        z = np.load(W / "holdout/internal/prior_tiles" / t / "als_mesh.npz")
        c = np.asarray(tinfo[t]["core_global"], float); lo, hi = c[:2] - ORIGIN, c[2:] - ORIGIN
        cen = z["V"][z["F"]].mean(1)[:, :2]
        sel = np.nonzero((cen >= lo).all(1) & (cen < hi).all(1))[0]
        F = z["F"][sel]; u, inv = np.unique(F, return_inverse=True)
        Vs.append(z["V"][u]); Fs.append(inv.reshape(-1, 3) + off); off += len(u)
        bt.append(z["building_tri"][sel]); s_ = z["tri_surface"][sel].astype(np.int64); ts.append(np.where(s_ >= 0, s_ + soff, -1))
        soff += int(max(z["tri_surface"].max(), 0)) + 1
    return dict(V=np.concatenate(Vs), F=np.concatenate(Fs), building_tri=np.concatenate(bt), tri_surface=np.concatenate(ts))


def prepare():
    t0 = time.time()
    tinfo = {r["id"]: r for r in json.loads((W / "inputs/tiles.json").read_text())}
    have = set(tinfo)
    split = json.loads((W / "image_split.json").read_text()); train = sorted(n.rsplit(".", 1)[0] for n in split["train"])
    V = FC._views()
    P = {}
    for prior in ("LoD2", "ALS"):
        with np.load(JP / f"patch_{prior}.npz", allow_pickle=False) as z:
            P[prior] = dict(centre=z["centre"], building=z["building"])
    sites, rows = {}, []
    for gname, bl in sorted(groups().items()):
        tg = time.time()
        names = {r["building"] for r in bl}; reg = bl[0]["search_region"]
        tiles = neighbours(sorted({t for r in bl for t in r["tiles"]}), have)
        D = OUT / "groups" / gname; D.mkdir(parents=True, exist_ok=True)
        np.savez(D / "lod2_mesh.npz", **merge_lod2(tiles)); np.savez(D / "als_mesh.npz", **merge_als(tiles, tinfo))
        cen = np.concatenate([P[p]["centre"][np.isin(P[p]["building"], list(names))] for p in ("LoD2", "ALS")])
        lo, hi = cen[:, :2].min(0), cen[:, :2].max(0)
        (D / "range.json").write_text(json.dumps(dict(id=gname, kind="xy_rect", polygon_local=[[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]],
                                                      note="JC 패치 중심(두 사전 정보) 사각형; 격자는 + 10 m")))
        smp = cen[np.linspace(0, len(cen) - 1, min(len(cen), 5000)).astype(np.int64)]
        vs = []
        for s in train:
            u, v, zc = V.project(f"{s}.jpg", smp)
            if int(((zc > 0) & (u >= 0) & (u < M.W) & (v >= 0) & (v < M.H)).sum()) >= 25: vs.append(s)
        (D / "views.json").write_text(json.dumps(dict(train=vs, rule="WIDEN0 학습 819장 가운데 묶음 패치 중심 표본(최대 5000)이 25개 이상 화면 안(z > 0)")))
        sh = np.asarray(bl[0]["als_shift_m"], float)
        assert all(np.allclose(r["als_shift_m"], sh) for r in bl)
        sites[gname] = dict(kind="campus_group", search_region=reg, buildings=sorted(names), tiles=tiles, mesh_dir=str(D), mvs_dir=str(W / "mvs/full"),
                            depth_name="{stem}.JPG.geometric.bin", views_file=str(D / "views.json"), views_key="train", images_dir=str(OUT / "inputs/images"),
                            shift=dict(LoD2=[0.0, 0.0, 0.0], ALS=sh.tolist()))
        rows.append(dict(group=gname, region=reg, buildings=len(names), tiles=len(tiles), views=len(vs), area_m2=float(np.prod(hi - lo + 20)), seconds=round(time.time() - tg, 1)))
        print(rows[-1], flush=True)
    FC.jdump(OUT / "sites.json", dict(at=FC.now(), sites=sites, rows=rows, seconds=round(time.time() - t0, 1), scientific_verdict=None))


def link():
    S = json.loads((OUT / "sites.json").read_text())["sites"]
    gnames = sorted(S)
    bgroup = {b: g for g, s in S.items() for b in s["buildings"]}
    summ = dict(at=FC.now(), rule=FC.C["region_rule"], rows=[], GT_read=False, scientific_verdict=None)
    for prior in ("LoD2", "ALS"):
        with np.load(JP / f"patch_{prior}.npz", allow_pickle=False) as z:
            d = {k: z[k] for k in ("centre", "region", "building", "mvs_mean_m", "prior_height_m", "area", "n")}
        N = len(d["area"]); reg = np.full(N, 9, np.int8); cov = np.zeros(N, bool); gi = np.full(N, -1, np.int16); jd = np.zeros(N, bool)
        pg = np.array([bgroup.get(b, "") for b in d["building"]])
        for k, g in enumerate(gnames):
            m = np.flatnonzero(pg == g)
            row = dict(prior=prior, group=g, region=S[g]["search_region"], patches=int(len(m)), area_m2=float(d["area"][m].sum()))
            cf = OUT / "sites" / g / prior / "cells.npz"
            if not cf.exists():
                row.update(status="확인 불가", why="결합 판정을 내지 못함"); summ["rows"].append(row); continue
            z = np.load(cf); grid = M.Grid(g)
            assert np.allclose(z["lo"], grid.lo) and int(z["nx"]) == grid.nx and int(z["ny"]) == grid.ny
            c = grid.cell(d["centre"][m]); ok = c >= 0
            inch = np.zeros(len(m), bool); inch[ok] = z["final_25"].ravel()[c[ok]]
            j_ = np.zeros(len(m), bool); j_[ok] = z["nsee"].ravel()[c[ok]] >= M.RULE["cells"]["min_views"]
            reg[m] = np.where(ok, np.where(inch, 2, 1), 9); cov[m] = ok; gi[m] = k; jd[m] = j_
            A = d["area"][m]
            row.update(status="냄", covered_patches=int(ok.sum()), covered_area_m2=float(A[ok].sum()), image_area_m2=float(A[inch].sum()),
                       image_share=float(A[inch].sum() / max(A[ok].sum(), 1e-9)), judged_area_share=float(A[j_].sum() / max(A[ok].sum(), 1e-9)),
                       outside_grid_patches=int((~ok).sum()))
            summ["rows"].append(row)
        miss = pg == ""
        th = np.where(reg == 2, d["mvs_mean_m"], np.where(reg == 1, d["prior_height_m"], np.nan))
        np.savez(OUT / f"fusion_campus_{prior}.npz", region=reg, target_h=th.astype(np.float64), covered=cov, judged=jd, group=gi, groups=np.array(gnames), n=N)
        summ[f"{prior}_covered"] = dict(patches=int(cov.sum()), of=N, area_m2=float(d["area"][cov].sum()), of_area_m2=float(d["area"].sum()),
                                        area_share=float(d["area"][cov].sum() / d["area"].sum()), patches_without_group=int(miss.sum()),
                                        image_share=float(d["area"][reg == 2].sum() / max(d["area"][cov].sum(), 1e-9)))
        print(prior, summ[f"{prior}_covered"], flush=True)
    FC.jdump(OUT / "link_summary.json", summ)


if __name__ == "__main__":
    {"prepare": prepare, "link": link}[sys.argv[1]]()
