# C4 Existing-ALS bounded technical-development preflight Return

- decision: `DEC-P1-017`
- artifact: `artifact://JointBuildGS/phase-payloads/p2/c4_existing_als_v1/P2-C4-EXISTING-ALS-BOUNDED-TECHDEV-v1`
- preflight: `210-PASSED_NONZERO_GRADIENT_AND_22000MIB_GPU_GATE`
- scientific_verdict: `null`

C4 config는 봉인 C3-2 config의 `out_dir`을 제외한 모든 기존 key를 exact 값으로
비교했다. seed 0, neutral initialization, 30,000 iteration, 937 current RGB,
image-derived semantic/depth 및 나머지 optimizer/densification 설정은 같다. 추가된
학습 입력은 Existing ALS depth, normal, confidence뿐이다. C5 경로는 열지 않았다.

4개 2022 ALS raw tile의 exact SHA-256을 확인하고 +45.7 m datum 변환 후 C3 scene
범위에서 0.75 m voxel derivative를 만들었다. confidence는 registration, density,
planarity, visibility, current-consistency의 곱이다. current MVS depth와 충돌하면
`exp(-|residual|/2m)`으로 ALS 쪽 confidence만 낮춘다. 937/937 view가 nonempty이며
총 support pixel 수는 19,277,173이다.

alignment gate에서 matched point는 103,453개, XY median/p95는 0.195/0.405 m,
signed Z median은 0.135 m로 gate를 통과했다. robust ALS depth와 sign-invariant ALS
normal은 10,000 support pixel에서 각각 nonzero gradient를 보였다. 직전 GPU free
memory는 24,872,615,936 bytes로 22,000 MiB gate를 통과했다.

첫 gradient check는 normal prior norm에 boolean mask를 적용하는 차원 indexing
버그로 실패했고 `100-c4-preflight-failed.json`을 보존했다. 수정을 단위 테스트로
확인한 뒤 이미 생성된 937 prior의 exact inventory/hash와 alignment를 다시 검사해
recovery preflight를 닫았다. training은 이 Return 시점까지 시작하지 않았다.
