"""PHD-MAIN-AXES71-v2 일 2 영역 나눔 (합 100 %) and 일 1 참값 밀도 (jointbuildgs:dev, CPU; reads the region files, no result).

  python a2_cells.py      -> AX/work/cells_<site>_<prior>.npz, /docs/tables/일2_영역나눔.md|json, /docs/tables/일1_참값밀도.md|json

Cells: ax_common.cells_of (the locked rule of the config, cells.rule). Per case and per prior (three sites summed):
  patches, area (m2, region file 'area') and its share of the in-range patch area; region rows (the thinned rows of rows_<prior>.npz = the
  GT points the cell metrics use; the v4 counts) and their share; scene GT points (the 전체 metric's GT: ULS of the building-surface cells)
  through their owner patch (dm_common.owner_of_scene_points) and their share, with the points without a patch as '패치 없음' in the sum.
Density (일 1): per patch the owned GT rows (all rows, before thinning) / area, expected spacing 1 / sqrt(density); by slope of the
prior-face normal (dm_common.Unit.n_p: arccos |n_z|) 0~30, 30~60, 60~90 deg. Patch size: area quantiles and the median distance from a
patch centre to the nearest other in-range patch centre (the clump rule's check, 일 6).
Checks: the v4 counts (order 5.2) and the distance task's place rows (DM/tables/d3_metrics.json n_gt). [이 발주에서 냄] scientific_verdict: null."""
import numpy as np
from scipy.spatial import cKDTree

from ax_common import (CASES, CELL_KO, CELLS, CID, CFG, DM, DOCS, KEY_KO, PRIORS, S1, SITES, SUMS, WORK, SiteGT, Unit, case_ko, cell_mask, cells_of, jdump,
                       jl, log, now, obs_masked)
import dm_common as DMC

V4_CHECK = {("B0_b10", "LoD2", "s_corr"): 33860, ("B173nb_b10", "ALS", "s_corr"): 96269, ("B0_b10", "ALS", "s_keep"): 1755, ("R1rep_b10", "ALS", "s_keep"): 14112,
            ("B0_b10", "LoD2", "c_refine"): 301740, ("B173nb_b10", "ALS", "c4"): 111}
DM_PLACE = {"s_corr": "c11", "s_keep": "img", "c_refine": "c2", "c4": "c4", "c_corr14": "c11s", "c_inh_invis": "c5"}


