"""PHD-MAIN-VISCMP-v3: write configs/phd/main_viscmp_v3/viscmp_v3.json (request 2.10-2.11: panels, rows, titles, colour ranges, point size,
fonts, cameras, crops, places from vp3_places.py) and the lock (time, sha256) in PF/config_lock.json, before the first figure.
  python3 -I c3_config.py   scientific_verdict: null"""
import hashlib
import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
VC = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_viscmp_v3/PHD-MAIN-VISCMP-v3"
OUT = REPO / "configs/phd/main_viscmp_v3/viscmp_v3.json"
METH = ["2DGS", "GeoGS", "결합", "CDGS", "본 방법"]
LOOK = {
    "task_id": "PHD-MAIN-VISCMP-v3", "request": "docs/experiments/phd/main_viscmp_v3/본실험_시각비교그림_발주문_v3.md", "scientific_verdict": None,
    "figures": {
        "V2": {"title": "기존 방법은 모두 보지 못한 벽을 비웠고, 본 방법만 사전 정보로 벽을 세웠다", "site": "B173nb_b10", "prior": "LoD2",
               "inputs": ["학습 전 사전 정보"], "methods": METH, "rows": ["결과 면"], "mesh": "virtual", "range_m": None,
               "foot": "이 벽은 학습 영상에 보이지 않았고 참값도 없어, 세운 벽이 참 벽 자리인지는 알 수 없다", "file": "V2_unseen_B173nb_LoD2"},
        "V1": {"title": "LoD2가 틀린 이 지붕에서 결합은 LoD2의 매끈한 면을 남겼고, 본 방법은 지금 지붕을 따랐다", "site": "R1rep_b10", "prior": "LoD2",
               "inputs": ["학습 전 사전 정보", "영상 깊이"], "methods": METH, "rows": ["결과 면", "확대", "참값과의 거리"], "range_m": 1.0, "file": "V1_correction_R1_LoD2"},
        "V3": {"title": "사전 정보가 더 정확한 이 지붕에서 결합은 참값에 붙었고, 본 방법은 영상 깊이를 따라 7 cm 위에 떴다", "site": "B173nb_b10", "prior": "ALS",
               "inputs": ["학습 전 사전 정보", "영상 깊이"], "methods": METH, "rows": ["결과 면", "참값과의 거리"], "range_m": 0.2, "file": "V3_refine_B173nb_ALS"},
        "V5": {"title": None, "title_rule": "request 3: chosen after drawing from the panel numbers (closest baseline, seed spread 2.8 x |s0 - s1| / sqrt 2, the proposed method's signed median)",
               "inputs": ["학습 전 사전 정보", "영상 깊이"], "methods": METH, "rows": ["결과 면", "참값과의 거리"], "range_m": 0.2, "file": "V5_keep"},
        "V4": {"title": "결측 자리에서 본 방법은 벽 바깥으로 부풀었고, GeoGS와 결측 지키기는 곧은 벽을 지켰다", "site": "R1rep_b10", "prior": "LoD2",
               "inputs": ["학습 전 사전 정보"], "methods": METH + ["결측 지키기"], "rows": ["결과 면", "참값과의 거리"], "range_m": 1.0,
               "foot": "점선 안은 영상 깊이가 없는 곳(결측)", "file": "V4_missing_R1_LoD2"}},
    "draw": {"dpi": 300, "font_size": 9, "title_size": 12, "panel_width_in": 2.3, "point_radius_px": 1, "cmap": "bwr", "no_surface_grey": "#bdbdbd",
             "gt_plain_grey": 0.25, "fade_outside_place": 0.3, "v2_background": "#dfe6ee", "mesh_light": "headlight: 0.12 + 0.78 |n . d|, one grey",
             "no_surface_rule": "rays from the GT point along +- its oriented normal meet no triangle within 2 x range (points without a normal: |d_g| > 2 x range)",
             "cbar_top": "+ 바깥·위", "cbar_bottom": "− 안·아래", "cbar_note": "회색: 가까이에 면 없음", "cdgs_note": "CDGS는 시점별 크기 맞추기를 생략한 변형이다",
             "depth_mesh": "the figure camera's 1024 x 741 training MVS depth map (S0/fork_inputs/s61/<site>/maps/mvs; COLMAP geometric depth: no depth where the confidence map is 0) as a pixel-grid mesh, no triangle over a jump > max(0.3 m, 1 % of depth)"},
    "values": {"panel": "median |d_g| of the place's region rows (the 7.1 table's quantity; stored r_d x r_sign, or computed for new meshes)",
               "colours": "scene GT points (SiteGT.Gb) of the crop: stored s_d x sign (s_sign, else s_sign_near)", "json": "signed median, rows, scene-point median, grey share, seed 1, v2 values"},
}


def main():
    places = json.loads((VC / "prep/places.json").read_text())
    OUT.write_text(json.dumps(dict(LOOK, places=places), indent=1, ensure_ascii=False))
    lock = dict(config=str(OUT.relative_to(REPO)), sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(), saved_at=time.strftime("%Y-%m-%d %H:%M:%S KST"),
                places_sha256=hashlib.sha256((VC / "prep/places.json").read_bytes()).hexdigest(),
                v5_candidates_sha256=hashlib.sha256((VC / "prep/v5_candidates.json").read_bytes()).hexdigest(),
                note="첫 그림 전 잠금. V5 자리는 다른 결과 파일을 열기 전에 적음(v5_candidates.json made 02:28:04)", scientific_verdict=None)
    (VC / "config_lock.json").write_text(json.dumps(lock, indent=1, ensure_ascii=False))
    print(lock)


if __name__ == "__main__":
    main()
