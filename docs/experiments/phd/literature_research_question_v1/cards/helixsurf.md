# HelixSurf — 근거 카드

`reviewed_at: 2026-09-09` · `scientific_verdict: null` · 추가 탐색 이유: **MVS와 표면 추정의 실제 양방향 feedback**이 ‘반복·공동 복원이 새롭다’는 후보와 직접 경쟁한다. 도시 외부 prior 재사용의 제품 직접 비교보다 정보 흐름/기하 구성요소 비교다.

## 원문·버전·확인 범위

- Liang, Huang, Ding, Jia, **HelixSurf: A Robust and Efficient Neural Implicit Surface Learning of Indoor Scenes with Iterative Intertwined Regularization**, CVPR 2023, 13165–13174. [공식 학회 PDF](https://openaccess.thecvf.com/content/CVPR2023/papers/Liang_HelixSurf_A_Robust_and_Efficient_Neural_Implicit_Surface_Learning_of_CVPR_2023_paper.pdf), [저자 arXiv v2](https://arxiv.org/abs/2302.14340v2), [저자 PDF v2](https://arxiv.org/pdf/2302.14340v2).
- 이번 학회 서버는 403, arXiv web parser는 파일 크기 제한이었다. **arXiv v2(2023-03-01), 19쪽 본문+supplement를 다운로드하고 Docker pypdf로 직접 읽었다.** SHA256 `fb96b1e6c00720f112b99fed1b1a1684f932ad49b109db04343d400cc8bd70e2`. 아래 절/페이지/표/그림은 이 버전 기준; 학회 최종본과 모든 문장이 동일하다고 가정하지 않는다.
- 공식 코드 shallow checkout HEAD [3b46727bf76b4f089afbc79a37a6fb37dc9c66c2](https://github.com/Gorilla-Lab-SCUT/HelixSurf/tree/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2), 2023-04-24. `gmvs` submodule gitlink [239b0b1051e48e2834bf0e023d1b789e4767ae4c](https://github.com/Gorilla-Lab-SCUT/gmvs/tree/239b0b1051e48e2834bf0e023d1b789e4767ae4c). 스크립트/핵심 함수를 읽었으며 실행·학습·실험 렌더 없음.

## 1. 문제와 입출력

보정된 다중 RGB로 복잡한 장면 표면과 세부를 복원한다. PM-MVS의 texture-rich 세부와 MLP SDF의 연속 표면/평활성 편향을 상보적으로 사용한다. **실제 관측은 RGB**, 카메라 calibration은 주어진 입력, MVS depth/normal·occlusion/view-selection 상태와 implicit surface depth/normal은 **동일 영상에서 반복 추정된 파생 기하**다. 재사용 ALS/LoD2와 같은 외부 prior가 아니다. output은 SDF zero-level mesh 및 부차적 NVS이다. [§3–4 pp3–6, Fig2]

기본 논문은 auxiliary training data 없이 학습하며 네트워크의 architecture/smoothness bias를 활용한다. 코드에는 별도 Omnidata pretrained-normal 옵션이 추가되어 있으므로 기본 비교와 구분한다. textureless 영역은 색이 균일하고 기하가 매끄럽다는 가정을 둔다. Supplement B p11은 MVS가 전혀 없는 부분의 초기 법선에 Manhattan 가정도 사용한다고 명시한다. 알려진 pose·동일 정적 장면 및 영상 superpixel의 기하적 유용성은 강한 조건이다.

## 2. 기여의 위치

| 요소 | N=논문 제안 / U=기존 사용 / ?=미확인 |
|---|---|
| 입력·전처리 | **N+U**: MVS 신뢰 부재로 textureless 영역 판별하는 결합; 기존 superpixel segmentation·Poisson·raycasting 사용. §4.1.1, Supp B/D |
| 좌표·카메라·정합 | **U**: 보정 camera 입력. 새 pose optimizer/좌표정합 기여는 없음. §4 첫 문단 |
| 표현 | **U**: MLP SDF와 color field, DeepSDF/NeuS 기반 연속 표현. §3, Supp A |
| 관측모형·렌더링 | **N+U**: NeuS SDF-induced 미분 가능 volume rendering 사용, dynamic occupancy ray sampling을 효율 기여로 제안. §4.3 |
| 증거 사용·감독·제약 | **N+U**: MVS→SDF geometric loss, SDF→MVS prior, textureless normal smoothing의 intertwined 결합; photometric/geometric consistency와 Eikonal은 기존 형식. 식5–9 |
| 초기화·최적화·모델 변경 | **N+U**: 양방향 중간 결과 교환, updated MVS 재학습, occupancy·smooth normal 갱신. Adam/PatchMatch/GEM 재사용. §3–4 |
| 추출·후처리 | **U+N**: final Marching Cubes는 기존; MVS Poisson의 unsupported faces 제거로 supervision 영역 생성하는 절차가 제안 흐름에 포함됨. §4.1.1,4.4, Supp D.3 |

## 3. 무엇을 고정하고 무엇을 수정하는가

| 대상 | 고정·변경·강한 가정 |
|---|---|
| RGB, calibrated poses, 초기 source-view pair list·superpixel | 입력/전처리로 재사용. geometry feedback으로 camera BA를 하는 경로는 확인되지 않음 |
| SDF/color MLP, density/occupancy | 학습·재계산. sample space occupancy는 16 training iterations마다 갱신하여 빈 공간 sampling을 줄임 |
| MVS per-pixel depth/normal, view/occlusion 판단 | PM-MVS 내부에서 최적화. 표면 추정 후 받은 depth/normal을 prior/초기 가설로 사용하여 **다시 이미지 matching** |
| smooth normal target | 현재 mesh/raycast와 superpixel·multi-view consistency로 다시 생성. geometry regularizer의 target 자체가 바뀜 |
| confidence/선택 | MVS 유효 pixel indicator, photometric residual 가중, normal-angle mask, geometric consistency filtering. calibrated uncertainty/currentness probability와는 다름 |

**확인된 실제 feedback:** `RGB→1차 MVS depth/normal→1차 SDF 학습→SDF mesh raycast depth/normal→2차 MVS 재추론→2차 SDF 학습`. RGB와 camera는 그대로라도 새로 계산한 MVS correspondence/plane과 surface가 변하므로 단순한 고정 depth 반복 가중이 아니다. 각 solve는 구간별 고정 target을 사용하지만 전체 경로는 양방향이다.

코드 증거는 [train.py L561–574](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/scripts/train.py#L561)의 1차 surface depth/normal export, [next_mvs.sh L20](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/run_scripts/next_mvs.sh#L20)의 `--dn_input`, [gmvs launch L132–165](https://github.com/Gorilla-Lab-SCUT/gmvs/blob/239b0b1051e48e2834bf0e023d1b789e4767ae4c/gmvs/scripts/launch.py#L132)의 input initialization→PatchMatch→fusion, [README의 2차 epoch 절차](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/README.md#L57)다. **모든 SGD step마다 두 알고리즘을 완전히 공동 미분하는 방식이라고 표현하지 않는다.**

[train.py L254–282](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/scripts/train.py#L254)는 현재 표면에서 planar normal을 다시 만들며 초기 MVS normal 비중을 감소시킨다. [L303–358](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/scripts/train.py#L303)은 RGB residual 가중, depth-loss clipping, normal-angle mask를 포함한다. 높은 현재 모델 일치도가 독립 참조 정확도를 증명하지 않는다는 것은 **우리 추론**이다. 고정 가정들을 풀면 수렴/평활성/속도 이득을 잃거나 잘못된 현재 표면의 self-reinforcement를 줄일 수 있으므로 비교가 필요하다.

## 4. 실제 검증 범위

- ScanNet 4 scene, 약 200–500 image/scene(원 video every tenth), 640×480; T&T large indoor 4 scene 및 outdoor qualitative, T&T 모든 image를 960×540로 사용. ScanNet reference는 dataset SLAM surface/calibration. 추가 DTU·iPhone 사례는 supplement qualitative. [§5 p6, §5.3 p8–9, Supp D.4/F pp13–14]
- Accuracy/completeness(양방향 평균), P/R/F-score@.05m. 기본 Table1 평균 F=.755 vs MonoSDF .733, NeuS .291, PM-MVS/다른 implicit 방법 비교. Accuracy는 MonoSDF .035가 Helix .038보다 낮아 모든 metric 우위가 아니다. 효율 약33min에는 MVS inference와 implicit 학습 포함. [Table1 p7; Supp Table5 p14]
- Table2는 ordinary/regularized MVS 및 textureless handling을 비교, Table3은 **MVS depth RMSE .147→.106, normal mean 35.5°→27.8°**로 역방향 정보 갱신의 효과를 따로 측정한다. Table4는 occupancy sampling의 시간 효과(33.2 vs393.4min)를 분리. ‘loop가 있음’ 이상의 저자 ablation 증거가 있다. 원문 평균을 임의 scene별 비악화 증거로 바꾸지 않는다.
- NVS는 남겨둔 9/10 frames 일부를 임의 선택해 supplement Fig15에 표시. 수치로 정밀하게 고정된 independent NVS test membership은 확인되지 않는다. 기하 반복 seed·confidence calibration·국소 악화 분포·도시 ALS/LoD prior·정합 오차 stress·시간차 복원은 미평가다.

## 5. 남은 오류와 전달 경로

| 조건·잔여 오류 | 사실·상태 | 전달 경로·다른 원인 |
|---|---|---|
| 무텍스처지만 곡률이 큰 표면 | **관측된 실패를 저자가 보고**, Supp H p14/Fig12 | uniform color→smooth-normal assumption→실제 곡면과 잘못된 regularization→artifact. 저자 원인 해석이며 모든 curved surface의 필연 실패는 아님 |
| 한 superpixel이 기하 corner를 가로지름 | Supp B p11의 **저자 분석**, adaptive K-means·mesh consistency를 해결책으로 제시 | 색 분할→법선 혼합 오류; 이미 완화책이 있으므로 '색-기하 경계 불일치를 고려 안 함'이라고 하지 않음 |
| MVS 결손을 textureless로 취급 | 규칙은 **원문 사실**, 실제 모든 결손 원인 분류는 **미평가** | **우리 추론:** occlusion·pose 오류·반복 texture도 결손 원인이 될 수 있음. 이 카드에서 오분류 빈도를 관측했다고 주장하지 않음 |
| 오판의 순환 증폭/유효 구조 손상 | **미평가** | 동일 RGB 기반 MVS/SDF 간 동의가 독립 증거가 아니므로 possible feedback bias. 논문이 실제로 이런 실패를 측정했다고 쓰지 않음 |

## 6. 연구 공백 후보

**이미 해결:** 비GS 표현에서도 image-derived geometry와 연속 표면을 서로 갱신하고, 감독 신뢰를 선택/가중하고, textureless 실패를 보완하며, feedback 효과를 분리 평가한다. ‘단방향 선행연구를 반복 최적화로 바꾼다’ 또는 ‘고정 MVS를 후단으로 수정한다’ 자체는 학위 기여로 불충분하다.

**남는 질문:** 외부 자산의 오차·표현 차이와 관측 충분성이 혼재할 때 이런 반복이 유효 구조 손상을 줄이는가, 아니면 오류를 강화하는가. 이는 HelixSurf의 외부 prior 연구 공백을 새롭게 입증한 것이 아니라 **적용조건 차이와 검증 후보**다. 가장 가까운 대안은 HelixSurf feedback, 강한 PM-MVS+implicit 순차, SRDM/Zhou 처리+같은 readout, 단순 weight/mask 조합이다.

**최소 비교:** 같은 정보·surface output·계산 예산으로 fixed geometry→surface, 1회 feedback, 원 HelixSurf형 alternating feedback 및 필요한 경우 제안법을 비교. 외부 prior를 넣는다면 입력 추가 자체의 효과와 feedback 효과를 분리하고 prior-free arm도 둔다. 참조는 학습의 두 파생 geometry와 독립이어야 하며 원래 성공 구역 악화·곡면 세부·완전성·비용을 같이 본다. **기각:** 1회/강한 순차가 동등하거나, 개선이 smoothing으로 세부를 잃거나, 평균 이득이 유효 구조 손상을 동반하거나, 새 independent evidence 없이 오류를 순환 강화하면 반복의 필요성·우위 주장을 기각/축소한다.
