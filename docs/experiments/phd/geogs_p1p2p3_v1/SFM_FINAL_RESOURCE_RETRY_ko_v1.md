# SfM Anchor 생략: 마지막 추가 자원 복구 범위

2026-09-10 · 실행 전 추가 계약 · `scientific_verdict: null`

사용자의 실제 SfM 초기화→refinement 비교를 완료하기 위해, 현재 선택된 지역별 시도가 자원 부족으로 학습에 실패한 경우에 한해 **지역별 한 번의 새 학습**을 추가한다. 성공하거나 실행 중인 P2/P3를 교체하지 않는다. 결과 품질을 읽기 전에 고정한 정책은 `configs/phd/geogs_p1p2p3_v1/sfm_final_resource_retry_v1.json`이며 task `contracts/`에 동일 bytes로 봉인한다.

P1 v2는 11,902회 optimizer를 완료한 뒤 다음 forward에서 CUDA OOM으로 종료했다. 해당 요청14.80GiB에 비해 가용14.78GiB였고, 원 코드에서는 이전 step의 parameter gradient를 새 forward 이후에 비운다. 마지막 계측9,162,913개 Gaussian의 gradient 저장량은 약1.98GiB다. 이전 densification과 optimizer가 끝난 뒤 다음 forward 전에 이 gradient를 비우는 자원 변경을 검증한다. 새 forward는 기존 `.grad`를 입력으로 사용하지 않으며 원 backward 직전 zeroing도 남긴다. 작은 CUDA fixture에서 실제 동등성을 확인하기 전에는 실행하지 않는다.

또한 P1 8k의 원 PLY 저장은 약0.68GB의 출력에 대해 모든 행을 Python tuple로 구성한다. 이는 RAM 피크에 영향을 줄 수 있다. 같은 header·61개 float32 필드·SH 순서·음의0·전체 파일 SHA를 유지하는 chunk 저장을 CPU fixture로 검증한다. 이 조치는 표면의 표본화나 학습 Gaussian 수를 줄이는 처리가 아니다. 기존 v2 depth/Adam 저장 방식,32GiB 제한, 원 학습·손실·densification·보호·렌더·8k/15k/22k/30k 캡처 조건은 그대로 둔다.

새 attempt는 `no_anchor_sfm_gradient_memory_v3_P1/P2/P3`로 분리한다. 모두 처음 SfM부터 시작하며 중간 checkpoint resume은 사용하지 않는다. 선택한 이전 attempt의 닫힌 실패 receipt·원인·설정·입력·source·더 앞선 실패와 의도 종료를 이어서 봉인하고 계산 비용을 보존한다. resource recovery version3과 pinned storage version2를 별도로 기록한다.

이번 마지막 추가 시도까지 실패하면 더 많은 새 학습이나 결과에 맞춘 Gaussian 상한·손실·해상도 변경으로 이어가지 않는다.22k/30k 미생성은 그대로 실패/미제공으로 보고하며, 이미 고정한 동일8k 보조 진단으로 관찰 가능한 결과를 제공한다. 보조 진단의 이전 trajectory는 새 시도의8k로 치환하지 않는다. 품질이 좋은 시도를 고르는 방식도 사용하지 않는다.

이 변경은 GPU/RAM 한계를 완화할 가능성이 있는 구현 조치다. 전체 CUDA trajectory 동일성·완료 또는 Anchor의 기하적 필요성을 보장하거나 입증하지 않는다. 기존 desktop·다른 서비스·원 결과는 보존한다.
