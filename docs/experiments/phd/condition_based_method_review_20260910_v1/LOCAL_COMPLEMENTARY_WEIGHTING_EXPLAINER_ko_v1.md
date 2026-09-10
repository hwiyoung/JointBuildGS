# 픽셀별 상보 가중과 포화 선형 함수의 해석

- 작성일: 2026-09-10
- task_id: `PHD-LOCAL-COMPLEMENTARY-WEIGHT-EXPLAINER-20260910`
- 상태: `DESIGN_DISCUSSION / COMPLEMENTARY_BASELINE_CANDIDATE`
- scientific_verdict: null
- 새 학습·추론·재구성·방법 실험 없음. 함수 설명용 그래프와 브라우저 표시 확인만 수행. GT는 평가 전용.

## 현재 논의의 첫 비교 후보

사용자는 prior–영상 depth 차이를 가중 입력으로 사용하는 데 동의했으며, prior에서 시작하는 refinement에서 상보 가중을 첫 후보로 검토하기를 선호한다. 이 질문을 검증하기 위해 별도의 영상 가중 b를 먼저 추정할 필요는 없다. 앞선 독립 a,b 제안은 가능한 확장이며, 상보 제어보다 우수하다고 확인되지 않았다.

## 전역 lambda와 국소 a의 역할

두 depth가 모두 유효한 픽셀 집합 Omega에서 다음과 같다.

\[
L_D=\frac{1}{|\Omega|}\sum_{p\in\Omega}
\left[\lambda_P(1-a_p)\rho(\hat D_p-D_{P,p})
+\lambda_V a_p\rho(\hat D_p-D_{V,p})\right],
\qquad a_p=g(|D_{P,p}-D_{V,p}|).
\]

lambda_P, lambda_V는 모든 픽셀에 공통인 기준 강도이며, a_p는 픽셀마다 다른 배율이다. 최종 계수 맵은 `w_P(p)=lambda_P*(1-a_p)`, `w_V(p)=lambda_V*a_p`다. 픽셀별 loss에 곱한 뒤 평균내야 한다. 먼저 전체 loss를 평균내고 평균 a를 곱하면 일반적으로 같은 결과가 아니다.

기존 depth 잔차도 픽셀별로 계산되지만, 그것만으로 픽셀마다 감독의 타당성을 판단해 다르게 사용하는 제어가 생기는 것은 아니다. 잔차는 현재 복원과 target의 불일치이고, a_p는 해당 위치에서 두 감독의 상대적 강도를 정하는 별도 규칙이다. 특히 L1은 잔차가 큰 만큼 gradient 크기가 계속 커지는 loss도 아니다.

상보 제어는 기존 depth에 가까운 출발점에서, 작은 입력 차이에는 prior 제약을 유지하고 큰 차이에는 영상 depth의 상대적 비중을 늘리려는 후보다. 큰 차이가 영상의 정확성을 보증한다는 뜻은 아니며, 이 가정의 충분성은 보존·수정의 동시 평가에서 확인한다.

독립 b를 도입하려면 영상 depth의 유효성·관측 지지 등에 대한 추가 추정 규칙을 정해야 한다. 같은 불일치 하나에서 b만 새로 만든다고 독립적인 정확성 정보가 생기는 것은 아니다. 현재는 `b=a`로 두고 별도 b 설계를 보류한다.

## 함수 그래프

\[
g(\Delta)=\begin{cases}
0,&\Delta\le\tau_0,\\
(\Delta-\tau_0)/(\tau_1-\tau_0),&\tau_0<\Delta<\tau_1,\\
1,&\Delta\ge\tau_1,
\end{cases}\qquad 0\le\tau_0<\tau_1.
\]

tau0는 0인 수평 구간이 끝나는 지점, tau1은 증가 직선이 1에 도달하는 지점이다. 둘 사이의 기울기는 `1/(tau1-tau0)`이므로 전환 폭이 넓을수록 완만하다. 상보 계수 `1-g`는 1에서 시작하여 같은 구간에서 직선으로 감소하고 0에 포화한다.

그래프는 설명용으로 tau0=0.5m, tau1=2m를 사용한다. 실험 문턱·권장 수치·실측 결과가 아니다. 국소 배율만 표시하며 lambda를 곱한 최종 loss 계수나 Gaussian 이동 비율을 표시하지 않는다.

## 놓치지 않을 조건

- lambda_P와 lambda_V가 다르면 a=0.5에서도 두 최종 계수는 같지 않다. 전체 depth 계수 `lambda_P*(1-a)+lambda_V*a`도 a에 따라 달라질 수 있다. 상보적인 것은 국소 배율이다.
- D_P=D_V이고 a=0이면 영상 depth 항은 0이지만 동일 깊이를 prior 항이 계속 감독한다. RGB 감독을 끈다는 뜻은 아니다.
- 상보식은 양쪽 target이 유효한 범위에 적용한다. prior 결손에는 영상 감독만, 영상 depth 결손에는 prior 감독만 쓰는 별도 유효성 처리가 필요하다. 결손은 a=0 같은 불신 판정으로 대체하지 않는다.
- a는 픽셀별 loss의 계수이며 3D 구조 고정 명령은 아니다. 여러 시점·픽셀과 다른 loss, primitive 갱신·생성·삭제 제약의 영향이 남는다. 구조 보호는 별도 제어로 유지한다.

## 설명용 그래프 확인의 운영 기록

대화 전용 시각화 경로에만 HTML·확인 스크립트·표시 확인 파일을 작성했다. 새 연구 데이터나 reconstruction 결과는 생성하지 않았다. Docker의 기존 `jointbuildgs:dev` 이미지로 시각화 미리보기를 만들고, 기존 `jointbuildgs:geogs-viewer-browser-v2` 이미지의 Chromium으로 표시·상호작용을 확인한다. 서비스·GPU·기존 payload에는 접근하지 않는다.

도구 확인 과정에서 dev 이미지에 Playwright가 없고 browser 이미지에는 Python/Playwright가 없음을 확인했다. browser 이미지의 Node와 Chromium을 이용하는 방식으로 전환했다. 이번에 생성한 미리보기의 재생성에서 덮어쓰기 방지 오류가 발생하여, 같은 작업 소유 미리보기에만 `--force`를 적용했다. 이들은 설명용 시각화 도구 확인 사항이며 방법 실험의 실패나 과학적 판정이 아니다.

표시 확인 결과: 736px·360px와 밝은·어두운 테마의 네 조합에서 표본 가중값, hover 표시, 두 곡선, 라벨 겹침·잘림, 가로 넘침, JavaScript 실행을 확인하여 PASS. 736px 밝은 테마와 360px 어두운 테마의 스크린샷도 직접 확인했다. 이는 브라우저 표시의 기술적 확인이며 `scientific_verdict: null`을 유지한다.
