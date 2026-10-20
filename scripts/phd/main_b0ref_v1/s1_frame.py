"""PHD-MAIN-B0REF-v1 일 1 5번: does the GeoGS cloud sit on the raw ULS in the comparison frame? (jointbuildgs:dev, CPU)

  python s1_frame.py   -> /b0/prep/frame_check.json, /docs/tables/t0_frame_check.md|json

The target building has no level roof face in the LoD2 (config comparison_frame.flat_roof), so the check uses the GeoGS points in the
roof space of all six roof faces (evaluation range). Per point: the nearest raw ULS point (all returns), distance and vector. If the
median distance is above 5 cm, a translation is fitted (median of the nearest-point vectors, three rounds) and used from then on.
The same numbers are also given in the study's frame (both clouds with their recorded height alignments: GeoGS z - 0.0746 + 0.0095,
ULS z - 0.0533 + 0.0095). [이 요청에서 냄] scientific_verdict: null."""
import numpy as np
from scipy.spatial import cKDTree

from b0_common import B0, CFG, DOCS, in_rect, jdump, load_crop, lod2_faces, log, now, roof_space


def nn_stats(d, v=None):
    out = dict(n=int(len(d)), median_m=float(np.median(d)), p05_m=float(np.percentile(d, 5)), p95_m=float(np.percentile(d, 95)),
               share_le_1mm=float(np.mean(d <= 0.001)), share_le_1cm=float(np.mean(d <= 0.01)))
    if v is not None:
        out["median_vector_m"] = np.median(v, 0).tolist()
    return out


def main():
    G = load_crop("geogs")["xyz"]; U = load_crop("uls_nadir")["xyz"]
    ev = in_rect(G[:, :2])
    roof = np.zeros(len(G), bool)
    for f in lod2_faces():
        if f["kind"] == 1:
            roof |= roof_space(f, G)[0]
    Gr = G[roof & ev]
    log("roof points", len(Gr))
    tree = cKDTree(U)
    d, i = tree.query(Gr, workers=8)
    v = U[i] - Gr
    rec = dict(roof_points=int(len(Gr)), raw_frame=nn_stats(d, v))
    fz = CFG["geogs_to_study_frame"]; uz = CFG["uls_to_study_frame"]
    dz_g = fz["z_gt_clean_m"] + fz["z_stage1_common_m"]; dz_u = uz["z_height_alignment_m"] + uz["z_stage1_common_m"]
    Gs = Gr + [0, 0, dz_g]
    Us = U + [0, 0, dz_u]
    d2, i2 = cKDTree(Us).query(Gs, workers=8)
    rec["study_frame"] = dict(nn_stats(d2, Us[i2] - Gs), geogs_dz_m=dz_g, uls_dz_m=dz_u, relative_dz_m=dz_g - dz_u)
    t = np.zeros(3); fit = []
    if rec["raw_frame"]["median_m"] > 0.05:
        for it in range(3):
            dd, ii = tree.query(Gr + t, workers=8)
            t = t + np.median(U[ii] - (Gr + t), 0)
            fit.append(dict(round=it + 1, translation_m=t.tolist(), median_before_m=float(np.median(dd))))
        dd, _ = tree.query(Gr + t, workers=8)
        rec["translation_fit"] = dict(rounds=fit, translation_m=t.tolist(), median_after_m=float(np.median(dd)))
    rec["used_translation_m"] = t.tolist()
    rec["rule"] = CFG["comparison_frame"]["check"]
    rec["made"] = now(); rec["scientific_verdict"] = None
    jdump(B0 / "prep/frame_check.json", rec)
    jdump(DOCS / "tables/t0_frame_check.json", rec)
    r, s = rec["raw_frame"], rec["study_frame"]
    L = ["# 표 0. 좌표 확인: 대상 건물 지붕의 GeoGS 점에서 원래 드론 LiDAR(모든 반사)의 가장 가까운 점까지 [이 요청에서 냄]", "",
         "| 좌표 | GeoGS 점 | 중앙값 (mm) | 5 분위 (mm) | 95 분위 (mm) | 1 mm 안 | 1 cm 안 | 가장 가까운 점 벡터의 중앙값 (mm, x·y·z) |",
         "|---|---:|---:|---:|---:|---:|---:|---|"]
    for name, q in (("비교 좌표(정리 전, 높이 맞춤 없음)", r), ("이 연구의 좌표(두 점군의 기록된 높이 맞춤)", s)):
        L.append(f"| {name} | {q['n']:,} | {q['median_m']*1e3:.1f} | {q['p05_m']*1e3:.1f} | {q['p95_m']*1e3:.1f} | {q['share_le_1mm']*100:.1f} % | "
                 f"{q['share_le_1cm']*100:.1f} % | {' · '.join(f'{x*1e3:+.1f}' for x in q['median_vector_m'])} |")
    L += ["", f"- 지붕 = 대상 건물 LoD2 지붕면 여섯의 지붕 공간(법선 방향 1.0 m 안, 평가 범위 안). LoD2에 수평 지붕면이 없어 평지붕 대신 썼다.",
          f"- 이 연구의 좌표에서 두 점군의 높이 맞춤 차 = {s['relative_dz_m']*100:+.2f} cm (GeoGS {s['geogs_dz_m']:+.4f} m, 드론 LiDAR {s['uls_dz_m']:+.4f} m).",
          f"- 옮김 맞춤: {'했음 ' + str(rec['translation_fit']) if fit else '하지 않음(중앙값이 5 cm 이하)'}"]
    (DOCS / "tables/t0_frame_check.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
