# 현재 영상으로 prior와 영상 감독의 유용성을 함께 판단하는 근거와 loss

- 작성일: 2026-09-10
- task_id: `PHD-PRIOR-IMAGE-JOINT-EVIDENCE-20260910`
- 상태: `LITERATURE_VERIFIED / DESIGN_CANDIDATE_NOT_FROZEN`
- scientific_verdict: null
- 범위: 원문·공식 코드의 읽기와 연구 설계. 새 학습·추론·렌더·재구성·방법 실험 없음. GT는 평가 전용.

## 1. 질문과 현재 결론

질문은 “현재 관측이 영상뿐인데, 기존 기하가 더 정확한 곳과 영상이 더 정확한 곳을 어떻게 함께 처리하는가?”이다. **두 요구를 함께 다룬 선행은 존재한다.** NeuRIS와 ND-SDF는 영상 예측 기하 prior의 유익한 제약과 영상에 의한 세부 복원을 함께 다룬다. ACMP는 영상의 photometric cost와 평면 prior의 compatibility를 하나의 목적함수에서 결합한다. FusionNet은 LiDAR·RGB에서 얻는 두 복원 branch의 국소적 유용성을 학습해 결합한다.

이 방법들은 현재 영상에서 정답 정확도를 직접 읽는 것이 아니다. 관측의 구별력, prior의 가정, 학습된 오류 패턴을 통해 추정한다. 서로 다른 기하가 현재 영상에서 구별되지 않고 prior의 오류를 알려줄 근거도 없으면 어느 쪽이 정확한지 확정할 수 없다. 이 경우 prior 유지와 prior의 현재 정확성 확인은 다르다.

기하 감독과 수정 제어가 현재 검토의 중심이지만 GS·위치만의 제어·DA3·별도 MVS target D_M을 확정하지 않았다. 이전 3-depth 후보식은 전체 보존·수정 방법이 아니다. 특히 q=0에서 prior와 DA3의 기본 가중치가 모두 남으므로, 잘못된 DA3가 유효 prior를 움직이는 문제를 자체적으로 해결하지 않는다.

## 2. 판단할 수 있는 근거와 판단할 수 없는 것

| 현재 영상에서 확인하는 상태 | 의미와 가능한 작용 | 주장할 수 없는 것 |
|---|---|---|
| prior 기하가 대안보다 여러 시점의 대응을 잘 설명 | 영상이 prior를 지지한다. 다른 영상 파생 depth가 이와 충돌하면 그 감독을 약화할 후보 근거 | 낮은 matching cost가 절대 정확성을 보증한다는 주장 |
| prior와 여러 대안의 영상 비용이 비슷함 | 해당 관측이 깊이를 잘 구별하지 못한다. prior의 오차 가정 아래 근거 없는 이동을 억제할 수 있음 | 영상이 prior의 정확성을 확인했다는 주장 |
| 다른 기하가 prior보다 명확하고 일관되게 관측을 설명 | prior 제약에서 벗어나는 수정을 허용할 후보 근거 | 가림·오정합·반복 무늬·외관 교란을 확인하지 않고 prior 오류로 확정 |

위 세 상태는 기존 O/O, O/X, X/O, X/X 평가 분류를 대체하는 새 정답 분류가 아니다. 정답을 모르는 학습 과정에서 확보하는 증거의 종류다. 위치·방향·경계 등의 기하 성분마다 증거의 강도가 다를 수 있다.

Prior의 센서·정합 오차 모델이나 공간 관계는 추가 근거가 될 수 있으나, 이들만으로 시점 차이나 모델링 오류까지 식별한다고 가정하지 않는다. 현재 영상의 근거가 부족하면 보수적으로 남겨둔 형상에도 정확성·현재성 주장을 제한한다.

## 3. ACMP: 같은 비용함수에서 prior 유지와 영상에 의한 수정을 허용

