# 봉인 후 보존 검사와 신규 경로 검토

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

**기존 스냅샷6,471개 파일의 바이트와 기존62개 서비스의 시점 식별정보는 일치했다.** 원 검사 전체 결과는 `exit 1 / DIFFERENCES_REQUIRING_REVIEW`로 보존한다. 유일하게 통과하지 않은 조건은 `no_unreconciled_new_outside_task_paths`이며, 초기 목록에 없던 GeoGS 작업 범위 밖 신규74개 경로가 감지됐다. 이 문서는 그 차이의 검토 기록이지 원 검사 결과를 PASS로 덮어쓴 영수증이 아니다.

## 실행과 원 증거

후보 봉인 뒤 기존 실행기로 다음 검사를 수행했다. 이 실행기는 기하 평가 summary에 의존하지 않으므로 P2 평가와 독립적으로 병행했다. 입력·모델·저장소는 읽기 전용, 출력은 새 보존 attempt였으며 실행기를 수정하지 않았다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/preservation/run_final.sh
```

외부 task는 `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`이다. 실제 증거 디렉터리는 `preservation/final_v1/attempt.jc7tpF/`이며 source 사본, 명령, Docker image, stdout, 원 exit code, 전체 파일·서비스 비교 목록을 보존한다. 아래 시각은 각 영수증 작성 시각이며 모든 개별 파일을 그 순간 동시에 검사했다는 뜻이 아니다.

| 원 증거 | 결과/시각 (KST) | SHA256 |
|---|---|---|
| `candidate_seal_gate.json` | PASS / 2026-09-08 21:01:10.736 | `e32cb73190934fb37b1f3e289c2470df030904964b484f53dce942337e97bd75` |
| `service_receipt.json` | PASS / 21:01:38.517 | `98a1aaf1086969c9f20c7fbfa27e93603a6e136feb3a338bd3312f2d20c9be2d` |
| `final_receipt.json` | DIFFERENCES_REQUIRING_REVIEW / 21:01:38.543 | `fcbaefb48d3a06401fa5c6f7e791f33b2f700d0f29064064c99249e11101e0b8` |

기존 후보 seal SHA `8fc78431dcdfc1bf803c0ac2db4a5bb2cad75c1c163ce2519b571d3710cd011d`와 연결된1,849개 파일,170,428,957,285 bytes를 전체 재해시했다. 주18개 표면78개와 보조 반복의 실패·미실행 범위는 기존 완료 계약 그대로다. 새 점수나 유리한 후보를 다시 선택하지 않았다.

## 확인된 기존 항목

- 스냅샷 파일6,471/6,471개가 SHA/bytes와 일치했다. 이전에 내용 해시를 보류한3,126개도 모두 완료했으며 잔여0개다.
- 저장소 HEAD, 기존 tracked dirty4개 경로의 상태와 binary patch, 별도 누락을 보완한 디렉터리 symlink 대상이 같았다.
- 앞서 관측한 `05_METHOD_STRUCTURE_CANDIDATE_ko_v1.md`는 크기·mtime·Git 상태가 같았다. 원 내용 SHA가 없어 이 항목은 metadata-only이며 내용 보존의 바이트 증명으로 확대하지 않는다.
- 기존 서비스62/62개의 ID·이름·image descriptor·ports·running 비교가 일치했다. 이는 특정 시점의 비교이며 전체 기간 무중단·무재시작·health·LAN/브라우저 가용성 검증이 아니다.
- 당시 기존 목록 밖 컨테이너90개도 기록됐다.3개 running,87개 not running이므로90개가 새로 실행 중인 서비스라는 뜻이 아니다. 정리·종료하지 않았다.

원 비교의 모든 파일 행은 `baseline_file_checks.jsonl`, 서비스 행은 `service_receipt.json`, 전후 Git 상태·해당 검사 조건은 `final_receipt.json`에서 기계 판독할 수 있다. 전체 workspace나 모든 외부 payload의 완전한 백업·보존 증명으로 확대하지 않는다.

## 추가74개 경로의 구분과 조치

Root와 별도 reviewer가 닫힌 final/service/gate/exit 기록으로 정확히74개의 중복 없는 경로를 확인했다. 경로 이름에 따른 구분은 다음과 같다.

| 이름상 범위 | 경로 수 |
|---|---:|
| `source_candidate_v1` | 24 |
| `source_candidate_viewer_v1` 및 관련 viewer 검사 | 14 |
| `source_judgment_research_v2` | 4 |
| `srdm_p1p2p3_v1` 및 관련 검사 | 31 |
| `thesis_topic_v1/06_METHOD_FLOW_COMPARISON_ko_v1.md` | 1 |
| 합계 | 74 |

상위 소유 디렉터리별로는 artifacts3/configs6/docs21/scripts23/src10/tests11개다. 정확한 목록은 원 `final_receipt.json`의 `unreconciled_new_paths_outside_task`에 있다. 이름에 따른 분류는 저자·실행 주체·다른 사용자 작업임을 확인한 결과가 아니다. 이 검토에서 신규 파일의 내용은 읽지 않았고, 파일·서비스의 이동·삭제·수정도 하지 않았다.

이 추가 경로들을 근거 없이 GeoGS의 산출물로 편입하거나 기존 파일의 변경으로 분류하지 않는다. **기존 항목 검증 완료와 신규74개 작성 주체 미확정**을 함께 유지한다. 검증기를 완화하거나 원 실패 exit를 바꾸지 않았으며 동일170GB를 다시 읽는 재검사를 수행하지 않는다. 이 검사 이후 생긴 별도 추가 경로나 변경까지 확인했다고 주장하지 않는다.

별도 reviewer는 위 네 개 작은 기록만 Docker CPU1·RAM256MiB의 read-only mount로 읽었다. Final에 포함된 service/gate 객체와 별도 원 파일의 SHA/bytes 연결, 서비스62행 및 유일한 false 조건을 대조했다. 새 파일의 저자나 내용을 알아내기 위한 추가 접근은 하지 않았다. 관련 이슈는 `PRESERVATION-ADDITIONS-001`이다.
