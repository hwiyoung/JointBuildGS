# allocator v2 전환 중 보존 점검

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

중간 점검 상태는 **PARTIAL**이다. 기록된 기존 파일의 삭제·크기 변경이나 검사한 소스·문서의 바이트 변경은 없고, 기존 실행 서비스 62개의 현재 ID·이름·이미지 표기·공개 포트·실행 상태가 일치한다. 참조 또는 과학 payload일 수 있는 파일 3,126개는 후보 봉인 전 접근 제한에 따라 존재와 크기만 검사했다. 전체 바이트 보존 완료나 무중단·백업 내구성을 선언하지 않는다.

| 검사 | 결과 | 범위와 한계 |
|---|---:|---|
| 기준 `workspace_before.json`의 기존 파일 | 6,471 / 6,471 존재·크기 일치 | 기준 snapshot이 기록한 파일 범위 |
| 소스·문서·설정·manifest SHA-256 | 3,345 / 3,345 일치 | 현재 작업의 추가 경로를 이유로 기존 파일을 제외하지 않음 |
| 잠재적 참조·기하·영상·표 payload | 3,126 존재·크기 일치 | 바이트 해시 보류; UAS payload를 읽지 않음 |
| HEAD | 동일 | `72f45bcf861c5fe6e0c70e28e0686a72e9424b17` |
| 기존 tracked dirty 파일 | 4개 상태·기준 바이트 동일 | 논문 주제 문서의 기존 편집을 HEAD로 되돌리지 않음 |
| 기존 실행 서비스 | 62 / 62 현재 식별 정보 일치 | 시작 시각·재시작 횟수·모든 immutable image ID가 초기 기록에 없어 중간 재시작 여부는 판정 불가 |
| allocator 경로 계약 | 13 / 13 일치 | 저장소·외부 계약 바이트, 동결 과학 설정 hash, 출력·anchor·allocator 경로 확인 |

원시 `interim_allocator_v2.json`의 `DIFFERENCES_REQUIRING_REVIEW` 상태는 보존했다. 후속 `interim_allocator_v2_reconciliation.json`에서 다음 관찰만 별도로 해석한다.

- Keycloak과 nginx의 Docker `--no-trunc` 출력은 이미지 태그 뒤 digest를 덧붙인다. 원래와 같은 기본 출력 형식으로 비교하면 정확히 같은 표기이며, 기존 ID·이름·포트·실행 상태도 일치한다. 원시 긴 표기와 차이 플래그는 삭제하거나 수정하지 않았다.
- `src/apps/experiment_dashboard/_shared/build`는 HEAD에 이미 있는 디렉터리 symlink다. 최초 snapshot의 `is_file()` 조건 때문에 빠졌으며, 현재 link target은 HEAD의 target과 일치한다. 대상 payload는 열지 않았다.
- `docs/experiments/phd/thesis_topic_v1/05_METHOD_STRUCTURE_CANDIDATE_ko_v1.md`가 기준 이후 새로운 untracked 경로로 관찰됐다. 생성 계보는 알 수 없으며 이번 작업 범위 밖이다. 내용을 읽거나 변경하지 않았고 생성 주체를 추정하지 않는다.

실행은 GPU·네트워크 없는 Docker에서 저장소와 계약을 읽기 전용으로 마운트해 수행했다. 출력만 이 작업의 `preservation/`에 추가했다. 기존 서비스 조작, 입력 수정, Git index 변경은 하지 않았다. 실행 image는 `jointbuildgs:dev`, ID `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`이며 CPU 2개·메모리 2 GiB로 제한했다.

외부 task root는 [payload resolver](../../../../artifacts/manifests/geogs_p1p2p3_v1.yaml)로 해석한다. 그 아래 보존 증거는 다음과 같다.

- `preservation/workspace_before.json`, `status_before.txt`, `services_before.txt`: 변경하지 않은 기준.
- `preservation/interim_allocator_v2.json`: 파일별 검사와 최초 service 비교 원자료.
- `preservation/interim_allocator_v2_reconciliation.json`: 원자료 hash를 연결한 표기·symlink 해석 및 경로 계약 검증.
- `preservation/services_interim_allocator_v2.jsonl`, `services_interim_allocator_v2_default_format.txt`: 서로 다른 Docker 출력 형식을 그대로 보존한 메타데이터.
- 같은 디렉터리의 `*_source.py`, `*_command.sh`, `*_image_id.txt`, `*.log`: 실제 스크립트·명령·image·실행 기록.