def one(site, prior, gt):
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")
    cell, facts = cells_of(site, prior, R)
    u = Unit(site, prior, gt)
    area = R["area"].astype(np.float64)
    ev = R["in_eval"].astype(bool)
    code = R["code_ext_v3"].astype(np.int64)
    r = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    own_all = np.bincount(r["patch"].astype(np.int64), minlength=len(area))
    dens = np.where(area > 0, own_all / np.maximum(area, 1e-12), np.nan)
    spacing = np.where(own_all > 0, 1.0 / np.sqrt(np.maximum(dens, 1e-12)), np.inf)
    nz = np.abs(u.n_p[:, 2])
    slope = np.degrees(np.arccos(np.clip(nz, 0, 1)))
    ratio1 = np.abs(R["gt_med"].astype(np.float64)) / R["tau"].astype(np.float64)
    vgeo = np.where(R["v1_kept"].astype(bool), R["mvs_minus_prior"].astype(np.float64) - R["gt_med"].astype(np.float64), R["mvs_minus_gt_at_gt"].astype(np.float64))
    ratio2 = np.abs(vgeo) / R["tau"].astype(np.float64)
    OM = obs_masked(site, prior)
    obs = OM["obs"].astype(bool)
    vg_om = OM["v_geo"].astype(np.float64)
    c23 = np.isin(R["code_ext_v3"], (2, 3)) & R["in_eval"].astype(bool)      # the code-3 decision's patches (v_geo outside codes 2-5 is the pixel branch)
    both = c23 & np.isfinite(vgeo) & np.isfinite(vg_om)
    vgeo_check = dict(compared=int(both.sum()), max_abs_diff_m=float(np.max(np.abs(vgeo[both] - vg_om[both]))) if both.any() else None,
                      nan_mismatch=int((c23 & (np.isfinite(vgeo) != np.isfinite(vg_om))).sum()), scope="코드 2·3, 평가 범위")
    vph = OM["v_photo"].astype(np.float64)
    np.savez_compressed(WORK / f"prefilter_{site}_{prior}.npz", ratio_before=(np.abs(vph) / R["tau"].astype(np.float64)).astype(np.float32), v_photo=vph.astype(np.float32))
    np.savez_compressed(WORK / f"cells_{site}_{prior}.npz", cell=cell, density=dens.astype(np.float32), spacing=spacing.astype(np.float32),
                        slope=slope.astype(np.float32), ratio1=ratio1.astype(np.float32), ratio2=ratio2.astype(np.float32), code=code.astype(np.int8),
                        in_eval=ev, obs=obs, has_gt=own_all > 0, area=area.astype(np.float32), own_rows=own_all.astype(np.int32))
    # region rows (thinned) and scene points
    r_cell = cell[u.r_pa]
    s_own = DMC.owner_of_scene_points(site, prior, gt)
    s_cell = np.where(s_own >= 0, cell[np.maximum(s_own, 0)], -2)            # -2 = no patch; -1 = the owner is outside the range
    out = dict(case=f"{site}/{prior}", facts=facts, vgeo_check=vgeo_check, obs_with_vphoto=int((obs & np.isfinite(vph)).sum()), obs_total=int(obs.sum()), area_total=float(area[ev].sum()), patches_total=int(ev.sum()),
               rows_total_in_range=int((r_cell >= 0).sum()), rows_outside_range=int((r_cell < 0).sum()),
               scene_total=int(len(s_cell)), scene_no_patch=int((s_cell == -2).sum()), scene_owner_outside=int((s_cell == -1).sum()), cells={})
    for k in CELLS + list(SUMS):
        m = cell_mask(cell, k)
        rr = cell_mask(r_cell, k) if k != "all" else r_cell >= 0
        ss = cell_mask(s_cell, k)
        out["cells"][k] = dict(patches=int(m.sum()), area=float(area[m].sum()), rows=int(rr.sum()), scene=int(ss.sum()))
    # code-4 part of 보존 · 거름 (the v4 '결측 영역' = 상속 · 결측 + 보존 · 거름 with code 4)
    m4 = ((cell == CID["c_keep_mask"]) & (code == 4)) | (cell == CID["c_inh_miss"])
    out["cells"]["c4"] = dict(patches=int(m4.sum()), area=float(area[m4].sum()), rows=int(m4[u.r_pa].sum()), scene=None)
    # density by slope (in-range patches with GT)
    dd = {}
    for lo, hi in ((0, 30), (30, 60), (60, 90.0001)):
        m = ev & (own_all > 0) & (slope >= lo) & (slope < hi)
        if not m.any():
            dd[f"{lo}-{int(hi)}"] = dict(patches=0)
            continue
        q = lambda a, p: float(np.percentile(a, p))
        dd[f"{lo}-{int(hi)}"] = dict(patches=int(m.sum()), area=float(area[m].sum()), density_p10=q(dens[m], 10), density_p50=q(dens[m], 50), density_p90=q(dens[m], 90),
                                     spacing_p50_cm=100 * q(spacing[m], 50), spacing_p90_cm=100 * q(spacing[m], 90),
                                     share_spacing_le_tau=float((spacing[m] <= R["tau"][m]).mean()), share_spacing_le_half_tau=float((spacing[m] <= 0.5 * R["tau"][m]).mean()))
    out["density_by_slope"] = dd
    out["patches_without_rows_in_range"] = int((ev & (own_all == 0)).sum())
    c = R["centre"][ev]
    d2, _ = cKDTree(c).query(c, k=2, workers=-1)
    a = area[ev]
    out["patch_size"] = dict(area_p10=float(np.percentile(a, 10)), area_p50=float(np.percentile(a, 50)), area_p90=float(np.percentile(a, 90)), area_max=float(a.max()),
                             nn_centre_m_p50=float(np.median(d2[:, 1])), nn_centre_m_p90=float(np.percentile(d2[:, 1], 90)))
    return out


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def main():
    data = {}
    for site in SITES:
        gt = SiteGT(site)
        for prior in PRIORS:
            data[f"{site}/{prior}"] = one(site, prior, gt)
            log(site, prior, data[f"{site}/{prior}"]["facts"])
    # sums per prior
    for prior in PRIORS:
        us = [data[f"{s}/{prior}"] for s in SITES]
        S = dict(case=f"합/{prior}", area_total=sum(x["area_total"] for x in us), patches_total=sum(x["patches_total"] for x in us),
                 rows_total_in_range=sum(x["rows_total_in_range"] for x in us), scene_total=sum(x["scene_total"] for x in us),
                 scene_no_patch=sum(x["scene_no_patch"] for x in us), scene_owner_outside=sum(x["scene_owner_outside"] for x in us), cells={})
        for k in us[0]["cells"]:
            S["cells"][k] = {f: (None if any(x["cells"][k][f] is None for x in us) else sum(x["cells"][k][f] for x in us)) for f in ("patches", "area", "rows", "scene")}
        data[f"합/{prior}"] = S
    # checks
    D3 = (jl(DM / "tables/d3_metrics.json") or {}).get("data", {})
    checks = []
    for (site, prior, k), want in V4_CHECK.items():
        got = data[f"{site}/{prior}"]["cells"][k]["rows"]
        checks.append(dict(case=f"{site}/{prior}", cell=k, v4=want, here=got, same=got == want))
    dm_rows = []
    for site, prior in CASES:
        u = f"{site}/{prior}"
        if u not in D3:
            continue
        for k, pl in DM_PLACE.items():
            o = D3[u]["method"]["values"][D3[u]["method"]["results"][0]].get(pl, {})
            ref = o.get("n_gt")
            got = data[u]["cells"][k]["rows"]
            dm_rows.append(dict(case=u, cell=k, place=pl, distance_task=ref, here=got, same=ref == got))
    sums_ok = {}
    for u, d in data.items():
        a = sum(d["cells"][k]["area"] for k in CELLS)
        rw = sum(d["cells"][k]["rows"] for k in CELLS)
        sc = sum(d["cells"][k]["scene"] for k in CELLS) + d["scene_no_patch"] + d["scene_owner_outside"]
        sums_ok[u] = dict(area_sum=a, area_total=d["area_total"], area_share_sum=pct(a, d["area_total"]), rows_sum=rw, rows_total=d["rows_total_in_range"],
                          scene_sum=sc, scene_total=d["scene_total"], patches_sum=sum(d["cells"][k]["patches"] for k in CELLS), patches_total=d["patches_total"])
    jdump(DOCS / "tables/일2_영역나눔.json", dict(task="PHD-MAIN-AXES71-v2", work="일 2", made=now(), rule=CFG["cells"]["rule"], rule_why=CFG["cells"]["rule_why"],
                                              data=data, sums=sums_ok, checks_v4=checks, checks_distance_task=dm_rows, scientific_verdict=None))
    write_md(data, sums_ok, checks, dm_rows)
    write_density(data)
    log("done")


