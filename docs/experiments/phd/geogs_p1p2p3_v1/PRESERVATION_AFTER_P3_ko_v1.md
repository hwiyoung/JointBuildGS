# P3 전체 보조 추출 이후 제한된 보존 감사

- 날짜: 2026-09-08
- 작업: `PHD-GEOGS-P1P2P3-v1`
- 결과: `PASS_P3_RESOURCE_BINDINGS_AND_CURRENT_SERVICE_IDENTITIES`
- `scientific_verdict: null`

주18개 resource 완료 marker를 확인한 뒤 P3 여섯 조건의 보조 추출14개를 감사했다. **14개 receipt–memory trace 연결이 일치했고, 필수7개는 PASS, 선택7개는 native 종료−9 및 cgroup OOM-kill 증가1을 확인했다. 18:57:41 KST에 조회한 기존62개 서비스 식별정보도62/62 일치했다.** 이 결과는 자원 기록과 그 시점의 서비스 식별 비교다. all21 봉인 후 별도 최종 보존 감사를 대체하지 않는다.

## 접근 시점과 입력 결박

마지막 `P3_D0_Prelease` resource marker가 없을 때는 파일 존재 여부만 확인했다. 18:57:33 KST에 마지막 marker를 발견한 뒤 실행했고, Docker의18개 marker gate는 **18:57:40.844844 KST**에 완료됐다. 실제 자원 감사는 **18:57:41.273353–18:57:41.420748 KST**였다.

이전 `preservation/after_p3_first_resource_jobs_v2/`의 검사 소스를 새 디렉터리에 복사해6조건/14변형으로 확장했다. 기존 소스와 감사는 수정하지 않았다. 모든 marker 경로에 `normpath`를 적용하고 정확한 작업 루트 내부 `queue_allocator_v2/resource_v3/claims/<지역_조건>/attempt.*/complete.json`만 허용했다. P3의 완료 영수증6개가 `ALL_FOUR_RESOURCE_PHASES_VERIFIED`인지 확인한 뒤 다음 연결을 대조했다.

1. 완료 marker의 정규화된 경로와 완료 영수증의 지역·조건·run family·계약 식별.
2. 완료 영수증 → 부모 `auxiliary_receipt.json`의 SHA256/bytes.
3. 부모 variant 목록 및 producer inventory → 각 `receipt.json`과 `memory.jsonl`의 SHA256/bytes.
4. variant 영수증 → trace SHA, 첫/마지막 표본과 before/after 기록, 모든 표본의 cap, OOM-kill 증가, memory-current 표본 최대와 host MemAvailable 표본 최저.

18개 marker + P3 완료 영수증6개 + 부모 영수증6개 + variant 영수증14개 + memory trace14개, 총58개 입력의 SHA/bytes를 감사 전후 대조했다. marker는 경로를 담은 완료 표시이며, 뒤따르는 영수증의 identity와 SHA 연결을 별도로 확인했다.

## 14개 변형의 실제 관찰

모든 trace 표본의 memory cap은 **34,359,738,368 bytes =32 GiB**였다. 필수7개는 native/validated 종료0과 OOM 증가0이다. 선택7개는 `TECHNICAL_RESOURCE_UNAVAILABLE`, native/validated 종료−9이며 각각 OOM-kill 증가가 정확히1이다.

| 대상 | 필수512: 상태 / receipt wall초 / host 표본 최저GiB | 선택: 상태 / receipt wall초 / host 표본 최저GiB |
|---|---|---|
| 공통 anchor, `D005_Pnative` | PASS /214.157198 /35.051579 |1024 OOM /195.856484 /21.987198 |
| final `D005_Pnative` | PASS /63.167731 /40.955219 |2048 OOM /57.365619 /22.010983 |
| final `D0005_Pnative` | PASS /63.599487 /39.606213 |2048 OOM /67.651259 /20.168808 |
| final `D0_Pnative` | PASS /63.444837 /40.058121 |2048 OOM /65.819818 /19.995499 |
| final `D005_Prelease` | PASS /67.457279 /40.499950 |2048 OOM /65.425448 /20.384407 |
| final `D0005_Prelease` | PASS /61.203502 /40.285847 |2048 OOM /61.439538 /20.485928 |
| final `D0_Prelease` | PASS /63.072940 /46.078514 |2048 OOM /67.236515 /26.018578 |

전체 host MemAvailable 표본 최저는 `D0_Pnative/mesh_2048`의 **21,470,003,200 bytes =19.995498657226562 GiB**다. 지역이나 조건의 품질 순위를 뜻하지 않는다. 주기적 표본 최저를 연속 시간의 실제 최저로 해석하지 않는다.

기계 판독 가능한14개 행의 `cgroup_lifetime_peak_bytes`는 같은 auxiliary 컨테이너에서 이전 변형·부모 처리까지 포함할 수 있는 누적 cgroup 기록이다. 개별 native 추출만의 peak 또는 GPU VRAM 값이 아니다. `sampled_peak_memory_current_bytes`는 해당 trace 표본의 최대이며 연속 시간 정점과 구분한다. 표의 `receipt_wall_seconds`는 원 variant 영수증의 값을 보존했다. native 실행·감시·wait 구간을 포함하고 사전 복사/대기 및 사후 검증은 포함하지 않으므로 전체 auxiliary phase driver wall과 합산하지 않는다. 세부 정의는 [자원 측정 범위](RESOURCE_MEASUREMENTS_ko_v1.md)를 따른다.

