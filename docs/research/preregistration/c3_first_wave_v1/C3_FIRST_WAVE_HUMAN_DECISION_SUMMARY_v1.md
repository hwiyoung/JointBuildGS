# C3 first-wave human decision summary v1

## 한 문장 결론

현재 C3 전략은 **“같은 937개 현재 영상/pose 장면을 한 번 학습하고, 외부 prior 없이
얻은 GS를 두 가지 고정 surface adapter로 읽어 51개 development 건물에서만 비교한다”**는
구현 목표까지 정한 상태다. 이 문서를 승인해도 학습은 시작되지 않는다.

- status: `HUMAN_DECISION_SUMMARY_DRAFT`
- execution status: `C3_EXECUTION_NOT_AUTHORIZED`
- scientific_verdict: `null`
- detailed strategy:
  `docs/research/preregistration/c3_first_wave_v1/C3_FIRST_WAVE_STRATEGY_DRAFT_v1.md`

## 무엇을 한 번 학습하는가

C3는 건물 51개를 따로 학습하는 실험이 아니다. Gate S0에서 고정한 공통 현재시점
장면 전체를 **하나의 scene model**로 학습한다.

| 항목 | 고정안 | 의미 |
|---|---|---|
| 입력 장면 | exact `962 images / 937 image-pose / 25 exclusions` | pose와 결합된 937 view만 학습에 사용 |
| 조건 | `C3_GS_image` | 외부 ALS나 LoD1 prior가 없는 image-only GS |
| 표현 | gsplat planar 2D Gaussian primitives | 프로젝트의 고정 구현 어휘와 일치 |
| 학습 단위 | 937-view full scene 1개 | 51개 건물별 모델이 아님 |
| 읽는 결과 | development 51 | 전략 점검용 결과만 사용 |
| 금지 | validation 11, held-out 10 | 입력/결과/중간 선택에 사용하지 않음 |

전체 scene model 안에는 AOI의 다른 위치가 포함될 수 있다. 그러나 development 51의
결과만 읽는다. development ID와 연결되지 않은 full-scene 출력은 별도 quarantine에
두며 성능표, tuning, 사례 선택에 사용하지 않는다.

## 어떻게 시작하는가

초기 Gaussian은 두 current-image-derived source를 결정적으로 합친다.

1. 공통 SfM sparse point **371,808개 전부**
2. 공통 dense MVS를 AOI 안에서 **0.40 m voxel**로 한 번만 샘플링한 seed

두 집합은 한 번 연결하며 random seed는 `0`이다. Dense seed는 5,000 update까지
보호하고, 최대 허용 개수는 3,000,000이다. 이를 넘으면 임의로 줄여 계속하지 않고
fail closed한다.

Gravity는 Gate S0에서 terrain MVS normal로 한 번 추정해 고정한 값을 그대로 쓴다.
UAS로 맞추거나 다시 추정하지 않는다. UAS는 학습 입력이 아니라 독립 score-only
reference다.

## 무엇을 최적화하는가

첫 wave는 의도적으로 단순하다. 현재 영상 자체의 일관성만 학습한다.

```text
L_total = 1.0 * (0.8 * L1 + 0.2 * (1 - SSIM))
        + 0.05 * L_self_normal_consistency
```

Distortion loss는 `0`이다. Depth-map, normal-map, monocular, semantic, mutual,
structure, MVC loss는 모두 `0`이고 payload도 mount하지 않는다. 따라서 C3에서
성능이 달라진다면 외부 prior나 평가 reference가 몰래 학습에 들어간 결과가 아니라,
동일한 영상 기하를 GS가 다시 최적화하고 연속 surface로 읽은 결과로 해석할 수 있다.

## 얼마나 학습하는가

| 항목 | 고정안 |
|---|---|
| update | 정확히 30,000 |
| SH degree | 최대 3, 1,000 update마다 증가 |
| densification | update 500–25,000, 매 100 update |
| opacity reset | 매 3,000 update |
| checkpoint | 5k, 10k, 20k, 30k |
| primary checkpoint | 30k |
| early stopping | 없음 |
| seed/job | 1개 |
| 상한 | 12시간, 12 GPU-hour |
| 자동 재시도 | 없음 |

중간 checkpoint는 실패 원인과 학습 안정성을 보는 audit용이다. 5k/10k/20k 결과가
좋아 보인다는 이유로 primary를 바꾸지 않는다.

## 같은 GS를 어떻게 CityGML 후보로 읽는가

