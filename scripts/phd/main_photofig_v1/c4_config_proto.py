"""PHD-MAIN-PHOTOFIG-v1 [사용자 요청, 그리는 법 견본]: write configs/phd/main_photofig_v1/photofig_v1_proto.json (the ways of looking of the
R1 wall-19 sample: view from p4_proto.py, crop, shading, the facade cell map, colours, bars) and the lock in PF/config_lock_proto.json.
Host python (json only). Run once before the sample is drawn.   python3 -I c4_config_proto.py   scientific_verdict: null"""
import hashlib
import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PF = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"
OUT = REPO / "configs/phd/main_photofig_v1/photofig_v1_proto.json"

LOOK = {
    "task_id": "PHD-MAIN-PHOTOFIG-v1",
    "asked": "사용자 10-20: R1 벽 19 견본 — 위 줄 같은 시점 음영(실사진, 지금 방법, 결측 지키기, 기록 셈), 아래 줄 벽 정면 칸 지도(결과 − 참값, 0.2 m 안 흰색), 맨 아래 재현율 막대, 지금 그림 3과 나란히",
    "scientific_verdict": None,
    "note": "그리는 법 견본. 값은 그림 3·8과 같은 결과, 같은 거리 파일에서 낸다. 시점은 p4_proto.py가 기하만으로 골랐다(PF/prep/places_proto.json).",
    "results": {"지금 방법 씨앗 0": "S1/stage1/R1rep_b10/prop_LoD2_s0", "결측 지키기": "FT/runs/R1rep_b10/fixB_LoD2_s0", "폭 좁히기(기록 셈)": "FT/runs/R1rep_b10/fixAT_LoD2_s0"},
    "bars": {"source": "docs/.../tables/fig3_r1.json, fig8_r1.json의 r02_face (이 면 결측 재현율 0.2 m)", "rows": ["지금 방법 씨앗 0", "지금 방법 씨앗 1", "결측 지키기", "폭 좁히기(기록 셈)"]},
    "top_row": {"photo": "colmap_dense/images/<영상>.JPG (학습 카메라의 1400 x 1013 왜곡 보정 영상), 자르기를 그대로 키움",
                "shading": "TSDF 메시(post/mesh_tsdf.ply, 지표와 같은 메시)를 같은 카메라 자세에서 화소 4배(초점 거리와 주점 4배)로 광선 투사(Open3D RaycastingScene, CPU). 밝기 = 0.25 + 0.75 x max(0, 면 법선 · 빛), 빛 = 카메라 좌표 (-0.35, -0.55, -0.76) 방향(왼쪽 위 앞). 광선이 맞히지 못한 곳 = 흰색. 맞힌 거리가 이웃 화소와 0.2 m 넘게 다르면 짙은 회색 선",
                "crop": "결측 패치 네 꼭짓점을 1400 영상에 투영한 상자 + 각 변 길이의 60 %"},
    "bottom_row": {"canvas": "벽 19 평면(LoD2) 정면 펼침: 가로 = 벽을 따라(바깥 법선의 왼쪽 수평 방향), 세로 = 높이. 칸 = 영역 파일의 0.25 m 패치(평가 범위)",
                   "value": "칸마다 참값 행의 '결과 − 참값' 중앙값(새 거리 지표의 거리 × 부호, 바깥 +). 행이 3개 미만인 칸 = 회색(참값 없음)",
                   "first_column": "참값 − LoD2 (영역 파일 gt_med) — 같은 색",
                   "bins_m": [-0.6, -0.4, -0.2, 0.2, 0.4, 0.6], "colours": ["#2166ac", "#67a9cf", "#d1e5f0", "#ffffff", "#fddbc7", "#ef8a62", "#b2182b"], "no_gt": "#d9d9d9",
                   "window": "결측 패치의 펼친 범위 + 사방 3 m"},
    "outline": "결측 영역(평가 범위의 사전 정보가 맞는 결측과 틀린 결측) = 검은 점선, 위·아래 줄 같음",
    "files": "figures/photo_proto_r1_wall19.png|pdf|json, figures/photo_proto_r1_wall19_vs_fig3.png, tables/proto_r1_wall19.json",
}


def main():
    places = json.loads((PF / "prep/places_proto.json").read_text())
    cfg = dict(LOOK, place=places)
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    lock = dict(config=str(OUT.relative_to(REPO)), sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(), saved_at=time.strftime("%Y-%m-%d %H:%M:%S KST"),
                places_sha256=hashlib.sha256((PF / "prep/places_proto.json").read_bytes()).hexdigest(), note="견본 그리기 전 잠금", scientific_verdict=None)
    (PF / "config_lock_proto.json").write_text(json.dumps(lock, indent=1, ensure_ascii=False))
    print(lock)


if __name__ == "__main__":
    main()
