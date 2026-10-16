"""PHD-CH6-FACTS65-v2 task 9 [이 발주에서 냄]: where the LoD2 prior of B0 is wrong. Read from the stage-1 region file v3 of the
B0 box (S1/regions_v3/regions_ext_v3_B0_b10_LoD2.npz; per patch: region code code_ext_v3, kind 1 roof-like / 2 wall-like, area,
gt_med = median of GT - prior (roof: vertical; wall: along the outward normal), the label tau, gt_points = GT points of the
label source, in_eval) with the face table of the box (DR/s02_box/B0_b10/lod2_surfaces.json) and the B0 labels
(S1/v3/box_gt/B0_b10: labels_LoD2.npz = gt_clean, labels_uls_LoD2.npz = ULS supplement; the ULS label is used only where
gt_clean has none). Sign: gt_med < 0 = the prior lies outside the current surface (above a roof, in front of a wall), as the
prep measure's case 5 (scripts/phd/main_prep_measure_v1/step05_cases.py line 232).
  1. codes 11, 12, 13, 14 in the evaluation range: patches, area, GT points, roof and wall apart; the five faces with the
     largest area of these codes, with the median offset, the side and the share of area outside;
  2. the front wall (face 22, DEBY_LOD2_4959323_2ee5087f..., 'B0의 벽(정면, 면 22)' of the prep measure report v1.1 2.4):
     gt_med over its labelled patches in the evaluation range (median, quartiles), shares beyond the wall tolerance, code mix;
  4. the label source of the front-wall patches (gt_clean or ULS) by patches and area.
No judgment, no training. (jointbuildgs:dev, CPU)
  python t9_b0_wrong.py
Writes /out/t9/b0_wrong.json and b0_wrong.md. scientific_verdict: null."""
import json
from pathlib import Path

import numpy as np

S1 = Path("/s1"); DR = Path("/dr"); O = Path("/out/t9"); O.mkdir(parents=True, exist_ok=True)
SITE, FRONT = "B0_b10", 22
WRONG = (11, 12, 13, 14)
KIND = {1: "지붕", 2: "벽"}


def q(x, p):
    return None if len(x) == 0 else round(float(np.percentile(x, p)), 4)


