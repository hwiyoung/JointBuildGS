"""PHD-MAIN-PHOTOFIG-v1: write configs/phd/main_photofig_v1/photofig_v1.json = the hand-written ways of looking (colours, colour ranges,
results per figure, numbers, candidates and expectations of the request 5) + the places, photos and sections chosen by p0_places.py
from geometry only; then the lock (time, sha256) in PF/config_lock.json. Host python (json only). Run once before the first figure.
  python3 -I c0_config.py      scientific_verdict: null"""
import hashlib
import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PF = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"
OUT = REPO / "configs/phd/main_photofig_v1/photofig_v1.json"

RESULTS = {
    "B173nb_b10/ALS": {
        "지금 방법 씨앗 0": "S0/stage0/b1_ALS", "지금 방법 씨앗 1": "S0/stage0/b2_ALS", "결측 지키기": "FT/runs/B173nb_b10/fixB_ALS_s0",
        "허용 구간 없애기": "S2/runs/B173nb_b10/abl_band_ALS_s0", "학습 전 사전 정보": "MT/gpu/samepath_ALS/mesh.ply",
        "dist": {"지금 방법 씨앗 0": "SD/dist/B173nb_b10_ALS__prop_ALS_s0.npz", "지금 방법 씨앗 1": "SD/dist/B173nb_b10_ALS__prop_ALS_s1.npz",
                 "결측 지키기": "FT/dist/B173nb_b10_ALS__fixB_ALS_s0.npz", "허용 구간 없애기": "FT/dist/B173nb_b10_ALS__abl_band_ALS_s0.npz",
                 "학습 전 사전 정보": "SD/dist/B173nb_b10_ALS__samepath_ALS.npz"}},
    "R1rep_b10/LoD2": {
        "지금 방법 씨앗 0": "S1/stage1/R1rep_b10/prop_LoD2_s0", "지금 방법 씨앗 1": "S1/stage1/R1rep_b10/prop_LoD2_s1",
        "결측 지키기": "FT/runs/R1rep_b10/fixB_LoD2_s0", "판정만 끈 방법": "S3/runs/R1rep_b10/nojudge_LoD2_s0"},
    "R1rep_b10/ALS": {
        "지금 방법 씨앗 0": "S1/stage1/R1rep_b10/prop_ALS_s0", "지금 방법 씨앗 1": "S1/stage1/R1rep_b10/prop_ALS_s1",
        "결측 지키기": "FT/runs/R1rep_b10/fixB_ALS_s0", "결측 지키기 다시 돌림": "FT/runs/R1rep_b10/fixAB_ALS_s0"},
    "B0_b10/ALS": {
        "지금 방법 씨앗 0": "S1/stage1/B0_b10/prop_ALS_s0", "지금 방법 씨앗 1": "S1/stage1/B0_b10/prop_ALS_s1",
        "지금 방법 다시 돌림": "FT/runs/B0_b10/fixA_ALS_s0", "폭 좁히기(기록 셈)": "FT/runs/B0_b10/fixAT_ALS_s0"},
    "note": "mesh = <run>/post/mesh_tsdf.ply (the metrics' mesh); render depth = <run>/model/dump/iteration_30000/<view>_depth.npy; Gaussians = .../gaussians.npz; "
            "distances = SD/dist (dist71 d2_dist.py) and FT/dist (fixtest dm_ft.py), r_* per region row (signed: + outside)",
}

