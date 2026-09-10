# 조건 기반 이종 기하 융합·영상 보정 문헌 검토

작성·원문/공식 코드 재열람: 2026-09-10. `scientific_verdict: null`.

이번 문서는 탐색적 학위 설계의 분석 자료다. 기존 계약·실행 계보를 변경하지 않는다. AGENTS.md를 읽었으며 학습·추론·렌더·재구성·방법 실험·프로젝트 도구·서비스를 실행하지 않았다. 기존 문서와 메모리는 탐색 색인으로만 사용했다. 아래 문헌 사실은 링크한 원문과 확인 가능한 공식 소스를 이번에 다시 열람한 범위다.

## 1. 먼저 구분할 조건과 방법군

**우리의 입력 조건 제안**이며 특정 논문의 결론이 아니다. 센서명을 역할로 치환하지 않는다. 점군은 정밀해도 성기거나 편향될 수 있고, LoD는 표면이 연속해도 생략·일반화가 있으며, DSM은 2.5D 표현상 수직면·중첩면을 담지 못한다. 영상은 관측 방향에 따라 큰 면의 위치를 더 잘 제약하거나 세부 깊이를 전혀 구별하지 못할 수 있다.

| 조건 | 이 조건 때문에 검토할 방법군 | 우선 비교 질문 |
|---|---|---|
| 초기 표면이 대체로 맞고 영상에 복원 가능한 차이가 존재 | photometric mesh refinement, class별 구조 정규화 | 기존 vertex 보정만으로 정확도·세부가 회복되는가? |
| 희소 range와 stereo가 상보적이나 일부 불일치 | LiDAR-guided matching, robust cost propagation | 기하를 나중에 합치기 전에 대응 추정을 개선하면 충분한가? |
| 두 기하의 국소 오차·해상도·완전성이 불균일 | sensor-specific volumetric fusion, quality-aware mesh fusion | 가중/선택 문제인가, 후보 자체가 틀린 문제인가? |
| 초기 구조는 유효하지만 영상의 깊이 제약이 약함 | 구조 정규화, state-dependent update, free-space constraints | 광도 개선이 기존 기하 손상으로 지불되는가? |
| prior 피복 밖은 영상에 보이거나, prior가 현재 틀림 | partial-prior constraints, local update, 생성/제거 | 'prior 없음'과 '존재하지만 틀림'을 기존 제어가 각각 다루는가? |
| 기하·외관 변화가 혼재 | appearance adaptation + geometry update | 외관으로 기하 오류를 흡수하거나 조명을 기하로 설명하는가? |
| 어떤 입력도 목표 깊이·현재성을 구별하지 못함 | 관측 가능성/불확실성 진단 | 정보 활용 개선의 주장보다 현재 복원 가능한 범위를 제한해야 하는가? |

새 문헌 확장은 **SRDM의 guided matching → mesh refinement의 실제 geometry feedback → learned heterogeneous fusion → partial-prior 변수 제약** 순서로 연결했다. 시간차 갱신을 다루는 Wu/GaussianUpdate는 추가·제거/변경이 실제 병목일 때 우선순위를 높인다.

## 2. 가까운 방법의 성공과 남은 범위

아래 '직접'은 목표 속성의 직접 경쟁 후보다. native 입력·표현이 다르면 입력 변환과 공통 출력 후단을 명시해야 하며, 원방법 수치의 충실 재현과 공통 정보 비교를 구분한다. **관측 실패 / ablation으로 완화·해결 / 미평가 / 적용 가정 밖**을 섞지 않는다.

### A. SRDM — Huang et al., ISPRS JPRS 2018

**역할: 직접 기하 복원 경쟁군.** Stereo + 희소 range → dense disparity/점군. 약한 prior로 얻은 첫 시차가 불일치 range를 기각하고, 남은 guidance로 두 번째 시차를 추정한다. 정합된 영상·카메라는 고정하며, 두 번째 prior 비용도 절단한다. 따라서 복원 결과가 감독 사용을 바꾸는 피드백이 이미 있다. 최종 시차가 pose/기각집합을 다시 고치는 반복은 확인하지 못했다. [저자 공개 원고 §3.2.3–4, 식18–22](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=11).