- 원문: [AAAI 2020, Planar Prior Assisted PatchMatch Multi-View Stereo](https://ojs.aaai.org/index.php/AAAI/article/download/6940/6794), 특히 Eq.4–7, Eq.13, Algorithm 1, Fig.2/4.
- 공식 코드: `GhiXu/ACMP`, pin `574c8e078b6f7bd93237bd180d46f5adf1169a19`.
- 입력/출력: calibrated RGB에서 영상별 depth/normal과 융합 점군. prior는 초기 PatchMatch의 낮은 비용 대응점을 삼각분할해 만든 평면이다. 독립적인 기존 LiDAR/LoD가 아니다.

원문 Eq.7의 뜻을 정리하면 `E(theta) = C_photo(theta)^2 / alpha - log P(theta | theta_prior)`이다. Prior compatibility는 깊이와 normal의 차이에 따라 감소하지만 양의 바닥값 gamma가 있다. **우리 수학적 해석:** 영상 비용이 후보를 구별하지 못하면 prior에 가까운 해를 선호하고, 영상이 다른 후보를 충분히 지지하면 유한한 prior 이탈 비용을 넘어설 수 있다. Prior의 정오를 먼저 분류할 필요는 없다.

[ACMP.cu:948–987](https://github.com/GhiXu/ACMP/blob/574c8e078b6f7bd93237bd180d46f5adf1169a19/ACMP.cu#L948)은 `exp(-photo_cost^2 / beta) * (gamma + depth_compatibility * normal_compatibility)`를 비교한다. 코드의 depth compatibility는 각 픽셀에서 평면으로부터 구한 depth 차이를 사용한다. 논문의 plane hypothesis 표기와 이 구현을 구분한다.

완성법은 이 prior-assisted 과정 뒤 multi-view geometric consistency로 재최적화한다. [main.cpp:334–351](https://github.com/GhiXu/ACMP/blob/574c8e078b6f7bd93237bd180d46f5adf1169a19/main.cpp#L334)에서 후속 단계는 `planar_prior=false`이다. 따라서 모든 단계에 prior 손실이 남는다고 설명하면 안 된다. 저자는 잘못된 초기 대응이 만든 prior 오류를 후속 기하 일관성으로 완화하며, prior-assisted-only 결과와 완성법을 비교한다.

검증한 성공: 저텍스처 평면의 완전성과 비평면·경계의 복원을 함께 개선하는 ETH3D 비교. 한계 범위: 외부 prior의 유효 부분을 불변으로 보존하거나 과거 metric 기하의 수정·보존을 함께 검증한 결과는 아니다. 강한 영상 비용이 틀리는 조건이나 prior 자체의 구조 오류에서는 정답 보장이 없다.

## 4. NeuRIS: normal 감독 유지와 제외를 한 복원 과정에서 수행

- 원문: [NeuRIS v2](https://arxiv.org/html/2206.13597v2), §3.2–3.3, §4.3/Table3/Fig.6–7.
- 공식 코드 pin: `fab2cc4ca45847fbee7490e978d3c60c582123b1`.
- 입력: calibrated RGB와 영상 예측 normal; 출력: SDF 표면·외관. 독립 기존 기하를 사용하는 방법은 아니다.

처음 normal prior로 구조를 확보한 뒤 현재 depth/normal로 원영상 patch를 warp해 NCC를 계산하고 normal 감독을 제어한다. 전체 목적은 RGB + 유효 normal 감독 + Eikonal이다. **사진이 잘 맞으면 prior를 버리는 규칙이 아니다.**

공식 [exp_runner.py:329–390](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L329)의 유지 조건은 현재 NCC cost < threshold, 이전 cost < threshold, 현재 peak normal과 prior의 각도 < 30도다. 기각은 누적된다. 논문 Eq.9는 normal vector L1이고, 공식 [models/loss.py:192–206](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/models/loss.py#L192)은 angular error를 사용한다.

중요 구현 사실: [models/patch_match_cuda.py:145–159](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/models/patch_match_cuda.py#L145)은 분산 분모가 0인 patch의 NCC를 1로 둔다. 이는 해당 경우 영상이 정확한 깊이를 증명했다는 뜻이 아니다. 다른 gate도 통과하면 prior를 유지하는 처리가 된다.

검증한 성공: Fig.6–7은 prior로 벽·바닥·책상을 복원하면서, 잘못된 normal의 제약을 제거해 의자 다리·얇은 구조도 복원한다. Table3의 평균 F-score는 NeuS .284, normal prior 추가 .724, check 포함 .736이다. 전체 metric의 개선과 정성 사례이며 모든 정확한 prior의 무손상 보장을 검증한 수치는 아니다.

우리 적용의 미확인: 현재 모델의 오류와 prior의 오류를 gate가 항상 구별하지 못한다. Metric prior가 평행 이동했지만 normal은 맞는 경우까지 이 규칙이 해결한다고 볼 근거가 없다. 한 번의 잘못된 기각이 재채택되지 않는 영향도 별도 질문이다.

## 5. ND-SDF: 보정 자유도와 원래 prior의 제약을 함께 조절

- 원문: [ND-SDF v3](https://arxiv.org/html/2408.12598v3), §3.3–3.4, §4.2/Table6/Fig.5, Appendix B.2.
- 공식 pin: `f58f29466a5f43e80dedb0cd155f57dae7569347`.

영상 예측 normal N, 현재 SDF normal n, 학습 회전 Q에 대해 의미를 정리하면 `L_N = (1-a(theta)) ell(n,N) + a(theta) ell(Qn,N)`이다. 작은 deflection에서는 원 normal을 prior에 직접 맞추고, 큰 deflection에서는 회전 보정이 불일치를 흡수한다. [models/loss.py:302–344](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/loss.py#L302)의 ell은 L1+cosine이며 각도 가중은 no_grad로 계산한다. 이 각도는 실제 prior 오차의 정답이 아니라 학습된 불일치다.

완성법은 큰 deflection 영역의 RGB 감독·sampling 및 렌더링 변환도 조절한다. 원문은 deflection만 사용한 ModelA에서 벽 주름을 관측하고, 원래/보정 prior loss를 함께 조절한 ModelB로 이를 개선한다. 이것은 **보정만 강화하면 유효 구조의 제약이 약해질 수 있고, 이를 함께 다룬 설계가 개선했다는 실제 ablation 근거**다. 추가 모듈 없는 ModelB가 완성법과 동일한 것은 아니다.

독립 기존 metric depth에 대한 직접 증거는 아니다. Appendix B.2는 normal 각도로 depth 감독까지 조절하는 근거로 동일 예측기의 공통 편향과 단안 depth의 scale 불확정성을 든다. 이 가정을 기존 LiDAR/LoD에 그대로 이식하지 않는다.

## 6. FusionNet: LiDAR와 RGB 정보를 함께 이용한 학습 기반 유용성 추정

- 원문: [Sparse and Noisy LiDAR Completion with RGB Guidance and Uncertainty, MVA 2019](https://arxiv.org/pdf/1902.05356), §3.1–3.3/Eq.1–3/Fig.2.
- 공식 pin: `wvangansbeke/Sparse-Depth-Completion`, `a01ac3c664664f648023564f66edb897202afbc6`.

Global branch는 RGB+LiDAR로 depth·guidance·confidence를 추정하고, local branch는 LiDAR+global guidance로 depth·confidence를 추정한다. 정확하고 충분한 LiDAR에는 local 정보가, 틀리거나 부족한 LiDAR·경계에는 global 정보가 더 기여하도록 학습한다. [Models/model.py:37–75](https://github.com/wvangansbeke/Sparse-Depth-Completion/blob/a01ac3c664664f648023564f66edb897202afbc6/Models/model.py#L37)은 두 softmax 혼합계수로 depth를 합성한다. 두 branch는 서로 독립적인 raw prior와 raw image가 아니다.

**Confidence 라벨 없이 학습한다는 것이 depth GT 없이 학습한다는 뜻은 아니다.** 원논문 Eq.3은 global/local/fused depth를 GT focal-MSE로 학습한다. 현재 공식 [main.py:295–301](https://github.com/wvangansbeke/Sparse-Depth-Completion/blob/a01ac3c664664f648023564f66edb897202afbc6/main.py#L295)은 최종/local/global/guidance 모두 GT regression에 넣으며 기본 MSE이다. [README:120](https://github.com/wvangansbeke/Sparse-Depth-Completion/blob/a01ac3c664664f648023564f66edb897202afbc6/README.md#L120)은 논문 이후 skip fusion 등 변경을 설명한다. 확인한 confidence는 예측 분산 자체가 아니라 상대 혼합계수다.

KITTI depth completion과 입력 LiDAR 오류 교정·branch 결합 ablation이 검증 범위다. 과거 ALS/LoD와 현재 도시 영상의 실험은 아니다. 우리 장면의 GT로 이 네트워크를 새로 학습하는 것은 현재 평가 전용 경계를 위반한다. 외부 사전학습 모델을 도입하는 후보와 원리 참고로 구분한다.

## 7. 방법 설계와 최소 비교로 연결할 사항

1. **가장 먼저 필요한 것은 정답 소스 분류기가 아니다.** 영상의 후보별 기하 설명력과 오류 허용 범위가 있는 prior 제약을 같은 최적화에 넣는 기존 원리가 출발점이 될 수 있다. 보존·수정의 동시 요구 자체는 이미 선행이 있다.
2. **무정보와 반증을 구분한다.** 영상에서 최소 비용 후보가 있다는 사실만으로 새로운 깊이를 강제하지 않는다. 후보 간 구별력·가시성·시점 간 지지를 확인하고, prior와 DA3의 일치만으로 정확성을 선언하지 않는다.
3. **남은 새 질문:** 독립 metric prior의 위치 오류·표현 한계·국소 유효 구조가 혼재할 때, 기존 robust prior + 영상 기하 비용 + 표면 일관성 제약으로 충분한가? 부족하면 어떤 감독/수정 제약이 원인인지 특정한다. ND-SDF의 normal 보정이나 adaptive weighting의 존재를 우리 신규성으로 재사용하지 않는다.
4. **최소 비교:** 기존 P1/P2/P3 GeoGS 제어를 재사용하고, 향후 동일 입력·anchor·DA3·추가 영상 정보·정합·표면 추출·계산 예산에서 (a) 기존 robust/local prior 제어, (b) 기존 영상 기하 비용과 완화 가능한 prior 제약의 결합, (c) 같은 정보에서 새 제약 원리만 변경한 후보를 비교한다. 특정 기존 요소가 필요한지 확인하기 전 모두 한꺼번에 도입하지 않는다.
5. **평가/기각:** 동일 영역의 수정 필요 부분과 원래 유효 부분을 함께 측정한다. 같은 손상 수준의 수정 개선 또는 같은 수정 수준의 손상 감소로 평가한다. 단순 낮은 learning rate나 과도한 고정으로 얻은 보존을 방법 우위로 주장하지 않는다. 기존 결합이 충분하면 새 원리의 범위를 축소한다. 정보가 없는 조건은 정확한 현재 기하를 복원했다고 주장하지 않는다.

Prior depth 가중과 구조 보호는 별도 제어다. Gaussian 중심의 보존만으로 최종 표면 보존을 보장하지 않으므로 depth 합성·불투명도·생성/삭제·추출 효과를 구분한다. 기존 계약과 결과는 소급 변경하지 않았으며, 이 문서는 실행 계약이나 확정 방법이 아니다.
