# 관측 지지 평가를 loss와 기하 수정으로 연결하는 구현 후보

- 작성일: 2026-09-10
- task_id: `PHD-OBSERVATION-SUPPORT-LOSS-20260910`
- 상태: `VERIFIED_PRECEDENTS / IMPLEMENTATION_DESIGN_NOT_FROZEN`
- scientific_verdict: null
- 범위: 원문·공식 코드 읽기, 후보 수식과 최소 비교 설계. 새 학습·추론·렌더·재구성·방법 실험 없음. GT는 평가 전용.

## 1. 질문에 대한 직접 답변

“관측이 수정을 얼마나 지지하는지 평가 → prior·영상 감독과 수정 제약에 반영 → 기하 최적화”는 국소 loss 가중으로 구현할 수 있다. 관측 지지를 loss의 mask/weight로 전달하는 것, 영상 정합 잔차 자체를 미분해 기하를 움직이는 것, 기하 변수의 업데이트를 제한하는 것은 구분한다. 첫 구현에 셋을 모두 새로 추가할 필요는 없다.

아래 선행은 연결 방식의 근거다. 모든 방법이 독립 기존 metric prior와 영상 depth 각각의 정오를 판단하거나 동일한 복원 목적을 검증한 것은 아니다. 아래의 normal 연구는 감독 제어 원리의 근거이며 normal loss를 우선 추가하자는 제안이 아니다.

## 2. 확인한 선행의 실제 연결

### NeuRIS: 현재 기하의 영상 검사 → normal 감독 gate

