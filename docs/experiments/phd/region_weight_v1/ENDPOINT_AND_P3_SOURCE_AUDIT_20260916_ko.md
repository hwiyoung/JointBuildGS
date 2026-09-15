# P1 보호 Gaussian과 P3 원본 depth 추가 진단

- 범위: 완료된 결과의 CPU 진단. 신규 학습 없음.
- 상태: 기술 집계 PASS, 기제·원인 판정 PARTIAL, `scientific_verdict: null`.
- Payload: `prior_weight_followup_v1/PHD-P1P2P3-PRIOR0005-R1A4-v1/endpoint_audit.9M8TKcB4`.
- 설정: `configs/phd/region_weight_v1/prior_0005_diagnostic_v1.json`의 복사본 `config.json`.
- 코드: `scripts/phd/prior_weight_followup_v1/audit_protected_endpoints.py`, `audit_p3_source_depth.py`.
- 실행: 설정에 지정된 GeoGS Docker image, CPU, 입력 read-only mount. 원본 결과·학습 마스크 불변.

## P1: 보호된 primitive의 삭제와 변화

동일 Anchor8000과 prior .0005 / R1=4의 최종30000 checkpoint를 비교했다.
동결된 실행 소스에서 보호 대상은 clone/split/prune에서 제외되고, 신규 primitive는
비보호 상태로 뒤에 추가됨을 확인했다. 보호 부분집합의 순서 보존을 이용한 대응이다.
전체 비보호 primitive의 영구 ID나 생성·삭제 이력에 의한 대응은 아니다.

| 측정 | 시작 | 최종 |
|---|---:|---:|
| 전체 Gaussian 수 | 1,136,384 | 1,900,424 |
| 보호 Gaussian 수 | 236,015 | 236,015 |
| 시작 중심이 0100_D R1에 투영되는 보호 Gaussian 4,557개의 불투명도 중앙값 | 0.7764 | 0.00130 |

이 R1 집단의 이동거리 중앙값은 1.87cm, 평균 18.24cm, 95백분위 96.85cm다.
최종 불투명도가 .01 미만인 비율은 99.91%다. 해당 primitive가 모두 바닥까지
이동하거나 실제 가지치기로 삭제되었다는 해석을 지지하지 않는다.

### 해석 제한

- R1 집단은 **시작 중심 투영**으로 선택했다. 가시성·과거 지붕 표면 귀속을 확정한 집단이 아니다.
- 불투명도 감소는 확인했지만, 렌더 기여는 footprint·겹침·가림에도 좌우된다.
  잔여 지붕층의 실제 렌더 기여나 추출 표면의 제거를 이 값만으로 판정하지 않는다.
- 실행 소스에 주기적 opacity reset도 있다. 시작–최종 차이를 MVS 가중치만의
  효과로 귀속하지 않는다. 원인 분리에는 같은 집단의 다른 조건 비교가 필요하다.
- 보호 대상 전체의 85.38%도 최종 불투명도 .01 미만이다. R1만의 선택적 현상이라고 주장하지 않는다.
- 전체 Gaussian 수 증가는 순증가다. 현재 지면이 어느 primitive의 이동·생성으로
  형성됐는지, 비보호 primitive가 몇 번 생성·삭제됐는지는 이 집계로 알 수 없다.

남은 기제 진단은 과거 지붕층과 현재 지면층을 나누고, 전체 장면의 가림을 유지한
상태에서 각각의 합성 렌더 기여·잔여 표면을 측정하는 것이다. 최종 checkpoint만으로
복원할 수 없는 생성·삭제 시간 이력은 미확인으로 유지한다.

## P3: 같은 GT 투영 픽셀에서 prior와 MVS 비교

기존 검증의 UAS 원본 row ID와 대상 지붕 membership을 사용했다. 각 카메라에서
가장 가까운 정수 픽셀에 투영하고, 픽셀별로 참조 crop 안의 가장 앞선 관측점을 선택한
뒤 지붕 표본 및 두 depth의 공동 유효 표본을 남겼다. 단위는 camera-Z 절대차 cm다.
GT는 평가에만 사용했으며 학습 가중치에는 사용하지 않았다.

| 뷰 | 공동 표본 | prior 중앙값 | MVS 중앙값 | prior 50cm 이내 | MVS 50cm 이내 |
|---|---:|---:|---:|---:|---:|
| 0142_D 상공 | 78,330 | 11.8 | 13.3 | 86.1% | 65.1% |
| 0046_D 사선 | 116,680 | 42.6 | 14.0 | 51.0% | 69.4% |

**시점에 따라 두 depth의 일치도 관계가 다르다.** P3 전체에서 MVS가 항상 더 나쁘다거나,
항상 더 낫다고 해석하지 않는다. 상공뷰는 중앙값 차이가 작지만 MVS의 큰 잔차 비중이 크다.

이 진단은 잘린 UAS 관측의 근사적인 가시성만 사용한다. 참조 crop 밖 가림,
불완전한 UAS, depth 경계, 정수 픽셀 대응 때문에 큰 잔차가 생길 수 있다.
따라서 원본 표면 정확도의 확정 순위나 최종 GS 악화의 원인 분리는 아니다.
전체 평균·꼬리·signed residual은 `p3_source_depth.json`에 그대로 보존했다.
두 뷰의 표본도 서로 다르며, 이 표와 기존 GT→mesh 거리는 다른 평가량이다.

P3는 신뢰하기 어려운 관측을 강화하지 않고 기존 구조를 보존하는 정책의 진단 사례로
유지할 수 있다. 자동 가중치는 지역 전체의 단일 우열보다 표면·관측별 근거를 필요로 한다.

## 산출물

- `endpoint_audit.json`: checkpoint·동결 소스·마스크 SHA, 버전, 보호 집단 통계.
- `p3_source_depth.json`: 입력 SHA, 원본 depth와 GT의 공동 표본 집계.
- `P3_*_source_depth.npz`: GT raw row ID, 픽셀, GT camera-Z, 두 source 잔차.
- 각 실행 로그와 실행한 script/config snapshot.