이 감사 대상은 필수 final512/shared-anchor512와 선택 final2048/shared-anchor1024다. main final1024 표면 payload를 다시 검사하지 않았다. 선택 추출의 자원 부족을 기하 품질0, 참조 부재 또는 과학적 실패 판정으로 바꾸지 않는다.

## 서비스 시각과 보존 주장의 범위

host에서 초기 snapshot과 같은 `docker ps -a --format '{{.ID}} {{.Names}} {{.Image}} {{.Status}} {{.Ports}}'` 목록만 조회했다. 실제 query 구간은 **2026-09-08 18:57:41.567493550–18:57:41.616385115 KST**, 수정하지 않은 서비스 비교기의 판정 시각은 **18:57:41.862921 KST**다. 원 UTC timestamp 파일의 나노초 문자열도 그대로 보존했다.

초기 `preservation/services_before.txt`의62개 ID·이름·default image descriptor·ports·running 값은 모두 동일했다. 새 실험 컨테이너는 원62개 비교 분모에 포함하지 않는다. 이 관찰은 무재시작 이력, HTTP/browser health, 데이터 byte 보존이나 durable backup의 증명이 아니다. 서비스·volume·license를 변경하거나 별도로 inspect하지 않았다.

자원 검사와 서비스 비교는 CPU1개, RAM256 MiB, network none, GPU 없음, 읽기 전용 root filesystem의 Docker에서 실행했다. 실제 입력은 개별 완료 metadata·auxiliary receipt·memory trace만 읽기 전용으로 연결했다. UAS·점수 또는 native metrics receipt·Gaussian 학습 trace·모델·checkpoint·메시·렌더/사진·유예된6,471개 baseline payload에는 접근하지 않았다. live controller/runtime·공식 source·조건·계약은 변경하지 않았다.

## 재현 경로와 닫힌 증거

외부 작업 루트의 새 경로:

```text
preservation/after_p3_all_resource_jobs_v1/
```

그 디렉터리에서 `bash run_audit.sh`로 실행했다. 같은 디렉터리에 `code`가 이미 있으면 중단하므로 종료된 감사를 덮어쓰지 않는다. 정확한 단계별 Docker 명령, 이미지ID, Git HEAD, config, source snapshot, stdout/stderr, 종료 코드, 입력 SHA/bytes와 결과를 보존했다. 고정 이미지는 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`다.

| 파일 | SHA256 |
|---|---|
| `audit_receipt.json` | `dea628ed83e40ea8366b63dc82de48c7aefd75459ef81db194f5944d2081be4f` |
| `resource_memory_audit.json` | `e242bc73df32da08ffbc3f1e5b7f4fc5f99eb6f4cac3d358e0023724e5e9459b` |
| `service_receipt.json` | `3370eaadaa30659d238a64dd45739d3df7c0bc66e7f8bfdeb776510c5d140c9f` |
| `closed_hash_verification_v1/receipt.json` | `7783db49ffc17c27d1ac93256526142645630a1f71133fa3999134ac63fa0520` |
| `audit_config.json` | `b93abe33bcbd0e3cd9b8d2c9d604f7bbee7024d3c2381103b2d3d670ee165088` |
| `code/audit_p3_all_resource_jobs_v1.py` | `9dc3c27c1485a4ddaf39e0ef16e86b4e5ee0103666e9a7dc11a51f7700a5135f` |
| `run_audit.sh` | `e4027c15ea40e385c246aa034fa399753c6de7bba7d2443b6afc90e888db763c` |

원 준비·자원 검사·서비스 비교·집계·닫힌 증거 검사는 모두 종료0이다. 집계는 당시 열려 있던 finalizer stdout/stderr와 나중에 기록할 overall exit를 명시적으로 해시 대상에서 제외했다. 집계 종료 후 독립 Docker 검증에서 선언된 닫힌 source/증거 **33개 중33개 SHA/bytes 일치**를 확인했다. 열린 자기 stdout을 빈 byte로 잘못 결박했던 과거 P2 오류를 반복하지 않았다.

후속 보고용 `report_readout_v1.py`는 Python3.10의 `datetime.fromisoformat`이9자리 소수초를 받지 못해 종료1이었다. 실패 소스·명령·stdout/stderr·종료 코드를 그대로 보존했다. 별도 `report_readout_v2.py`가 원 소수초 문자열을 유지한 채 KST 표시만 변환해 종료0으로 완료했다. 이 오류와 수정은 이미 통과한 자원 감사·서비스 snapshot·원 영수증·33개 해시 결과를 변경하지 않았다. 후속 보고용 파일들은 먼저 완료된 감사 집계33개 선언 범위에 포함되지 않는다.

이 문서도 사람의 과학적 판정을 대신하지 않으며 `scientific_verdict: null`을 유지한다.

