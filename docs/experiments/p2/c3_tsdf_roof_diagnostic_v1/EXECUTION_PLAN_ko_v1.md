# P2 C3 roof-aware TSDF 및 3건물 진단 계획 v1

- task_id: `P2-C3-TSDF-ROOF-DIAGNOSTIC-RECOVERY-v1`
- authority: 2026-08-04 사용자 직접 지시, 단일 Experiment Host local execution
- scientific_verdict: `null`

## 목적

기존 C3 checkpoint를 재학습하지 않고 다음 다섯 질문을 분리해 측정한다.

1. 같은 checkpoint depth와 같은 camera 집합에서 roof-only Poisson과 roof-masked TSDF의 차이
2. 전체 semantic Gaussian과 실제 mesh/Roofer 입력 roof evidence의 표시 분리
3. `4906975` C3-1 Roofer 25면과 C3-2 1면의 plane support/residual 차이
4. `4907177`의 2022 reference와 2024 영상·LiDAR·MVS 사이에서 변화, ID 정합, 가시성, 복원 부족의 분리
5. `108580336` mesh의 multi-view support, footprint coverage, component/boundary 및 observed-point 거리

## 비교 통제

- C3-1과 C3-2는 건물별로 동일한 24개 camera를 쓴다.
- camera는 current-MVS terrain에서 얻은 건물별 ground Z와 footprint의 고정 3D prism 투영면적으로 선택한다.
- Poisson과 TSDF는 동일한 roof semantic depth pixel과 동일 camera에서 출발한다.
- Poisson은 다중시점 consensus oriented point를 입력으로 사용한다.
- TSDF는 같은 roof pixel의 camera ray, depth, intrinsic, extrinsic을 직접 적분한다.
- mesh/Roofer의 정확도 metric은 재계산하지 않는다. 새 값은 post-hoc 진단값이며 official G3/G4/PASS가 아니다.

## 실행 금지

- GS training 0회
- Roofer 0회
- G2 0회
- C4/C5 access 0회
- 기존 v13 payload 수정·삭제 0회
- scientific verdict 작성 금지

## 판독 경계

TSDF가 더 연속적이거나 Roofer가 더 단순해 보여도 정확도 우세로 판정하지 않는다. LoD2는 2022 epoch context와 reference-alignment 진단에만 사용하며 current geometry의 절대 정확도 GT로 승격하지 않는다.

## Recovery v1

최초 namespace는 두 condition의 24-view Poisson/TSDF extraction을 정상 완료했으나,
후속 영상 진단 container의 non-root uid가 봉인된 semantic mask 파일을 읽지 못해 중단됐다.
이는 extraction이나 semantic inventory 누락이 아니라 파일 권한 gate다. Recovery v1은 최초
namespace를 수정·재사용하지 않고 extraction control과 모든 point/mesh hash를 검증해 새
namespace로 계승한다. 후속 read-only semantic 진단만 root container에서 수행하고 생성물은
일반적인 0755 directory/0644 file mode로 남긴다. checkpoint render extraction 추가 호출은 0회다.