def write_md(data, sums_ok, checks, dm_rows):
    L = ["# 일 2 영역 나눔 — 칸마다 넓이와 참값 점 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "",
         f"- 만든 때 {now()}. 스크립트 `scripts/phd/main_axes71_v2/a2_cells.py`, 칸 규칙 = 설정 `configs/phd/main_axes71_v2/axes71_v2.json` cells.rule(잠금 39ffd056).",
         "- 넓이 비율의 분모 = 평가 범위 안 사전 정보 패치 넓이 전체. 영역 행 = 칸 지표가 쓰는 참값 점(rows_<사전 정보>.npz의 솎은 행; v4의 수와 같은 꼴). "
         "장면 점 = 전체 지표의 참값 점(건물 표면 칸의 드론 LiDAR)을 대응 패치로 칸에 넣은 것이며, 대응 패치가 없는 점은 '패치 없음' 줄로 합에 넣는다.",
         "- 반올림 전 값은 같은 이름의 json.", ""]
    for u, d in data.items():
        nm = u if u.startswith("합") else case_ko(*u.split("/"))
        if u.startswith("합"):
            nm = f"{'LoD2' if u.endswith('LoD2') else '항공 LiDAR'} 합(세 지역)"
        L += [f"## {nm}", "", "| 칸 | 패치 | 넓이 (m²) | 넓이 비율 (%) | 영역 행 | 영역 행 비율 (%) | 장면 점 | 장면 점 비율 (%) |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for k in CELLS:
            c = d["cells"][k]
            L.append(f"| {CELL_KO[k]} | {c['patches']:,} | {c['area']:,.1f} | {pct(c['area'], d['area_total']):.2f} | {c['rows']:,} | {pct(c['rows'], d['rows_total_in_range']):.2f} | "
                     f"{c['scene']:,} | {pct(c['scene'], d['scene_total']):.2f} |")
        L.append(f"| 패치 없음 | — | — | — | — | — | {d['scene_no_patch']:,} | {pct(d['scene_no_patch'], d['scene_total']):.2f} |")
        if d.get("scene_owner_outside"):
            L.append(f"| 대응 패치가 평가 범위 밖 | — | — | — | — | — | {d['scene_owner_outside']:,} | {pct(d['scene_owner_outside'], d['scene_total']):.2f} |")
        s = sums_ok[u]
        L.append(f"| **합** | {s['patches_sum']:,} | {s['area_sum']:,.1f} | {s['area_share_sum']:.2f} | {s['rows_sum']:,} | {pct(s['rows_sum'], s['rows_total']):.2f} | {s['scene_sum']:,} | {pct(s['scene_sum'], s['scene_total']):.2f} |")
        L += ["", "| 의도별 합 | 패치 | 넓이 (m²) | 넓이 비율 (%) | 영역 행 | 영역 행 비율 (%) |", "|---|---:|---:|---:|---:|---:|"]
        for k in SUMS:
            c = d["cells"][k]
            L.append(f"| {KEY_KO[k]} | {c['patches']:,} | {c['area']:,.1f} | {pct(c['area'], d['area_total']):.2f} | {c['rows']:,} | {pct(c['rows'], d['rows_total_in_range']):.2f} |")
        if "facts" in d:
            f = d["facts"]
            L += ["", f"- 칸에 들지 않은 평가 범위 패치 {f['unassigned_in_eval']}개. 겹침의 차례로 옮긴 패치(참값 있는 것): 거른 영상 오류 ∩ 코드 2 → 보존 · 거름 {f['obs_and_code2']}개, "
                  f"거른 영상 오류 ∩ 코드 3 문턱 넘음 → 한계 {f['obs_and_limit']}개, 거른 영상 오류 ∩ 코드 4 → 보존 · 거름 {f['obs_and_code4']}개. 코드 0인데 참값 행이 있는 패치 {f['code0_with_rows']}개와 "
                  f"코드가 0이 아닌데 참값 행이 없는 패치 {f['nonzero_code_without_rows']}개는 참값 없음. 코드 11인데 |gt_med| < τ인 패치 {f['code11_ratio_below1']}개."]
        L.append("")
    L += ["## 맞춰 볼 것", "", "| 경우 | 칸 | v4 의도 한눈에 | 여기 | 같음 |", "|---|---|---:|---:|---|"]
    for c in checks:
        L.append(f"| {case_ko(*c['case'].split('/'))} | {KEY_KO.get(c['cell'], '결측 영역(상속 · 결측 + 보존 · 거름 코드 4)')} | {c['v4']:,} | {c['here']:,} | {'같음' if c['same'] else '어긋남 !'} |")
    L += ["", "| 경우 | 칸 | 새 거리 지표의 곳 | 그 곳의 참값 점 | 여기 | 같음 |", "|---|---|---|---:|---:|---|"]
    for c in dm_rows:
        L.append(f"| {case_ko(*c['case'].split('/'))} | {KEY_KO.get(c['cell'], '결측 영역')} | {c['place']} | {c['distance_task'] if c['distance_task'] is not None else '—'} | {c['here']:,} | {'같음' if c['same'] else '다름'} |")
    (DOCS / "tables/일2_영역나눔.md").write_text("\n".join(L) + "\n")


def write_density(data):
    L = ["# 일 1 참값 밀도 — 기울기 구간별 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 밀도 = 패치에 대응한 참값 행(솎기 전) ÷ 패치 넓이(점/m²), 기대 간격 = 1/√밀도. "
         "기울기 = 사전 정보 면 법선의 연직에서의 각. 평가 범위 안, 참값 행이 있는 패치.", "",
         "| 경우 | 기울기 (°) | 패치 | 밀도 10 % · 50 % · 90 % (점/m²) | 기대 간격 50 % · 90 % (cm) | 간격 ≤ τ 패치 (%) | 간격 ≤ τ/2 패치 (%) |", "|---|---|---:|---|---|---:|---:|"]
    for u, d in data.items():
        if u.startswith("합"):
            continue
        for b, x in d["density_by_slope"].items():
            if not x.get("patches"):
                L.append(f"| {case_ko(*u.split('/'))} | {b} | 0 | — | — | — | — |")
                continue
            L.append(f"| {case_ko(*u.split('/'))} | {b} | {x['patches']:,} | {x['density_p10']:.0f} · {x['density_p50']:.0f} · {x['density_p90']:.0f} | "
                     f"{x['spacing_p50_cm']:.1f} · {x['spacing_p90_cm']:.1f} | {100 * x['share_spacing_le_tau']:.1f} | {100 * x['share_spacing_le_half_tau']:.1f} |")
    L += ["", "| 경우 | 패치 넓이 10 % · 50 % · 90 % · 최대 (m²) | 이웃 패치 중심 거리 50 % · 90 % (m) | 참값 행 없는 평가 범위 패치 |", "|---|---|---|---:|"]
    for u, d in data.items():
        if u.startswith("합"):
            continue
        p = d["patch_size"]
        L.append(f"| {case_ko(*u.split('/'))} | {p['area_p10']:.4f} · {p['area_p50']:.4f} · {p['area_p90']:.4f} · {p['area_max']:.4f} | {p['nn_centre_m_p50']:.3f} · {p['nn_centre_m_p90']:.3f} | {d['patches_without_rows_in_range']:,} |")
    (DOCS / "tables/일1_참값밀도.md").write_text("\n".join(L) + "\n")
    jdump(DOCS / "tables/일1_참값밀도.json", dict(task="PHD-MAIN-AXES71-v2", work="일 1 참값 밀도", made=now(),
                                              data={u: dict(density_by_slope=d["density_by_slope"], patch_size=d["patch_size"]) for u, d in data.items() if not u.startswith("합")},
                                              scientific_verdict=None))


if __name__ == "__main__":
    main()
