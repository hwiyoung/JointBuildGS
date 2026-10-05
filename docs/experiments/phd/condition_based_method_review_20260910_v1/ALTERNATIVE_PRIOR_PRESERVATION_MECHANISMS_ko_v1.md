# Prior 보존·배제의 추가 선행과 우리 설계의 우선 후보

- 작성일: 2026-09-10
- task_id: `PHD-PRIOR-PRESERVATION-ALTERNATIVES-20260910`
- 상태: `LITERATURE_REVIEW / DESIGN_CANDIDATE_NOT_FROZEN`
- scientific_verdict: null
- 범위: 문헌·공식 구현 확인, 수학적 해석과 최소 비교 계획. 새 학습·추론·렌더·재구성·방법 실험 없음. GT는 평가 전용.
- 기존 헌장·DEC-P1-025·실행 계보는 보존한다. 이 문서는 탐색 설계이며 실행 계약이 아니다.

## 1. 질문에 대한 판단

감독 항의 유지·기각, prior 이탈 벌점의 상한, 감독 보정변수 이외에도 검토할 설계 축이 있다. (1) 깊이와 불확실성을 함께 누적하는 추정, (2) 단일 깊이가 아닌 여러 가능한 깊이의 감독, (3) 절대 위치와 상대 형상을 구분하는 제약, (4) 어떤 감독이 어떤 변수를 움직일 수 있는지 정하는 최적화가 해당한다.

이는 서로 배타적인 알고리즘 분류가 아니다. Bayesian update는 적응 가중으로, 다중 후보 loss는 선택으로, ARAP는 보정변수와 관계 제약으로도 해석된다. 새 범주를 추가한 것만으로 방법 신규성이 생기지 않는다. 아래 방법 중 일부는 보존·배제를 직접 다루고, 일부는 보호 대상을 설계하는 구성요소다. 모두가 독립적인 과거 metric prior의 정오를 현재 영상으로 판별한 것은 아니다.

## 2. REMODE: 깊이 상태와 측정 불확실성을 함께 갱신