CANDIDATES = {
    "fig1": [
        {"candidate": "반사: 유리에 비친 둘레가 유리 뒤의 면처럼 잡힘", "image_depth": "유리면보다 카메라에서 먼 쪽에 잡힌다. 그 자리가 둘레 건물을 유리면에 비친 자리와 맞는다", "gt": "유리면 높이", "photo": "둘레 건물이나 하늘이 비쳐 보인다"},
        {"candidate": "투과: 유리 너머 실내가 잡힘", "image_depth": "유리면보다 아래, 실내 구조의 높이에 잡힌다", "gt": "—", "photo": "유리 너머 실내가 보인다"},
        {"candidate": "틀과 무늬: 유리 틀과 먼지 무늬가 정합을 이끎", "image_depth": "유리면 가까이, 틀을 따라 잡힌다. 그렇다면 영상 깊이가 맞고 다른 자료가 틀렸을 수 있다", "gt": "—", "photo": "틀이 촘촘하다"},
        {"candidate": "참값 쪽: 드론 LiDAR가 유리를 지나 안쪽에서 반사됨", "image_depth": "—", "gt": "유리면보다 아래에 점이 많거나 여러 층이다. 항공 LiDAR도 같은 모양일 수 있다", "photo": "—"}],
    "fig2": [
        {"candidate": "번짐: 유리 쪽의 틀린 면이 결측 패치 위로 이어짐", "expect": "결측 패치의 결과 면이 유리 쪽 결과 면과 끊김 없이 이어진다. 결측 패치에 앉은 가우시안의 많은 몫이 영상 깊이 출신이거나 밀도 제어로 생겼다. 새로 켠 화소가 있는데도 결과 면이 거의 바뀌지 않았다"},
        {"candidate": "결측 패치 자신의 당김이 약함", "expect": "결측 패치 위에 사전 정보 출신 가우시안이 거의 남지 않았다. 새로 켠 화소가 결측 패치의 일부만 덮는다"},
        {"candidate": "참값 쪽", "expect": "그림 1의 '참값 쪽'이 맞고, 결측 패치의 참값도 유리면이나 틀보다 아래다. 결과 면은 사진에서 보이는 겉면의 높이와 맞는다"}],
    "fig4": [
        {"candidate": "허용 구간이 넓어 당기지 않음", "expect": "결과와 사전 정보의 차가 대부분 허용 구간 안이고, 결과가 영상 깊이와 거의 같다. 허용 구간 없애기의 결과는 사전 정보 쪽에 있다"},
        {"candidate": "영상 깊이가 지역 전체에서 고르게 치우침", "expect": "(영상 깊이 − 참값)이 지붕과 맨땅, 여러 건물에서 비슷하다. 이 경우 폭과 함께 높이 맞춤도 원인 후보다"},
        {"candidate": "이 지붕만의 영상 깊이 문제", "expect": "(영상 깊이 − 참값)이 이 지붕에서만 크다. 지붕 겉의 재질이나 무늬가 사진에서 보인다"}],
    "reading": {
        "grades": "후보마다 맞는 근거와 맞지 않는 근거를 적고 '확인', '가능·근거 불완전', '확인 불가'를 단다. 둘 이상이 함께 맞을 수 있다",
        "fig1_operational": "카메라에서 먼 쪽 = 영상 깊이의 점이 참값(맨 위 겹)보다 그 시선을 따라 더 멀다(높이로는 아래). 유리면 높이 = 그 자리 LoD2 지붕면(유리)의 높이. 여러 층 = 참값 높이 분포에 0.5 m 넘게 떨어진 무리가 둘 이상(점 5 % 이상). 이어짐 = 결측 패치와 이웃 유리 패치의 경계에서 두 결과 면의 높이 차가 0.1 m 안",
        "fig2_operational": "가우시안의 출신 = 30,000회 덤프 gaussians.npz 'origin'(0 영상, 1 사전 정보). 덤프에 밀도 제어 표시가 없어 '같은 처음 점에서 둘 이상 남은 가우시안'의 몫을 밀도 제어의 몫으로 함께 적는다",
        "fig4_operational": "'대부분' = 70 % 넘게. '거의 같다' = 차의 중앙값이 2 cm 안. '비슷하다' = 지붕 면마다와 맨땅의 중앙값이 그 NMAD 안에 든다"},
}

