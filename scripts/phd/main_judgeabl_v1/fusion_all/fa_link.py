"""PHD-MAIN-JUDGEABL-v1 5절: JC 전 건물 패치(JP patch_<prior>.npz 순서)를 결합 판정 칸에 잇는다 (detect.patch_flags 와 같은 규칙:
패치 중심의 0.25 m 칸이 최종 변화 칸(색 문턱 25)이면 변화). 패치는 자기 탐색 지역(JC region)의 격자에만 잇는다.
  v2: 자기 탐색 지역 격자 밖 패치 = 9 (덮이지 않음).
  region 2 = 영상 깊이 사용 (목표 = mvs_mean_m), 1 = 사전정보 사용 (목표 = prior_height_m), 9 = 덮이지 않음 (none 지역, 끝내지 못한 지역; 목표 NaN)
  python fa_link.py -> /res/fusion_<prior>.npz (region, target_h, covered, judged, in_grid, site), /res/link_summary.json. 참값 읽지 않음."""
import json
from pathlib import Path

import numpy as np

import fa_common as FC
from fa_common import M

JP = Path("/ph/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1")
REGS = ["SW", "R1", "R2", "R3E", "R4", "R5", "B0"]
summ = dict(at=FC.now(), rule=FC.C["region_rule"], not_covered=FC.C["not_covered"], rows=[], GT_read=False, scientific_verdict=None)
for prior in ("LoD2", "ALS"):
    with np.load(JP / f"patch_{prior}.npz", allow_pickle=False) as z:
        d = {k: z[k] for k in ("centre", "region", "mvs_mean_m", "prior_height_m", "area", "n", "kind")}
    N = len(d["area"])
    reg = np.full(N, 9, np.int8); covered = np.zeros(N, bool); judged = np.zeros(N, bool); in_grid = np.zeros(N, bool)
    site_ix = np.full(N, -1, np.int8)
    for k, r in enumerate(REGS + ["none"]):
        m = np.flatnonzero(d["region"] == r)
        row = dict(prior=prior, region=r, patches=int(len(m)), area_m2=float(d["area"][m].sum()))
        cf = FC.RES / "sites" / f"{r}_search" / prior / "cells.npz"
        if r == "none" or not cf.exists():
            row.update(status="확인 불가", why="탐색 지역 없음 (지역 MVS·정합 값·1단계 범위 없음)" if r == "none" else "결합 판정을 내지 못함")
            summ["rows"].append(row); continue
        z = np.load(cf); grid = M.Grid(f"{r}_search")
        assert np.allclose(z["lo"], grid.lo) and int(z["nx"]) == grid.nx and int(z["ny"]) == grid.ny
        c = grid.cell(d["centre"][m]); ok = c >= 0
        inch = np.zeros(len(m), bool); inch[ok] = z["final_25"].ravel()[c[ok]]
        jd = np.zeros(len(m), bool); jd[ok] = z["nsee"].ravel()[c[ok]] >= M.RULE["cells"]["min_views"]
        reg[m] = np.where(ok, np.where(inch, 2, 1), 9); covered[m] = ok; judged[m] = jd; in_grid[m] = ok; site_ix[m] = k     # v2: 격자 밖 = 덮이지 않음
        A = d["area"][m]
        row.update(status="냄", covered_patches=int(ok.sum()), covered_area_m2=float(A[ok].sum()), image_area_m2=float(A[inch].sum()), prior_area_m2=float(A[ok & ~inch].sum()),
                   image_share=float(A[inch].sum() / A[ok].sum()), outside_grid_patches=int((~ok).sum()), outside_grid_area_m2=float(A[~ok].sum()),
                   judged_area_share=float(A[jd].sum() / A[ok].sum()),
                   n_lt4_area_m2=float(A[(d["n"][m] >= 0) & (d["n"][m] < 4)].sum()), image_and_mvs_nan_area_m2=float(A[inch & ~np.isfinite(d["mvs_mean_m"][m])].sum()))
        summ["rows"].append(row)
    th = np.where(reg == 2, d["mvs_mean_m"], np.where(reg == 1, d["prior_height_m"], np.nan))
    np.savez(FC.RES / f"fusion_{prior}.npz", region=reg, target_h=th.astype(np.float64), covered=covered, judged=judged, in_grid=in_grid, site=site_ix,
             sites=np.array(REGS + ["none"]), n=N)
    cov = covered
    summ[f"{prior}_covered"] = dict(patches=int(cov.sum()), of=N, area_m2=float(d["area"][cov].sum()), of_area_m2=float(d["area"].sum()))
    print(prior, summ[f"{prior}_covered"], flush=True)
FC.jdump(FC.RES / "link_summary.json", summ)
for r in summ["rows"]:
    print(json.dumps(r, ensure_ascii=False))
