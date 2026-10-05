# Wu–Vallet 동등조건 재실행: P1·P2·P3

2026-09-07 · `PHD-WU-VALLET-MATCHED-v5` · `scientific_verdict: null`

**세 구역을 같은 시점 선택·입력 생성·광선 판정·정제 코드로 다시 실행했다.** 세 후보를 모두 봉인하고 소스/설정/원점 계보의 일치를 검사한 뒤, 기존과 정확히 같은 UAS 참조로 평가했다. [새 비교 화면](http://127.0.0.1:8901/)은 P3를 기본으로 ALS·영상 기하·갱신·UAS를 동기화해 보여준다. 기존 v1–v4와 8897–8900은 보존했다.

## 1. 무엇을 바로잡았는가

이전 v4 주표는 P1/P2의 추가 관측지원 시점과 P3의 기존 hash-first 시점을 섞었다. 이 차이를 통제하기 전에 구역별 결과 차이를 방법의 효과로 설명한 것은 불충분했다. 이번에는 P3까지 전체 고정 뷰를 같은 규칙으로 검사하고 같은 updater로 재실행했다. 지역 안의 비교군도 동일한 입력 원점을 공유한다. 별도 OpenMVS 융합점은 주비교에서 분리해 문맥 자료로 표시한다.

알려진 작은 영역 필터 재유입 버그는 v3에서 이미 교정돼 있었다. v5는 이를 독립적으로 검증하고, 과거 v2의 잘못된 최종 keep mask 대신 raw evidence만 전달하는 API로 재유입 경로를 차단했다. v3의 교정된 점 선택 의미를 바꾸지 않았다. **핵심 검사 59개, 평가·동등조건 검사 18개 PASS**이며 실제 세 구역 updater 소스 해시가 시험한 소스와 같다. 추가로 입증된 알고리즘 버그는 발견하지 못했다. 시험 통과를 저자 코드와의 동일성 증명으로 해석하지 않는다.

## 2. 세 구역에 적용한 동일 조건

| 구역 | 검사한 기존 고정 뷰 | 선택 시점 | 영상 메시 XY 지원 셀 | ALS 원점 | Wu 입력 영상 원점 |
|---|---:|---:|---:|---:|---:|
| P1 | 113 | 90 | 3,508 | 20,189 | 77,353 |
| P2 | 66 | 296 | 7,745 | 45,986 | 230,225 |
| P3 | 157 | **134** | 6,558 | 52,762 | 153,314 |

모두 native 영상 메시의 0.5m XY 점유 셀 최대, 최소 64면, 동률 동일 seed/hash 규칙이다. 셀 수는 시점 선택용 prism 메시이고 최종 점 수는 전체 문맥 메시를 동일 prism으로 자른 원점이므로 경계 정점 수가 약간 다르다. P3는 이전 133번 결과를 재사용하지 않았다.

재실행한 P1/P2의 최종 좌표·출처·old/new 유지 마스크·old/new 상태 6개 배열은 기존 v4 관측지원 결과와 모두 정확히 같았다. P3는 시점 변경으로 76,500→77,738점이 됐다. [이전 출력과의 원배열 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-PREVIOUS-COMPARISON-v5/run/receipt.json).

메시 edge/depth jump, ALS scan 연결, XY 25m buffer와 Z[-90,80] 문맥, 양방향 광선, 거리 0.3m, 면적 0/0.25/1/4m², CHANGED-only 대조가 전 구역 동일하다. 주표는 모두 1m²이며 결과에 따라 최적 문턱을 고르지 않았다. P3의 legacy 배열 키 변환은 acquisition 44개/trajectory 10개 배열의 dtype·shape·bytes가 동일함을 확인했다.

각 구역에서 `ALS_before=common.old_xyz`, `Image_before=common.new_xyz`, `Naive_union=두 배열의 결합`, `Wu=같은 원점의 선택 부분집합`이다. 파라미터뿐 아니라 준비 코드 4개/갱신 코드 6개의 동일 해시와 시험 소스의 연결까지 [평가 전 공통조건 gate](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/MATCHED_PROTOCOL.json)에서 통과했다.

## 3. UAS 평가 결과

UAS는 모든 구역의 평가 기준이다. 입력 생성·갱신에는 raw UAS와 기존 UAS crop이 마운트되지 않았다. 세 후보와 공통조건 gate를 봉인한 뒤 v4의 같은 참조 NPZ를 재사용했다. P1 1,127,634점 / P2 2,325,976점 / P3 3,087,747점, 원점 전량으로 평가했다. 과거 평가를 보며 개발한 구역이므로 독립 blind/confirmatory 시험은 아니다.

아래 F1@0.5m는 양방향 참조 근접도의 조화평균으로 높을수록 좋으며, 변화 검출 정답에 대한 F1이 아니다.

| 구역 | ALS 단독 | 영상 단독 | 단순 합집합 | Wu 1m² |
|---|---:|---:|---:|---:|
| P1 | 61.84% | 91.89% | 94.69% | **96.95%** |
| P2 | 52.04% | 90.46% | 92.91% | **93.50%** |
| P3 | 90.14% | 65.59% | **90.44%** | 86.17% |

| 구역·방법 | 평균 출력→참조(m) | 평균 참조→출력(m) | 참조 XY 셀 결손 |
|---|---:|---:|---:|
| P1 ALS | 1.0819 | 1.2972 | 0 / 3,600 |
| P1 영상 | 0.0676 | 0.3139 | 92 / 3,600 |
| P1 합집합 | 0.2775 | 0.1149 | 0 / 3,600 |
| P1 Wu | 0.1185 | 0.1510 | 1 / 3,600 |
| P2 ALS | 1.7061 | 1.3237 | 12 / 8,799 |
| P2 영상 | 0.1005 | 0.8541 | 1,059 / 8,799 |
| P2 합집합 | 0.3678 | 0.1416 | 0 / 8,799 |
| P2 Wu | 0.2679 | 0.1629 | 12 / 8,799 |
| P3 ALS | 0.1356 | 0.3089 | 11 / 8,633 |
| P3 영상 | 0.3102 | 1.2701 | 2,077 / 8,633 |
| P3 합집합 | 0.2655 | 0.2507 | 7 / 8,633 |
| P3 Wu | 0.4673 | 0.2941 | 166 / 8,633 |

| 면적 민감도 F1@0.5m | 0m² | 0.25m² | 1m² | 4m² | 1m² CHANGED-only |
|---|---:|---:|---:|---:|---:|
| P1 | 96.74% | 96.85% | 96.95% | 97.04% | 95.99% |
| P2 | 93.57% | 93.53% | 93.50% | 93.53% | 86.77% |
| P3 | 83.70% | 84.79% | 86.17% | **90.07%** | 85.18% |

동일 시점 선택을 적용해도 P3의 1m² 결과 악화가 남았다. 다만 4m²에서는 ALS의 F1에 매우 가까워지고 역방향 평균 거리도 줄어든다. 따라서 ‘Wu는 P3에서 어떤 설정으로도 악화된다’고 해석하면 안 된다. 원문의 정확한 정제 문턱이 미공개인 이상 이 민감도를 반드시 같이 보고한다.

## 4. 정성 결과와 원인 해석

[P1 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P1/cross_sections.png), [P2 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P2/cross_sections.png), [P3 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-EVALUATION-v5/run/P3/cross_sections.png)은 동일 고정 폭의 모든 원점을 보여준다. P1/P2는 과거 표면을 현재 영상 표면으로 갱신하는 효과가 유지된다. P3는 영상 단독의 지붕 결손을 ALS로 보완하지만, 지붕 아래의 참조와 떨어진 영상면도 함께 들어온다. P3 1m²에서 새 점 32,196개를 추가하고 ALS 7,220개를 삭제했다.

P3에서 추가한 영상점의 참조 평균 거리는 0.9643m, 그중 5,285점은 2m를 넘는다. 이들은 `accepted_changed` 5,107점과 `raw_single` 178점이다. 보존 ALS의 평균 거리는 0.1160m이며, 삭제한 ALS 7,220점 중 6,394점은 참조 0.5m 이내다. [판단 상태별 진단](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-DECISION-SUPPORT-v5/run/receipt.json)에서 영상 기하가 변화 관계로 판정되는 지점을 추적했다. 거리 >2m는 사후 진단 묶음이며 확정 오류·변화 라벨이 아니다.

핵심 synthetic 검사에서는 두 입력과 sensor-ray가 동일하면 실제 철거와 조밀한 잘못된 영상 깊이를 구별할 관측이 없다는 기제도 확인했다. 이는 현재 코드가 어떤 동작을 하는지 검증하는 합성 대조다. 실측 P3의 모든 문제나 원저자 구현의 실패를 증명하지 않는다.

## 5. 재현 범위와 연구 판단

이번에 통제한 것은 모든 구역과 비교군에 **동일한 대체 입력·구현·평가 절차를 적용하는 조건**이다. 원문의 PSMNet 재학습·다중시점 전방교차 대신 COLMAP depth, 실측 대신 추정 ALS 궤적을 사용한다. 삼각형 판정·면적·정점 집계의 일부 세부는 명시적 재구현 선택이다. 2026 저자의 정확한 predicate는 미확보이며 2023의 tetrahedron formulation과 우리 sampled ray가 다르다는 사실을 구분한다. 이 차이는 단순 구현 버그라는 증거도, 원방법과 동일하다는 증거도 아니다.

기존 방법의 정적 구조 보존과 변화 부분 갱신 효과는 P1/P2에서 인정한다. P3의 현재 입력 조건에서 남는 부정확한 새 표면 유입은 추가 검증 대상이다. 입력 생성/정제 차이까지 통제하기 전에 이를 우리의 확정 기여로 채택하지 않는다. A 판단과 B 재구성의 독립성은 유지하며 GS/텍스처/렌더 실험은 이번 작업에 포함하지 않았다.

## 6. 실행·보존

[프로토콜](PROTOCOL_ko_v5.md), [이슈·예외](ISSUES_ko_v5.md), [결과 manifest](../../../../artifacts/manifests/phd/wu_vallet_matched_v5/technical_result_manifest_v5.json)에 실제 실행·검증·해시를 연결한다. `run_stage.sh update P1|P2|P3`, `evaluation ALL`, `comparison ALL`, `viewer ALL`이 고정 source snapshot과 Docker image를 남긴다. 재실행은 새 run ID를 써서 기존 출력을 보존한다.

실제 Chrome/SwiftShader에서 세 지역·각 5조건·출처 모드·동기 시점·단면·정량·모바일을 검사해 **1,722개 검증 PASS, 455개 자산 HTTP/해시 확인, 17개 스크린샷**을 기록했다. [P3 비교 캡처](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-BROWSER-QA-v5/desktop_P3_before_after_reference.png)와 [전체 원점 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_matched_v5/PHD-WU-VALLET-MATCHED-BROWSER-QA-v5/desktop_P3_native_sections.png)을 육안 확인했다. 8897–8900 기존 서비스는 그대로 응답하며 8901만 추가했다.

P3 adapter의 문자열 검증 TypeError와 입력용 외부 Bash의 종료 예외는 별도 기록했다. 완료한 후보·원배열·동일 소스는 독립 평가 gate에서 다시 검증했다. 전체 artifact/원자료를 고쳐 문제를 숨기지 않았다. 현재 좌표 처리의 CRS·datum/epoch·정합 한계는 v4와 같고, 수치는 공식 절대 정확도나 확정 변화 정답이 아니다. 기존 코드·결과·서비스를 보존하며 commit/push는 하지 않았다.