LOOK = {
    "task_id": "PHD-MAIN-PHOTOFIG-v1",
    "request": "docs/experiments/phd/main_photofig_v1/본실험_실사진그림_발주문_v1.md",
    "scientific_verdict": None,
    "note": "결과를 보기 전에 정한 보는 법(발주 2.9). 자리와 사진은 scripts/phd/main_photofig_v1/p0_places.py가 영역 파일, 패치 저장소, 참값, 카메라 기하와 사전 정보 렌더 깊이(학습 입력)만으로 골랐다(PF/prep/places.json, 아래 'places'에 그대로 옮김). 결과 파일은 열지 않았다.",
    "colours": {"참값": "#000000", "사전 정보": "#7f7f7f", "영상 깊이": "#8c564b (통과 = 채운 점, 떨어짐 = 빈 점)", "지금 방법": "#ff7f0e (씨앗 1 = 옅은 주황 점선 #fdbf6f)",
                "결측 지키기": "#1f77b4", "폭 좁히기": "#2ca02c", "다시 돌림": "#c7c7c7 점선", "허용 구간": "사전 정보 둘레 옅은 회색 띠 #d9d9d9", "좁힌 폭": "옅은 초록 띠 #c7e9c0",
                "수동 비행": "옅은 검정 #595959", "판정만 끈 방법": "옅은 회색 #bdbdbd"},
    "colour_ranges": {"fig1_b_image_depth_minus_gt_m": [-1.0, 1.0], "fig2_patch": "결과 면이 참값 0.2 m 안인 패치 = 그 방법의 색, 밖 = 빈 테두리",
                      "fig4_minus_gt_m": [-0.15, 0.15], "fig4_map_m": [-0.15, 0.15], "fig5_minus_gt_m": [-0.25, 0.25], "fig6_counts": "0.25 m 칸의 점 수, 로그, 세 칸 같은 범위",
                      "fig3_patch": "사전 정보가 맞는 결측: 0.2 m 안이면 파랑 칠; 사전 정보가 틀린 결측: 빨간 테두리, 결과가 사전 정보 면 0.2 m 안이면 빨강 칠"},
    "photo_rule": "p0_places.py 머리글(학습 영상, 자리의 패치 중심이 모두 영상 안이고 80 % 넘게 사전 정보 렌더 깊이로 보임; 지붕 = 연직 영상(광축 20° 안) 가운데 가장 크게 본 것; 벽 = 바깥 법선과 시선의 각이 가장 작은 것). 바탕 = S0/fork_inputs/s61/<지역>/images/<영상>.jpg(학습이 읽은 1024×741 영상, 원본 화소 그대로 자름). 그림 6 = 그 벽을 가장 정면에서 본 학습 영상을 벽면에 펴서 바탕으로 깖",
    "section_rule": "폭 0.5 m 띠. 지붕 = 자리의 긴 축(평면 PCA)을 따라 선 연직 단면, 벽 = 결측 패치 높이의 가운데에서 벽을 따라 자른 수평 단면, 길이 = 자리 + 양쪽 2 m. 그림 1은 유리를 가로지르게(사례 영역의 짧은 축). 결과 면 = 지표와 같은 TSDF 메시(post/mesh_tsdf.ply)를 띠 가운데 평면으로 자른 선",
    "on_photo_rule": "결과 = 그 영상의 30,000회 덤프 렌더 깊이. 참값과의 차 = 참값 점을 그 영상에 투영하고 참값끼리 깊이를 비교해(0.25 m 안의 맨 앞 겹) 보이는 점만 남겨, 새 거리 지표의 점마다 거리(참값→결과, 바깥 +)로 칠함. 영상 깊이 − 참값은 높이 차(같은 화소의 영상 깊이 3차원 점의 z − 그 점에서 0.25 m 안의 참값 맨 위 겹 z 중앙값)",
    "results": RESULTS,
    "candidates_and_expectations": CANDIDATES,
    "numbers": {
        "fig1": ["유리(사례 영역) 넓이, 맞는 자료를 판단할 수 없는 패치 수(전제 위배), 결측 패치 수(자리와 2 m 둘레)",
                 "유리 위 영상 깊이가 관측 신뢰도 검사를 통과한 몫(패치 저장소 a1_sum ÷ pix_sum, 학습 영상 모두)",
                 "동의 시점 수: 저장되어 있지 않음(COLMAP write_consistency_graph 0). 같은 규칙의 근사로 다시 구함: 그림 1 연직 영상의 통과 화소마다, 다른 학습 영상의 영상 깊이로 앞뒤 재투영 오차 1 px 안인 시점 수(COLMAP filter_min_num_consistent 2, filter_geom_consistency_max_cost 1 px). 근사라고 밝힘",
                 "(영상 깊이 − 참값) 중앙값과 NMAD", "유리 위 참값의 1 m²당 점 수, 여러 반사의 몫, 높이 분포(층)", "같은 자리 수동 비행 − 연직 비행 높이 차(비교 좌표, 높이 맞춤 없음)",
                 "(항공 LiDAR − 참값) 중앙값 = 영역 파일 gt_med(참값 − 사전 정보)의 부호를 바꾼 중앙값"],
        "fig2": "패치 표(발주 5.2)", "fig4": "발주 5.3 숫자", "table_A": "발주 6절", "table_B": "발주 6절",
    },
    "waits": "scripts/phd/main_photofig_v1/wait_mem.sh (가용 30 GB 아래이거나 jbgs-ftg-* 후처리가 돌면 기다림)",
}


def main():
    places = json.loads((PF / "prep/places.json").read_text())
    cfg = dict(LOOK, places=places)
    OUT.write_text(json.dumps(cfg, indent=1, ensure_ascii=False))
    b = OUT.read_bytes()
    lock = dict(config=str(OUT.relative_to(REPO)), sha256=hashlib.sha256(b).hexdigest(), saved_at=time.strftime("%Y-%m-%d %H:%M:%S KST"),
                places_sha256=hashlib.sha256((PF / "prep/places.json").read_bytes()).hexdigest(),
                note="첫 그림 전 잠금(발주 2.9). 결과 파일을 열기 전에 저장", scientific_verdict=None)
    (PF / "config_lock.json").write_text(json.dumps(lock, indent=1, ensure_ascii=False))
    print(lock)


if __name__ == "__main__":
    main()