- 원문: [Pizzoli et al., ICRA 2014](https://rpg.ifi.uzh.ch/docs/ICRA14_Pizzoli.pdf), Eq.2–8, §III-B–C.
- 공식 코드: `uzh-rpg/rpg_open_remode`, pin `960e1fc11d3ef6d5ab58fb95ba2a4130c0bd16b8`.
- 입력/출력: 보정된 카메라의 단안 영상 시퀀스에서 깊이·불확실성 복원. Native prior는 이전 영상 관측의 posterior이며 외부 ALS/LoD가 아니다.

현재 영상에서 삼각측량한 깊이 z를 Gaussian inlier와 uniform outlier의 혼합으로 모델링한다.

\[
p(z\mid d,\rho)=\rho\mathcal N(z;d,\tau^2)+(1-\rho)\mathcal U(z;d_{\min},d_{\max}),\qquad
q(d,\rho)=\mathcal N(d;\mu,\sigma^2)\mathrm{Beta}(\rho;a,b).
\]

공식 [seed_update.cu:81–110](https://github.com/uzh-rpg/rpg_open_remode/blob/960e1fc11d3ef6d5ab58fb95ba2a4130c0bd16b8/src/seed_update.cu#L81)을 정리하면, inlier 책임도 c와 gain K에 대해 다음 평균 갱신을 얻는다.

\[
\mu'=\mu+cK(z-\mu),\qquad K=\frac{\sigma^2}{\sigma^2+\tau^2}.
\]

기존 추정의 분산이 작으면 이동량이 작고, 새 관측의 분산이 작고 inlier 설명력이 높으면 새 관측 쪽으로 이동한다. 분산과 Beta 상태도 갱신한다. 따라서 무엇을 신뢰할지 고정된 전역 가중 하나에 맡기지 않는다. 원문은 후단의 불확실성에 따른 정규화도 포함하므로 전체를 측정 배제 하나로 요약하지 않는다.

**우리 적용의 제한:** 잘못된 기존 기하를 과도하게 작은 분산으로 초기화하면 올바른 새 관측도 무시할 수 있다. 이는 식에서 도출한 경쟁 원인 가설이며 원논문에서 관측한 ALS 갱신 실패가 아니다. 공식 [코드:53](https://github.com/uzh-rpg/rpg_open_remode/blob/960e1fc11d3ef6d5ab58fb95ba2a4130c0bd16b8/src/seed_update.cu#L53)은 수렴·발산 seed 갱신을 중단한다. 시간 변화나 체계적인 기존 모델 오류를 다루려면 상태 가정을 바꿔야 한다. 별도 confidence 정답이나 장면 GT 학습은 이 posterior update에 필요하지 않다. 원문과 공개 smoothing 코드 차이가 있어 여기서 검증한 구현 주장은 posterior update에 한정한다.

## 3. SCADE: 감독을 하나의 깊이로 확정하지 않음

- 원문: [SCADE, CVPR 2023](https://arxiv.org/html/2303.13582v1), §4.2.3, Table3, §6.
- 공식 코드: `mikacuy/scade`, pin `23139b164461169e32121234696df88580c3d644`.
- 입력/출력: 소수 영상과 학습된 다중 후보 monocular depth prior로 NeRF·새 시점 영상을 복원. 외부 metric prior 보존의 직접 검증은 아니다.

NeRF의 ray termination 표본 x_i와 prior의 여러 깊이 후보 y_j에 대한 논문 식은 다음과 같다.

\[
L_{\mathrm{SC}}=\sum_i\min_j |x_i-y_j|^2.
\]

각 예측 표본이 prior 후보 중 하나에 가깝도록 하며, **모든 prior 후보를 실제 표면으로 복원하도록 요구하지 않는다.** 여러 영상이 공유하는 3D 표현에서 함께 설명되는 모드를 찾는다. 단일 평균 깊이로 감독을 축약하지 않는 것이 핵심이다. 공식 [loss:93–126](https://github.com/mikacuy/scade/blob/23139b164461169e32121234696df88580c3d644/model/run_nerf_helpers.py#L93)은 기본 `is_joint=False`에서 prior 후보 축을 최소화하지만, scalar `torch.norm`을 사용하므로 제곱이 아닌 절댓값 잔차다. 논문과 구현을 구분한다.

Table3은 같은 prior의 단일 평균보다 다중 후보의 새 시점 영상 품질이 개선되는 비교를 제공한다. 정확한 기존 기하 보존과 오류 수정의 동시 성능을 직접 측정한 표는 아니다. 원문 §6은 prior 품질과 domain gap에 따른 악화를 한계로 남긴다. 올바른 후보가 없으면 잘못된 모드로 유도하는 영향이 남으며, 이를 자동 차단하지 않는다. RGB와 유한 prior 벌점을 함께 사용하므로 전체 알고리즘이 후보 밖의 표면을 복원할 수 없다는 뜻은 아니다. 단순히 prior depth와 DA3 depth의 잔차 중 작은 것을 택하면 현재 기하에 가까운 오답에 머물 수 있다.

참고로 [DS-NeRF](https://arxiv.org/html/2107.02791v3)는 Gaussian depth prior와 ray termination 분포 사이의 KL을 사용한다. 단일 평균만 감독한다고 설명하면 틀린다. 다만 틀린 prior 중심을 자동 기각하는 방법은 아니다. 공식 [loss](https://github.com/dunbar12138/DSNeRF/blob/cacad3c86086f5749970d277437e55ba243037e9/loss.py#L54)는 Gaussian kernel과 `-log(weights)`를 결합한다. 기본 [학습 호출](https://github.com/dunbar12138/DSNeRF/blob/cacad3c86086f5749970d277437e55ba243037e9/run_nerf.py#L462)은 `err`를 전달하지 않으므로 논문의 개별 재투영 오차 모델과 동일시하지 않는다.

## 4. ARAP: 절대 위치와 상대 형상을 분리

- 원문: [Sorkine–Alexa 2007](https://igl.ethz.ch/projects/ARAP/arap_web.pdf).
- [저자 프로젝트](https://igl.ethz.ch/projects/ARAP/)가 연결한 [CGAL 구현 설명](https://doc.cgal.org/4.5/Surface_modeling/index.html)을 확인했다.
- 분류: 표면 편집의 구성요소. 영상에 의한 prior 신뢰도 판정이나 자동 도시 복원 전체 방법이 아니다.

기존 점 p_i, 수정 점 x_i, 국소 회전 R_i에 대해 다음 상대 변위를 제약한다.

\[
R_{\mathrm{ARAP}}=\sum_{i,j}w_{ij}\left\|(x_i-x_j)-R_i(p_i-p_j)\right\|^2.
\]

모든 점을 기존 절대 위치에 고정하지 않으면서 이웃 형상을 유지한다. 예를 들어 지붕 전체의 높이는 수정하면서 기울기와 이웃 형상을 유지할 수 있다. 무엇을 보존하는지가 absolute depth loss와 다르다. R_i라는 보정변수가 있어 기존 분류와 중첩된다.

**우리 적용의 제한:** 국소 회전으로 설명되지 않는 골·이웃 형상이 잘못되었다면 그 오류를 유지·전파할 수 있다. 국소 회전을 허용하므로 세계좌표에서의 절대 기울기까지 고정하는 제약은 아니다. 사용자 control/ROI가 이동을 정하는 원래 편집 문제와, 영상에서 수정 근거를 찾아야 하는 우리 문제를 구분한다. 따라서 depth prior의 가중과 별도로 관계 보존을 비교할 근거는 있지만, ARAP를 지금 필수 모듈로 정할 근거는 없다.

## 5. EnerGS: 감독을 전달하는 변수와 공간 정보를 설계

- 원문: [EnerGS, 2026](https://arxiv.org/html/2604.26238v1), §3.3–4.
- 공식 pin: `ucla-mobility/EnerGS`, `a222ed59b05a56eecf7b7199e02eb80bcb288775`.

Gaussian 중심은 geometric energy로 갱신하고 photometric gradient의 xyz optimizer 전달을 차단한다. appearance·covariance·densification은 영상의 영향을 받는다. [학습 코드:704](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/train_energs.py#L704), [force gate:214](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/energs/gaussian_model.py#L214).

Photo gradient 통계와 view coverage가 geometric force의 크기에 반영되는 feedback도 있으므로 영상이 위치에 전혀 관여하지 않는다고 설명하면 틀린다. Occupied/free/unknown 공간을 구분하는 것도 해당 방법의 중요한 입력 해석이다. **Trusted field 자체가 틀렸을 때 현재 영상으로 이를 바로잡는 검증은 확인하지 못했다.** 따라서 변수 전달 설계의 참고이며, 우리 보존·수정 전체 요구를 이미 충족했다는 사례로 쓰지 않는다.

## 6. 우리 경우의 우선 후보: 영상이 허용하는 깊이 안에서 prior 변경 최소화

우선순위 제안은 **영상의 깊이 증거를 반드시 한 target으로 축약할 필요가 있는지**부터 비교하는 것이다. Bayesian 상태·새 예측 네트워크·ARAP·새 최적화기를 모두 도입하는 계획은 아니다. 아래 식은 여러 깊이를 유지하는 문헌에서 얻은 시사점을 우리 문제에 적용한 설계 예시이며 SCADE 원래 식도, 신규성이 확인된 식도 아니다.

한 ray의 후보 깊이 d에 대한 현재 영상 대응 비용 C_p(d)를 평가한다. 카메라·가시성·대응 잡음에 관한 검사가 유효한 경우, 영상이 충분히 구별하지 못하는 후보들을 다음 집합으로 표현할 수 있다.

\[
\mathcal A_p=\{d\in\mathcal D_p:C_p(d)\le\min_{d'\in\mathcal D_p}C_p(d')+\epsilon_p\}.
\]

\(\mathcal D_p\)는 카메라와 비-GT 장면 범위로 정하는 깊이 탐색 범위이며 prior와 DA3 사이로 제한하지 않는다. 넓은 범위의 탐색 뒤 근방을 세분하는 구현도 가능하나 현재 확정하지 않는다. \(\epsilon_p\)는 영상 비용의 허용 차이이며 정답 depth 오차 허용치가 아니다. 값·정규화·가시성·시점 선택 규칙은 아직 미정이다. 여러 저비용 구간이 떨어져 있으면 그 사이의 고비용 깊이까지 허용하도록 합치지 않는다.

**단일 ray에서 보존·수정의 작용을 설명하는 제한된 식:**

\[
d^*=\arg\min_{d\in\mathcal A_p}(d-D_P)^2.
\]

동일한 뜻을 하나의 목적함수로 쓰면 \(L_p(d)=(d-D_P)^2+\iota_{\mathcal A_p}(d)\)이고, \(\iota\)는 집합 안에서 0, 밖에서 무한대인 constraint indicator다. 이는 제약 최적화의 기존 표현이다. 유한한 squared-distance 벌점으로 완화하면 기존 depth와 영상 허용 범위 사이의 절충점에 머물 수 있으므로 정확한 제약과 동일한 보장을 주장하지 않는다.

| 영상 증거와 prior의 관계 | 이 제한된 식의 작용 | 해석의 경계 |
|---|---|---|
| D_P가 좁은 A_p 안에 있음 | d*=D_P | 영상과 prior가 함께 설명되는 경우의 보존 |
| 영상이 깊이를 구별하지 못해 A_p가 넓고 D_P를 포함 | d*=D_P | 근거 없는 이동을 억제하는 정책이며 prior의 정확성 확인은 아님 |
| 신뢰할 수 있는 영상 증거가 D_P를 A_p 밖에 둠 | A_p에서 D_P에 가장 가까운 깊이로 이동 | prior가 요구하던 깊이를 채택하지 않으면서 필요한 이동만 허용 |
| A_p 자체가 틀림 | 정확한 prior를 훼손하거나 틀린 prior를 유지할 수 있음 | 비용 최소값·선명한 모드·시점 일치만으로 진실성이 보장되지 않음 |

**이 식에서 배제는 prior loss를 삭제하는 것과 같지 않다.** 현재 영상이 배제한 prior 깊이를 최종 선택하지 못하게 하는 의미다. 동시에 prior에서 벗어날 필요가 없는 경우에는 prior가 해를 결정한다. 이는 prior가 정답이라는 분류를 먼저 요구하지 않는다.

하지만 세 가지가 아직 핵심 연구 과제다.

1. **A_p 추정의 타당성:** 모든 후보의 비용이 높은 outlier 관측에서도 최소값은 생긴다. 단순 상대 비용 threshold만으로 채택하지 않는다. 가림·정합·반복 무늬·잡음·시점 간 지지와 후보 구별력을 구분해야 한다. 시점 일부로 만든 후보를 다른 현재 입력 시점으로 확인하는 비교는 가능하지만 GT를 confidence 학습이나 threshold 선택에 사용하지 않는다. 동일 오류가 모든 시점에 공통이면 이 검사도 실패할 수 있다.
2. **과소 수정:** prior에 가장 가까운 허용 경계가 영상 최적점보다 실제로 덜 정확할 수 있다. 보존만 증가하고 필요한 수정·세부가 줄면 개선이 아니다. 과도하게 넓은 A_p로 사실상 prior를 고정하는 결과도 포함한다.
3. **전체 표현으로 전달:** 위 식은 prior가 존재하는 ray의 설명용 문제다. 공통 3D 기하가 모든 ray 제약을 동시에 만족할 수 있는지, RGB·다른 감독·불투명도·생성/삭제·추출이 표면을 바꾸는지까지 정해야 한다. Prior 결손에는 변경 최소화 anchor가 없으므로 영상·표면 생성의 별도 경로가 필요하다. 무조건적인 DA3 point-depth loss를 그대로 더하면 A_p 안에서도 잘못된 target이 기하를 이동시킬 수 있다. DA3는 확정 감독이 아니며, 유지한다면 동일한 증거 모델에서 역할을 명시해야 한다.

## 7. 관계 보존의 도입 시점과 최소 비교

기존 높이는 틀리지만 이웃 형상은 유효한 조건이 중요하고 depth 감독 제어만으로 손상을 통제하지 못하면, 별도로 \(L_{\mathrm{image\ geometry}}+\lambda_P R_{\mathrm{absolute}}+\lambda_R R_{\mathrm{relation}}\)를 비교한다. Absolute prior의 완화가 관계 제약의 동시 약화를 뜻하지 않게 한다. 반대로 관계 자체가 틀린 조건에서 수정이 막히는지도 반드시 포함한다. 이는 기존 요소 도입 후보이며 그 합 자체는 새 기여가 아니다.

계획의 첫 비교는 다음과 같다. 이번에 실행하지 않는다.

| 질문 | 최소 비교 | 기각·축소 조건 |
|---|---|---|
| 같은 영상 정보가 있을 때 감독 표현을 바꾸는 효과가 있는가? | 같은 C_p·후보 범위·초기 기하에서 충분히 조정한 robust prior + 연속 영상 비용과 A_p + 변경 최소화 비교 | 기존 연속 비용과 robust loss가 같은 수정·손상 수준을 달성하면 새 규칙 필요성 축소 |
| 보존이 단지 적게 움직인 결과인가? | 같은 손상 수준에서의 수정/세부 개선 또는 같은 수정 수준에서의 손상 감소를 비교 | 관측이 충분한 곳의 수정·완전성을 희생한 보존이면 우위 기각 |
| 절대 depth와 관계 보존을 분리해야 하는가? | 같은 영상 감독에서 absolute 제약만 / 기존 관계 제약 추가 | 잘못된 기울기·골을 유지하거나 유효 세부를 평활화하면 해당 관계 제약 축소 |
| 새로운 증거가 필요한가, 기존 정보 활용의 차이인가? | 같은 현재 영상·정합·가시성·추출·예산을 공유 | 추가 시점·추가 계산·다른 추출이 이득을 설명하면 원리 효과와 분리 |

기존 P1/P2/P3 실행은 기존 제어의 성공·잔여를 확인하는 개발 근거로 재사용한다. 새 C_p를 쓰는 비교의 효과까지 기존 실행으로 대체해 추론하지 않는다. Prior depth 가중과 GeoGS primitive 보호는 독립 제어로 유지한다. 정확도·완전성·현재성·관측 가능 세부·외관·계산량은 분리하고, 같은 영역에서 수정 필요 부분과 원래 유효 부분을 함께 평가한다.

학위 기여 후보는 집합이나 제약식을 썼다는 사실이 아니라 **어떤 영상 증거로 수정 가능한 범위를 추정했으며, 기존 충분한 제어보다 왜 필요한 수정과 유효 구조 손상을 더 잘 구별했는가**다. 현재는 그 가설과 비교를 구체화한 상태이며 방법 신규성·실제 개선은 미확인이다.
