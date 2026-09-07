# P3 첫 조건 완료 시점의 실행 인계

2026-09-08 14:25 KST 시점 기록 · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

**진행 중이며 최종 결과 분석이나 완료 보고가 아니다.** 주 조건13/18개의 필수 산출물이 완료됐다. P1·P2는 여섯 조건 전부, P3는 `D005_Pnative`다. P3 `D0005_Pnative`는27,600회였고, `D0_Pnative`의 학습 container를 시작했다. 세 추가 native 반복과 후보 봉인·UAS 평가·실제 지역 비교 화면 검증은 아직이다. 지역 UAS와 품질 점수는 분석·설정 선택에 열어 사용하지 않았다.

## 실제 완료한 P3 원설정

같은 봉인 입력·공식 실행 source·allocator_v2에서 처음부터30,000회까지 실행했다. 최종 기록은 Gaussian4,799,188개, 보호 대상226,262개다. 이는 전체 학습 context의 수이며 표면 정확도·완전성 결과가 아니다. 단계 영수증의 상태는 모두 `PASS`, native/validated exit0이다.

| 단계 | 기록된 driver wall (초) | 확인된 산출물 |
|---|---:|---|
| train | 6,053.172711 | 완전 상태 checkpoint와 최종 native PLY |
| render | 335.855926 | 실제 평가 사진 렌더, 최종1024 raw/post 표면 |
| metrics | 76.506416 | 공식 지표 원자료 파일 생성과 형식 검증 |
| resource_v3 auxiliary | 560.115901 | 아래 네 시도의 영수증·해시·메모리 기록 |

기본 세 단계 원 영수증은 외부 task의 `runs_allocator_v2/P3/D005_Pnative/`, 보조 단계는 `extraction_resource_v3/primary/P3/D005_Pnative/auxiliary_receipt.json`이다. 단계 wall의 시작/끝과 Docker 전체 실행 시간은 다르며, 봉인 입력 전체 SHA 재검증 등은 기본 단계 clock 전에 수행된다. 순수 최적화·지표 계산 시간이나 동일 학습량 비교로 바꾸지 않는다. [시간 정의](EVALUATION_REVIEW_ko_v1.md)를 따른다.

| 보조 추출 | 실제 시도 시간 (초) | 결과 |
|---|---:|---|
| 공통 anchor512 | 214.157198 | 필수 raw/post PASS, OOM kill 증가0 |
| 공통 anchor1024 | 195.856484 | 선택 `TECHNICAL_RESOURCE_UNAVAILABLE`, native−9·OOM kill 증가1 |
| 최종512 | 63.167731 | 필수 raw/post PASS, OOM kill 증가0 |
| 최종2048 | 57.365619 | 선택 `TECHNICAL_RESOURCE_UNAVAILABLE`, native−9·OOM kill 증가1 |

모두 같은 사전 고정32GiB cgroup 한계의 개별 실제 시도다. 선택 실패를 성공·참조 부재·품질0점으로 바꾸지 않는다. 각 원 영수증은 해당 보조 경로의 `auxiliary/{anchor_512,anchor,mesh_512,mesh_2048}/receipt.json`에 있다. 부모 wall과 하위 시도 시간을 중복 합산하지 않는다.

## 계속 실행되는 단계와 보존

`runtime/resource_v3_continuation/attempt.bPR61e/`의 상위 작업(session53747)이 주18개 → 추가 반복3개 → 정확한 후보 봉인 → 지역 기하/렌더 평가 → summary/사례 그림을 순서대로 수행한다. 동작 중인 controller/launcher/학습 source는 수정하지 않는다. 현재 실행은 다음으로 확인한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/runtime/monitor_progress.sh
```

공식 원본·실행 adapter·과학 설정·세 실행 계약·입력·공통 anchor 계보를 유지한다. P3 anchor의 완전 상태 SHA는 `3b0de04d99435e36d05ffca49951976352bd663192cce14e59f2bddb58bdf567`이다. 정확한 최초 복원과 이후 CUDA 궤적 차이는 [상태 검증](STATE_VALIDATION_ko_v1.md)에 구분돼 있다. 모든 조건에 prior 초기화와 anchor 영향이 남는다.

[P2 완료 후 보존 감사](PRESERVATION_AFTER_P2_ko_v1.md)의 닫힌 증거24건과 당시 서비스62개 식별 정보는 확인했다. 최초 감사의 자기 stdout 해시 오류는 원본을 보존하고 정본v2/독립 검증으로 수정했으며 [PRESERVATION-001](ISSUES_ko_v1.md)에 기록했다. 6471개 기존 파일의 최종 바이트 검사는 all21 봉인 뒤 실행한다. 기존 Wu–Vallet 결과·서비스·관련 없는 사용자 작업과 Git HEAD는 유지하며 커밋하지 않았다.

## 자동 실행 이후에도 남는 필수 작업

자동 summary/cases 완료 문구로 사용자 요청이 끝나지 않는다. 아래 네 명령과 실제 그림·화면을 읽는 지역별 해석, 최종 분석/인계를 모두 수행해야 한다. 현재 네 명령은 실행 전이다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_control_trajectories.sh
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_factor_contrasts.sh
bash scripts/phd/geogs_p1p2p3_v1/viewer/browser_qa.sh full_results_display_v1 \
  'http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_v2.json&qa_mode=full'
bash scripts/phd/geogs_p1p2p3_v1/preservation/run_final.sh
```