def main():
    R = np.load(S1 / f"regions_v3/regions_ext_v3_{SITE}_LoD2.npz")
    names = {int(v): str(n) for v, n in zip(R["code_ext_values"], R["code_ext_names"])}
    code, kind, area, med, tau = R["code_ext_v3"].astype(int), R["kind"].astype(int), R["area"], R["gt_med"].astype(np.float64), R["tau"]
    ev, ext, gtp = R["in_eval"].astype(bool), R["surf_ext"].astype(int), R["gt_points"].astype(np.int64)
    tab = {int(s["ext"]): s for s in json.loads((DR / "s02_box" / SITE / "lod2_surfaces.json").read_text())["surfaces"]}
    G = S1 / "v3/box_gt" / SITE
    lab_g = np.load(G / "labels_LoD2.npz")["label"]; lab_u = np.load(G / "labels_uls_LoD2.npz")["label"]
    src = np.where(lab_g >= 0, "gt_clean", np.where(lab_u >= 0, "uls", "none"))
    assert len(lab_g) == len(code) == len(lab_u)
    out = dict(site=SITE, prior="LoD2", code_names=names, evaluation_range=dict(patches=int(ev.sum()), area_m2=round(float(area[ev].sum()), 1)))
    # 1. codes 11-14 by kind
    by = []
    for c in WRONG:
        for k in (1, 2):
            m = ev & (code == c) & (kind == k)
            by.append(dict(code=c, name=names.get(c, ""), kind=KIND[k], patches=int(m.sum()), area_m2=round(float(area[m].sum()), 1),
                           gt_points=int(gtp[m].sum()), area_outside_m2=round(float(area[m & (med < 0)].sum()), 1)))
    out["wrong_by_code_kind"] = by
    allc = {}
    for c in sorted(set(code[ev].tolist())):
        m = ev & (code == c)
        allc[str(c)] = dict(name=names.get(c, ""), roof_m2=round(float(area[m & (kind == 1)].sum()), 1), wall_m2=round(float(area[m & (kind == 2)].sum()), 1))
    out["all_codes_in_evaluation_range"] = allc
    # 1. top five faces of codes 11-14
    mw = ev & np.isin(code, WRONG)
    faces = []
    for e in np.unique(ext[mw]):
        m = mw & (ext == e); s = tab.get(int(e), {})
        mf = m & np.isfinite(med)
        faces.append(dict(face=int(e), gml=s.get("gml", ""), building=s.get("building", ""), type=s.get("type", ""),
                          wrong_area_m2=round(float(area[m].sum()), 1), face_area_in_eval_m2=round(float(area[ev & (ext == e)].sum()), 1),
                          codes={str(c): round(float(area[m & (code == c)].sum()), 1) for c in WRONG if (m & (code == c)).any()},
                          median_offset_m=None if not mf.any() else round(float(np.median(med[mf])), 3),
                          q1_m=q(med[mf], 25), q3_m=q(med[mf], 75),
                          outside_area_share=None if not mf.any() else round(float(area[mf & (med < 0)].sum() / area[mf].sum()), 3),
                          side="바깥" if mf.any() and np.median(med[mf]) < 0 else ("안쪽" if mf.any() else "참값 없음"),
                          gt_points=int(gtp[m].sum())))
    faces.sort(key=lambda d: -d["wrong_area_m2"])
    out["top_faces"] = faces[:5]; out["faces_with_wrong_codes"] = len(faces)
    # 2. front wall
    fw = ev & (ext == FRONT); fl = fw & np.isfinite(med) & (lab_g >= 0) | fw & np.isfinite(med) & (lab_u >= 0)
    x = med[fl]; t = float(np.median(tau[fw])) if fw.any() else None
    out["front_wall"] = dict(face=FRONT, gml=tab[FRONT]["gml"], building=tab[FRONT]["building"], type=tab[FRONT]["type"],
                             face_area_total_m2=round(float(tab[FRONT].get("area_m2", 0)), 1),
                             patches_in_eval=int(fw.sum()), area_in_eval_m2=round(float(area[fw].sum()), 1), labelled_patches=int(fl.sum()),
                             labelled_area_m2=round(float(area[fl].sum()), 1),
                             median_m=q(x, 50), q1_m=q(x, 25), q3_m=q(x, 75), p10_m=q(x, 10), p90_m=q(x, 90), wall_tau_m=t,
                             share_beyond_tau=None if not len(x) else round(float(np.mean(np.abs(x) > tau[fl])), 4),
                             share_outside_beyond_tau=None if not len(x) else round(float(np.mean(x < -tau[fl])), 4),
                             share_inside_beyond_tau=None if not len(x) else round(float(np.mean(x > tau[fl])), 4),
                             share_outside=None if not len(x) else round(float(np.mean(x < 0)), 4),
                             code_area_m2={str(c): round(float(area[fw & (code == c)].sum()), 1) for c in sorted(set(code[fw].tolist()))})
    # 4. label source on the front wall and on the wrong-code patches
    def srcs(m):
        return {s: dict(patches=int((m & (src == s)).sum()), area_m2=round(float(area[m & (src == s)].sum()), 1)) for s in ("gt_clean", "uls", "none")}
    out["label_source_front_wall"] = srcs(fw); out["label_source_wrong_codes"] = srcs(mw)
    out["rule"] = __doc__.split("\n\n")[0]; out["scientific_verdict"] = None
    (O / "b0_wrong.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    L = ["# B0 LoD2에서 사전 정보가 틀린 곳 (평가 범위, 1단계 영역 파일 v3)", "",
         f"평가 범위: 패치 {out['evaluation_range']['patches']:,}개, {out['evaluation_range']['area_m2']:,} m²", "",
         "| 코드 | 이름 | 면 | 패치 | 넓이 | 그 가운데 사전 정보가 바깥 | 참값 점 |", "|---|---|---|---|---|---|---|"]
    for d in by:
        L.append(f"| {d['code']} | {d['name']} | {d['kind']} | {d['patches']:,} | {d['area_m2']:,} m² | {d['area_outside_m2']:,} m² | {d['gt_points']:,} |")
    L += ["", "넓이가 큰 면 다섯 (코드 11~14의 합)", "", "| 면 | 건물 | 종류 | 틀린 곳 넓이 | 평가 범위 안 면 넓이 | 코드별 넓이 | 어긋남 중앙값 (사분위) | 방향 | 바깥 넓이 몫 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f in out["top_faces"]:
        L.append(f"| {f['face']} | {f['building'].replace('DEBY_LOD2_', '')} | {f['type']} | {f['wrong_area_m2']:,} m² | {f['face_area_in_eval_m2']:,} m² | "
                 f"{', '.join(f'{k}: {v}' for k, v in f['codes'].items())} | {f['median_offset_m']} m ({f['q1_m']}~{f['q3_m']}) | {f['side']} | {f['outside_area_share']} |")
    fwd = out["front_wall"]
    L += ["", f"정면 벽(면 {FRONT}, {fwd['gml']}): 평가 범위 안 패치 {fwd['patches_in_eval']:,}개({fwd['area_in_eval_m2']:,} m²), 라벨이 있는 패치 {fwd['labelled_patches']:,}개",
          f"- 참값 − LoD2(바깥 법선 방향) 중앙값 {fwd['median_m']} m, 사분위 {fwd['q1_m']}~{fwd['q3_m']} m, 10~90 % {fwd['p10_m']}~{fwd['p90_m']} m",
          f"- 벽면 허용 오차 {fwd['wall_tau_m']} m를 넘는 몫 {fwd['share_beyond_tau']} (바깥 {fwd['share_outside_beyond_tau']}, 안쪽 {fwd['share_inside_beyond_tau']}); 사전 정보가 바깥인 몫 {fwd['share_outside']}",
          f"- 코드별 넓이(m²): {fwd['code_area_m2']}",
          f"- 라벨 출처(정면 벽): {out['label_source_front_wall']}", f"- 라벨 출처(코드 11~14): {out['label_source_wrong_codes']}"]
    (O / "b0_wrong.md").write_text("\n".join(L) + "\n")
    print("\n".join(L)); print("code names:", names)


if __name__ == "__main__":
    main()
