# GeoGS P1·P2·P3 실행 이슈

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

**RGB-BASELINE-001 · EFFECTIVE_SCALE_DIFFERENCE_CAUSALITY_UNRESOLVED, 2026-09-15:** 기본 `.005/native`의 품질 문제를 저자 제공 예제와 대조했다. 동일 percent_dense=.01의 실제 clone/split 경계는 예제.446m 대 P1/P2/P3 2.008/2.684/2.124m다. 카메라 수·extent·XYZ 학습률도 다르다. CPU 감사 exit0, 새 학습0이며 큰 Gaussian의 잔류 원인 후보로만 기록한다. 저자55,413점의 실제 입력은 sparse_lod와 동일하므로 SfM 초기화라는 과거 대화 귀속을 정정한다. 상세는 [NATIVE_EFFECTIVE_SCALE_AUDIT_ko_v1.md](NATIVE_EFFECTIVE_SCALE_AUDIT_ko_v1.md)에 있다.

| ID | 상태 | 문제·근거 | 조치·영향 |
|---|---|---|---|
| PRESERVATION-ADDITIONS-001 | BASELINE_UNCHANGED_NEW_PATHS_OBSERVED | 최종 보존 검사 `preservation/final_v1/attempt.jc7tpF`가 범위 밖 새 경로를 감지하여 exit1/DIFFERENCES_REQUIRING_REVIEW. 21:01:38 KST의 기존6471개 bytes, 기존dirty4개 patch·HEAD·symlink 및 기존서비스62개 identity는 모두일치 | 원보고·실패exit 유지. source_candidate/srdm 등 새 경로의 작성 주체를 추정하거나 내용·서비스를 변경하지 않음. 유일 false인 새경로 검토 조건과 기존보존 PASS를 구분해 추가 문서화하며,170GB 전체검사를 불필요하게 반복하지 않음 |
| LAUNCHER-IDENTITY-002 | RESTORED_BEFORE_NATIVE_SEAL_FINISHED | root가 실행 중 repo launcher에 후속 옵션을 추가. 실제 Bash fd255의 위치6184, 원6335/변경6458 bytes로 tail 위치 위험 확인 | 현재 native seal이 계속되는 동안 원 launcher를 실행 사본 SHA613ea2dc…로 정확히 복원하고 검증된 개선판은 별도 `finalize_primary18_inputs_v2.sh` SHA748d4a3a…로 보존. 중단·관찰된 파서 실패 없음, 후속 full runner는 새 파일 사용. [상세](EVALUATION_COMPLETION_AMENDMENT_ko_v2.md) |
| EVALUATION-ORDER-001 | AMENDED_BEFORE_REFERENCE_ACCESS | 주18개가 모두 완료됐지만 보조 반복 P1/P2 CUDA OOM과 제어기 종료로 all21 성공 조건이 주 분석을 지연 | `evaluation_completion_v2.json`을 추가해 주18개와 보조 실패/미실행 상태를 봉인한 뒤 평가. 원 조건·입력·지표·선택법 유지, 반복 품질 변동 미측정. [변경 문서](EVALUATION_COMPLETION_AMENDMENT_ko_v2.md) |
| ARCHIVE-PREP-001 | NOT_EXECUTED_NOT_APPROVED_FOR_USE | 준비된 실패 보존 도구의 소스 검토에서 os.walk 읽기 실패 누락 및 조상 symlink 경계 검증 부족 확인 | 실제 이동·재시도 없음. 합성13 PASS가 이 경계 검증을 뜻하지 않음. 이번 완료 범위에서 실행하지 않으며 기존 실패 경로 보존 |
| INPUT-001 | RESOLVED | 입력 감사의 첫 read-only Docker 호출에서 image 기본 WORKDIR가 mount 위치와 달라 실패 | 명시적 -w 적용 후 조회 성공. source/산출물 변경 없음 |
| STATE-001 | CONFIRMED_SOURCE_BLOCKER | 공식 checkpoint가 protection/RNG/controller/카메라 stack 상태를 저장하지 않으며 stage 보호 등록 전에 기록됨 | 별도 완전 상태 보완과 연속/재개 parity gate 필요. 아직 동일 anchor 결과 없음 |
| CRS-001 | OPEN_INTERPRETATION_LIMIT | 기존 작업 EPSG:25832, UAS header EPSG:32632, +45.7m ALS bridge의 datum/epoch 한계 | 기존 변환 고정, UAS 정합 보정 금지. 보정된 절대 정확도 주장 금지 |
| DA3-001 | COMPLETED_DEVIATION | 공식 전처리는 전체 이미지 일괄 추론; 세 지역 입력에 대응하는 DA3가 없었음 | train-only balanced 7·8뷰 revision2, 고정 모델/840 해상도로 98/57/137맵 생성·봉인. 전체 영상 공동 추론과의 차이는 유지 |
| INPUT-002 | OPEN_ADAPTATION_LIMIT | 공식 입력 LoD2 mesh와 과거 ALS scan-beam mesh는 다른 생산 과정 | 변환 손실·구멍·연결을 기록하고 원 ALS와 파생 mesh를 별도 평가 |
| NATIVE-001 | RESOLVED_PREPARATION | 최초 예제 validator가 sparse_lod의 text COLMAP 대신 binary만 가정 | 공식 로더의 binary/text fallback에 맞춰 validator 교정. 기존 추출 바이트 재검증, 덮어쓰기 없음 |
| ENV-001 | RESOLVED_IMPORT | mesh extraction import에서 system libstdc++의 CXXABI_1.3.15 부재 | conda libstdc++ loader 우선순위로 expanded imports PASS. 런처에 실제 환경 기록 |
| NATIVE-002 | RETRY_RUNNING | 최초 공식 학습이8,000회 보고 단계의 FigureCanvasAgg.tostring_rgb에서 실패. 공식 요구 Matplotlib3.10.9가 해당 함수를 제거. checkpoint 전 실패,623.85초 | 실패 원본 보존. 코드·제어 그대로, Matplotlib3.9.2 호환 image로 새 native_example_retry_compat_v1 실행. 실패 run의 완성 결과0 |
| DA3-002 | RESOLVED_WRAPPER | 첫 DA3 wrapper가 namespace package의 __file__을 가정 | api.__file__ 기준 source 검증으로 교정. inference 전 오류, 로그 보존 |
| DA3-003 | RESOLVED_MEMORY_PREFLIGHT | 첫배치 성공 뒤 다음배치에서 allocator cap 안 캐시 단편화와 함께 OOM | batch 뒤 tensor 해제/gc/empty_cache. 같은 모델8뷰840에서 큰배치 반복 통과. 모델·해상도 변경 없음 |
| DA3-004 | RESOLVED_REVISION2 | P1 마지막2뷰 batch의 pose-scale Umeyama covariance rank가 퇴화 | 새 공통 balanced consecutive train-only batch revision. 98/57/137뷰 모두7·8뷰 그룹으로 완료. 원batch/실패 보존, 참조·학습결과 접근 전 조정 |
| CAMERA-001 | ADAPTER_VALIDATED | 지역 원 K의 cx/cy를 공식 FoV 로더가 버려 최대6.2032px의 합성 투영 오차 | opt-in calibration adapter + 같은 native CUDA renderer 검사0.00560px. 원예제는 원동작 유지. 남은0.5px convention 차이는 별도 한계 |
| INIT-001 | COMPLETED_ADAPTATION | Trimesh.Scene.ray 부재로 공식 visibility가 예외 후 True fallback | train-only Open3D first-hit 검사 wrapper, 공식 sample/projection/assembly 유지. 평가참조/사진색 입력 없음. 초기점 93583/93497/94644개 봉인 |
| SEAL-001 | RESOLVED_VALIDATOR | 최초 입력 seal 검사가 공식 prior ray-miss의 양의 infinity까지 오류로 거부 | 공식 finite-positive loss mask와 일치하도록 prior의 +inf/NaN을 결손으로 기록. 원 depth 바이트 유지. 음수 prior와 DA3 nonfinite는 계속 거부; DA3의 유한 음수는 SEAL-002에서 별도 감사 |
| SEAL-002 | RESOLVED_WITH_INPUT_LIMIT | 다음 seal 검사가 DA3 cubic 복원의 유한 음수를 거부 | 원해상도 292개 모델 출력은 모두 양수. 공식 INTER_CUBIC 재계산과 최종 배열이 전부 바이트 일치. P1/P2/P3 음수 751/3366/960픽셀, 최소 -66.53/-69.95/-88.18m. 원 배열 유지, 공식 finite-positive 마스크가 제외. 검사기는 정확한 audit와 동일 수치를 요구하도록 수정 |
| STATE-002 | OBSERVED_INDEPENDENT_TRAJECTORY_DIFFERENCE | 같은 seed의 원본/상태기록 추가본 독립 실행이8,000회 전 Gaussian 수에서 약0.35% 차이 | 독립 실행의 exact parity를 PASS로 두지 않음. 실제 동일 checkpoint 복원 직후 전체 상태·hook·PLY 렌더와100회 재개를 따로 검증. 비교 자체를 생략하거나 오차 허용으로 복원 불일치를 숨기지 않음 |
| STATE-003 | RESOLVED_AUDIT | 실제 checkpoint 감사 comparator가 NumPy uint32 RNG 배열을 torch2.1.2 tensor로 바꾸다 실패 | 원 source/checkpoint 유지, optimizer 실행 전 실패 기록. NumPy 원 dtype 비교로 검사기만 교정, 새 출력의 실제 복원 상태 exact PASS |
| STATE-004 | RESOLVED_AUDIT | 다음 실제8,001 step 감사가 성공한 step 뒤 보고 변수 loss를 참조하여 KeyError | 실제 total_loss 보고로 wrapper만 수정. fresh retry에서 상태·hook·PLY렌더 exact 및 한 native step PASS. 이전 실패·성공 상태 영수증 보존 |
| OOM-001 | FAILED_RUN_PRESERVED_RECOVERY_PENDING | P1 D005_Pnative가 마지막 진행 표시14,720회·4,845,783 Gaussian에서 native rasterizer forward OOM. 요청7.09GiB, free6.30GiB, allocated7.31GiB, reserved-but-unallocated9.13GiB. FAIL 영수증1,419.07초 | 원 로그·trace·8,000/8,100 checkpoint 보존. native/128 allocator의 같은 anchor 복원·한 단계 PASS; 실패 구간 이후 복구는 아직 증명되지 않음. [복구 조건과 증거](ALLOCATOR_RECOVERY_ko_v2.md) |
| OOM-002 | FAILED_RUN_PRESERVED_RECOVERY_PENDING | P1 D0005_Pnative도 마지막 진행 표시14,410회(재개6,410회)·4,890,928 Gaussian에서 같은 native forward OOM. 요청8.03GiB, free5.36GiB, allocated7.37GiB, reserved-but-unallocated10.40GiB. FAIL 영수증830.25초 | 임의 Gaussian 상한·해상도·손실 변경 없이 별도 allocator_v2 실행 경로와 동일 런타임 정책 준비. 기존 실패 시도와 새 조건을 주 비교에 혼합하지 않음. [복구 조건과 한계](ALLOCATOR_RECOVERY_ko_v2.md) |
| STATE-005 | POLICY_REFINED_WITH_LIMIT | 100회 후 CUDA RNG까지 항상 exact로 요구하면 수치 차이→split 선택 수→난수 tensor 크기 변화와 초기 복원 결함을 혼동할 수 있음. 기존 P1 100회 RNG는 실제 모두 같았음 | 초기 전체 상태·RNG/hook/PLY렌더와 한 단계 검사는 유지. 이후 CUDA RNG 값 차이만 UNRESOLVED_BRANCH_DYNAMICS 진단; RNG 구조·CPU/Python/NumPy·카메라·iteration·설정·소스 차이는 계속 차단. 8개 Docker 테스트 PASS, 독립 궤적 parity 주장 없음 |
| TEST-001 | RESOLVED_TEST_INVOCATION | evaluation_driver와 test_geogs_state_v1을 repository-only Docker mount에서 함께 호출하여 driver 8개 PASS 뒤 state import가 `No module named arguments`로 실패. 해당 fixture에 필요한 공식 source/GPU mount가 빠진 호출 | 학습 상태의 새 결함이 아닌 테스트 실행 환경 오류. 올바른 현재 CPU suite인 evaluation_driver+anchor_gate 16개 PASS. 변경 없는 state fixture의 기존 올바른 CUDA PASS와 새 allocator의 실제 production restore/한 단계 PASS를 유지; 부적절한 호출을 state PASS로 집계하지 않음 |
| RESOURCE-001 | SCHEDULING_GUARD_VALIDATED | 지역 추출 전 자원 검토에서 두32GiB CPU 메모리 상한의 동시 최대 사용은 기존 서비스 여유를 침범할 가능성이 있음. 실제 동시 TSDF OOM은 미발생 | render/auxiliary를 task-local 읽기 전용 공유 inode의 flock으로 직렬화. native 설정·weight 바이트 유지. Docker 실제 프로세스 간 대기/해제 및 비추출 우회2개 검사 PASS. 대기 시간 별도 기록 |
| TOOL-001 | LOCAL_FALLBACK_COMPLETED | 자원 잠금 작업의 추가 sub-agent 호출이 `agent thread limit reached`로 거부됨 | 부모가 같은 범위의 구현과 Docker 검증을 직접 수행. 과학 실행이나 기존 서비스의 오류로 집계하지 않음 |
| LAUNCHER-001 | RECOVERY_PREPARED | P1 allocator_v2 두 조건의 train은 모두30,000회 PASS인데, 상위 Bash가 뒤이어 line59 quote EOF로 종료. 실행 중 launcher 파일의02:42:32 수정이 두 학습 창(02:18/02:19–04:04/04:05)에 포함되고 현재 bash -n은 PASS이므로, 장기 실행 중 파일 교체 후 Bash의 기존 읽기 위치가 어긋난 설명이 강하게 지지됨 | 변경 전 현재 launcher 사본과 stat, 기존 실패 queue/log 보존. 최종 docker 호출을 exec로 전환하여 종료 뒤 shell 파일을 다시 읽지 않게 함. 완료 train/체크포인트/PLY 해시 검증 뒤 render→metrics→auxiliary만 별도 복구. 실행 중인 장기 shell은 추가 편집 금지 |
| SEAL-003 | VALIDATOR_GAP_FIXED | 봉인 전 코드 검토에서 phase PASS와 현재 파일 해시만 확인하면 생산 완료 뒤 교체된 파일을 과거 PASS 영수증과 잘못 연결할 여지가 확인됨. 실제 파일 변조나 교체는 관측하지 않음 | 주·보조 raw/post mesh 및 최종 checkpoint/PLY를 생산 영수증의 해시·기록된 크기와 대조. 보조 영수증의 과거 미기록 크기는 만들어 넣지 않고 SHA로 바이트를 검증. 같은 크기의 mesh 교체·hash 누락/중복·크기·checkpoint 변조를 포함한 관련 Docker30개 테스트 PASS |
| MEMORY-001 | MEMCG_OOM_CONFIRMED | P1 바닐라 anchor1024가 TSDF 적분50/98뷰 뒤 native -9로 종료.04:25:24 kernel CONSTRAINT_MEMCG가 해당 Docker cgroup의32GiB 한계에서 python을 종료한 사실을 확인. auxiliary phase FAIL151.01초 | 정상30k train/render/metrics와 실패 anchor/로그 보존. 별도48GiB 단독 자원 시험 준비. 장면·학습·추출 해상도 변경 없음. 시스템 전체 OOM과 구분 |
| MEMORY-002 | MEMCG_OOM_CONFIRMED | P1 D0005_Pnative mesh512는 PASS; 다음2048 TSDF가04:27:40 같은32GiB cgroup 한계로 native -9 종료. auxiliary phase FAIL136.06초 | 기존512 결과·2048 실패/로그 보존. anchor와2048 문제는 최종1024 모델 표면의 실패가 아님. 원인과 자원 한계를 먼저 확인하며 실패를 참조 부재/품질0점으로 변환하지 않음 |
| MEMORY-003 | MEM48_PROBE_FAILED_PRESERVED | 별도 공식 anchor1024 시험도48GiB에서98/98 TSDF 통합 뒤 메시화 중 native -9.205.55초, cgroup peak 정확히48GiB, oom_kill1, Docker OOMKilled true. 관측된 최소 host 가용11.10GiB | 실패 영수증·cgroup/GPU/host 로그와 stopped container 보존.48GiB를 성공한 복구 조건으로 승격하지 않음. 같은 사전 등록512해상도의 별도 anchor 자원 시험으로 필수 동일해상도 anchor/최종 비교의 실행 가능성을 확인. 주30k학습·1024결과 바이트 불변 |
| LAUNCHER-002 | FIXED_BEFORE_REPEAT_EXECUTION | 새 연속 실행 검토에서 반복 runner의 process-substitution logger가 GPU flock FD9를 상속하여 학습 종료 후에도 다음 실행의 flock -n이 잠깐 실패할 수 있음을 발견. 지연 logger를 둔 Docker 검사에서 단순 tee redirection만으로는 중간 shell의 잠금이 남는 현상을 재현 | logger를 `exec tee`로 교체하며 FD9를 닫도록 수정. logger가 살아 있어도 GPU 잠금 재취득과 로그 보존을 확인. 실제 반복 학습 전에 수정했으며 과학 설정·모델·학습 제어 변경 없음 |
| DISPLAY-001 | FIXED_SYNTHETIC_VALIDATED_ACTUAL_QA_PENDING | 후보 봉인·UAS 접근 전 표시 코드 검토에서 고정 source색을 실제 RGB로 안내하고, 존재하지 않는 source_count 필드를 읽어 원 평가 표본 수를 누락하는 문제를 확인. 현재 TSDF 표시도 면적 표본의 Points이며 원본 PLY 링크가 없어 삼각형 연결 상태를 직접 확인하기 어려움 | 색·표본 계보, 봉인 원본 PLY 링크와 실제 clipped 삼각면 보기를 연결했다. 기존 기하·렌더·봉인·자원 계산 hash와 수치/선택 가드 유지. 관련 CPU58, 합성 browser433, root 결합130 PASS/3 SKIP로 확인했으며 최종 실제 지역 QA는 봉인 후 필요. [검증 기록](DISPLAY_VALIDATION_ko_v1.md) |
| DISPLAY-002 | FIXED_SYNTHETIC_VALIDATED_ACTUAL_QA_PENDING | 참조와 예측이 모두 빈 ROI에서 metric은 기존 규칙대로 NOT_ASSESSED_REFERENCE_ABSENT이지만, 기존 summary가 이 후보를 available로 보내면 점 표시의0개 표본 검사가 오류로 끝날 수 있음을 코드에서 확인. 실제 지역에서 이 경우가 발생했다고 확인한 것은 아님 | 표시만 no_geometry_reference_absent와 명시적 이유로 분리했다. 원 NA/F1 정책 불변, 참조 없는 양의 기하는 표시, 참조 있는 빈 예측은 기존 복원 실패 유지. 실제 evaluator의 여섯 합성 경계·브라우저 primitive0/요청0 및 실제QA 코드 가드 통과. 실제 지역에서의 발생 여부는 미확인 |
| BROWSER-001 | RESOLVED_SYNTHETIC_ENVIRONMENT | 표시 합성검사 첫 Chromium 시도는 crashpad --database is required, 둘째는 VK_KHR_surface/VK_KHR_xcb_surface 미지원으로 초기화 실패. 지역 결과·UAS 접근 전의 검사 환경 실패 | 두 attempt와 chrome/exit 로그를 보존했다. container 전용 XDG와 기존 private Xvfb·ANGLE GL·LIBGL_ALWAYS_SOFTWARE=1의 Mesa 경로에서 합성 검증 통과. 학습 GPU·기존 host X/서비스 변경 없음. 상세 경로는 [표시 검증](DISPLAY_VALIDATION_ko_v1.md) |