**성공:** 부분 불일치 처리, 희소 range의 전파, 영상 단독보다 규칙적이고 정확한 지붕 복원을 보고한다. **관측 실패·저자 설명:** 균일 강도에서 실제 시차 jump가 있으면 작은 시차 변화 가정 때문에 mismatch가 남는다. **미평가:** 정합 잔차와 낮은 texture가 함께 있는 경우의 유효 prior 오기각률, 최종 현재 textured surface의 손상·회복 동시 평가. [§4/Fig.14, §5, 원고 pp.19–20](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=19).

**공식 코드:** 이번 검색·원문에서 저자 실행 저장소를 확인하지 못했다. 로컬 SRDM 재구현을 공식 코드나 위 저자 결과로 취급하지 않는다. **중요성·최소 비교 [우리 제안]:** 기하 손상과 세부 누락 모두에 연결되므로 image-only / SRDM / SRDM+기존 경계·다중쌍 검사 / 제안 규칙을 비교한다. 기존 보강으로 해소되면 새 판정/반복 모듈의 필요성은 축소한다.

### B. Photometric Multi-View Mesh Refinement — Rothermel et al., ISPRS JPRS 2020

**역할: 직접 보정 경쟁군.** Coarse mesh + calibrated satellite images → refined 3D mesh. 영상 간 texture transfer의 ZNCC gradient를 RPC/RFM을 거쳐 vertex로 보내고 thin-plate smoothness와 합친다. 갱신 mesh가 다음 반복의 입력이다. 영상 비용이 기하를 실제 수정하는 방법이며 초기 표면만 선택하는 방식이 아니다. [원문 §3.1–3.3](https://arxiv.org/html/2005.04777v1#S3).

**성공:** 기존 MVS 초기값의 세부·경계·수직면 개선을 보고한다. **관측 문제→기존 해결:** 초기 vertex가 정답에서 멀면 수렴 문제가 있었고 hierarchical refinement로 완화했다. **관측 trade-off:** Table5의 S2P→refined 일부 ROI에서는 완전성 또는 RMSE가 악화된다. 모든 초기값·지표에서 이득이라는 주장은 아니다. **미평가:** 이 연구의 초기값은 MVS이며 오염된 과거 LiDAR/LoD를 조건별 교정하면서 유효 구조를 보존하는 검증은 별개다. [§3.3, §5/Tables4–5](https://arxiv.org/html/2005.04777v1#S5).

**공식 코드:** 이번에 논문에 대응하는 저자 실행 저장소는 식별하지 못했다. **중요성·최소 비교 [우리 제안]:** GS 채택 이전에 같은 초기 표면·현재 영상·camera·허용 감독으로 photometric refinement + tuned regularization의 충분성을 확인한다. 새 규칙의 효과가 초기값/세분화/추출 차이로만 설명되면 기여를 축소한다.

### C. Semantically Informed Multiview Surface Refinement — Bláha et al., ICCV 2017

**역할: 직접 보정 경쟁 + 구조 제약 도입 후보.** 초기 mesh, calibrated images, 영상의 semantic likelihood를 받는다. shape를 고치며 label을 고정하고, shape를 고정하며 label을 다시 추정한다. class별 smoothing·경계 방향·surface orientation 제약이 양쪽에 전달된다. 초기 topology가 유지되고 local optimization이 가능한 근접 초기값을 전제한다. [원문 §3–3.2](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/09/Blaha-et-al-ICCV-2017.pdf#page=3).

**성공:** SynthCity의 기하 정량 및 항공/지상 장면의 semantic 정량·기하 정성 개선. **평가 한계:** 실제 장면에는 기하 GT가 없었다. **적용 가정 밖:** topology가 틀리거나 초기 표면이 멀리 있는 상황. 이를 관측된 실패로 바꾸어 쓰지 않는다. **미평가:** 틀린 class prior와 실제 관측이 충돌할 때의 유효 구조 손상률. [§4/Table3](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/09/Blaha-et-al-ICCV-2017.pdf#page=6).

**공식 코드:** 공개 코드 언급은 검색되었으나 이번에는 저자 제공 저장소와 핵심 구현을 검증하지 못했다. **중요성·최소 비교 [우리 제안]:** 반복·class별 제약·구조/세부 동시 개선 자체가 새롭다는 주장은 제외한다. 같은 영상 파생 labels를 제공한 photometric-only / fixed structural constraints / 기존 shape↔label iteration / 제안 제약을 비교한다. GT labels는 제공하지 않는다.

### D. SenFuNet — Sandström et al., ECCV 2022

**역할: 융합 구성요소·원인 설명 우선.** 센서별 depth stream을 TSDF와 특징으로 누적하고 국소 결합 가중치를 학습한다. Replica/CoRBS/Scene3D 등에서 이질 센서·outlier 대응 성공을 보고한다. 학습은 GT TSDF를 요구한다. **관측 실패·저자 설명:** 매끄럽지만 틀린 센서 선택, 선택이 나을 경계에서 평균화, 두 센서가 겹친 outlier를 가질 때 제거의 한계. 이는 제안법 자체의 국소 잔여 사례다. [원문 §3–4, Appendix J/Fig.17](https://arxiv.org/html/2204.03353v2#A10).

**공식 구현 재확인:** commit `43c1682e29c700df4577d9dcf0ac3b8ebdd8f496`, `filtering_net.py` L192–224의 sigmoid α와 α/1−α TSDF 결합. 두 관측이 모두 있는 경우의 결합과 단일센서 상태 처리가 다르다. [공식 코드](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/modules/filtering_net.py#L192).

**피드백·경계:** 원 depth/pose를 직접 고치는 방법으로 보지 않는다. 최종 융합에서 센서별 TSDF로 되돌아가는 갱신은 이번 단일 파일 검토로 확인하지 않았다. **중요성·최소 비교 [우리 제안]:** 국소 연속 가중만으로 충분한지의 강한 기준이다. 무조건 direct baseline으로 추가하면 학습정보/센서/표현 차이가 생긴다. 동일 허용 학습정보·기하 변환에서 global / local robust weights / 새 규칙을 비교하며, 'noisy but right'와 'smooth but wrong'의 상대 순위 및 같은 영역의 손상·교정을 평가한다.

### E. EnerGS — Song et al., 2026

**역할: partial-prior 직접 경쟁 + 변수 제약 도입 후보.** 부분 LiDAR 기하를 occupied/free/unknown field로 만들고, 위치는 기하 energy로, covariance·opacity·외관은 photo loss로 갱신한다. trusted occupied/free를 전제하며, unknown에서는 약한 제약과 photo-driven densification을 허용한다. **성공:** KITTI/Waymo의 PSNR·기하 관련 지표 및 ablation. **trade-off:** Table1의 SSIM·Thick 등 모든 지표에서 우세하지는 않으며 §5.4는 낮아진 leakage와 낮아진 occupied coverage가 함께 생길 수 있음을 설명한다. [원문 §3–5/Tables1–2](https://arxiv.org/html/2604.26238v1).

**공식 구현 재확인:** commit `a222ed59b05a56eecf7b7199e02eb80bcb288775`, `train_energs.py` L675–692는 backward 뒤 `_xyz.grad = None`, coverage 갱신을 명시한다. photo가 center를 직접 옮기는 경로는 차단되지만 densification·다른 속성 경로는 남는다. [공식 코드](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/train_energs.py#L675).

**미평가·우리 추론:** trusted field가 현재 틀린 조건에서 기존 중심을 현재 영상으로 교정하는 능력은 별도 질문이다. 이는 보고된 실패가 아니다. DSM/LoD에서 LiDAR ray-derived free space를 동일하게 얻었다고 가정할 수 없다. **최소 비교:** 동일 field/초기값에서 tuned joint gradient / EnerGS식 분리 / 조건부 위치 수정. 기하 개선이 이미 기존 strong/weak energy 조정으로 달성되거나 새 위치 경로가 유효 구조를 훼손하면 새 원리를 축소한다. [원문 §4.1의 가정](https://arxiv.org/html/2604.26238v1#S4.SS1).

## 3. 조건부 후속 비교군과 인용 확장

| 문헌 | 입출력·실제 피드백·보고 성공 | 부족 상태와 지금 역할 |
|---|---|---|
| Wu–Vallet–Demonceaux, Mobile Mapping Mesh Change Detection and Update, 2023 | 여러 시점 sensor mesh·관측 위치→거리/ray·지속성·품질을 이용한 triangle 선택/접합. 미변화에는 quality, 변화에는 novelty 우선. Robotcar/Stereopolis 사례. 최종 mesh→원 depth 재추정 경로는 확인하지 못함 | **직접 갱신 경쟁 후보.** 같은 meshes에서 quality/ray 기반 기존 조합이 충분한지 우선 확인. LiDAR 실험을 영상 mesh 정량 실패로 확장하지 않음. 공식 핵심 코드 미확인. [§III–V](https://arxiv.org/html/2303.07182v1) |
| RoutedFusion, CVPR2020 | 새 depth + 이전 TSDF→학습 비선형 volume update; 다음 관측에 누적 상태가 재사용됨. edge/thin structure·noise에서 TSDF 대비 성공 | **상태 의존 갱신 도입 후보.** 학습정보·depth 분포가 다르므로 우리 raw prior+RGB의 완성 직접 비교와 구분. 공식 `pipeline.py`에서 current volume을 읽고 detach 저장; routing은 fusion training 중 no_grad. [원문 §3–4](https://arxiv.org/html/2001.04388v2), [코드 L195–260](https://github.com/weders/RoutedFusion/blob/dc6e0f582654ffcbd227c95e9a63e9654d45fa77/modules/pipeline.py#L195) |
| GaussianUpdate, ICCV2025 | 기존 **학습된 3DGS 외관/기하** + 새 RGB/pose→외관 적응, 제거/추가, joint refinement. 후단이 외관을 다시 갱신하므로 단계 존재로 단방향 분류 금지 | **추가·제거 및 외관 분리 후보.** 사라진 객체 잔류·densify-only 신규 객체 누락은 저자 ablation에서 제안 요소로 개선된 문제. 완성 제안법의 잔여 실패로 인용 금지. 무색 LiDAR/LoD는 native 입력과 다름. 공식 프로젝트에 연결된 실행 코드 핵심 경로는 이번에도 확인하지 못함. [§3.2/§4.3](https://arxiv.org/html/2508.08867v1), [공식 프로젝트](https://zju3dv.github.io/GaussianUpdate/) |
| Romanoni et al., Single-View Semantic Mesh Refinement, ICCVW2017 | Bláha를 명시 인용하며 pairwise photo + single-view semantic consistency와 mesh-derived class prior를 검토 | **구조 제약/감독 편향의 추가 후보.** 원문 초록의 입력/관련성만 확인; 본문·공식 구현·세부 ablation 검증 전이므로 우열 판정 보류. [저자 원문](https://arxiv.org/abs/1708.04907) |

Bláha/Rothermel의 related work는 curvature regularization의 photo-consistency별 조정, 효율적인 국소 refinement, geometry–pose 공동 refinement를 이미 연결한다. 이 내용은 **추가 읽기 색인**이며 인용된 개별 논문의 구현/성과를 확인한 것으로 세지 않는다. [Bláha §2](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/09/Blaha-et-al-ICCV-2017.pdf#page=2), [Rothermel §2](https://arxiv.org/html/2005.04777v1#S2).

## 4. 남는 부족의 중요성·경쟁 원인·최소 계획

아래는 **우리의 아직 실행하지 않은 설계**다. 모든 행에서 같은 원영상·초기 구조·감독 정보·정합·추출·계산 예산을 맞춘다. 감독의 정보량이 달라지는 native 방법 비교는 별도로 표시한다. prior 깊이 가중과 위치/scale/rotation/생성·삭제 보호는 별도 요인으로 다룬다.

| 우선 질문 | 경쟁 원인 | 먼저 충분성을 시험할 기존 해법 | 새 기여 후보 및 기각/축소 조건 |
|---|---|---|---|
| 정확한 구조와 틀린 구조가 같은 국소 영역에 섞일 때 수정이 필요한 성분만 바꿀 수 있는가? | 신뢰 순위 오류 / supervision bias / 허용 변수 차단 / 강한 constraint가 틀림 | robust loss·local confidence·tuned structure regularization·EnerGS식 변수 분리 | 관측이 구별하는 위치/방향 성분에만 수정 자유도를 주는 제약 후보. 단순 가중·분리가 동등하면 신규성 축소 |
| 세부가 원영상에는 있는데 최종 표면에서 사라지는가? | matching ambiguity / 보간 / regularization / topology / extraction | SRDM+기존 경계 처리, photometric mesh refinement, 동일 표면 해상도 비교 | 정보가 없다는 경우와 전달 차단을 분리하는 추정 원리 후보. 허용 관측이 깊이를 구별하지 못하면 관측 기반 회복 주장 기각 |
| photo error 감소가 현재 기하 개선으로 연결되는가? | 외관이 기하 오차 흡수 / pose 잔차 / visibility 오류 / 부정확 supervision | appearance adaptation, geometry/appearance variable schedule, 기존 visibility mask | 외관·기하 gradient 전달 보정 후보. 영상 PSNR만 좋아지고 독립 표면 오차·유효 구조 손상이 악화되면 기하 기여 기각 |
| correct-but-noisy보다 smooth-but-wrong이 선호되는가? | 학습 분포 / geometry feature의 편향 / 국소 혼합 / 두 후보 모두 틀림 | robust local weighting와 기존 관측 일관성 검사 | 동일 후보에서 관측의 지지를 반영한 보정 후보. 후보 둘 다 틀리고 raw evidence도 구별 못하면 선택 개선으로 해결 주장 금지 |

평가에서는 각 동일 영역의 **필요한 교정량과 유효 구조 손상량**을 함께 기록한다. 예측→참조 거리와 참조→예측 거리/완전성, 현재성, 관측 가능한 세부, 외관, 시간·메모리를 분리한다. 전체 평균 향상뿐 아니라 기존 방법이 이미 성공한 영역과 제안법의 악화도 보고한다. GT는 이 분석과 평가에만 쓰며 학습 감독·mask·가중·수정 허용 여부의 입력으로 사용하지 않는다.

**현재 기여 판단:** 보존+수정, 반복, 가중, 생성/제거 또는 GS 채택은 각각 이미 선행 원리다. 그렇다고 목표 전체의 차별성이 소멸하는 것은 아니다. 조건별 정보·제약·변수 전달의 어느 연결이 남는 부족을 만드는지와, 기존 해법의 조정으로도 제거되지 않는 경우를 겨냥하는 하나의 추정/제약 규칙이 방법 기여 후보가 될 수 있다. 이 후보의 필요성과 성능은 아직 검증되지 않았다.

## 5. 검토 범위·미확인·예외

- 원문/공식 공개 소스의 읽기만 수행했다. 코드 pin은 기존 색인을 현재 원격 파일과 재대조한 고정 버전이며 최신 HEAD 또는 논문 실행 설정의 완전 재현이라는 뜻은 아니다.
- Rothermel 수치표는 arXiv HTML에서 확인했다. PDF screenshot 요청은 timeout이어서 표의 숫자를 별도로 전사하지 않았다. 원문이 보여주는 일부 지표 악화의 방향만 요약했다.
- Wu2026 원문 페이지 요청은 internal error였다. 이전 문서의 구체 결과를 이번에 확인한 사실로 옮기지 않았으며 이 문서의 근거표는 재열람한 Wu2023까지다.
- Bláha 저자 홈페이지 요청은 internal error였고 공식 코드 핵심 구현은 확인하지 못했다. Romanoni 학회 PDF는 403이므로 초록 이상의 세부 주장은 보류했다. 문헌 획득 예외이며 연구 방법 실행 실패가 아니다.
- 문헌 색인에 사용한 memory: `MEMORY.md` 28–35행. 현재 논문 사실은 해당 기억에서 가져오지 않았다.