현재 [runtime layout](../../../../configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json)의 SHA-256은 `28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5`이고 외부 `contracts/runtime_layout_allocator_v2.json`과 같다. 새 비교 출력은 `runs_allocator_v2/`, `parity_allocator_v2/`, `queue_allocator_v2/`이다. P1의 기존 두 CUDA OOM 시도와 8,000회 anchor는 기존 `runs/P1/`에 보존한다. 경로 검증은 복구 학습의 최종 성공이나 결과 품질 검증을 뜻하지 않는다. 실패와 복구 해석은 [별도 기록](ALLOCATOR_RECOVERY_ko_v2.md)을 따른다.

후보 봉인 후에는 보류한 payload의 불투명 바이트 hash와 최종 작업 종료 시점의 파일·서비스 식별 정보를 추가 영수증으로 검사해야 한다. 이 중간 기록을 덮어쓰지 않는다.

## resource_v3 첫 두 job 이후 재확인

새 자원 경로의 P1 D005_Pnative/D0005_Pnative 보조 추출 뒤 서비스62개의 기준 식별 정보가 모두 현재와 일치했다. 증거는 `preservation/after_resource_v3_first_jobs_v1/service_receipt.json`과 현재 목록·실행 명령·검사기 사본이다. 이 역시 재시작 이력·브라우저 건강·데이터 바이트에 대한 증명은 아니다.

같은 경로의 `resource_memory_audit.json`은6개 variant의 영수증과 cgroup memory trace 해시·첫/마지막 표본·실제32GiB 상한·OOM counter를 재검증했다. 필수3개는 PASS, 선택3개는 native SIGKILL과 해당 OOM 증가가 일치했다. 주기적 메모리 표본에서 가장 낮은 host MemAvailable은22,887,583,744bytes, 약21.32GiB였다. 표본 사이의 순간 최저값을 보장하지 않으며 cgroup lifetime peak는 한 auxiliary container 안에서 누적된다. 모델·지역 품질값·UAS payload는 열지 않았다.

## 32GiB 추출 OOM 이후 서비스 재확인

2026-09-08 보조 TSDF의 두 cgroup OOM 뒤, 최초 running 서비스62개의 ID·이름·image descriptor·공개 포트·running 상태를 다시 대조하여 모두 일치함을 확인했다. 원 snapshot과 동일한 Docker 기본 표시 형식을 사용했다. 결과는 외부 task의 `preservation/after_memcg_oom_v1/receipt.json`과 원 현재 목록·검사기 사본에 있다. 이 점검은 해당 시점의 식별 상태 확인이며 서비스가 한 번도 재시작되지 않았다는 증명, 실제 브라우저 동작 또는 데이터 바이트 검증을 뜻하지 않는다.

## P2 첫 두 job 이후 재확인

P2 D005_Pnative/D0005_Pnative의6개 보조 추출 기록을 기존 검사기 그대로, GPU·네트워크 없는 CPU1·메모리256MiB Docker에서 재검증했다. 필수512 추출3개는 PASS, 선택 anchor1024/최종2048 추출3개는 각각 native exit −9와 cgroup OOM kill 증가1이 일치했다. 모든 trace의32GiB 상한, 영수증에 연결된 SHA-256 및 첫/마지막 표본이 일치했다. 주기적 표본의 host MemAvailable 최솟값은24,729,817,088bytes, 약23.03GiB였다. 이는 표본 사이의 순간 최저값 보장이 아니다.

기존 서비스62개의 현재 ID·이름·기본 image descriptor·포트·running 상태도 기준과 모두 일치했다. 증거는 `preservation/after_p2_first_resource_jobs_v1/`의 `resource_memory_audit.json`, `service_receipt.json`, 실행 명령·검사기 사본·image ID·로그·exit code이다. 지역 품질값·모델·UAS와 보류 중인 payload 바이트는 열지 않았다. 현재 식별 정보 확인을 전체 파일 보존, 무중단 또는 실제 브라우저 건강으로 확대 해석하지 않는다.