## 2026-09-08 04:05 KST 이후 상태 갱신

- OOM-001/002의 allocator_v2 **학습 복구는 실제 완료**: P1 D005_Pnative 6,316.71초, D0005_Pnative 6,398.82초. 두 run의 native/validated exit 0, 최종30,000회 완전 checkpoint와 native PLY 저장·해시 확인 PASS. 이전 OOM 실패 시도는 계속 보존한다. 렌더·표면·전체 pipeline 완료를 뜻하지 않는다.
- NATIVE-002의 호환 image 공식 예제는 이미30,000회 학습·실제 렌더·TSDF raw/post mesh·native metrics를 완료했다. 본문의 RETRY_RUNNING은 당시 상태다. 예제 점수는 P1/P2/P3 성능이 아니다.
- LAUNCHER-001은 학습 결과 실패와 분리한다. 원 queue 실패를 지우거나 완료 학습을 재실행하지 않는다. 복구 후 각 후속 phase 영수증으로 해결 여부를 갱신한다.

## resource_v3 연결 완료 이후 상태

- 두 기존 P1 allocator_v2 학습의 최종1024 render/raw/post와 native metrics 파일 생성은 실제 PASS했다. 구 auxiliary는 MEMORY-001/002 실패 상태를 원 경로에 보존하며 새 자원 계약으로 별도 추출한다. 지역 품질값은 아직 분석·설정 선택에 읽어 사용하지 않았다.
- 별도32GiB 공통 anchor512 시험은 실제 raw/post 표면과 train/test 사진 export까지 PASS했다. 이를 곧바로 본 결과로 승격하지 않고, 고정 [resource_v3 계약](EXTRACTION_RESOURCE_AMENDMENT_ko_v3.md)의 새 경로에서 생산 영수증을 남긴다.
- 새21개 final/48개 planned auxiliary 연결과 sealer·평가·뷰어를 통합 검토했다. 현재 원 두 학습을 기다리는 `runtime/resource_v3_continuation/attempt.bPR61e`가 이후 주18개→반복3개→봉인·평가를 순서대로 실행한다. 필수 실패나 확인되지 않은 실패는 완료 단계로 넘기지 않는다.