- [원문 §3.2](https://arxiv.org/html/2206.13597v2#S3.SS2)는 현재 복원 depth·normal의 국소 평면으로 다중뷰 patch NCC를 계산한다. 여러 원본 후보 기하 각각을 비교하는 알고리즘은 아니다.
- 공식 pin `fab2cc4ca45847fbee7490e978d3c60c582123b1`의 기본 경로는 현재 `point_peak/normal_peak`를 사용한다. 원문의 volume-accumulated 기하와 동일한 표본이 아니다. 현재 NCC 통과, 과거 gate 통과, 현재/prior normal 차이 <30°를 함께 요구한다. `no_grad` NCC는 normal loss의 사용 여부로 전달되며 그 자체를 이 경로에서 미분하지 않는다. [exp_runner.py:295](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L295), [loss 연결](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/models/loss.py#L127).
- 원문 normal residual은 vector L1, 공개 코드 normal residual은 angular error다. 기각 상태가 누적된다. RGB와 SDF regularization은 남는다.
- Table3에서 normal 도입 후 F-score .724, check 추가 .736이며 평면과 얇은 구조의 동시 복원을 보인다. 외부 LiDAR의 위치 보존을 입증한 결과는 아니다. 현재 기하의 오류를 prior 오류로 오인할 수 있다는 것은 우리 적용의 경쟁 가설이다.

### PGSR: 일관성 평가 → 국소 가중·기각 → 미분 가능한 기하/영상 잔차

- [원문](https://arxiv.org/html/2406.06521v2), 공식 pin `de24f1a38b350387e8d8fe381b2cd70c1ae946e7`.
- 현재 reference plane depth를 3D로 올려 neighbor에 투영하고, 그 위치의 neighbor rendered depth를 읽어 reference로 돌아온 픽셀 오차 e를 계산한다. 공개 기본 경로는 유효 투영 및 e<1px에서 `w=exp(-e).detach()`를 사용한다. [train.py:221–242](https://github.com/zju3dv/PGSR/blob/de24f1a38b350387e8d8fe381b2cd70c1ae946e7/train.py#L221).
- 실제 기하 항은 선택 픽셀에서 `mean(w*e)`다. 현재 reference의 normal·plane distance로 실제 영상 patch를 warp하고 NCC 잔차도 최소화한다. Reference patch 읽기는 no_grad지만 homography와 neighbor sampling에는 gradient가 남아 기하를 갱신한다. [train.py:270–330](https://github.com/zju3dv/PGSR/blob/de24f1a38b350387e8d8fe381b2cd70c1ae946e7/train.py#L270).
- 공개 `lncc`는 `1-corr²` 형태와 cost<.9 gate를 사용한다. 원문의 1-NCC 표기와 구분한다. 공개 patch 기본 크기는7×7, 논문은11×11이다. [loss_utils.py:106–141](https://github.com/zju3dv/PGSR/blob/de24f1a38b350387e8d8fe381b2cd70c1ae946e7/utils/loss_utils.py#L106), [기본 설정](https://github.com/zju3dv/PGSR/blob/de24f1a38b350387e8d8fe381b2cd70c1ae946e7/arguments/__init__.py#L98).
- `detach`는 가중의 미분을 막을 뿐, 깊이·warp 잔차의 기하 미분을 막지 않는다. 기각이 영구 누적되지는 않는다. 현재 GS의 왕복 일관성은 독립적인 기하 정확성 인증이 아니며, 외부 prior 보존·배제의 직접 검증도 아니다.

### AGS-Mesh: 서로 다른 기하 cue 검사 → 해당 감독만 제한

- [원문](https://arxiv.org/html/2411.19271v2#S4), 공식 pin `93fda851a20cf0bd5fce642c46da0c83c637165e`.
- DNC는 sensor-depth에서 구한 normal과 pretrained normal의 각도를 비교해 sensor-depth L1을 제외한다. 전처리 mask는 고정이다. ANR는 현재 rendered-depth normal과 pretrained normal의 각도를 비교해 외부 normal L1을 매번 제한한다. 재포함이 가능한 경로이며 RGB와 다른 기하 항은 남는다. [DNC](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/depth_normal_consistency.py#L89), [trainer](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py#L118).
- 원문 Appendix A의 DNC/ANR 문턱은10°지만 공개 기본 DNC는20°, ANR는 .1rad(약5.73°)다. Depth mask 적용 기본 시점7k, ANR15k와 초기 normal 경계 제외도 구분한다.
- 방향 일치만으로 절대 위치 편차를 직접 판정하지 않는다. 이를 prior depth와 영상 depth의 두 독립 가중으로 바꾸는 것은 adaptation이다.

### CL-Splats: 변화 근거 → 수정할 Gaussian 집합 → 변수 갱신 제한

- [원문 §3](https://arxiv.org/html/2506.21117v2)는 기존 GS 렌더와 현재 영상의 DINOv2 특징 차이를2D mask로 만들고 다중뷰 투표로3D 수정 집합을 구성한다. 바깥은 고정하며 해당 집합을 RGB loss로 최적화한다. 원논문은2D loss mask만으로 충분하지 않은 ablation과 얇은 변화 영역 누락 실패를 제시한다.
- 공개 pin `587fffc207f9c7cbb348f35e6d1d223d007eab69`은 저자가 원논문과 차이가 있을 수 있다고 명시한 재구현이다. 비활성 parameter gradient와 Adam `exp_avg/exp_avg_sq`를0으로 만들고 densification 관련 gradient·mask 계보도 제어한다. [gradient와 Adam state](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/clsplats/representation/cl_gaussians.py#L362), [재구현 disclaimer](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/README.md#L335).
- Depth-Anything V2 lifting 및 gsplat/full-image loss+gradient mask를 원논문의 exact local kernel과 동일시하지 않는다. 모든 pruning 경로의 무조건 보존을 감사한 것도 아니다. 기존 색 있는 GS의 변화 갱신은 무색 이종 prior의 정오 판정과 입력 가정이 다르다.

## 3. 우리 첫 구현 후보의 입력과 관측 지지

입력은 기존 기하 P, 현재 영상과 카메라, 영상 기반 depth V(DA3 또는 ACMP 비교), 현재 학습 기하 G_t다. P와 V는 같은 단위·ray·영상 해상도로 준비한다. G_t는 동일 렌더 정의의 현재 기하 가설이다. 첫 비교에서 별도 외부 normal 감독은 추가하지 않는다.

**무색 prior의 RGB 렌더를 사진과 직접 비교하는 것이 아니다.** 가설 H가 정한 표면으로 reference 영상의 patch를 다른 현재 영상에 대응시키고, 두 실제 사진 patch의 일치도를 계산한다. Patch warp는 국소 평면 또는 patch 내부 depth를 이용할 수 있으며 두 구현은 비교 전에 고정해야 한다.

\[
C_{H,k}(p)=1-\operatorname{NCC}\big(I_v[\mathcal P_p],W_{v\leftarrow k}(I_k;H)[\mathcal P_p]\big),\qquad H\in\{P,V,G_t\}.
\]

이는 **우리 후보의 signed NCC 비용 정의**이며 PGSR 공개 코드의 squared-correlation 식과 같지 않다. P/V/G_t에 같은 비용 정의·patch·시점 목록을 사용한다. 영상 밖·가림 불명·낮은 texture·부족한 시차는 낮은 비용과 별개로 판정 불가 상태로 다룬다. 무텍스처 patch의 NCC를 좋은 기하 근거로 해석하지 않는다.

Prior를 여러 시점에서 렌더한 depth끼리 왕복 일치한다는 사실은 동일 모델의 자기일관성이다. **현재 영상이 그 prior를 지지하는 근거를 대신하지 않는다.** 후보들 사이의 단순 depth 차이도 어느 쪽이 틀렸는지 판별하지 않는다.

## 4. 점수에서 국소 loss 가중으로: 실제 계산 가능한 비교 규칙

아래는 선행의 검사·mask 원리를 두 depth와 현재 기하에 옮긴 **최소 비교용 구성**이다. 새 알고리즘의 신규성이나 실제 효과가 확인된 식은 아니다.

사전 선택한 neighbor 목록 N_p에 대해 `v_{h,s,k}`는 동일 비교에서 평가가 가능한 관측을 뜻한다. 각 가설별로 유리한 시점만 골라 평균하지 않는다. 절대 비용 문턱 tau_C와 차이 여유 delta는 같은 비용 척도에서 사용한다.

\[
r_{h\succ s}(p)=\frac{1}{|N_p|}\sum_{k\in N_p}
v_{h,s,k}(p)\,\mathbf1[C_{h,k}<\tau_C]\,
\mathbf1[C_{s,k}-C_{h,k}>\delta],
\qquad r_s(p)=\max_{h\in\{P,V,G_t\}\setminus\{s\}}r_{h\succ s}(p).
\]

r_s가 크다는 것은 다른 **같은 후보 하나가 여러 시점에서** s보다 분명히 낮고 수용 가능한 영상 비용을 보였다는 뜻이다. 시점마다 다른 최선 후보를 먼저 고르면 서로 양립하지 않는 지지를 합칠 수 있으므로 후보별 집계 뒤 max를 취한다. 판정 가능한 뷰가 없거나 N_p가 비면 r_s=0으로 둔다. 이 비율은 정답 확률이 아니다. 시점의 비독립성과 반복 무늬 오류는 남는다.

영상 target의 절대 영상 지지를 `q_V=mean_k(v_{V,k} * 1[C_{V,k}<tau_C])`로 두고, 유효 depth mask m_P/m_V를 곱하면 다음 비교식이 된다.

\[
w_P=m_P(1-r_P),\qquad w_V=m_V q_V(1-r_V),
\]

\[
L_{\mathrm{depth}}=\frac{1}{|\Omega|}\sum_{p\in\Omega}
\left[\lambda_P w_P\rho(\hat D_t-D_P)+\lambda_Vw_V\rho(\hat D_t-D_V)\right].
\]

Omega는 비교에서 고정한 기본 픽셀 영역이다. 가중 합으로 다시 정규화하면 전체 가중 감소의 의미가 달라지므로 정규화도 명시한다. 모든 weight가0인 경우는 depth 항0이며 RGB·원래 활성 regularizer는 남는다.

| 관측 근거 | 가중의 작용 |
|---|---|
| P보다 V 또는 현재 G_t가 명확히 나음 | r_P 증가 → 잘못된 prior 요구를 완화 |
| V보다 P 또는 현재 G_t가 명확히 나음 | r_V 증가 → 부적절한 영상 target 요구를 완화 |
| 두 target이 비슷하게 영상을 설명하고 V의 지지가 충분 | 두 감독을 함께 사용 |
| 영상이 깊이를 평가할 근거가 부족 | q_V와 r_P가 작음 → 영상 depth 요구를 줄이고 prior의 기존 제약을 유지 |

마지막 행은 prior 정답 판정이 아니라 보수적 정책이다. Prior가 없는 곳에서 q_V도0이면 이 depth 규칙이 기하를 완성하지 못한다. 이 규칙은 특히 유효 prior 손상을 줄이는 비교이며, 영상 예측기의 학습된 사전 지식을 약한 관측 영역에서 과도하게 배제하는지 평가해야 한다.

**낮은 비용과 깊이 구별력은 다르다.** P/V의 깊이가 다른데 두 영상 비용이 비슷하게 낮으면 위 식에서 q_V는 높고 r_P/r_V는 모두 작을 수 있다. 이때 두 depth의 절충으로 유효 prior가 이동할 수 있다. 따라서 이 최소식이 모든 영상 모호성을 처리한다고 주장하지 않는다. 목표 depth 주변의 다른 깊이 후보 비용 또는 서로 다른 P/V의 비용 차이를 이용해 **구별되지 않는 변경 요구를 추가로 약화하는 규칙**은 다음 비교 후보이며, 단순 NCC 수용 가중과 효과를 분리해야 한다. 후보 범위가 좁으면 구별력을 과대평가하므로 정답이 두 target 밖에 있는 조건도 필요하다.

**학습 중 갱신의 뜻:** P/V와 고정 카메라·사진만 비교하면 가중은 정적이다. 단순히 같은 검사를 매번 다시 호출해도 적응 제어가 되지 않는다. 위 후보는 변화하는 G_t를 포함하므로 r_P/r_V가 바뀔 수 있다. Visibility와 검사 간격 K의 정의도 사전 고정한다. 현재 G_t를 좋은 판단 기준으로 과신하면 잘못된 기하에 유리한 가중이 유지될 위험이 있으므로 P/V만의 정적 검사와 비교해야 한다.

## 5. loss가 Gaussian에 전달되는 위치

각 검사 시점의 w_P/w_V는 gradient에서 분리하고, 정해진 K step 동안 또는 다음 검사까지 상수로 사용한다. 렌더 깊이 D_hat은 분리하지 않는다. 개념적인 구현은 다음과 같다.

```text
if support_check_due:
    no_grad:
        evaluate P, V, and current G using current-image patch agreement
        wP, wV = support_to_weights(costs, visibility, texture, camera_support)
render current Gaussian depth Dhat
loss = existing_active_losses + mean(lambdaP*wP*rho(Dhat-DP)
                                  + lambdaV*wV*rho(Dhat-DV))
backward(loss)
apply the separately specified primitive protection and optimizer update
```

고정된 가중 아래에서 렌더 깊이의 gradient는 다음 형태로 Gaussian 위치 등의 변수에 전달된다.

\[
\nabla_\theta L_{\mathrm{depth}}=\frac1{|\Omega|}\sum_p
\left[\lambda_Pw_P\rho'(\hat D_t-D_P)+\lambda_Vw_V\rho'(\hat D_t-D_V)\right]\nabla_\theta\hat D_t.
\]

즉 어떤 target의 힘을 줄였는지가 실제 최적화 요구로 반영된다. Weight를 자유롭게 학습해 loss만0으로 줄이는 경로를 추가한 것은 아니다. 다만 가중 미분을 끊는 것만으로 다음 검사에서의 잘못된 자기확증을 막지는 않는다. Gaussian 위치 외에도 opacity·scale 등이 depth를 바꿀 수 있으며, Adam에서는 gradient 배율이 실제 변위의 동일 배율을 보장하지 않는다.

## 6. 별도 수정 제약은 언제 필요한가

Loss 가중은 **어떤 감독의 요구를 반영하는가**를 제어한다. CL-Splats 같은 변수 제어는 **어떤 Gaussian 속성을 실제로 바꿀 수 있는가**를 제어한다. w_V=0이어도 RGB·다른 기하 항·opacity·생성/삭제가 남으므로 전체 표면의 무변화를 보장하지 않는다.

첫 비교에서는 GeoGS의 native 보호를 독립적으로 고정한다. 좋은 수정 근거와 target이 있는데도 수정이 막히는 경우에 한해 보호 변경을 별도 비교한다. 실제 고정은 gradient만0으로 하는 것과 optimizer momentum까지 제어하는 것을 구분해야 한다. 변수별 변위 상한을 도입한다면 step별 상한인지 초기 상태로부터의 누적 상한인지도 구분한다. 생성/삭제와 최종 표면 보호는 또 다른 경로다.

## 7. 두 target이 함께 틀릴 때와 최소 비교

P/V와 현재 G_t가 모두 틀리면 위 가중 규칙은 올바른 새 깊이를 제공하지 않는다. 원영상에 추가 정보가 있다면 ACMP 등으로 target을 개선하는 비교, 또는 PGSR형 미분 가능한 다중뷰 영상 loss를 현재 기하에 적용하는 비교가 필요하다. 두 depth 항의 재가중만으로 새 target이 생겼다고 주장하지 않는다. RGB 등 다른 항이 올바른 해로 이끌 가능성까지 부정하는 것은 아니다.

우선 비교는 (1) 더 적합한 depth + 기존 제어, (2) 같은 depth + P/V 정적 국소 검사, (3) 같은 정보에서 현재 G_t를 포함한 갱신 검사다. 각 비교에서 실제 감독 강도와 판정 영역의 변화를 함께 기록한다. 원영상 직접 기하 loss 또는 primitive 보호 변경은 해당 원인이 남는 경우 별도로 추가한다. 조건을 모두 한꺼번에 조합하지 않는다.

문턱·patch·K·가시성·시차·texture 검사 수치는 아직 고정하지 않았으며 GT로 선택하지 않는다. 평가에서 필요한 수정과 유효 구조 손상을 같은 영역에서 함께 보고, 정적 기존 제어보다 유효 감독을 더 많이 기각하거나 초기 오류를 고착시키면 동적 제어 가설을 기각한다. 기존 원리 도입과 새로운 추정 규칙의 효과를 구분한다. 기존 문서·실행 결과·서비스는 변경하지 않았다.
