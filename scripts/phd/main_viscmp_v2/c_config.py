"""PHD-MAIN-VISCMP-v2: write configs/phd/main_viscmp_v2/viscmp_v2.json (panels, titles, names, light, fade, values, places from
vp_places.py) and the lock (time, sha256) in PF/config_lock.json, before the first figure. Host python (json only).
  python3 -I c_config.py   scientific_verdict: null"""
import hashlib
import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
VC = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_viscmp_v2/PHD-MAIN-VISCMP-v2"
OUT = REPO / "configs/phd/main_viscmp_v2/viscmp_v2.json"
LOOK = {
    "task_id": "PHD-MAIN-VISCMP-v2", "request": "docs/experiments/phd/main_viscmp_v2/본실험_시각비교그림_발주문_v2.md", "scientific_verdict": None,
    "figures": {
        "V2": {"title": "기존 방법은 모두 보지 못한 벽을 비웠고, 본 방법만 사전 정보로 벽을 세웠다", "site": "B173nb_b10", "prior": "LoD2",
               "panels": ["사진", "학습 전 사전 정보", "2DGS", "GeoGS", "결합", "본 방법"], "mesh": "가상 시점 메시(빈칸 채우기 virtual 구성 요소가 벽 값을 센 메시)",
               "value": "벽이 선 몫(0.25 m, 빈칸 채우기 virtual 구성 요소의 wall.share, '맞음으로 미룸' 패치)", "foot": "이 벽에는 참값이 없어, 세운 벽이 참 벽 자리인지는 알 수 없다"},
        "V1": {"title": "사전 정보를 믿는 GeoGS와 결합은 LoD2의 단순한 지붕을 남겼고, 본 방법은 지금 지붕을 따랐다", "site": "R1rep_b10", "prior": "LoD2",
               "panels": ["사진", "참값", "학습 전 사전 정보", "GeoGS", "결합", "2DGS", "본 방법"], "value": "이 자리 참값 점의 거리 중앙값(cm, 새 거리 지표 s_d)"},
        "V3": {"title": "사전 정보가 영상보다 정확한 이 지붕에서 본 방법은 2DGS와 함께 참값 위에 떴고, 결합은 사전 정보를 따라 참값에 붙었다", "site": "B173nb_b10", "prior": "ALS",
               "lines": ["참값", "학습 전 사전 정보", "2DGS", "GeoGS", "결합", "본 방법"], "value": "이 지붕 참값 점의 '결과 − 참값' 중앙값(cm, 새 거리 지표 s_d x 부호)과 점의 수"},
        "V5": {"title": "영상이 틀린 이 덩어리에서 본 방법은 2DGS와 함께 참값 위에 떴고, 결합은 사전 정보를 따라 참값에 붙었다", "site": "B0_b10", "prior": "ALS",
               "lines": ["참값", "학습 전 사전 정보", "2DGS", "GeoGS", "결합", "본 방법"], "value": "이 덩어리 참값 행의 '결과 − 참값' 중앙값(cm, r_d x 부호)과 행의 수"},
        "V4": {"title": "본 방법은 결측 자리에서 벽을 안으로 무너뜨렸고, GeoGS와 결합, 결측 지키기는 곧은 벽을 지켰다", "site": "R1rep_b10", "prior": "LoD2",
               "panels": [["사진", "참값", "학습 전 사전 정보", "2DGS"], ["GeoGS", "결합", "본 방법", "결측 지키기"]], "value": "이 면의 결측 재현율(0.2 m, r 행 c4)"}},
    "render": {"light": "시점 쪽 빛 하나: 밝기 = 0.12 + 0.78 |면 법선 · 시선|, 회색 한 색, 맞히지 못한 곳 흰색", "gt": "참값 점 = 짙은 회색(0.25) 점, 점끼리 z 버퍼",
               "fade": "자리 밖 = 흰 바탕 위 불투명 30 %", "scale": "학습 카메라 = 1400 x 1013 모델의 초점 거리 x 4로 자른 상자를 렌더",
               "section_lines": {"참값": "#000000 점", "학습 전 사전 정보": "#7f7f7f", "2DGS": "#9467bd", "GeoGS": "#8c564b", "결합": "#17becf", "본 방법": "#ff7f0e"},
               "section_ylim": "참값 중앙값 ± 0.3 m"},
    "names": "request 2 (vc_common.res_name)",
}


def main():
    places = json.loads((VC / "prep/places.json").read_text())
    OUT.write_text(json.dumps(dict(LOOK, places=places), indent=1, ensure_ascii=False))
    lock = dict(config=str(OUT.relative_to(REPO)), sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(), saved_at=time.strftime("%Y-%m-%d %H:%M:%S KST"),
                places_sha256=hashlib.sha256((VC / "prep/places.json").read_bytes()).hexdigest(), note="첫 그림 전 잠금. 렌더를 보고 자리를 바꾸지 않는다", scientific_verdict=None)
    (VC / "config_lock.json").write_text(json.dumps(lock, indent=1, ensure_ascii=False))
    print(lock)


if __name__ == "__main__":
    main()
