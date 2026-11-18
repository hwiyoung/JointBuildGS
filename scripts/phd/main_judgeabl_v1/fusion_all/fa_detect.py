"""PHD-MAIN-JUDGEABL-v1 5절: 한 자리(상자 또는 탐색 지역) x 사전 정보의 결합 판정 칸 (학습 없음, CPU).
  python fa_detect.py images <site>              -> /res/inputs/<site>/images/<stem>.jpg (fork_inputs_v6 와 같은 방법), images.json
  python fa_detect.py pairs <site>               -> /res/sb/prep/mvsfuse/pairs_<site>.json (inherited/pairs.py main 그대로)
  python fa_detect.py run <site> <LoD2|ALS> [--nproc 14]
        -> /res/sites/<site>/<prior>/cells.npz (세 색 문턱의 최종 변화 칸, 25 의 투표·제거·넓힘 층, nsee, prior_cells, dz_med),
           detect.json (원래 detect.json 의 판정 기록, 패치 셈 없음), timing
판정 단계는 inherited/detect.py 의 judge, decide 를 그대로 부른다 (detect.unit 의 1~2 단계와 같은 순서, 같은 값). 3 단계(합친 깊이)와
지역 파일 패치 셈(counts, records)은 판정에 쓰이지 않아 하지 않는다. scientific_verdict: null."""
import argparse
import json
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

import fa_common as FC
from fa_common import DT, M


def images(site):
    import cv2
    t0 = time.time()
    s = FC.site_cfg(site)
    out = Path(s["images_dir"]); out.mkdir(parents=True, exist_ok=True)
    tr, dropped = FC.train_views(site)
    src = Path(FC.C["dense_images"])
    made = 0
    for x in tr:
        q = out / f"{x}.jpg"
        if q.exists():
            continue
        img = cv2.imread(str(src / f"{x}.JPG"))
        cv2.imwrite(str(q), cv2.resize(img, (M.W, M.H), interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 95])
        made += 1
    FC.jdump(FC.RES / "inputs" / f"images_{site}.json", dict(site=site, train=len(tr), made=made, without_depth_map=dropped, source=str(src),
                                                                 rule="cv2.resize INTER_AREA to 1024 x 741, JPEG 95 (= fork_inputs_v6.py:108-109)",
                                                                 seconds=round(time.time() - t0, 1), scientific_verdict=None))
    M.log(site, "images", len(tr), "made", made, round(time.time() - t0, 1), "s")


def pairs(site):
    import pairs as PR
    PR.main(site)