## resource_v3 선택 추출의 확인된 자원 실패 — 2026-09-08 09:55 KST

P1 여섯 조건의 final2048과 공통 anchor1024에 이어 P2 `D0005_Pnative`의 선택 final2048도32GiB에서48.8473초 후 native−9, `cgroup_oom_kill_delta: 1`로 종료했다. 새 계획에서 허용한 `TECHNICAL_RESOURCE_UNAVAILABLE`이며, 추출 성공이나 참조 부재·복원 실패0점으로 바꾸지 않는다. 개별 로그·메모리 trace·SHA는 `extraction_resource_v3/primary/P2/D0005_Pnative/auxiliary/mesh_2048/receipt.json`과 같은 디렉터리에 보존한다.

이 P2 조건의 필수1024 raw/post·실제 사진 렌더·native metrics와 필수512 raw/post는 PASS했다. 원/새 queue 모두7/18개 완료이며, P2 나머지 조건과 P3·세 추가 반복은 아직 미완료다. 이후 선택 추출의 각 실제 시도도 같은 원 영수증과 최종 `extraction_availability.csv`/`extraction_attempt_resources.csv`에 개별 기록한다. 필수 실패나 확인되지 않은 종료를 이 선택 미가용 규칙으로 넘기지 않는다.

2026-09-08 11:10 KST 추가 확인: P2 `D005_Pnative`의 선택 anchor1024/final2048도 각각115.8425/48.8742초 후 동일32GiB cgroup의 native−9·OOM kill 증가1로 종료했다. 첫 두 P2 조건의6개 보조 추출은 `preservation/after_p2_first_resource_jobs_v1/resource_memory_audit.json`에서 영수증/메모리 trace 연결을 재검증했다. 이후 `D0_Pnative` final2048도46.8152초, native−9·OOM kill 증가1로 종료했으며 해당 `extraction_resource_v3/primary/P2/D0_Pnative/auxiliary/mesh_2048/receipt.json`에 보존했다. 이 세 P2 조건 모두 필수1024/512 표면과 실제 렌더·native metrics는 PASS했다. 주 완료 수는9/18개이며 지역 품질 분석과 UAS 접근은 아직이다.