30k의 **동일 checkpoint**를 두 가지 adapter가 읽는다.

- `A_DIRECT_DEPTH_FUSION`: 937개 고정 view에서 렌더한 depth를 직접 융합한다.
- `A_TSDF_MC`: 같은 depth를 TSDF에 융합하고 marching cubes로 surface를 만든다.

두 adapter는 exact 937 view list와 한 번만 생성하는 shared rendered-depth cache를
공유한다. adapter별로 GS를 다시 학습하지 않는다. 각 surface는 external roofprint
없이 동일한 고정 Roofer-style Stage 3 read-out에 전달될 예정이다.

다만 실행 전에는 두 adapter의 모든 수치 parameter, Roofer unique-operation cap,
전체 wall-clock/storage cap, project image 및 toolchain identity를 exact config와
implementation commit으로 더 묶어야 한다. 이 값이 확정되기 전에는 Experiment Host가
실행할 수 없다.

## 무엇이 결과로 남는가

- native GS audit, 5k/10k/20k/30k checkpoint와 학습 receipt
- Gaussian component lineage, support, Z-drift audit
- 30k checkpoint에서 나온 두 개의 extracted surface
- 두 adapter별 고정 Stage 3 output
- development 51의 건물별 표, group-balanced descriptive table, 고정 case sheet
- 입력·cache·surface·Stage 3 output을 잇는 manifest

G2/G3/G4와 `PASS_usable`은 최종 criterion/reference가 동결되고 해당 evaluator를
실제로 적용하기 전까지 `null/PENDING`이다. 첫 실행 결과는 어느 adapter가 다음
확인 대상으로 더 적합한지 **provisional nomination**만 할 수 있다. 자동 최종 선택이나
성공 판정은 하지 않는다.

## 지금 사람이 승인하는 것과 승인하지 않는 것

이 summary에 대한 전략 승인은 아래 네 가지 핵심을 그대로 고정한다는 뜻이다.

1. Gate S0의 exact 937-view full scene을 한 번 학습하고, 동결된 development ID
   **정확히 51개**에서만 결과를 읽는다. 건물을 추가·제외·교체하지 않는다.
2. 초기화는 SfM 371,808점과 0.40 m dense-MVS seed의 deterministic concat이며,
   random seed는 **정확히 `0` 하나**다.
3. loss는 위에 적은 photometric
   `1.0 * (0.8 L1 + 0.2 (1-SSIM))`와 self-normal consistency `0.05`만 켜고,
   distortion 및 모든 external/per-view prior loss는 `0`으로 둔다.
4. 학습은 early stopping 없이 **정확히 30,000 update**를 수행하는 고정 schedule이며,
   primary checkpoint는 30k다.

즉, 승인은 “51개 exact development 대상, seed 0, 위 loss, 고정 30k schedule”을
구현 목표로 채택하는 결정이다. 그 결정 아래에서만 다음 준비 작업을 승인한다.

- 위 C3 전략을 구현 목표로 채택한다.
- 재사용 가능한 implementation/config/tests를 만들고 검토한다.
- exact implementation commit과 비용 상한을 묶은 새 handoff DRAFT를 준비한다.

다음은 승인하지 않는다.

- C3 학습이나 adapter/Stage 3 실행
- validation 11 또는 held-out 10 접근
- C4/C5 실행
- 성능 threshold 또는 최종 adapter 선택
- Gate 통과, 성능 우위, usable 성공 수, scientific verdict
- Experiment Host writer transfer나 GPU job 시작

실행에는 별도 검토를 마친 exact implementation/config commit, 고정 project
image/toolchain, adapter 수치와 Roofer operation cap, bounded runtime/storage,
새 두-host handoff의 activation/receipt chain, 그리고 사용자의 명시적 실행 승인이
모두 필요하다.

## 사람이 확인할 핵심 선택

현재 전략의 과학적 질문은 하나다.

> 같은 current-image geometry를 GS로 재최적화했을 때, MVS를 바로 읽는 C2보다
> component association/coverage와 수직 정합이 더 안정적인가? 그리고 roof
> orientation/shape guardrail을 훼손하지 않는가?

이 질문과 위의 단일 full-scene/단일-seed/두-adapter 비교가 연구 의도에 맞는다고
확인하면, 다음 단계는 구현과 handoff DRAFT 준비다. 확인만으로 성능 실행 권한이
생기지는 않으며 `scientific_verdict`는 계속 `null`이다.
