"""PHD-MAIN-JUDGEABL-v1 5절 캠퍼스 판 검산 (같을 필요 없음, 차이만 적는다; 참값 읽지 않음). FA_CFG=judgeabl_v1_fusion_campus.json.
  (가) 세 실험 지역 상자: JUDGEAPPLY region[4] (상자 MVS) 와 캠퍼스 판 구분 (같은 JA 패치 중심) — 넓이
  (나) 지역 MVS 판 (fusion_<prior>.npz) 과 캠퍼스 판 (fusion_campus_<prior>.npz): 둘 다 덮은 JC 패치의 구분 — 넓이
  (다) 칸: 지역 판 격자의 칸 중심을 캠퍼스 묶음 격자에 이어, 두 판 모두 사전 정보가 있는 칸에서 최종 변화 칸이 같은지
  -> /res/campus/check.json"""
import json
from pathlib import Path

import numpy as np

import fa_common as FC
from fa_common import M

R0 = Path("/res")                       # 지역 판 결과 (fusion_all/)
JA = Path("/ph/main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1/decisions")
JP = Path("/ph/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1")
BOX = {"B0_b10": "C_B0", "B173nb_b10": "C_R2", "R1rep_b10": "C_R1"}
out = dict(at=FC.now(), box=[], regional_patches=[], regional_cells=[], GT_read=False, scientific_verdict=None)


def campus_flags(g, prior, xy):
    z = np.load(FC.RES / "sites" / g / prior / "cells.npz"); grid = M.Grid(g)
    c = grid.cell(xy); ok = c >= 0; inch = np.zeros(len(c), bool); inch[ok] = z["final_25"].ravel()[c[ok]]
    return ok, inch


for site, g in BOX.items():
    for prior in ("LoD2", "ALS"):
        dec = np.load(JA / f"{site}__{prior}.npz", allow_pickle=True); A = dec["area"].astype(float); ja = dec["region"][4]
        ok, inch = campus_flags(g, prior, dec["centre"]); cr = np.where(inch, 2, 1)
        out["box"].append(dict(site=site, group=g, prior=prior, patches=len(A), in_campus_grid_area_share=float(A[ok].sum() / A.sum()),
                               equal_area_share=float(A[ok & (cr == ja)].sum() / A[ok].sum()),
                               box_image_campus_prior_m2=float(A[ok & (ja == 2) & (cr == 1)].sum()), box_prior_campus_image_m2=float(A[ok & (ja == 1) & (cr == 2)].sum()),
                               box_image_m2=float(A[ok & (ja == 2)].sum()), campus_image_m2=float(A[ok & (cr == 2)].sum())))
        print(out["box"][-1], flush=True)

for prior in ("LoD2", "ALS"):
    a = np.load(R0 / f"fusion_{prior}.npz"); b = np.load(FC.RES / f"fusion_campus_{prior}.npz")
    with np.load(JP / f"patch_{prior}.npz", allow_pickle=False) as z:
        area, region = z["area"], z["region"]
    for reg in ["SW", "R1", "R2", "R3E", "R4", "R5", "B0"]:
        m = (region == reg) & a["covered"] & b["covered"]; A = area[m]; ra, rb = a["region"][m], b["region"][m]
        out["regional_patches"].append(dict(prior=prior, region=reg, both_covered_area_m2=float(A.sum()), equal_area_share=float(A[ra == rb].sum() / max(A.sum(), 1e-9)),
                                            regional_image_campus_prior_m2=float(A[(ra == 2) & (rb == 1)].sum()), regional_prior_campus_image_m2=float(A[(ra == 1) & (rb == 2)].sum()),
                                            regional_image_m2=float(A[ra == 2].sum()), campus_image_m2=float(A[rb == 2].sum())))
        r = np.load(R0 / "sites" / f"{reg}_search" / prior / "cells.npz"); g = f"C_{reg}"
        z = np.load(FC.RES / "sites" / g / prior / "cells.npz"); grid = M.Grid(g)
        nx, ny = int(r["nx"]), int(r["ny"]); lo = r["lo"]
        cx = lo[0] + (np.arange(nx) + .5) * M.CELL; cy = lo[1] + (np.arange(ny) + .5) * M.CELL
        gx, gy = np.meshgrid(cx, cy); c = grid.cell(np.stack([gx.ravel(), gy.ravel()], 1)); ok = c >= 0
        both = ok & r["prior_cells"].ravel(); both[ok] &= z["prior_cells"].ravel()[c[ok]]
        fr = r["final_25"].ravel(); fc = np.zeros_like(fr); fc[ok] = z["final_25"].ravel()[c[ok]]
        out["regional_cells"].append(dict(prior=prior, region=reg, cells_both_prior=int(both.sum()), equal_share=float((fr[both] == fc[both]).mean()) if both.any() else None,
                                          regional_change_cells=int((fr & both).sum()), campus_change_cells=int((fc & both).sum()),
                                          only_regional=int((fr & ~fc & both).sum()), only_campus=int((~fr & fc & both).sum())))
        print(out["regional_patches"][-1], out["regional_cells"][-1], flush=True)
FC.jdump(FC.RES / "check.json", out)