2026-09-08 11:37 KST에는 P2 `D005_Prelease`까지 필수 산출물을 완료했다(주10/18개). 이 조건의 final512는28.4230초 PASS, 선택 final2048은48.8435초 후 native−9·OOM kill 증가1이다. 원 영수증은 `extraction_resource_v3/primary/P2/D005_Prelease/auxiliary/`에 보존하며 선택 자원 미가용을 표면 품질의0점으로 바꾸지 않는다.

2026-09-08 12:24 KST에는 P2 `D0005_Prelease`까지 필수 산출물을 완료했다(주11/18개). final512는26.6606초 PASS, 선택 final2048은46.8372초 후 native−9·OOM kill 증가1이다. 해당 `extraction_resource_v3/primary/P2/D0005_Prelease/auxiliary/`의 영수증과 trace를 보존한다. P3 원 제어 학습을 시작했으며 P2의 마지막 조건은 학습 중이다.

2026-09-08 12:50 KST에는 P2 마지막 `D0_Prelease`의 필수 산출물도 완료됐다(주12/18개). final512는26.6373초 PASS, 선택 final2048은50.9907초 후 native−9·OOM kill 증가1이다. 해당 `extraction_resource_v3/primary/P2/D0_Prelease/auxiliary/`에 원 기록을 보존한다. P1·P2의 모든 필수1024/512 표면·실제 렌더·native metrics가 확보됐으며, P3와 세 반복의 완료·최종 UAS 평가는 남아 있다.

## PRESERVATION-001 — P2 감사 영수증의 자기 stdout 해시 수정

P2 전체 감사의 최초 `preservation/after_p2_all_resource_jobs_v1/audit_receipt.json`은 쓰기가 끝나지 않은 `finalize_stdout.log`를 0바이트로 해시했다. 최종 로그는 148바이트여서 이 항목의 선언과 실제 바이트가 달랐다. 원 영수증과 로그는 보존하고, 닫힌 증거 파일만 묶으며 실행 중 finalizer 스트림을 명시적으로 제외한 `audit_receipt_v2.json`을 정본으로 추가했다. 추출·메모리·서비스 측정값은 바뀌지 않았다.

별도 `closed_hash_verification_v1/receipt.json`에서 정본에 선언된 닫힌 증거24건의 해시·크기를 모두 검증했다(`PASS_ALL_DECLARED_CLOSED_HASHES`, exit0). 정본 SHA256은 `45164c0a032c2d85f25874a6c4dbe82657aa37733dabe7f79a5524037fd23add`, 독립 검증 영수증 SHA256은 `34d9d851a8cf3f07e505204acdf99bc5b909a46599140a95330fa1287538a8d9`이다. 해결 상태는 `FIXED_CLOSED_EVIDENCE_VERIFIED`이며, 상세 범위와 한계는 [P2 전체 보존 감사](PRESERVATION_AFTER_P2_ko_v1.md)에 기록한다.

## P3 첫 조건의 선택 추출 자원 실패 — 2026-09-08 14:25 KST

P3 `D005_Pnative`의 공통 anchor1024와 final2048도 고정32GiB cgroup에서 각각195.8565/57.3656초 후 native−9·OOM kill 증가1로 종료했다. 원 영수증·메모리 trace·로그는 `extraction_resource_v3/primary/P3/D005_Pnative/auxiliary/{anchor,mesh_2048}/`에 보존했다. 선택 `TECHNICAL_RESOURCE_UNAVAILABLE`이며 참조 부재·품질0점·추출 성공으로 바꾸지 않는다.

같은 조건의 필수 최종1024 raw/post·실제 렌더·native metrics·공통 anchor512·최종512는 PASS했다. 주 완료 수13/18개이며 P3 나머지 조건·세 추가 반복·UAS 평가는 남아 있다. 단계 시간과 실제 시도는 [P3 첫 완료 기록](EXECUTION_STATUS_ko_v7.md)에 구분한다.

2026-09-08 14:52 KST에는 P3 `D0005_Pnative`의 필수 산출물도 완료됐다(주14/18개). 최종512는63.5995초 PASS, 선택 최종2048은67.6513초 뒤 같은32GiB cgroup의 native−9·OOM kill 증가1이다. 해당 `extraction_resource_v3/primary/P3/D0005_Pnative/auxiliary/mesh_2048/`의 원 영수증·로그·trace를 보존하며, 선택 자원 미가용을 표면 품질0점으로 바꾸지 않는다.

## PRESERVATION-002 — P3 감사 준비의 동등 경로 비교 오류

`preservation/after_p3_first_resource_jobs_v1/`의 새 mount planner가 완료 marker에 남은 `JointBuildGS-operator/../JointBuildGS-artifacts` 표기를 정규화하지 않고 예상 경로와 비교하여 거부했다. 이 시도는 준비 단계 exit1이며 자원 영수증/메모리 trace 감사나 서비스 snapshot을 시작하기 전이다. 코드·로그·실패 기록은 원 경로에 보존했다.

별도 `after_p3_first_resource_jobs_v2/`에서 `os.path.normpath` 후 정확한 task 내부 `claims/P3_<condition>/attempt.*/complete.json`만 허용하도록 비교를 수정했다. 실제 자료를 유리하게 교체하거나 검사 범위를 넓히지 않았다. v2의 자원/서비스 감사와 닫힌 증거34건 검증은 모두 exit0·PASS이며 원 추출/학습/서비스는 수정하지 않았다. 해결 상태는 `FIXED_NORMALIZED_PATHS_CLOSED_EVIDENCE_VERIFIED`, 실제14:58 KST 결과와 정본 해시는 [P3 실행 인계](EXECUTION_STATUS_ko_v7.md)에 남긴다.

## P3 세 번째 조건의 선택 추출 자원 실패 — 2026-09-08 16:24 KST

P3 `D0_Pnative`의 필수 최종1024/512 raw/post·실제 렌더·native metrics도 완료됐다(주15/18개). 선택 최종2048은65.8198초 뒤32GiB cgroup의 native−9·OOM kill 증가1이며, 해당 `extraction_resource_v3/primary/P3/D0_Pnative/auxiliary/mesh_2048/`의 원 실패/메모리 기록을 보존한다. 선택 자원 미가용을 참조 부재·품질0점·추출 성공으로 해석하지 않는다.

## RESOURCE-REPORT-001 — 최종 자원 표의 측정 범위 명시

후보 봉인·지역 품질 접근 전 source 검토에서 최종 자원 표의 같은 `child_peak_rss_bytes` 열이 일반 driver의 `RUSAGE_CHILDREN`, training trace의 `RUSAGE_SELF`, resource_v3 renderer의 `wait4`를 담는다는 점과 `raw child-phase wall time` 설명이 실제 driver 측정 구간을 충분히 나타내지 못함을 확인했다. 원 숫자 계산 오류를 확인한 것은 아니다.

수정 전 source를 `runtime/resource_measurement_review_v1/attempt.oQnJ8K/before/`에 보존하고, 아직 실행 전인 summary의 보고 metadata만 보완했다. scope 열·정의JSON·영수증 경로를 추가하고 설명 문자열을 교정했다. Docker9/9 PASS에서 허용 metadata 제거 후 전체 AST, 합성 원 수치/행, 정의JSON의 SHA/크기 결합, 다른 source/계약17개 해시 보존을 확인했다. 실제 지역 payload를 읽거나 live 실행기·과학 조건·지표를 변경하지 않았다. 상태는 `FIXED_METADATA_SYNTHETIC_VALIDATED_ACTUAL_SUMMARY_PENDING`이며 [상세 정의·검증](RESOURCE_MEASUREMENTS_ko_v1.md)을 따른다.

## P3 네 번째 조건의 선택 추출 자원 실패 — 2026-09-08 17:00 KST

P3 `D005_Prelease`의 필수 최종1024/512 raw/post·실제 렌더·native metrics도 완료됐다(주16/18개). 선택 최종2048은65.4254초 뒤32GiB cgroup의 native−9·OOM kill 증가1이며, `extraction_resource_v3/primary/P3/D005_Prelease/auxiliary/mesh_2048/`의 원 실패/메모리 기록을 보존했다. 선택 자원 미가용을 참조 부재·품질0점·추출 성공으로 바꾸지 않는다.

