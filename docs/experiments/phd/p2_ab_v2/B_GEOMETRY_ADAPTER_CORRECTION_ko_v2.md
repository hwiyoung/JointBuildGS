# B v2 기하 합성 계약 수정

`scientific_verdict: null`. 최초 v2 결과는 `INVALID_FOR_METHOD_CONCLUSION`으로 보존한다. 단순히 그림의 point tail만 제거한 것이 아니다. 잘못된 깊이가 사용된 초기 관측/색과 기하 손실까지 다시 계산해야 하므로 원래 12개 비교 조건을 새 run에서 반복한다.

## 확인한 문제

기존 gsplat 1.4 overlay는 2D Gaussian의 plane 좌표와 화면 low-pass 중 작은 rho로 RGB opacity를 계산했다. 화면 splat만 지지되는 거의 평행한 ray에서도 무한 평면 교점 camera-Z를 그 opacity와 곱해 surface auxiliary에 넣었다. 361번 실제 `(u,v)=(264,494)`에서 저장 깊이 4,261.009m가 만들어졌다. 저장 깊이와 XYZ 역투영의 최대 차이는 0.000087m로 역투영 자체는 맞았다. 기존 backward는 화면 branch 또는 opacity clamp에서 교점 깊이의 직접 미분도 누락했다.

이 오류는 RGB 사진 비교와 geometric surface의 지원이 다르다는 점을 빠뜨린 구현 오류다. 기존 RGB 보존·finite gradient 검사만으로 올바른 표면이나 미분을 검증했다고 볼 수 없다. 별도 native source 검사는 ALS 자체에도 기하 오류가 있음을 보였으므로 모든 과거 기하 오차가 이 구현 오류에서 나왔다고도 말하지 않는다.

## 새 계약

`geometry_contract=independent_plane_hit_v1`이며 구체 구현 ID는 `PHD_P2_V2_C4_FILTERED_RGB_C8_INDEPENDENT_PLANE_GEOMETRY_v1`이다.

1. C4 RGB pass는 기존 screen low-pass appearance와 RGB alpha를 유지하고, 사용하지 않는 unsafe surface auxiliary 연산·미분을 컴파일 분기로 제거한다.
2. C8 pass는 dummy 8-channel feature를 쓰며 plane rho만으로 opacity를 계산한다. finite한 양의 camera-Z 교점(near plane 0.01m), 기존 Gaussian alpha cutoff 1/255를 만족한 primitive만 합성한다. 별도 pass이므로 geometry transmittance, last primitive, early stop이 RGB와 독립적이다.
3. 같은 geometry weight로 mass, camera-Z 가중합, world-frame 법선 가중합을 계산한다. 기대 깊이는 depth sum / geometry mass이며, mass=0은 missing이다. 저장된 0은 placeholder이지 0m 표면이 아니다.
4. geometry mass의 transmittance를 1e-4 이하로 내리는 primitive까지 적산하고 종료한다. 남은 mass가 작아도 깊이 오차가 같은 단위로 작다는 보장은 없다.
5. backward는 plane alpha 미분과 직접 교점 깊이 미분을 분리한다. alpha가 clamp되어도 직접 depth gradient는 남는다. Torch 정규화에서 분자와 분모 gradient를 모두 전달한다.

초기 관측/가림 비교, source self-visibility, coverage, depth-normal 일관성, multiview 양쪽, 표면 추출은 geometry mass를 사용한다. normal finite difference는 현재 기하가 이웃에도 존재하는 곳에 제한하고, multiview 보간 footprint도 현재 target 기하 지원을 확인한다. RGB alpha coverage는 별도로 기록한다. 추출 world/local XYZ와 법선은 같은 축이며 법선은 가중합이므로 0에 가까운 상쇄 법선은 유효 방향으로 취급하지 않는다.

중심 camera-Z 정렬과 gsplat projected tile culling은 그대로다. ray의 실제 hit-depth 정렬을 증명하지 않으며 여러 유효 면의 기대 깊이가 실제 단일 표면이라는 보장도 없다. 표현 지지·수치적 합성 검산은 현재 정확도나 prior 적격성 보장이 아니다.

## 검산과 재현

새 generator는 [b_prepare_geometry_adapter.py](../../../../scripts/phd/p2_ab_v2/b_prepare_geometry_adapter.py), 실제 CUDA 검산은 [b_adapter_audit.py](../../../../scripts/phd/p2_ab_v2/b_adapter_audit.py)다. artifact 공통 접두 경로는 `/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v2/`이다.

| 산출물 | 역할 |
|---|---|
| `PHD-P2-AB-V2-B-SURFACE-AUDIT-v1` | 최초 실제 ray 및 역투영 오류 구분 |
| `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-v2` | 새 CUDA fwd/bwd와 생성 manifest |
| `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-AUDIT-v1` | 원 RGB baseline 및 최초 22개 검산 |
| `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-AUDIT-v2` | empty/behind/zero/parallel 및 확실한 early-stop 검산 추가 |
| `PHD-P2-AB-V2-B-GEOMETRY-ADAPTER-AUDIT-v3/corrected/audit.json` | 최종 31개 검사 PASS, nonidentity camera normal 및 실제 fullframe 유효성 포함 |

실제 RGB/alpha는 합성 fixture와 361번 원래 state에서 C4 수정 전후 byte 동일하다. 두 평면의 mass·깊이와 정규화 opacity/Z gradient, 포화 opacity의 직접 Z gradient를 해석식과 비교했다. means x/z, quaternion y, tangent scale x, opacity에 대한 finite difference의 최대 절대차는 0.000164였다. 이는 검사한 매끄러운 branch/5좌표에서의 결과이며 모든 threshold/정렬 경계의 미분 보장이 아니다.

361번 문제 ray의 새 깊이는 183.898m, geometry mass는 0.999596이다. fullframe geometry 지원은 171,213px, RGB 지원은 171,862px이며 지원 깊이 범위는 [174.919,238.226]m였다. 뒤 카메라·0 opacity·정확히 평행·빈 장면은 finite missing 출력으로 검산했다. 비유한 Gaussian 입력은 관측 missing이 아니라 입력 오류라는 전제를 유지한다.

## 재실행

새 [b_run_corrected_docker.sh](../../../../scripts/phd/p2_ab_v2/b_run_corrected_docker.sh)는 실행 CUDA SHA가 adapter manifest 및 검산 SHA와 모두 같은지 확인한다. root 결과에는 adapter 계약, 두 CUDA SHA, audit 경로/SHA, source snapshot을 보존한다. 각 arm의 초기/최종 `geometry_mass_ID.npy`는 RGB `alpha_ID.npy`와 분리된다. 모든 초기/최종 평가 프레임에 finite·mass 범위·missing·깊이 범위 검사를 기록한다.

- `PHD-P2-AB-V2-B-CORRECTED-NATIVE-v1`: 같은 native ALS G0의 7개 arm + 별도 MVS G0 image_only.
- `PHD-P2-AB-V2-B-CORRECTED-REPRESENTATION-v1`: 같은 4분할 ALS G0의 fixed/proposed.
- `PHD-P2-AB-V2-B-CORRECTED-PRIOR-SHIFT-v1`: 같은 ALS Z+1m의 free/proposed.

원래 2,048-step, source, 영상, loss 가중치, solver domain 설정을 유지한다. UAS를 읽어 parameter를 고르거나 prior를 보정하지 않는다. 새 기하 유효성 정의에 따라 초기 관측 지원과 색이 바뀌는 것은 수정 효과의 일부다. 기존 수치와 새 수치는 같은 관측 분모로 직접 비교할 수 없다.