control과 보존 검사는 all21 봉인을, factor는 봉인과 summary를, 실제 브라우저 QA는 manifest/사례 그림을 필요로 한다. 문서·소스의 독립 연결 검토에서는 현재 실행 경로의 확실한 누락을 발견하지 못했다. 과거 `evaluation/RUNTIME_LAYOUT.md`의 단독 예시에 빠졌던 repeat/resource 인자는 문서에서 보완했으며 실제 finalizer는 이미 세 인자를 전달한다. 이 검토는 실제 지역 결과·UAS를 사용한 검증이 아니다.

최종 보고에는 세 지역의 양방향 기하·밀도/임계값 민감도·실제 독립 평가 사진·raw/post·같은512 anchor/최종·추가 native 반복·자원을 함께 읽어야 한다. 동일 단면·참조 거리 지도·실제 사진과 비교 화면에서 개선·유지·악화·판단 불가를 근거와 함께 남긴다. 원문에서 이미 보인 오류/결손 prior 대응을 인정하고, 제약 완화의 관찰 효과를 반복 재판단의 필요성이나 우리의 우위로 확대하지 않는다. 최종 `RESULTS`와 `HANDOFF`, 실제 경로·사용법·표시 확인·기계 판독 원자료가 모두 필요하다.

외부 task는 [resolver](../../../../artifacts/manifests/geogs_p1p2p3_v1.yaml)를 따른다. 현재 viewer는 `127.0.0.1:8902` 한정이며 LAN 접근이나 내구성 있는 백업을 확인한 것은 아니다.

## 2026-09-08 14:52 KST 후속 확인

P3 `D0005_Pnative`의 필수 산출물도 완료돼 주14/18개다.8,000→30,000회 학습의 최종 Gaussian4,858,722개·보호226,262개를 기록했고, train/render/metrics driver wall은 각각6,531.659944/330.151593/40.315145초다. 모두 native/validated exit0·PASS이다. 기본 원 영수증은 `runs_allocator_v2/P3/D0005_Pnative/`에 있다.

새 resource_v3 최종512는63.599487초·PASS·OOM 증가0, 선택 최종2048은67.651259초·native−9·OOM 증가1이며32GiB 한계의 확인된 자원 미가용이다. 부모 auxiliary wall153.436127초와 개별 비용은 중복 합산하지 않는다. 원 기록은 `extraction_resource_v3/primary/P3/D0005_Pnative/`에 보존한다. 현재 `D0_Pnative`는16,500회였고, 같은 anchor에서 `D005_Prelease`를 시작했다. 이후 네 조건의 종료와 세 추가 반복·최종 분석 작업은 계속 필요하다.

## 2026-09-08 14:58 KST 앞선 두 P3 조건 보존 감사

`preservation/after_p3_first_resource_jobs_v2/audit_receipt.json`에서 완료 기록 → 부모 보조 영수증 →6개 개별 영수증·메모리 trace의 SHA/크기와 표본 시작/끝·32GiB 제한·OOM 증가량·peak/min을 검증했다. 필수3건 PASS/OOM0, 선택3건 native−9/OOM 증가1이다. 주기적 host MemAvailable의 최소 표본은21,656,092,672바이트(20.168808GiB)이며 `D0005_Pnative` 최종2048 시도에서 기록됐다. 순간 전체 최저값이나 무중단을 증명하는 값은 아니다.

실제 서비스 목록 조회는14:58:16.397882286–16.451537778 KST이며, 기존62개의 현재 식별 정보가 모두 기준과 일치했다. 닫힌 감사 증거34/34의 해시·크기도 독립 검증했다. 정본 영수증 SHA256은 `033719984f8d547467441d7422fe4724860a9483efe3c5eaa5722796bce6068f`, `closed_hash_verification_v1/receipt.json`의 SHA256은 `a2d53d6a9c2a633d04e42453dfcbe4cd4113c962c1ca71d3bf4acf31d110f6fc`이다. root도 두 영수증과 원 자원/서비스 영수증의 해시를 다시 확인했다.

검사는 개별 metadata/메모리 trace만 읽기 전용으로 연결한 CPU1·메모리256MiB·네트워크/GPU 없는 Docker에서 수행했다. UAS·품질 점수·모델·메시·렌더·Gaussian trace·보류한6471개 payload 바이트는 읽지 않았다. 최초 `after_p3_first_resource_jobs_v1/`은 동등한 경로의 비정규 표기를 거부한 준비 단계 실패이며 실제 자원/서비스 조회 전 상태로 보존했다. v2에서 경로 정규화 후 예상한 정확한 task 내부 파일만 허용하여 해결했다. 상세 실패는 [PRESERVATION-002](ISSUES_ko_v1.md)에 기록한다. 최종 전체 보존 감사와 실제 지역 분석은 여전히 필요하다.