## 2026-09-08 18:09 KST — P3 약한 깊이 가중치·보호 해제 조건의 선택 추출

P3 `D0005_Prelease`도 필수 최종1024/512 raw/post·실제 렌더·native metrics를 완료했다(주17/18개). 선택 최종2048은61.4395초 뒤32GiB cgroup에서 native−9·OOM kill 증가1로 종료됐다. 필수512는61.2035초·PASS·OOM 증가0이다. `extraction_resource_v3/primary/P3/D0005_Prelease/auxiliary/mesh_2048/`의 원 실패/메모리 기록을 보존하며, 이 선택 자원 미가용을 기하 평가0점으로 치환하지 않는다.

## 2026-09-08 18:56 KST — 마지막 P3 조건의 선택 추출과 주18개 완료

P3 `D0_Prelease`의 필수 최종1024/512 raw/post·실제 렌더·native metrics를 완료해 주18/18개다. 선택 최종2048은67.2365초 뒤32GiB cgroup에서 native−9·OOM kill 증가1로 종료됐다. 필수512는63.0729초·PASS·OOM 증가0이다. 원 기록은 `extraction_resource_v3/primary/P3/D0_Prelease/auxiliary/mesh_2048/`에 보존한다. 이제 주 조건의 선택2048 및 세 공통 anchor1024가 모두 같은 자원 상한에서 미가용으로 기록됐지만, 반복 세 조건의 가용성 시도와 all21 봉인은 아직 필요하다.

## REPEAT-001 — P2 바닐라 반복의 첫 densification 부근 CUDA OOM

- 상태: `DIAGNOSIS_IN_PROGRESS`, 주18개 완료 결과는 보존, P1 반복은 계속 실행.
- 실제 실패: `native_repeat_allocator_v2/P2/D005_Pnative/train_receipt.json`은18:59 KST에 FAIL·native/validated exit1, driver wall20.131426초를 기록했다. 실패 로그는8,100회 첫 trace가 쓰이기 전 `train.py:1078 → densify_and_prune → gaussian_model.py:428`의 `torch.max(self.get_scaling, dim=1)`에서 CUDA OOM을 보고한다. CUDA 비동기 오류 보고 때문에 실제 allocation 요청 위치의 단독 확정 근거로 삼지 않는다.
- GPU 기록: 같은 GPU1 UUID `GPU-fab8b9b4-e6eb-9f2b-71e3-7997f092d21e`의5초 장치 표본은91→2,376→20,078→23,658MiB였다.23,658MiB는 약23.1GiB다. 프로세스의 live tensor/RSS나 정확한 실패 시점의 peak와 동일하지 않다.
- 비교 근거: 성공한 P2 weak/zero 및 native100회 parity와 driver/config/layout/image/input/기록 환경·45개 구현 해시와 GPU UUID/초기91MiB가 일치했다. weak/zero 명령과는 prior 계수만 다르고, 성공 native parity는 같은 명령에 `--jbgs_stop_after 8100`만 추가했다. 따라서 확인된 설정 드리프트나 항상 실패하는 anchor라고 결론내리지 않는다. 성공한 native parity의8,100회 peak allocated는4,690,284,032바이트, peak reserved는24,788,336,640바이트였으며 이 peak 통계가 실패 시점의 live/reserved 분해를 대신하지 않는다.
- 조치: 원 실패 파일과 queue/repeat 시도 로그를 보존하고 같은 설정의100회 계측 진단을 새 경로에 준비한다. 학습 source·과학 조건·allocator·주 결과를 변경하지 않는다. 진단은 정식 반복 결과를 대체하지 않으며 해결 여부는 아직 미확인이다. UAS와 실제 평가 렌더 점수는 계속 닫혀 있다. 실패 traceback 확인 중 로그에 함께 출력된 학습 loss는 설정 선택에 사용하지 않았다.
- 후속 실행 제어: 현재 원 controller는 P1→P3 반복을 계속 실행하고, 이미 실패한 P2 worker의 exit1을 이후에 확인하게 된다. 이 사실을 지우거나 live controller를 편집하지 않는다. 복구 후에도 all21 실제 산출물 검증과 새 최종화 진입이 필요하다.

