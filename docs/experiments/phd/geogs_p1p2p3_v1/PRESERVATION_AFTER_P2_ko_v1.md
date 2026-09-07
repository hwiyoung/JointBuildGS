# P2 전체 resource 추출 이후 제한된 보존 감사

- 날짜: 2026-09-08
- 작업: `PHD-GEOGS-P1P2P3-v1`
- 결과: `PASS_P2_RESOURCE_BINDINGS_AND_CURRENT_SERVICE_IDENTITIES`
- `scientific_verdict: null`

P2의 여섯 주 비교 resource job에 완료 marker/receipt가 모두 생긴 뒤 독립적으로 검사했다. **14개 추출의 receipt–cgroup trace 연결이 일치했고, 2026-09-08 12:56:25 KST의 기존 62개 서비스 식별 정보도 62/62 일치했다.** 이 감사는 해당 시점의 메모리 기록과 서비스 식별에 한정된다.

## 메모리·완료 기록

기존 `runtime/audit_first_resource_v3_jobs.py`를 수정하지 않고 새 `preservation/audit_p2_resource_jobs_v1.py`로 범위를 확장했다. 여섯 `ALL_FOUR_RESOURCE_PHASES_VERIFIED` 완료 기록에서 auxiliary receipt의 SHA/bytes를 확인하고, 각 auxiliary가 열거한 variant receipt SHA를 확인했다. 이어 14개 memory trace의 SHA, 첫/마지막 표본과 receipt의 before/after, 모든 표본의 **32 GiB cap**, OOM-kill 증가량, 표본 memory-current 최대와 host MemAvailable 최솟값을 대조했다.

필수 7개는 모두 `PASS`, native/validated 종료 0, OOM-kill 증가 0이었다. 선택 7개는 모두 `TECHNICAL_RESOURCE_UNAVAILABLE`이며 각 native 종료 −9와 해당 cgroup OOM-kill 증가 **정확히 1**을 확인했다. 선택 실패를 기하 품질 0이나 참조 부재로 해석하지 않는다.

| 대상 | 필수 512 결과 / host 가용 메모리 표본 최저 GiB | 선택 추출 결과 / host 가용 메모리 표본 최저 GiB |
|---|---|---|
| 공통 anchor, `D005_Pnative` | PASS / 43.294 | 1024: OOM / 25.783 |
| final `D005_Pnative` | PASS / 48.337 | 2048: OOM / 24.794 |
| final `D0005_Pnative` | PASS / 48.141 | 2048: OOM / 23.031 |
| final `D0_Pnative` | PASS / 47.809 | 2048: OOM / 23.341 |
| final `D005_Prelease` | PASS / 48.007 | 2048: OOM / 23.898 |
| final `D0005_Prelease` | PASS / 48.919 | 2048: OOM / 24.057 |
| final `D0_Prelease` | PASS / 46.178 | 2048: OOM / 19.463 |

전체 표본상 host MemAvailable 최저는 `D0_Prelease/mesh_2048`의 **20,898,435,072 bytes = 19.4631843567 GiB**였다. 주기적 표본의 최저이며 연속 시간의 실제 최저라는 주장은 아니다. cgroup lifetime peak는 같은 auxiliary 컨테이너의 이전 variant까지 누적될 수 있으므로 개별 추출의 peak로 바꾸어 해석하지 않는다. 정확한 14개 행과 source/input SHA는 `resource_memory_audit.json`에 있다.

이 범위는 resource_v3의 필수 final512/shared-anchor512와 선택 final2048/shared-anchor1024이다. 기존 main final1024의 표면 payload를 다시 검사한 것이 아니다.

## 기존 서비스와 접근 범위

초기 `preservation/services_before.txt`와 같은 default-format `docker ps -a` 결과를 만들고, 수정하지 않은 `preservation/verify_service_snapshot.py`를 실행했다. 원래 62개 container의 ID·이름·기본 image descriptor·ports·running 값이 **62/62 일치**했다. 서비스 비교기의 실제 시각은 **12:56:25.323529 KST**이며 이후 집계 receipt 생성 시각으로 바꾸지 않는다.

이 일치는 무중단/무재시작 이력, HTTP/browser health, 데이터 byte 보존 또는 durable backup을 입증하지 않는다. 새 실험 컨테이너는 원래 62개 비교 분모에 포함하지 않는다. 서비스나 volume/license를 조작하거나 별도로 inspect하지 않았다. host 서비스 조회는 `docker ps` 목록에 한정했다.

감사 Docker는 CPU 1개, RAM 256 MiB, network none, GPU 없음으로 실행했다. receipt·memory trace·queue 완료 metadata만 개별 읽기 전용 마운트했다. UAS·정량 품질·Gaussian 학습 trace·모델·메시 payload·유예된 6,471개 baseline byte는 열지 않았다. 프로젝트 코드와 runtime/contracts도 바꾸지 않았다.

## 증거 경로와 집계 메타데이터 수정

외부 작업 루트의 새 디렉터리:

```text
preservation/after_p2_all_resource_jobs_v1/
```

실행 명령은 저장소 루트에서 `bash scripts/phd/geogs_p1p2p3_v1/preservation/run_p2_resource_audit_v1.sh`였다. 해당 경로가 이미 있으면 중단하므로 기존 감사를 덮어쓰지 않는다. 정확한 Docker 명령·고정 이미지 ID·Git HEAD·감사 설정·코드 사본·stdout/stderr·종료 코드와 다음 결과를 보존했다.

| 파일 | SHA256 |
|---|---|
| `resource_memory_audit.json` | `c611b289868eafd7c0d87519b5c8a87a9e2261bc8788abd72b51e97667967c49` |
| `service_receipt.json` | `a88c338161e19b596c4f20d4febc5e14ff9b7f0c2e51106d140735f5f7caad56` |
| **`audit_receipt_v2.json`** | `45164c0a032c2d85f25874a6c4dbe82657aa37733dabe7f79a5524037fd23add` |
| `closed_hash_verification_v1/receipt.json` | `34d9d851a8cf3f07e505204acdf99bc5b909a46599140a95330fa1287538a8d9` |

최초 집계 `audit_receipt.json`은 자기 `finalize_stdout.log`가 출력 완료되기 전에 해시하여 그 파일을 빈 byte로 기록했다. 실제 종료 후 stdout은 148 bytes였다. **원 메모리·서비스 검사 결과, 로그, 잘못된 v1 집계 모두 그대로 보존**했다. 별도 `audit_receipt_v2.json`은 종료된 증거만 바인딩하고 열린 finalizer stream을 명시적으로 제외하므로 최종 집계로 사용한다. v1 대비 바뀐 선언 증거가 해당 stdout뿐임을 확인했으며 학습·메모리 검사값·서비스 snapshot은 변경하지 않았다.

추가 CPU 1개/RAM 256 MiB Docker 검사에서 v2가 선언한 종료된 소스·증거 **24개 중 24개 SHA/bytes 일치**를 확인했다(`PASS_ALL_DECLARED_CLOSED_HASHES`). v2 수정과 이 검사의 명령·코드·로그·종료 코드도 같은 디렉터리에 있다. 원 inspector 및 서비스 비교기 사본은 현행 파일과 byte-identical이고 `git diff --check`를 통과했다.

원 검사·v2 집계·닫힌 증거 해시 검사는 모두 종료 코드 0이다. 이 보고는 이후 전체 실험 완료 시점의 baseline byte 감사나 실제 결과/서비스 사용 검증을 대신하지 않는다.
