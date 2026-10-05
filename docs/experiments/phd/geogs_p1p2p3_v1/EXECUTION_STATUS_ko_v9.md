# 주18개 봉인 완료와 실제 평가 진입

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

2026-09-08 20:07:49 KST에 주18개 전체 결과를 봉인했다. 보조 native 반복은 P1/P2 CUDA OOM 실패와 P3 미실행으로 남는다. 추가 진단·재시도 없이 주 비교의 실제 정량·정성 분석을 진행한다. 근거와 한계는 [평가 시작 조건 변경](EVALUATION_COMPLETION_AMENDMENT_ko_v2.md)에 있다.

- seal: `contracts/candidates_sealed_v1.json`
- 상태: `PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE`
- SHA256: `8fc78431dcdfc1bf803c0ac2db4a5bb2cad75c1c163ce2519b571d3710cd011d`
- 표면 후보78개, 봉인 파일1,849개, 총170,428,957,285 bytes
- 최초 봉인에서 `reference_accessed: false`
- 최초 실행: `runtime/finalization_primary18_v2/attempt.mLvO9B`

최초 native sealer는 전체 바이트·영수증·후보·필수/선택 추출 상태를 검사하고 위 JSON과 닫힌 `seal.log`를 생성한 뒤 정상 종료했다. 이후 별도 Docker의 contracts-only `FinalizationGate.candidate_seal()`로 주18개와 필수 후보 전체, 보조 상태, 파일 목록·계약 결합을 다시 확인했다.

그 다음 원 wrapper가 시작한 **두 번째 전체 재해시**만 중단했다. 대상은 `8d1ca0df9fce9d331aa0f196a9abeecb9cdc3d7e7e795691905353b41a9f21f8`(`elegant_dewdney`), 명령은 `python /control/finalization_control.py --mode decision --stage seal`이었다. `/task`는 read-only, `/control`은 해당 `attempt.mLvO9B`였음을 확인한 뒤 `docker stop --time 5 <위 ID>`로 정지했다. 이 제어 단계는 새로운 표면이나 평가 점수를 생성하지 않는 중복 바이트 검사다. 원 wrapper의 exit1은 이 명시적 중단 결과로 보존하며 전체 wrapper PASS로 보고하지 않는다. native sealer·모델·학습·기존 서비스는 중단하지 않았다. Docker CLI는 `--time` 대신 `--timeout`을 권하는 deprecation 문구를 출력했다.

20:08 KST 이후 다음 별도 launcher로 실제 평가를 시작했다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/runtime/finalize_primary18_inputs_v2.sh run
```

- 새 실행: `runtime/finalization_primary18_v2/attempt.Pty1O1`
- 새 launcher SHA: `748d4a3a84d58bc37529b6d35218fc5154d5671e52eca740c402e90872c0d226`
- gate SHA: `018dd2a038a49eac4b7d668239ce320f28806745350124f771068158567c6c5a`
- 평가 코드 SHA: `bb216504b9098576902ddfbaf13d0096775d13995eb003daece519d8f6b7b202`
- 렌더 평가 코드 SHA: `8e490ad6d83e045d0f0b0666ed3f581d2eb741151797447cc3b3a902db29e5cc`

새 runner는 완전한 원 seal을 유지하며 각 지역의 실제 소비 입력만 SHA/bytes로 검증한다. 이후 최종 보존 감사에서는 모든 봉인 파일을 다시 확인한다. 처음부터 다시 학습하지 않으며, 평가 지표·임계값·표본화·조건/사례 선택법은 변경하지 않는다. 이 문서 작성 시점에는 지역별 실제 평가 진행 중으로, 최종 표·그림·viewer QA·수동 분석·최종 보존·완료 인계는 아직 필요하다.

이후 완료 순서는 actual summary/cases 생성 → 요인 대비·제어 궤적·실제 browser QA·최종 보존 → 실제 표/그림의 수동 분석 및 인계다. 독립적인 후처리는 자원 한도 안에서 병렬 수행할 수 있다. 보조 반복의 품질 변동 미측정과 CRS/참조 피복 한계는 최종 분석에 유지한다.