예약/할당 메모리 구분과 비동기 오류 위치의 한계는 [PyTorch2.1 CUDA 설명](https://docs.pytorch.org/docs/2.1/notes/cuda.html#cuda-memory-management)에 근거한다. 현재 원인은 운영 메타데이터만으로 확정되지 않았다.

## REPEAT-002 — P1 반복의 렌더러 CUDA OOM과 원 controller 종료

19:16 KST에 확인한 P1 반복 영수증은 FAIL·native/validated exit1·driver wall991.796377초다. 마지막 정상 trace는14,500회, 전체 Gaussian6,104,588개·보호236,015개다. 이어진 `train.py:825 → gaussian_renderer → _C.rasterize_gaussians` 호출에서13.85GiB 할당 요청에 대한 PyTorch CUDA OOM을 기록했다. 오류 메시지의 free는13.32GiB, PyTorch allocated8.90GiB, reserved-but-unallocated549.27MiB였다. 기존 desktop process의260MiB 점유가 함께 보고됐으며 기존 서비스를 중지하거나 변경하지 않는다. 여러 rounded 메시지 값을 합쳐 정확한 메모리 원인 분해로 삼지 않는다.

원 기록은 `native_repeat_allocator_v2/P1/D005_Pnative/`에 있다. 실패 영수증 SHA256은 `9f4438bbd0e91c3286b4f9cc7af2add51cc5b2a84972c5340db89a4c69d7a1e1`, invocation SHA256은 `aaf4905e4688ef4a04dfb8b2b3e53d8415d310d758190f40f95f82dbb4a83931`이다. 원 controller의 `repeat_exit_codes.txt`는 `1 1`, 전체 종료도1이며 P3 반복은 시작하지 않았다. 주18개 결과는 모두 보존한다.

현재 상태는 `DIAGNOSIS_AND_BOUNDED_RETRY_PREPARATION`이다. P2 짧은 계측 진단과 함께, 원 실패의 모든 byte/경로 계보를 보존한 후 같은 anchor·seed·과학 설정·allocator로 각 실패 지역을 한 번만 다시 시작하는 절차를 검토한다. 아직 재시도를 실행하거나 성공을 선언하지 않았다. 재시도가 성공해도 최초 실행 실패를 비용·재현성 관찰에서 제외하지 않으며, 성공한 실행끼리의 품질 차이는 완료 가능한 실행에 조건부인 비교로 표시한다. UAS/평가 렌더 품질값은 여전히 닫혀 있다.

## PRESERVATION-003 — P3 감사 후 보고용 시각 포맷 오류

P3 전체 자원/서비스 감사와 닫힌 증거33/33 검증은 모두 종료0이다. 그 뒤 별도 보고용 `report_readout_v1.py`만 Python3.10의9자리 소수초 parsing 오류로 종료1이었다. 원 timestamp와 실패 소스/명령/로그를 보존하고 새 v2에서 원 소수초 문자열을 유지해 해결했다. 자원 값·서비스 snapshot·정본 감사 영수증·33건 해시 결박은 변경하지 않았다. 자세한 시각·범위는 [P3 보존 감사](PRESERVATION_AFTER_P3_ko_v1.md)에 기록했다.

## SFM-NO-ANCHOR-001 — 새 SfM 초기화 경로의 CUDA OOM과 자원 복구

2026-09-10 추가 요청으로 실행한 `no_anchor_sfm_v1/`의 P1/P2/P3는 각각 약10,780/14,400/8,710 부근에서 CUDA OOM으로 종료했다. 정확한 마지막 정규 trace·Gaussian 수·할당 오류·driver 시간과 원 receipt는 [실행 기록](SFM_NO_ANCHOR_EXECUTION_ko_v1.md)에 있다. 원 로그·초기 상태·기존 Anchor/최종 결과를 보존한다. 이는 Anchor의 인과적 필요성이나 SfM 초기화의 품질 실패를 입증하지 않는다. 기존 바닐라 추가 반복에서도 메모리 실패가 있었으므로 성공한 기존 실행과만 비교해 일반화하지 않는다.

과학 config를 유지한 CPU depth/Adam moment 보관 복구 v1의 P1/P2는 전송 비용을 줄이는 검증된 pinned-buffer v2로 교체하기 위해 정확한 native child만 SIGTERM했다. `native_exit_code=-15`, `stop_intent.json`의 `RESOURCE_TRANSFER_OPTIMIZATION`과 소요 비용을 OOM과 구분한다. v2는 작은 CUDA 상태·계산 동등성 검증 및 source hash 봉인 후 P1/P2를 새로 시작했고 P3는 GPU0 lane에 대기시켰다. 기존 서비스는 중단하지 않았다. 8k/15k 진단 checkpoint를 추가 보존하며22k/30k 결과는 아직 없다. 작은 동등성 검증은 전체 학습 궤적 동일성을 보장하지 않는다.

첫 v1 CUDA fixture는 device index 누락으로 실패했고, 고정 fixture v2에서 `cuda:0`로 보완해 통과했다. 원 실패 근거·script snapshot을 보존했다. 세 번의 작은 GPU 검증이 활성 학습과 잠시 겹친 자원 편차, pinned-cache RAM guard의 한계, 최종 완료 미확인은 같은 실행 기록에 연결한다. `scientific_verdict: null`.

## SFM-QUEUE-001 — 상위 launcher 종료 기록을 GPU lane 해제로 오인한 P3 조기 시작

상태: `CONFIRMED_QUEUE_PREDICATE_DEFECT_RECOVERY_PENDING`, 2026-09-09 16:01 UTC(한국시간2026-09-10 01:01) 읽기 감사. P1/P2 v2 native 학습 컨테이너는 살아 있고 trace가 진행 중인데, 두 `queue/P*/exit_code.txt`가15:57:55.446269 UTC에0으로 기록되었다. 두 queue의 `status.txt`는 `TRAINING`, 닫힌 train receipt는 없었다. 따라서 이0은 native 학습이나 지역 전체 성공을 뜻하지 않는다.

P3의 보존된 `lane_wait/launcher_snapshot.sh`는 P1 `exit_code.txt`의 **존재만** 기다린 뒤 P3를 GPU0에 시작한다. 값·지역 완료 상태·producer receipt·살아 있는 GPU 컨테이너를 검사하지 않는다. `lane_wait/started_utc.txt`는15:58:03 UTC이고, P1 GPU0가 계속 실행되는 동안 P3가 같은 GPU로 들어갔다. P3는 camera 준비의 `world_view_transform.cuda()`에서 `RuntimeError: CUDA error: out of memory`를 보고했고 첫 training trace 전에 종료했다. 정확한 CUDA 할당 지점은 비동기 오류 보고의 한계가 있어 호출 위치만으로 단정하지 않는다. 이는 최종 복원 품질 결과가 아니라 잘못된 동시 실행으로 발생한 기술 실패다.

P3 native driver 구간은15:58:23.5416913–15:58:28.5709558 UTC, **5.029073881916702초**, receipt `FAIL`/native·validated exit1이다. queue에서 시작한15:58:03부터의 전체 경과와 이5초 구간은 다르다. 같은 run의15:58:23.561 장치 표본은GPU0 UUID `GPU-4bdfcab8-1464-94b0-0a2f-dd9693ace2a0`의 사용 메모리24,080MiB·GPU utilization94%이며 P3 자체 메모리 사용량이 아니다.

직접 확인된 제어 결함은 **상위 shell의 종료 파일과 실제 GPU 작업 종료를 동일시한 대기조건**이다. `run_region.sh`의 EXIT trap은 그때의 `$?`를 기록하며 TERM/INT를 명시적으로 구분하거나 native 종료·전체 pipeline 완료를 검증하지 않는다. 운영 중 보고된 exec session49373/75332의 exit143과 초기 `run_phase.sh` PPID1 생존 관측은 상위 launcher에 SIGTERM이 전달되어 EXIT trap이 직전 상태0을 썼을 가능성과 부합한다. 그러나 이 감사에서는 신호 발신자·발생 주체를 확인하지 못했으며, root가 관측한 exec-session 반환을 보존된 native receipt처럼 취급하지 않는다. 16:00:47의 독립 `ps` 조회에서는 해당 host launcher/phase shell이 보이지 않았고, 16:01:08의 Docker/trace 조회에서는 P1/P2 native 컨테이너가 계속 실행 중이었다. 초기와 후속 process 관측을 섞지 않는다.

보존 근거(task 상대 경로):

- `no_anchor_sfm_memory_recovery_v2/queue/P1/exit_code.txt`, `no_anchor_sfm_memory_recovery_P2_v2/queue/P2/exit_code.txt`: 두 파일 SHA256 `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa`; 각각의 launcher snapshot SHA256 `f117eae7a711b43dd8d9d87e7ac39f48ef62301df6e76bea9e183233e352507a`.
- `no_anchor_sfm_memory_recovery_P3_v2/lane_wait/launcher_snapshot.sh`: SHA256 `1b7419540214dd878b4d3bb0946bdb2725dd3f750630451df8484e202e25d4f2`; 같은 폴더에 queued/started UTC와 종료1을 보존.
- `no_anchor_sfm_memory_recovery_P3_v2/runs/P3/SFM_noanchor_D005_Pnative/receipt.json`: SHA256 `71bcfdbb8a7361e5b992030c563da091a6386f22f52ccba9f78e44cee63631c3`.
- 같은 P3 run의 `native.log`: SHA256 `fcb077b87d356dc83ef52feb4abfe34c151ab266ea70d8e0802669e0a1f502f1`; `gpu.csv`, invocation, wrapper 로그도 원 경로에 보존.

현재 조치는 P1/P2 native 학습을 유지하면서 실제 컨테이너 생존·종료 receipt·후속 처리 상태를 함께 추적하는 지속 supervisor를 준비하는 것이다. 이 감사 자체는 제어 source·queue·컨테이너를 변경하지 않았고 문서만 추가했다. supervisor 설치·P3 재시도 성공은 아직 이 기록의 확인 범위가 아니다. 기존 queue0을 고치거나 지우지 않으며 별도 사건 기록으로 무효한 완료 신호임을 표시한다. 조기 P3의 비용도 보존하되 품질 실패나 데이터 결손으로 해석하지 않는다. `scientific_verdict: null`.

후속 조치 확인: 16:02:25 UTC에 시작한 독립 session의 `orchestration_recovery_v1/P1/continue_existing_v2.sh`(PID1764349)와 P2 동일 경로(PID1764368)가 PPID1로 유지되는 것을 읽기 조회했다. 이 supervisor는 기존 training receipt가 생기고 native container가 사라진 후 producer PASS를 확인해 후속 export/evaluation을 잇는다. 새 `run_queued_P3_v3.sh`는 P1 producer receipt·continuation supervisor 종료 파일·실제 supervisor PID 부재·GPU0 compute process 부재·P1 train/export container 부재를 함께 확인한다. 기존 queue의 exit파일 존재만으로 진입하는 조건은 사용하지 않는다. 이는 제어 복구의 구현·기동 확인이며 이후 export 완료나 P3 재실행 성공 확인은 아니다.

조기 P3 v2 실패는 새 P3 경로의 optional `prior_initialization_failure`에 원 receipt/log SHA와 `cause: RESOURCE_SCHEDULING_ERROR`로 봉인하도록 지원했다. 봉인·자원 집계는 원 producer FAIL/native1·동일 지역/condition·generic CUDA OOM 메시지와 first-step audit 부재를 검사한다. CUDA OOM 발생 자체는 기록하되 학습 중 메모리 실패나 복원 품질 실패에 합산하지 않는다. 비용은 `new_prior_initialization_failures.csv`의 별도 계보 보기에도 남기며 동일 receipt가 다른 비용 표와 겹치므로 중복 합산하지 않는다. Docker6개 회귀 검사와 실제 원 P3 v2 근거의 읽기 검증은 PASS했다. 기존 v1/v2 봉인·queue·원 실패 파일은 변경하지 않았다.

## SFM-RESOURCE-PREFLIGHT-001 — P2 cgroup 증거 목록 검사의 준비 실패

상태: `RESOLVED_PREPARATION_ONLY`, 2026-09-09 17:18:24 UTC. P2 최종 자원 구현의 preflight가 실제 resource failure receipt의 추가 관측/불가 로그까지 원인 역할3개로 제한해 `Unexpected cgroup evidence role or duplicate`로 종료1이었다. source/config/학습이 생성되기 전의 구현 오류이며 P2의 추가 fresh 학습 횟수에 포함하지 않는다. 이전 준비 디렉터리 전체를 `no_anchor_sfm_gradient_memory_v3_P2/failed_preflight_v1/`에 보존하고, 정확한 오류·빈 입력·미생성 실행을 확인하는 `retry_preflight_v1` gate로 다시 준비했다.

모든 연결 증거의 SHA/bytes 검사는 유지한다. 원인 판단은 kernel `CONSTRAINT_MEMCG`·정확한 container ID/victim PID/32GiB와 실제 Docker inspect stdout/명령을 교차 확인하며, 빈 events·자동 제거 후 실패한 cgroup 읽기는 원인 증거로 쓰지 않는다. 새 준비와 봉인, 실제 P2 evidence bundle CPU 검증은 PASS다. 봉인 SHA256 `f563709dccc11e56fbe95e612c6b0922d795bacdba9bfaf7bae367139ffeb586`, 실패 보존 manifest SHA256 `a67c5a5e9d2cc1c3926064b7dfab66d8b0dcb0d5f15758ab50a32b6f51561a23`이며 [실행 기록](SFM_NO_ANCHOR_EXECUTION_ko_v1.md)에 명령/경로/범위를 연결했다. 기존 실패 결과와 서비스는 보존했고 이 조치에서 GPU 학습을 실행하지 않았다. 남은 위험은 본 장면의30k 완주와 최종 기하/RGB 품질 미확인이며 `scientific_verdict: null`이다.

## SFM-FINAL-RESOURCE-001 — P1/P3 마지막 자원 구현의 학습 메모리 한계

상태: `UNRESOLVED_RESOURCE_LIMIT_NO_FURTHER_P1_RETRY`. P1의 고정 마지막 시도 `no_anchor_sfm_gradient_memory_v3_P1/runs/P1/SFM_noanchor_D005_Pnative/receipt.json`은 native1·FAIL, driver3254.0149105349556초다. `model/jbgs_memory_recovery/receipt.json`의 마지막 완료10608 뒤10609 renderer backward에서 CUDA OOM이 발생했다. 원 로그는1.16GiB 요청, 가용10.38MiB, PyTorch allocated22.93GiB를 보고한다. 마지막 정규10600 trace의 Gaussian 수6,495,677과 정확한 마지막 완료 횟수를 구분한다.

이전 gradient의 다음 forward 전 해제와 CPU state offload는 실제 적용됐지만 장면 학습의 메모리 한계를 해소하지 못했다. 전체 trajectory는 과거 반복과 달라 같은 iteration의 자원 변화만으로 단일 원인을 확정할 수 없다. GPU1에는 기존 desktop compute가 없었으며 원 OOM·현재 OOM·의도적 종료·저장 중 host cgroup OOM을 구분한다. P1은 사전에 고정한 추가 fresh1회 상한에 도달했으므로 새 제한값·점 개수 cap·해상도 변경으로 다시 시도하지 않는다.22k/30k는 미제공이고 F1=0이나 성공으로 대체하지 않는다. 고정 역사적8k 보조 결과와 모든 실패 상태·비용을 보존한다. `scientific_verdict: null`.

후속 P3 역시 `UNRESOLVED_RESOURCE_LIMIT_NO_FURTHER_P3_RETRY`다. `no_anchor_sfm_gradient_memory_v3_P3/runs/P3/SFM_noanchor_D005_Pnative/receipt.json`은 native1·FAIL, driver2354.3413484441116초다. 마지막 완료8541 이후8542 renderer backward에서1.33GiB CUDA 할당이 실패했고 가용1.18GiB를 보고했다. 마지막 정규8500 trace의 Gaussian 수는7,424,205다. native·독립 supervisor 종료와 host GPU1 compute 부재를 확인했다. P3도 추가 fresh 실행을 하지 않으며22k/30k 미제공과 보존된8k를 구별한다. 과거 P3 storage-v2의11271회 후SSIM OOM, 그보다 앞선 GPU 중복 초기화 실패와 각각 별도 시도다.

## SFM-PREFIX-RESOURCE-001 — P3 CPU 상태 검증의 메모리 압박

상태: `RESOLVED_VALIDATION_ONLY`. 대형 checkpoint/PLY를 읽는 역사적8k CPU 검증의2GiB 제한에서 메모리 압박과 과도한 I/O가 관측됐다. 정확한 P3 검증 컨테이너만2→8GiB로 변경한 뒤 실제 `PREFIX_8000_VALIDATED`로 완료했다. 전후 inspect/cgroup·명령·편차는 `completed_prefix8000_v1/P3/validation/resource_memory_amendment_v1/`에 보존했다. P1 검증은 변경 전에 이미 PASS로 종료했고 P1에 대한 변경 시도는 적용 전에 실패했으므로 P1의 제한을 변경한 것으로 기록하지 않는다. frozen 원 명령과 producer bytes는 보존했으며 학습의32GiB 제한·GPU·과학 설정은 바꾸지 않았다. 실제3지역 상태 검증·공식8k 추출은 PASS지만 원22k/30k 완료를 의미하지 않는다. `scientific_verdict: null`.

## SFM-FINAL-REPORT-OOM-001 — P2 정기 평가 실패로22k 저장 미도달

상태: `UNRESOLVED_RESOURCE_LIMIT_CLOSED_NO_FURTHER_RETRY`, 2026-09-09 21:51 UTC. 마지막 P2의22,000번째 optimizer update는 반환했으나 그 다음 `training_report → renderFunc → rasterizer forward`가11.04GiB 할당 요청에서 CUDA OOM으로 실패했다. 가용8.62GiB, PyTorch allocated13.91GiB, reserved-unallocated202.79MiB를 원 로그가 보고했다. native/validated1, driver13,834.020002713893초, peak child RSS14,222,950,400byte다. 원 receipt SHA`65ed9d68de101e693f5d2f3b3a636085286d61b6a0ef22f541af291ce05ed9af`, native log SHA`175e501ff29aa6e46d5dd1c11e2bacf3125b287f7961fe451926d5060a56f462`를 보존한다.

원 순서는 optimizer update → 정기 평가 → 일반 PLY 저장 → iteration 경계/complete capture다. lifecycle은 전체 경계 마지막21999와 active22000/GPU_READY를 기록하고, 마지막 정규 trace는21900이다. 따라서22k optimizer 호출 반환, 전체 iteration 경계 완료, 디스크에 검증 가능한22k 상태를 구분한다.22k PLY/complete receipt는 없고 마지막 완전 저장은15k다. 고정22k preview 정책은 실행 gate 미충족으로 미실행이다. 일부 정기 평가 이미지5파일은 셔플된 test 카메라의 부분 출력이어서9장 갤러리나 고정photo0로 사용하지 않는다.

자원 wrapper는 정기 평가 전에 GPU moments/현재 gradient를 추가로 비우지 않았다. 소스와 lifecycle에서 moments4,795,045,136byte/GPU_READY 보관이 확인되지만, 이를 전체 OOM 메모리 분해나 새 조치의 성공 예측으로 확대하지 않는다. 평가·저장 경계가 현재 복구의 미해결 구현 요인이다. 기존 desktop의260MiB 점유만으로 약2.42GiB의 보고된 요청-가용 차이를 설명할 수 없으며 서비스를 변경하지 않았다.

P2 native와 독립 supervisor가 exit1로 닫혔고 GPU0 학습 프로세스가 사라졌다. queue/supervisor의 status.txt에 남은 TRAINING/RUNNING 문구는 이전 단계 표기이며 닫힌 receipt를 우선한다. 지역당 추가 fresh1회 상한에 도달해 다시 학습하지 않는다. P1/P3도 이미 종료됐으므로 주22k/30k 전체를 미제공으로 발행하고 별도 역사적8k 실제 결과를 유지한다. 이 기술 실패는 Anchor의 인과적 필요성을 입증하지 않는다. `scientific_verdict: null`.

## SFM-RESOURCE-FLAG-001 — CUDA 오류 문자열의 보조 host-memory flag 오탐

상태: `RESOLVED_ADDITIVE_CORRECTION`. 최종 비용 읽기 감사에서 `summarize_resources.py`의 host-memory 감지가 부분 문자열 `MemoryError:`를 사용해 `torch.cuda.OutOfMemoryError:`에도 일치함을 발견했다. 원 `termination_reason`은 CUDA를 먼저 판별하므로 정확했고, 비용·실패 여부·viewer·기하/RGB 수치에는 영향이 없다. 잘못된 보조 `host_memory_failure_observed_in_log`를 독립 CPU OOM 증거로 해석하면 안 된다. cgroup OOM은 원 커널 증거와 별도 verified 필드로 판단한다.

재사용 소스의 해당 판별만 정확한 CPU 예외명/token 일치로 수정했다. 원 발행 source/CSV는 보존하고 새 `evaluation/no_anchor_sfm_v1/resource_flag_correction_v1/new_failed_training_attempts.corrected.csv`를 Docker CPU에서 생성했다.12행 중 CUDA 실패8행의 해당 flag만 True→False이며 다른 열·순서·원인·비용은 그대로다. CPU/CUDA 오류 구분과 원본 대비 변경 범위를 검증했다. 실제 실행은 `PASS_HOST_MEMORY_FLAG_CORRECTION`; receipt SHA`ed31ed8b06d3f85f380b6199c601fda9494ed2bc2cd5412a2e3dbc4c325dd82f`, 정정 CSV SHA`f2ca7d475ea67182760b5ebb0f2487bba0956fae137b5f182f5c3b5e3f5555b3`다. 같은 폴더에 code/config/command/log/exit0을 보존했다. 전체 결과를 재발행하거나 학습을 다시 실행하지 않았다. 비용 `closed_costs_v1`은 이 flag를 계산·출력에 사용하지 않았으므로 기존 합계가 유지된다. `scientific_verdict: null`.

## INPUT-DA3-001 — DA3 깊이 입력의 배치별 척도·이동 파손 (2026-09-10 사후 확인)

봉인 학습 입력 `inputs/P*/da3/raw_depth`를 동결 UAS 참조와 prior 광선투사 깊이로 뷰별 강건 affine 대조한 결과, 잔차 <1 m·|s−1|<0.05 를 만족하는 뷰가 P1 0/98, P2 8/57(배치 0), P3 12/137(배치 0·15·16)뿐이다. 나머지는 s 0~2.9, t ±300 m, 잔차 5~78 m 이며 P1 47뷰·P3 32뷰는 DA3가 상수에 가깝다. 정상 배치는 모두 연직·동질 배치다. 학습은 `use_scale_invariant` 없이 metric L1(λ .05)로 이 지도를 소비했고 dual gate는 대부분 .05 를 유지했다. 주18개 결과의 기하 해석(P1 들뜸, P3 실내 띠, P2 지면·수목 붕괴)은 이 결함과 분리되지 않는다. 기존 산출물은 변경하지 않았다. 상세 = [DA3 입력 정확도 감사와 기각 조건 검증](DA3_INPUT_ACCURACY_AND_KILLTEST_ko_v1.md). `scientific_verdict: null`.

## VIEW-P2-FOCUS-001 — 표시 확대 검사 경계의 소수점 판정

상태: `RESOLVED_DISPLAY_AUDIT_ONLY`, 2026-09-10. P2 확대 화면을 캡처하는 첫 검사에서 `scrollIntoView` 이후 패널 y=−0.25px를 음수라는 이유로 거부해 `Row not fully visible`로 종료했다. 원 viewer 또는 후보 로딩 실패가 아니다. 전체 viewport 캡처로 바꾼 별도 v2 출력은 `PASS_DISPLAY_INSPECTION`, PNG4개와 동일 카메라·서로 다른 후보 확인을 완료했다. 원 시도 v1의 code/log/receipt는 보존했다. 부수 읽기 명령의 host `jq` 부재는 Docker Node로 대체했다. 새 학습·평가 수치 변경·공유 앱 변경은 없다. 상세: [표시와 Anchor 통제 분석](P2_VIEW_VISIBILITY_AND_ANCHOR_CONTROLS_ko_v1.md). `scientific_verdict: null`.

## INPUT-DA3-002 — INPUT-DA3-001의 배치 파손 귀속 및 가림 감사 정정

상태: `ATTRIBUTION_CORRECTED_INPUT_ACCURACY_REMAINS_OPEN`, 2026-09-10. 동일RGB·K·표정의 두 사진쌍에서 배치 간 원 깊이 절대차 중앙값은0.885m와0.136m이나, 기존 지역별 참조 비교 차이는 훨씬 크고 비교 참조 깊이도 달랐다. prior 역시context영역만으로 만든표면이라 외부앞가림물을보장하지않는다. “같은자세raycast이므로가림정확”, “P1 전뷰등은미터깊이가아님”, “whole DA3 map이상수”의 확정해석을 철회한다. 기존 INPUT-DA3-001과 원 산출물은 역사기록으로보존한다. 실제사진/깊이8그림을 Docker에서 생성·확인했고P1 수직에가까운사례에는약2.5m불일치가남아 정확성검증은계속필요하다. 새추론·학습·정합·원결과변경은없다. 상세: [귀속 정정 및 시각 확인](DA3_AUDIT_INTERPRETATION_CORRECTION_ko_v1.md). `scientific_verdict: null`.

## DA3-REPORT-001 — 정성 검토 HTML 패키저 크기 상한

상태: `BLOCKED_PORTABLE_REPORT_PAYLOAD_LIMIT`. Docker에서 원입력 비교 PNG8개·summary·notebook 생성은PASS/exit0이다. 이를 내장한 canonical HTML 보고서 포장은 처음 chart 필수, 다음 query provenance 조건으로 실패했고, 마지막은 payload3,000,000byte 상한으로 거부됐다. 마지막 실패 후 추가 포장 시도를 중단했다. 원 PNG를 줄이거나 원입력을 변경하지 않았다. task/input_diagnostics_v1/da3_visual_review_v1/report에 artifact.json/source/시도별 로그를 보존한다. HTML 완성으로 표시하지 않으며 실제그림 직접링크와 DA3_AUDIT_INTERPRETATION_CORRECTION_ko_v1.md를 제공한다. 과학 수치·원결과에 영향없음. `scientific_verdict: null`.

## DA3-SPATIAL-001 — 공간 셀의 DA3·결과 집계 참조점 불일치

상태: `RESOLVED_ADDITIVE_SAME_POINT_MAPS`, 2026-09-10. `evaluation/da3_refinement_spatial_v1/`의 최초 셀 지도는 DA3 편차를 strict 상부 참조점에서 집계했지만 결과 거리변화는 같은 XY 셀의 모든 높이 참조점에서 집계했다. 따라서 이 두 지도의 겹침과 로그의 `cell_spearman`은 정확히 같은 점 집합의 대응이 아니다. 원점별 `error_cohort_transitions.csv`와 paired NPZ는 동일 참조점 계산이라 영향이 없고 독립72행 검증도 일치했다.

원 CSV·로그·PNG를 보존하고 `strict_correspondence_v1/`에 새 소스/설정/명령/receipt와 동일점 지도·셀 CSV를 생성했다. 세 지역 모두 DA3·거리변화·조건 대비에 같은 strict 참조점 ID를 사용함을 검사했고 `PASS_SAME_POINT_CORRESPONDENCE`, exit0이다. 원 셀상관계수는 본문 근거에서 제외하며 원 지도는 모든 높이 주변 결과의 맥락용으로만 남긴다. 실제 같은점 지도와 cohort 그림을 열어 확인했다. 새 학습·입력·원 표면 수정은 없다. DA3 단독 인과 효과와 외부 가림 불확실성은 미해결이며 `scientific_verdict: null`이다.