def run(site, prior, nproc):
    T0 = time.time(); times = {}
    V, train, _ = M.views(site)
    pj = json.loads((M.SB / "prep/mvsfuse" / f"pairs_{site}.json").read_text())
    prs = {r["view"]: r["pair"] for r in pj["pairs"]}
    P = M.Prior(site, prior)
    grid = M.Grid(site)
    RR = M.RULE["removal"]
    # 건물 영역: 칸과 지면 높이 (= detect.unit)
    t = time.time()
    bcells, hg, binfo = [], np.full(max(P.n_bld, 1), np.nan), []
    if prior == "ALS":
        gsel = ~P.building_tri
        cen = P.V[P.F[gsel]].mean(1)
        gcell = grid.cell(cen)
    for b in range(P.n_bld):
        tb = np.nonzero(P.tri_bld == b)[0]
        cb = M.raster_triangles(grid, P.V, P.F[tb])
        bcells.append(cb)
        if prior == "LoD2":
            walls = tb[P.tri_type[tb] == 1]
            lows = [float(P.V[P.F[walls[P.tri_surface[walls] == s_]]].reshape(-1, 3)[:, 2].min()) for s_ in np.unique(P.tri_surface[walls])]
            hg[b] = float(np.median(lows)) if lows else np.nan
            binfo.append(dict(building=b, name=P.building_names[b] if P.building_names and b < len(P.building_names) else None, triangles=int(len(tb)),
                              cells=int(len(cb)), wall_surfaces=len(lows), ground_m=None if not lows else round(hg[b], 3)))
        else:
            mk = np.zeros(grid.n, bool)
            mk[cb] = True
            ring = M.dilate(mk.reshape(grid.ny, grid.nx), RR["band_m"]).ravel() & ~mk
            sel = (gcell >= 0) & ring[np.maximum(gcell, 0)]
            hg[b] = float(np.median(cen[sel, 2])) if sel.any() else np.nan
            binfo.append(dict(building=b, triangles=int(len(tb)), cells=int(len(cb)), band_ground_triangles=int(sel.sum()),
                              ground_m=None if not sel.any() else round(hg[b], 3)))
    times["buildings_s"] = round(time.time() - t, 1)
    DT.G.update(V=V, P=P, grid=grid, site=site, prior=prior, pairs=prs, n_bld=P.n_bld, tri_bld=P.tri_bld, hg=hg, dz_only=False)
    M.log(site, prior, "buildings", P.n_bld, "views", len(train), "paired", sum(1 for s in train if prs.get(s)), "grid", grid.nx, grid.ny)
    t = time.time()
    with mp.get_context("fork").Pool(nproc) as pool:
        res = pool.map(DT.judge, train, chunksize=1)
    times["views_s"] = round(time.time() - t, 1)
    M.log("views done", times["views_s"])
    ver = dict(views=len(res), max_mismatch_px=max(r["ver"]["mismatch_px"] for r in res), max_abs_m=max(r["ver"]["max_abs_m"] for r in res))
    paired = [r for r in res if r["pair"] is not None and "vote_cells" in r]
    t = time.time()
    n = grid.n; THR = DT.THR
    nsee = np.zeros(n, np.int64); nch = np.zeros((len(THR), n), np.int64)
    for r in paired:
        c = r["vote_cells"]; nsee[c] += 1
        nch[:, c] += (2 * r["vote_ch"] > r["vote_n"][None, :]).astype(np.int64)
    prior_cells = np.zeros(n, bool)
    for r in res:
        prior_cells[r["hit_cells"]] = True
    dz_cell = np.concatenate([r["dz_cell"] for r in res]); dz_val = np.concatenate([r["dz"] for r in res])
    dz_med, dz_cnt = DT.cell_median(dz_cell, dz_val, n)
    del dz_cell, dz_val
    rem_n = np.sum([r["rem_n"] for r in paired if "rem_n" in r], 0) if any("rem_n" in r for r in paired) else np.zeros(max(P.n_bld, 1), np.int64)
    rem_sim = np.sum([r["rem_sim"] for r in paired if "rem_sim" in r], 0) if any("rem_sim" in r for r in paired) else np.zeros((len(THR), max(P.n_bld, 1)), np.int64)
    ss = dict(ny=grid.ny, nx=grid.nx, lo=grid.lo, nsee=nsee, nch=nch, n_bld=P.n_bld, rem_n=rem_n, rem_sim=rem_sim, bcells=bcells,
              prior_cells=prior_cells.reshape(grid.ny, grid.nx), dz_med=dz_med.reshape(grid.ny, grid.nx), dz_cnt=dz_cnt, in_eval=grid.in_eval)
    finals, decisions = {}, {}
    for t_i, th_ in enumerate(THR):
        final, rec, layers = DT.decide(ss, t_i, extra=False)
        finals[int(th_)] = final; decisions[str(int(th_))] = rec
        if t_i == 0:
            main_layers = layers
    times["cells_s"] = round(time.time() - t, 1)
    RD = FC.RES / "sites" / site / prior; RD.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RD / "cells.npz", lo=grid.lo, cell=M.CELL, nx=grid.nx, ny=grid.ny, nsee=nsee.reshape(grid.ny, grid.nx).astype(np.int32),
                        thresholds=np.array(THR), prior_cells=ss["prior_cells"], dz_med=ss["dz_med"], vote=main_layers["vote"], removal=main_layers["removal"],
                        grown=main_layers["grown"], **{f"final_{k}": v for k, v in finals.items()})
    pstats = [dict(view=r["view"], pair=r["pair"], seconds=r["seconds"], **r["stats"]) for r in res]
    times["all_s"] = round(time.time() - T0, 1)
    A = M.CELL ** 2
    rec0 = decisions["25"]
    FC.jdump(RD / "detect.json", dict(at=FC.now(), site=site, prior=prior, rule=M.RULE, decisions_1015=M.DECISIONS_1015, config=FC.site_cfg(site),
                                     training_views=len(train), paired_views=len(paired), buildings=binfo, recast_check=ver, decisions=decisions,
                                     areas_m2=dict(vote=round(rec0["vote_cells"] * A, 2), removal_added=round(rec0["removal_added_cells"] * A, 2),
                                                   grown=round(rec0["growth_added_cells"] * A, 2), final=round(rec0["final_cells"] * A, 2)),
                                     not_made=["composite depth (step 3)", "region-file patch counts", "colour reference (tau maps not made)", "1.5 m growth reference"],
                                     seconds=times, scientific_verdict=None))
    FC.jdump(RD / "views.json", dict(site=site, prior=prior, views=pstats, scientific_verdict=None))
    M.log(json.dumps(dict(site=site, prior=prior, final_m2=round(rec0["final_cells"] * A, 1), s=times)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["images", "pairs", "run"])
    ap.add_argument("site"); ap.add_argument("prior", nargs="?")
    ap.add_argument("--nproc", type=int, default=14)
    a = ap.parse_args()
    t0 = time.time()
    if a.mode == "images":
        images(a.site)
    elif a.mode == "pairs":
        pairs(a.site)
    else:
        run(a.site, a.prior, a.nproc)
    tf = FC.RES / "timing.jsonl"; tf.parent.mkdir(parents=True, exist_ok=True)
    with tf.open("a") as f:
        f.write(json.dumps(dict(at=FC.now(), mode=a.mode, site=a.site, prior=a.prior, seconds=round(time.time() - t0, 1))) + "\n")