## 2026-09-08 16:24 KST 후속 확인

P3 `D0_Pnative`도 필수 산출물을 완료해 주15/18개다.8,000→30,000회 학습에서 최종 Gaussian5,332,800개·보호226,262개를 기록했다. train/render/metrics driver wall은 각각6,380.397346/325.487676/40.393155초이며 모두 native/validated exit0·PASS다. 기본 원 영수증은 `runs_allocator_v2/P3/D0_Pnative/`에 있다.

resource_v3 최종512는63.444837초 PASS/OOM0, 선택 최종2048은65.819818초 뒤32GiB cgroup의 native−9/OOM 증가1이다. 부모 auxiliary wall152.963464초와 하위 비용은 중복 합산하지 않는다. 원 기록은 `extraction_resource_v3/primary/P3/D0_Pnative/`에 보존한다. 이제 P3의 보호 유지 세 조건이 모두 필수 산출물을 완료했으며 `D005_Prelease`와 `D0005_Prelease`가 진행 중이다. 마지막 `D0_Prelease`, 세 추가 반복과 모든 실제 지역 분석은 남아 있다.

아직 실행 전인 summary의 자원 보고 메타데이터에서 같은 RSS 열의 서로 다른 측정 범위와 부정확한 `child-phase wall time` 설명을 보완했다. `resource_measurement_scope`·정의JSON과 summary receipt 경로를 추가했으며 원 숫자·행·계산·과학 조건·지표·사례 선택은 유지했다. [자원 측정 정의](RESOURCE_MEASUREMENTS_ko_v1.md)의 Docker9/9 PASS와 전후 source 차이·영수증 해시는 root도 확인했다. 변경 source SHA는 `ef536619c08d1a6092e749ea5ac89e4de607d407fbb3315a438a0ee63b52c2f1`이다. 실제 summary 실행을 뜻하지 않으며 live controller/학습/추출 source는 변경하지 않았다.

## 2026-09-08 17:00 KST 후속 확인

P3 `D005_Prelease`도 필수 산출물을 완료해 주16/18개다.8,000→30,000회 학습에서 최종 Gaussian5,739,772개·보호0개를 기록했다. train/render/metrics driver wall은 각각6,880.495949/345.769923/40.283875초이며 모두 native/validated exit0·PASS다. 기본 원 영수증은 `runs_allocator_v2/P3/D005_Prelease/`에 있다.

resource_v3 최종512는67.457279초 PASS/OOM0, 선택 최종2048은65.425448초 뒤32GiB cgroup의 native−9/OOM 증가1이다. 부모 auxiliary wall158.389066초와 개별 시도 비용은 중복 합산하지 않는다. 원 기록은 `extraction_resource_v3/primary/P3/D005_Prelease/`에 보존한다. 현재 `D0005_Prelease`는19,000회, 마지막 주 조건인 `D0_Prelease`는8,900회였다. 두 조건과 세 추가 반복·봉인·실제 정량/정성 분석은 계속 필요하다. 새로운 품질 판정이나 설정 선택은 하지 않았다.

## 2026-09-08 18:09 KST 후속 확인

P3 `D0005_Prelease`까지 필수 산출물을 완료해 주17/18개다.8,000→30,000회 학습의 최종 Gaussian은4,447,762개·보호0개다. train/render/metrics driver wall은 각각5,761.304654/319.857308/40.328572초이며 모두 native/validated exit0·PASS다. 기본 원 영수증은 `runs_allocator_v2/P3/D0005_Prelease/`에 있다.

resource_v3 최종512는61.203502초 PASS/OOM0, 선택 최종2048은61.439538초 뒤32GiB cgroup의 native−9/OOM 증가1이다. 부모 auxiliary wall143.500909초와 하위 비용은 중복 합산하지 않는다. 원 기록은 `extraction_resource_v3/primary/P3/D0005_Prelease/`에 보존한다. 마지막 주 조건인 `D0_Prelease`는23,900회까지 확인했다. 주18개 이후 세 native 반복과 all21 봉인·실제 분석이 여전히 필요하며 UAS와 지역 품질값을 새로 열지 않았다.

학습 대기 중 [계획 §5](EXPERIMENT_PLAN_ko_v1.md)와 [상태 검증](STATE_VALIDATION_ko_v1.md)의 한-step 표현을 검사 소스와 세 지역 검증 영수증으로 재확인했다. exact는 optimizer 실행 전 복원/hook/같은 anchor PLY-render에 해당하며, 한 native step은 카메라·step counter·개수·유한성의 건전성 검사다. 갱신 모델/Adam 전체 tensor의 bitwise parity를 검증한 것으로 읽히던 문장을 정정했다. 코드·조건·영수증·historical 상태 기록은 변경하지 않았다.
