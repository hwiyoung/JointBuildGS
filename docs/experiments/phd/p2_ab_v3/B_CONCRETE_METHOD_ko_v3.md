# B v3: 선택한 표면을 유지하며 현재 영상의 외관과 세부를 갱신하는 방법

- 상태: 구체 설계 + 같은 P2의 색 전용 원인분리 실험. `scientific_verdict: null`.
- 기존 v1/v2 결과·코드·manifest를 보존한다. 이번 초기 ALS는 진단용 입력이며 A가 승인한 표면이 아니다.
- 구현 완료 범위는 §3의 잔차 가중치와 §6의 고정 기하 비교이다. §2·4·5의 면 결속·세부 갱신·증감은 설계이다.

## 1. 재사용할 요소와 연구 기여의 위치

[2DGS](https://surfsplatting.github.io/)의 평면 Gaussian, 광선–평면 교점, 깊이 왜곡·법선 일관성 손실을 표현의 출발점으로 삼는다.
2DGS는 중심·크기·방향을 최적화하므로 과거 입력 기하를 불변으로 유지하는 방법은 아니다. [원문 §4–5](https://arxiv.org/html/2403.17888v1)
[SuGaR](https://anttwo.github.io/sugar/)의 표면 정렬과 mesh-bound Gaussian은 명시적 면에 표현을 묶는 참고 요소이다. 선택적 후속 최적화에서는 mesh도 함께 움직인다.
따라서 기여 후보는 결속 자체나 잔차 가중치가 아니라 **A가 선택한 현재 사용 가능한 표면·성분 권한을 B의 변수와 실제 출력 검사까지 전달하는 방법**이다.
목표는 현재 영상 복원의 결손·오류 보완과 양호 영역의 열화 통제이다. 과거 ALS 보존 자체를 최종 목적이나 현재 정확성으로 바꾸지 않는다.

## 2. Gaussian과 최종 표면이 같은 기하를 갖도록 묶기 — 설계

A에서 선택한 source/patch/face/edge ID, 현재 사용 상태, 지지 영역, 위치·법선·경계별 허용 성분을 받는다.
입력이 점뿐이면 삼각분할을 했다는 이유로 빈 공간·다른 층 사이에 연속 면 지지를 만들지 않는다. 유효한 면 연결과 미확인 연결을 구분한다.
허용된 삼각형 집합을 `M₀=(V₀,F)`로 두고, Gaussian i의 소유 면 `fᵢ`와 면 안의 무게중심 좌표 `bᵢ`를 저장한다.

`μᵢ = Σₖ bᵢₖ V[fᵢ,k]`, `bᵢₖ ≥ 0`, `Σₖ bᵢₖ=1`.

Gaussian 법선은 현재 소유 면의 법선이며, 중심에 독립적인 면 밖 이동 변수를 두지 않는다. 접선 축은 면 안에서 정의한다.
세부 형상은 Gaussian마다 흩어진 이동이 아니라 공유 mesh 정점 또는 세분 정점의 `Vₖ = V₀ₖ + uₖ + hₖ n₀ₖ`로 표현한다.
`uₖ`는 승인된 구조 성분, `hₖ`는 승인된 국소 법선 세부이다. 둘 다 없으면 해당 기하를 고정한다. A의 높이 한계를 3D 이동 한계로 승격하지 않는다.
인접 면은 정점을 공유해 균열을 막고, 경계 정점은 고정하거나 승인된 원래 경계선의 허용 구간 안에서만 움직인다.

| 변수 | 외관 단계 | 구조·세부 단계 |
|---|---|---|
| 색/SH | 관측 품질·잔차 가중치로 갱신 | 고정하여 기하 오차와 색의 상쇄를 줄임 |
| mesh 정점·법선·경계 | 고정 | A가 허용하고 다뷰 기하 관측이 있는 성분만 갱신 |
| 면 ID·중심 결속·크기·opacity·개수 | 이번 probe에서는 모두 고정 | 별도 표현 변경 단계와 출력 지지 검사 필요 |

면 결속만으로 GS 출력 표면이 보존되지는 않는다. 아래 세 처리를 **함께 구현해야** 그 주장을 시험할 수 있다.

1. **경계 누출:** 광선–Gaussian 평면 교점의 소유 삼각형 무게중심 좌표를 계산한다. 소유 면/허용 patch 밖이면 기하와 RGB 양쪽 기여를 0으로 자른다. 화면 저역 필터도 이 소유 영역을 다시 넘어가지 않게 처리한다.
2. **여러 층 혼합:** 명시적 mesh의 가장 앞 교점과 face/layer ID를 구한다. 기하 누적은 그 층과 일치하는 교점만 사용한다. 다른 깊이 층의 기대 깊이를 실제 면으로 내보내지 않는다. 면 경계 tie와 수치 허용치는 renderer 검산으로 고정한다.
3. **opacity 결손:** mesh가 남아 있어도 앞면의 GS 기하 mass가 사라지면 렌더 표면 결손이다. 고정 광선의 앞면 지지·mass를 별도로 검사하며 뒤층이 비쳐 보인 것을 앞면 유지로 세지 않는다.

최종 기하는 `M(V)`와 그 앞면 교점으로 정의하고, GS 기하 read-out이 동일 소유 면·깊이와 일치하는지도 내보낸다.
현재 v2 renderer에는 이 face clipping/mesh 첫 교점 결속이 없다. 이번 색 전용 probe가 이를 구현했다고 해석하지 않는다.

## 3. 영상과 다른 부분은 색의 학습 기여를 올리기 — 구현

먼저 `M`을 초기 기하의 유효 지지에서 명백한 전경 가림을 제외한 고정 관측 마스크로 둔다. 가림 처리의 조건과 미확인 깊이는 v2의 기록을 그대로 보존한다.
노출이 완전히 포화된 픽셀을 위한 작은 휴리스틱만 추가한다: RGB 전 채널이 `≤1/255` 또는 `≥254/255`이면 `q=0.25M`, 나머지는 `q=M`이다.
이는 추정된 잡음 확률이나 현재성 점수가 아니다. 반사·노출·카메라 오차와 진짜 외관 변화를 판별했다고 주장하지 않는다.

`rₚ = mean_c |Îₚc − Iₚc|`, `s = max(median_{q>0}(detach(r)), 1/255)`.

`aₚ = detach(1 + β min(rₚ/s, 2))`, `wₚ = detach(qₚ aₚ / Σq a)`.

`L_app = 0.8 Σₚ wₚ rₚ + 0.2 (1 − masked_SSIM₁₁(Î,I;M))`.

`β=0`은 같은 품질 마스크의 균일 비교, `β=1`은 잔차 상대 가중치가 최대 3인 비교이다. 잔차 강조는 L1에만 적용하고 SSIM은 양쪽 모두 같은 이진 M을 쓴다.
median 바닥값은 잔차가 거의 0일 때 나눗셈을 안정화한다. `Σq=0`이면 실행에서 명시적으로 실패하며, 가짜 0 손실로 성공 처리하지 않는다.
가중치와 q는 미분 그래프에서 분리한다. L1의 영상 미분은 `wₚ sign(Îₚc−Iₚc)/3`이며, 큰 잔차가 스스로 가중치를 낮추는 미분 경로가 없다.
optimizer에는 SH0만 전달한다. 중심·법선·크기·opacity·개수에는 gradient를 만들지 않는다. 따라서 높은 RGB 잔차만으로 기하 이동 권한이 생기지 않는다.
관측이 충분한데도 같은 면 위의 색 표현이 부족하면 §5의 표현 세분화를 검토한다. 그 경우에도 먼저 외관 분해능 문제인지 검증한다.

## 4. 구조·세부 갱신의 실행 순서 — 설계, 이번에는 미실행

세부 후보는 A의 성분 권한과 현재 영상의 다뷰 깊이/대응 지지를 모두 요구한다. 단일 RGB 잔차나 동일 학습 영상의 낮은 재투영 오차만으로 새 현재 기하를 승인하지 않는다.
관측 지지에는 실제 source/view ID, 가시성·삼각측량 조건·재투영 불일치가 포함되어야 한다. 공유 MVS/카메라 오차는 별도 미확인 상태로 남긴다.
허용된 세부에 대해 색을 고정하고 다뷰 기하 일관성, 면 법선–깊이 법선 일치, 국소 세부 정규화와 사진 손실을 사용한다. 손실 가중치와 대응 잔차 척도는 후속 구현 전에 고정한다.

갱신마다 아래 순서로 검사한다.

1. 허용된 mesh 변수만 Adam 갱신한 뒤 위치 성분·법선·경계 구간에 투영한다. 모든 정점과 면의 뒤집힘·자기 교차를 검사한다.
2. 동일 topology에서 원래 정점과의 변위를 검사한다. 삼각형 내부의 같은 무게중심 대응은 정점 변위의 볼록결합이므로 정점별 동일한 변위 한계가 면 내부 대응 한계도 제한한다. 이는 가장 가까운 실제 현재 표면 오차의 보장은 아니다.
3. 최적화 전에 정한 학습 카메라의 고정 광선 집합에서 실제 mesh 교점과 GS 기하 read-out을 다시 계산한다. 원래 위치·법선·앞면 ID, 허용 층 변경, 경계 밖 기여, 지지/mass 손실을 검사한다.
4. 위반하면 **기하 제안만** `1,1/2,…,1/64`로 줄여 다시 검사한다. 모두 실패하면 기하와 해당 Adam 상태를 복구한다. 별도로 끝난 색 갱신까지 무조건 취소하지 않는다.
5. accepted step의 실제 출력 변화·허용 한계 여유·거절 사유·관측 지원량을 기록한다. latent 변수 범위 통과와 출력 표면 검사를 각각 보고한다.

광선 검사에 사용할 훈련 영역과 해상도는 사전에 고정하며 평가 영상·UAS를 단계 선택에 사용하지 않는다. 유한 광선 검사는 연속 공간 전체의 지지 보장이 아니다.
전체 보호 이미지 격자 보존을 주장하려면 그 전체 격자를 검사해야 한다. 격자 사이의 경계·면 연속성은 위의 명시적 mesh/clip 조건으로 별도 다룬다.
이 설계는 갱신량을 항상 0으로 만들어 끝내는 검사가 아니다. 허용 접공간의 기하 제안과 색 갱신을 분리하고, 실제 비영 세부 변화와 개선을 검증해야 한다.

## 5. 색 해상도와 기하 세부의 증감을 분리하기 — 설계

색 잔차가 여러 가시 뷰에서 남고 투영된 Gaussian 크기가 해당 영상 특징보다 크면 같은 소유 면 안에서 자식을 배치한다.
자식의 면 ID·source provenance를 유지하고 부모 면을 평면 상태로 세분한다. 이 단계만으로 새로운 면 밖 기하를 만들지 않는다.
자식 개수를 늘리고 크기를 줄였다고 opacity·지지가 보존되지는 않는다. 고정 광선에서 부모의 투과율·RGB를 맞추어 자식을 초기화하고 §4의 지지·경계 검사를 통과한 뒤 부모를 제거한다.
실패하면 증감을 복구한다. 이후 자식 정점의 비평면 이동은 §4의 별도 기하 권한이 있을 때만 연다. 미관측 부분의 근거 없는 생성은 이 절차에 포함되지 않는다.
SH 차수는 별도 색 전용 진단에서 3까지 확장한다(§7). 노출 보정·면 texture atlas·증감은 구현하지 않았다. SH0 한계와 기하 세부 실패를 혼동하지 않는다.

## 6. 같은 P2의 색 전용 원인분리 실험

입력은 수정 renderer의 `PHD-P2-AB-V2-B-CORRECTED-NATIVE-v1/geometry_fixed/gaussians_initial.npz`와 동일 ALS source seeds이다.
33 학습·11 외관 평가 뷰, native crop에서 v2가 명시한 최대 1536 크기와 768 학습 tile을 그대로 사용한다. 양쪽 초기 Gaussian·view/tile 순서·512 steps·Adam 일정을 맞춘다.
공통 q는 영상 clipping 휴리스틱까지 같고 **잔차 강조 β만** 다르다. 비교 이름 `uniform`은 이 공통 q 안의 균일 잔차 가중치를 뜻한다.
학습률 0.015→약0.0015, SH0를 decoded RGB [0,1] 범위로 제한한다. 중간 128회마다 같은 11뷰를 평가하지만 평가값으로 모델/단계를 선택하지 않는다.
평가는 초기 지지 전체의 픽셀 가중 MAE와 같은 고정 q의 MAE를 함께 기록한다. 품질 가중치 때문에 원래 지지 분모에서 픽셀이 사라지지 않는다.
각 arm의 실제 Gaussian 전체 NPZ, 초기/최종 RGB·depth·기하 mass·RGB alpha, 고정 target/support/q와 매 step loss·gradient·tile을 저장한다.
깊이·기하 mass·RGB alpha는 초기와 모든 평가 뷰에서 `array_equal`을 검사한다. 이는 이 실험의 기하 불변 검산이며 초기 기하가 현재 정확하다는 뜻은 아니다.

실행 경로: `/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v3/PHD-P2-AB-V3-B-APPEARANCE-v1/`.
결과와 검산은 §7에 기록한다. 이 비교로 B 전체의 성패·수렴·고품질 texture/detail 복원·A→B 성공을 판정하지 않는다.
강한 기존 GS/2DGS/SuGaR와의 비교는 해당 방법의 표현·densification·SH·학습 예산을 갖춘 별도 실험이어야 하며 이 2-arm probe로 대체하지 않는다.

## 7. 실행 결과와 재현성

두 run 모두 `COMPLETED_DIAGNOSTIC`이다. 색 표현의 별도 대조는 `PHD-P2-AB-V3-B-SH3-v1`에 보존한다.
SH3는 gsplat의 표준 SH 평가를 사용한다. 15×RGB 고차 계수를 0으로 추가해 처음 RGB가 같도록 하고 SH0 학습률의 1/20을 고차 계수에 사용한다. 두 가중치 조건에 같은 설정을 사전 고정했으며 결과에 따라 재조정하지 않았다.

| 색 표현·잔차 가중치 | 고정 지지 픽셀 가중 MAE ↓ | 고정 q 가중 MAE ↓ | 뷰 평균 MAE ↓ | 뷰 평균 SSIM ↑ |
|---|---:|---:|---:|---:|
| 같은 초기 G0 | 0.182965 | 0.181204 | 0.191453 | 0.303035 |
| SH0 uniform | 0.185543 | 0.183771 | 0.184648 | 0.345269 |
| SH0 residual_weighted | 0.185017 | 0.183260 | 0.185127 | 0.345038 |
| SH3 uniform | 0.171514 | 0.169884 | 0.171496 | 0.367766 |
| SH3 residual_weighted | 0.171059 | 0.169456 | 0.171879 | 0.366832 |

**확인한 것:** 기하를 완전히 고정해도 색 표현을 SH3로 확장한 조건에서는 초기보다 전체 픽셀 MAE와 SSIM이 모두 개선됐다. SH0에서는 SSIM과 뷰 평균 MAE가 개선되어도 전체 픽셀 MAE는 악화됐다.
잔차 강조는 각 SH 차수의 전체 픽셀 MAE를 약 0.0005 낮췄으나 뷰 평균 MAE·SSIM은 균일 조건보다 조금 나빴다. 잔차 마스크만으로 외관 문제를 해결했다거나 모든 지표에서 우세하다고 말할 수 없다.
**원인 해석의 범위:** 이 통제 비교는 색 표현 자유도가 결과에 영향을 주었다는 증거이다. SH3가 흡수한 것이 실제 물성·노출·반사·정합 오차 중 무엇인지는 분리하지 않았다. view-dependent SH 색 개선을 현재 기하·세부 정확성 개선으로 바꾸지 않는다.
128/256/384/512회의 전체 MAE는 SH0 uniform에서 0.182867/0.183769/0.184834/0.185543, SH3 uniform에서 0.177425/0.173892/0.172058/0.171514였다. 마지막 단계가 사전 종료점이며 수렴 판정이나 평가 기반 최적 단계 선택은 하지 않았다.

네 arm의 초기 기하와 512개 view/tile 순서는 동일했다. 두 run의 초기 RGB·target·support·q·depth·mass·alpha 파일 전체도 byte-identical이었다.
실제 11뷰에서 고차 0의 SH3 RGB가 SH0 RGB와 정확히 같았다. 네 arm 모두 기하 파라미터와 최종 depth/mass/alpha의 초기 대비 exact 검사를 통과했다.
매 step 기하 gradient가 없었고 SH3 고차 gradient는 모두 finite·비영이었다(최소 norm: uniform 0.004151, weighted 0.005167). 5개 기본 + 2개 SH 단위검산도 CPU Docker에서 통과했다.
전체 소요시간은 SH0 35.20초, SH3 41.01초이며 초기화·중간/최종 평가·파일 저장을 포함한다. 성능 최적화된 training-only benchmark 시간이 아니다.
실제 SH3 state는 `sh0`, `sh_rest`, `sh_degree=3`을 함께 저장한다. NPZ의 `rgb`는 SH0에서 복호화한 DC 색이며 특정 시점의 전체 SH3 렌더 색을 대신하지 않는다.
SH3 고차 계수에는 별도 norm 정규화를 추가하지 않았다. L1은 gsplat RGB를 직접 쓰고, SSIM·평가 MAE·PNG는 [0,1]로 자른 RGB를 쓴다. 이러한 표시/목적함수 차이까지 포함한 제한된 표현 진단이다.
v2 동결 B 소스 46개와 먼저 완료한 SH0 probe의 source SHA 모두 변하지 않았다. 기존 payload를 수정하지 않았다.

- [SH3 표현](../../../../src/phd/p2_ab_v3/appearance_sh.py), [별도 SH3 script](../../../../scripts/phd/p2_ab_v3/b_sh_probe.py), [별도 SH3 config](../../../../configs/phd/p2_ab_v3/b_sh_probe_v1.json), [SH 검산](../../../../tests/phd/test_p2_ab_v3_appearance_sh.py).
- SH3 실행은 아래 동일 Docker 환경에서 `python -m scripts.phd.p2_ab_v3.b_sh_probe --config configs/phd/p2_ab_v3/b_sh_probe_v1.json`이다. 각 run의 `result.json`, `source_snapshot/`, `training.jsonl`이 exact 입력/소스/수치의 기록이다.

- [가중치·gradient 분리](../../../../src/phd/p2_ab_v3/appearance.py), [실행 script](../../../../scripts/phd/p2_ab_v3/b_appearance_probe.py), [고정 config](../../../../configs/phd/p2_ab_v3/b_appearance_probe_v1.json), [단위검산](../../../../tests/phd/test_p2_ab_v3_appearance.py).
- Docker 단위검산: `python -m unittest tests.phd.test_p2_ab_v3_appearance` — 5 PASS. 실제 실행은 동일 image에서 `python -m scripts.phd.p2_ab_v3.b_appearance_probe --config configs/phd/p2_ab_v3/b_appearance_probe_v1.json`.
- image `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`, Git `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`; 새 소스는 snapshot SHA가 권위이며 Git만으로 식별하지 않는다.
- repo→`/workspace/JointBuildGS`, artifact backend→`/artifacts/JointBuildGS`는 읽기 전용. 새 결과만 `/output` RW, v2 runtime cache의 새 v3 사본만 `/root/.cache/torch_extensions` RW이다.
- `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-v2/overlay`의 CUDA forward/backward를 installed gsplat의 같은 파일에 RO mount한다. 런이 수정 결과의 exact SHA와 대조한다.
- GPU 1, network none, CPU 6, RAM 24GB; `JBGS_P2_GEOMETRY_ADAPTER=c4_c8_v1`, `JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM=1`, `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=1`, `MAX_JOBS=2`, `PYTHONDONTWRITEBYTECODE=1`.
- v2의 동결 manifest에 결속된 46개 B 소스를 전후 검증한다. 이 실험은 기존 연구 결과를 덮어쓰거나 UAS로 학습/선정하지 않는다.
