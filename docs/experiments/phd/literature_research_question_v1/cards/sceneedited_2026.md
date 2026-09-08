# SceneEdited — Lin et al. (WACV 2026)

- 검토일: 2026-09-09. `scientific_verdict: null`.
- 서지: Chun-Jung Lin, Tat-Jun Chin, Sourav Garg, Feras Dayoub, *SceneEdited: A City-Scale Benchmark for 3D HD Map Updating via Image-Guided Change Detection*, WACV2026, 6330–6339. [CVF 출판 페이지](https://openaccess.thecvf.com/content/WACV2026/html/Lin_SceneEdited_A_City-Scale_Benchmark_for_3D_HD_Map_Updating_via_WACV_2026_paper.html), [accepted paper PDF](https://openaccess.thecvf.com/content/WACV2026/papers/Lin_SceneEdited_A_City-Scale_Benchmark_for_3D_HD_Map_Updating_via_WACV_2026_paper.pdf), [arXiv v1 2025-11-19 + 보충자료 HTML](https://arxiv.org/html/2511.15153v1).
- 주 근거: WACV accepted 10쪽 PDF 직접 읽기; 보충 D는 arXiv v1. 서로 다른 버전의 그림 번호를 자동으로 같다고 취급하지 않는다. PDF SHA256 `69ca3a6d072fe9270781b9b471fe980227a90bd3390c7316ba7fab5333b6f8ff`.
- 공식 구현: [ScenePoint-ETK](https://github.com/ChadLin9596/ScenePoint-ETK), 확인 commit `36a1df1d0ebf87c135659c4eba0a7861190d550c` (2026-03-02). 코드 전체 tree와 `evaluation/map_updating.py`, `scene_db/diff_scene.py`, `argoverse2/log_splits.json` 확인. **편집·평가 toolkit은 공개 확인**; Table3 predictor 전체 driver·checkpoint·runtime 재현까지 확인한 것은 아니다. 실행하지 않았다.
- 추가한 이유/비교 역할: 초기 목록 밖이지만 **기존 point cloud+현재 RGB→갱신 3D** 및 평가 공백에 직접 경쟁한다. native camera는 차량, prior는 합성 편집한 voxel map이므로 항공 ALS/LoD2 조건과 같은 benchmark는 아니다.

## 1. 문제와 입출력

**[원문 사실]** Argoverse의 실제 동기 LiDAR/RGB/calibration에서 정적20cm voxel map을 만들고 삽입·삭제 편집으로 오래된 map을 합성한다. 입력은 outdated map과 현재 RGB/pose, 목표는 current point map이다. baseline은 DUSt3R/MASt3R/VGGT의 사전학습 기하와 **GT change mask**를 사용한다. [§3–4/6, pp.6332–6337](https://openaccess.thecvf.com/content/WACV2026/papers/Lin_SceneEdited_A_City-Scale_Benchmark_for_3D_HD_Map_Updating_via_WACV_2026_paper.pdf#page=3).

**[우리 분석]** 실제 관측에 합성한 변경을 평가하므로 실측 시간차의 joint acquisition errors는 자동 포함되지 않는다. LiDAR는 GT 생성·dynamic 제거·change mask 가시성 정제에도 쓰인다. GT mask로 수행한 main baseline을 허용 RGB/old-map만 쓰는 autonomous method 성능으로 부르면 안 된다. raw LiDAR가 auxiliary로 배포되지만 실험별 사용범위를 명시해야 한다.

## 2. 기여의 위치

| 요소 | 판정 | 실제 역할 / 근거 |
|---|---|---|
| 입력·전처리 | 새 benchmark/toolkit + 기존 사용 | dynamic cuboid 제거·voxel map·합성 편집 provenance; §4.1–4.4 |
| 좌표·카메라·정합 | 기존 사용 | sensor calibration, unchanged GT-mask correspondence, scale 포함 Kabsch–Umeyama; §6.1 |
| 표현 | 기존 방법 사용 | 20cm voxelized point map, 추가/삭제 point sets |
| 관측모형·렌더링 | 기존 사용 | calibration projection, LiDAR depth로 occlusion 정제; §4.3 |
| 증거·감독·제약 | 새 benchmark 설계 | image/point change annotation, GT-mask oracle diagnostic; §3/6 |
| 초기화·최적화·모델 변경 | 기존 방법 사용 | pretrained image-to-3D, 후정합·부분 기하 추가, 보이는 obsolete 점 삭제 |
| 추출·후처리 | 새 toolkit 구성 + 기존 사용 | edit index 추적·point-set evaluation/serialization; §4.4/5 |

§3은 **명시적 change detector가 필수는 아니라고 직접 명시**한다. “판단 후 복원”을 문제 정의의 유일한 형태로 고정하지 않는 선례다. [§3](https://arxiv.org/html/2511.15153v1#S3).

## 3. 무엇을 고정하고 수정하는가

**[원문 사실]** predictor가 depth/pose/points를 내고 GT mask로 고른 unchanged correspondence에 scale·alignment를 맞춘다. 5장씩 생성한 변화영역 점을 누적한다. 삭제는 FOV 밖·가려진 점을 보존한다. [§6.1–6.2, Fig.5–7](https://openaccess.thecvf.com/content/WACV2026/papers/Lin_SceneEdited_A_City-Scale_Benchmark_for_3D_HD_Map_Updating_via_WACV_2026_paper.pdf#page=7).

```text
기하생성: RGB 5장 → pretrained depth/pose/points → scale/alignment → added points
                                              ↑
                             고정 old map + GT unchanged mask/calibration
삭제: old map + GT change mask + visibility → visible 삭제 / unobserved 유지
최종: 보존된 old map + 추가/삭제 적용 → point map
```

**[우리 분석]** baseline의 고정 지도와 GT mask는 reconstruction/registration 효과를 격리하기 위한 통제다. 이를 실제 판단 시스템의 가정으로 옮길 수 없다. 반복 batch 누적은 이루어지나 fused map이 detector/predictor weights·camera·mask를 다시 수정하는 joint loop는 확인되지 않는다. pretraining 모델 내부의 inference와 benchmark 외부 feedback은 구분한다.

fixed GT mask를 예측 mask로 바꾸면 실제 사용 조건에 가까워지지만 판정 오류와 정합 대응오류가 동시에 늘 수 있다. old-map 고정을 풀면 geometry scale/align을 유연하게 맞출 수 있으나 올바른 지도까지 변형할 수 있다. 이 trade-off는 **우리 추론**이다.

## 4. 실제 검증 범위

**[원문 사실]** 847 current map/2255 outdated map, 추가239 test scene에서 공통 성공218만 거리평균한다. DUSt3R/MASt3R/VGGT 실패는 각각6/11/14다. 삭제264 scene은 GT-mask visibility diagnostic이다. [Table2–4, pp.6334–6335](https://openaccess.thecvf.com/content/WACV2026/papers/Lin_SceneEdited_A_City-Scale_Benchmark_for_3D_HD_Map_Updating_via_WACV_2026_paper.pdf#page=5).

**[공식 코드 사실]** log split 파일에는 train550/val150/test150 source log가 있다. 이것과 논문의239/264 edited-test subset 대응, 사용된 모델 학습 overlap, spatial independence는 이번 source inspection으로 닫히지 않았다. [고정 split 파일](https://github.com/ChadLin9596/ScenePoint-ETK/blob/36a1df1d0ebf87c135659c4eba0a7861190d550c/src/scene_point_etk/argoverse2/log_splits.json).

**[미확인]** 본문 Table2는 outdated2255, arXiv 보충B는2235로 표기한다. 서로 다른 배포/집계 subset인지 오기인지 확인되지 않았다. 카드의2255는 본문 Table2 수치이며 최종 데이터 census로 인증한 값이 아니다.

**[평가 감사]** point-set Chamfer는 m²이고 나머지 거리들은 m; surface normal/roof topology/appearance/render 평가는 아니다. 결과값의 의미를 확인한 공식 [거리 구현](https://github.com/ChadLin9596/ScenePoint-ETK/blob/36a1df1d0ebf87c135659c4eba0a7861190d550c/src/scene_point_etk/evaluation/map_updating.py#L12)은 양방향 squared Chamfer, Hausdorff, 평균/median 기반 변형과 empty-set 처리를 갖는다. Table3의 선택된 성공평균만 쓰면 실패를 누락하므로 failure rate를 반드시 함께 보고한다. A100 한 장 runtime은 보고되나 end-to-end detector·전처리 포함 범위는 재현 driver 확인이 필요하다. 전체 unchanged 구조 악화도 별도 계량해야 한다.

## 5. 남은 오류와 전달 경로

| 상태 | 구분·근거 | 전달 경로 / 다른 원인 |
|---|---|---|
| **관측된 실패** | [저자 해석] MASt3R는 정합이 좋아도 건물 결손, VGGT는 구조를 생성해도 정합 오류; Fig.6 | predictor geometry와 map alignment를 서로 다른 오류원으로 보여줌 |
| **관측된 실패** | [원문 사실] Table3에서 predictor별 실패; [저자 해석] dynamic RGB가 correspondence/정합을 방해; §6.1 | static mask로 남은 dynamic→정합 오류→추가 geometry 편차 |
| **관측 조건 한계** | [원문 사실] 부분 visibility는 완전 관측을 뜻하지 않음; 높은 건물 상단/FOV밖 점 보존; §6.2/Fig.7 | 불충분 관측→삭제 가능한 피복 제한 |
| **관측된 민감도** | [저자 해석] image 수를 늘리면 실패·오차가 악화되는 경우; 보충D/Fig.11 | 입력 증가→predictor/정합 불안정. 모든 MVS의 일반 한계로 확대 금지 |
| **미평가** | [우리 분석] 실제 연도별 ALS 오류·표현 수준 차이·photometric 변화, current texture | 합성 voxel edit가 이 조건을 재현한다는 근거 없음 |

근거: [§6](https://openaccess.thecvf.com/content/WACV2026/papers/Lin_SceneEdited_A_City-Scale_Benchmark_for_3D_HD_Map_Updating_via_WACV_2026_paper.pdf#page=7), [보충D](https://arxiv.org/html/2511.15153v1#A4). **잔여 오류가 확인된 연구**이며 “benchmark가 있으니 문제는 해결됨”도 “GT-mask이므로 가치 없음”도 타당하지 않다.

## 6. 연구 공백 후보

**이미 해결:** 수정 영역별 추가/삭제 평가, 합성 변경의 정확한 원점 추적, 기존 지도와 영상의 구조 갱신 benchmark, observability 제한, geometry/registration oracle diagnostic. 동일 benchmark 기능을 다른 데이터로 만들었다는 사실만으로 방법론 신규성을 선언하지 않는다.

**후보 [적용 조건/검증 확장]:** 합성 편집에서 좋은 기존 조합이 실제 측정오차·불완전 prior·항공 관측에서도 유효 구조 손상을 통제하는가? 현재 SceneEdited는 이 질문 전체의 답이 아니지만 준비된 비교/평가 구조를 제공한다. 단순히 real data를 추가하는 것은 경험적 검증 기여일 수 있으며 자동으로 새 알고리즘 기여는 아니다.

**최소 비교/기각:** GT-mask vs predicted-mask, known calibration vs 허용 정합추정, 기존 predictor+robust alignment vs 제안 수정의 영향을 분리한다. 관측 충분/가림, valid/edited prior, 성공/실패 모두 포함하고 no-update·simple update·기존 stereo+정제 baseline을 둔다. GT mask에서도 candidate reconstruction의 추가 이득이 없으면 판단 모듈을 먼저 복잡하게 만들 이유가 약하다. 반대로 GT에서는 가능하나 실제 mask에서 불가능하면 관측 확보/유보 방향으로 축소한다. 기존 조합이 조건별 오류를 같은 수준으로 줄이면 새 공동/반복 방식의 필요성은 기각한다.
