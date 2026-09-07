# P1·P2·P3 공식 GeoGS 진단 실험계획 v1

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · 비확증 개발 실험 · `scientific_verdict: null`

이번 사용자의 지시는 계획 구체화부터 공식 원방법 실행, 제어 변경, 정량·정성 분석까지 포함한다. 이 문서는 그 범위를 실행 전에 구체화한다. 기존 E1–E6 조건·phase와 다른 별도 GeoGS 진단이며, 아래 P1/P2/P3는 **기존 세 공간 crop**이다. 연구 phase P1–P3를 다시 실행하는 의미가 아니다. 사용자가 지정한 공식 학습·렌더러·추출 경로를 사용하므로 이번에만 공식 diff-surfel-rasterization을 사용한다. 정본의 gsplat 구현 정책이나 기존 연구 결과는 변경하지 않는다. 동일 호스트의 새 경로에서 수행하며 two-host 쓰기 소유권 이전은 없다.

## 1. 확인하려는 작동 원리

같은 과거 ALS에서 만든 구조로 GeoGS의 anchor를 만든다. 그 동일 상태에서 prior 깊이에 맞추라는 요구와 구조 보호를 각각 바꾸어 refinement한다. 현재 관측에 맞는 표면·외관의 회복과, 유용한 구조의 손상을 함께 본다. 어느 지역 전체도 영상 또는 ALS가 정답이라고 미리 지정하지 않는다. 새 선택 알고리즘과 반복 재판단은 구현하지 않는다.

공식 GeoGS가 이미 제공하는 구조 안정화, 영상 세부 복원, 오류·부분 결손 LoD 실험을 인정한다. 전문은 이번에 제공된 PDF로 확보되어 있다. 기존 문서의 ‘전문 미확보’는 당시 접근 상태다. [원문 감사](PAPER_AUDIT_ko_v1.md)는 페이지별 근거와 제한을 기록한다. 특히 원문의 prior 손상 실험은 초기점과 깊이를 다시 생성하며, 이번 동일 anchor 이후 제어 변경과 구별된다.

## 2. 시작 상태와 보존

- 작업 HEAD: `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`. 기존 수정·미추적 연구 파일과 8876–8901 등의 서비스가 존재한다. 기존 파일 내용·서비스 ID 목록을 새 외부 경로의 `preservation/`에 기록한다. 기존 파일을 stage/commit하거나 서비스를 재시작하지 않는다.
- 원확보 GeoGS: `../JointBuildGS-artifacts/phase-payloads/phd/geogs_contribution_v1/PHD-GEOGS-CONTRIBUTION-v1/sources/GeoGS`. 실제 HEAD는 지정 커밋 `db40c95c657ec03ff21c83cb99cf39f4e90247a6`, working tree는 clean이다. CUDA submodule은 원확보 경로에 미초기화 상태였으므로 새 사본에서만 확보한다.
- 공식 renderer `e0ed0207b3e0669960cfad70852200a4a5847f61`, simple-knn `86710c2d4b46680c02301765dd79e465819c8f19`를 결박한다. 원본·실행 보완본·제어 변경을 SHA와 patch로 분리한다.
- 기존 GeoGS 장면 학습·렌더·메시: **0회**. 이전 CPU 합성 제어 진단과 Wu–Vallet 결과는 성능 결과로 전용하지 않는다.
- 신규 코드/설정/문서: 각 소유 디렉터리의 `phd/geogs_p1p2p3_v1/`. 외부 출력: `phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/`. 기존 출력 재사용은 읽기 전용이며 신규 실행 디렉터리는 존재하면 실패한다.

## 3. 입력 계약

[기계 판독 설정](../../../../configs/phd/geogs_p1p2p3_v1/experiment_v1.json)에 경로·해시·범위·조건·완료 기준을 둔다. 실행 전 입력 영수증에서 실제 파일 해시와 행 대응, 누락을 확인해야 한다.

| 지역 | scene-local x / y / z 범위(m, 상한 미포함) | 기존 RGB | 학습 / 평가 |
|---|---|---:|---:|
| P1 | [-23,7) / [-21,9) / [-44.272,-25.962) | 113 | 98 / 15 |
| P2 | [110,158) / [86,132) / [-49.386,-17.679) | 66 | 57 / 9 |
| P3 | [-60,-20) / [-42,12) / [-49.223,-16.993) | 157 | 137 / 20 |

기존 정확한 1400×1013 undistorted RGB와 카메라를 사용한다. 파일 이름 정렬 후 0부터 8의 배수 index를 평가로 떼는 공식 `--eval`, `llffhold=8` 규칙이다. 실제 명단을 저장하고 로더 결과와 대조한다. 같은 지역의 모든 조건에 정확히 같은 RGB·pose·초기점·prior/DA3 깊이를 사용한다. 원 RGB를 재보정하거나 UAS로 카메라를 고치지 않는다.

기존 카메라·영상 기하의 생산 과정은 전체 개발 관측에 기반하므로 새 관측을 완전히 봉인한 독립 획득 실험이 아니다. 평가 RGB는 이번 GS 최적화·DA3·색 초기화에는 사용하지 않는다. 여러 crop의 영상도 중복된다(P1/P2 31, P1/P3 107, P2/P3 30). 세 crop 평균을 독립 장면 일반화 통계로 해석하지 않는다.

작업 좌표는 EPSG:25832, 기존 world shift [690953,5336071,604]와 ALS Z bridge +45.7m를 그대로 결박한다. UAS header EPSG:32632와의 datum/epoch 해석은 미해결이다. UAS로 정합 보정하거나 최적 설정을 선택하지 않으며, 동일 좌표 처리에서의 참조 편차로 보고한다. 보정 완료된 절대 정확도라고 주장하지 않는다.

수직 bridge의 기존 근거는 [projection datum 설정](../../../../configs/input_and_alignment/projection_datum.json)의 GCG2016 `45.700`과 [이전 방법론 §1.6](../../../research/methodology/기준문서_방법론·모집단·비교설계_v1.md)의 DHHN2016→타원체고 해석이다. 과거 카메라 높이 해석에는 ALS/참조 모델 대조 이력이 있으며, 이번에 새 UAS 정합으로 검증한 값은 아니다. 이전 QA의 작은 잔차를 이번 세 crop의 UAS 절대 정확도 인증으로 옮기지 않는다.

### ALS 입력 변환

GeoGS 원입력은 정합된 LoD2 mesh다. 이번 세 crop은 **ALS 표면 입력 변형**이며 ‘원 LoD2 성능 재현’이라고 부르지 않는다. 공식 예제는 원입력 실행 경로 확인에만 쓴다.

기존 ALS acquisition 원점/strip/return/scan/beam 대응에서 crop XY+25m, Z[-90,80)m의 공통 문맥을 읽는다. 기존 scan–beam 삼각망 생성 규칙(max scan gap 1, beam-coordinate gap 32, 3D edge 2m)을 그대로 사용한다. 수직면을 자동 제거하는 높이차 문턱이나 UAS 유도 mesh 보정은 넣지 않는다. 취득 메타데이터의 추정 요소, 탈락 삼각형·미표현 점·구멍·잘못된 연결 가능성은 변환 영수증과 그림에서 별도 평가한다.

파생 표면에서 공식의 면적 비례 초기화·가시성 필터·prior raycast 경로를 연결한다. 수치 파라미터와 초기화 색의 입력 영상 목록을 결박한다. 보호 점군은 같은 prior 표면에서 만든다. 모든 arm에 같은 파생 바이트를 준다. 원 ALS, 파생 prior mesh, 영상 기하를 각각 UAS와 비교하여 변환 손실을 최적화 효과와 구별한다.

원문은 ray distance라고 설명하지만 공개 LoD2Depth의 Open3D pinhole raycast는 camera-Z를 생성하는 경로다. renderer의 깊이, K/R/t, 저장 배열의 NaN·단위·축을 synthetic camera와 실제 투영 왕복으로 확인한 뒤 실행한다. 단순히 두 depth 배열 크기가 같다고 정합되었다고 보지 않는다.

### DA3

공식 전처리와 `depth-anything/DA3NESTED-GIANT-LARGE`, process-res 840, 원해상도 복원을 기준으로 한다. RTX3090 24GiB에서 전체 137 train뷰 동시 처리를 가정하지 않고, 정렬된 **train-only 연속 8뷰 배치**를 사전에 규정한다. 각 배치의 metric pose conditioning을 유지하며 정확한 명단·모델 revision·weight hash를 기록한다. 전체 영상 동시 추론과 다른 전처리 조건이라는 점을 표시한다. 기존 예제 DA3의 평가영상 참여 여부는 미확인이며, 예제 지표를 독립 novelty-view benchmark로 승격하지 않는다.

메모리 preflight가 실패하면 오류를 보존하고 전체 지역에 적용할 전처리 수정안을 **학습 결과를 보기 전에** 새 설정 revision으로 기록한다. 지역별로 유리한 DA3 설정을 선택하지 않는다. 평가 RGB와 UAS는 전처리 컨테이너에 제공하지 않는다.

**입력 검사 후 확정된 revision 2:** 원래 마지막 2뷰 배치에서 공식 pose-scale 정렬이 rank 부족으로 실패했다. 세 지역 모두 정렬된 학습뷰를 `ceil(N/8)`개의 연속 균등 배치로 나눈다. 실제 배치는 7·8뷰이며 카메라 중심 rank는 모두 3이다. 배치 사이 메모리 해제만 추가하고 모델·840 해상도·seed·학습/평가 명단은 유지한다. 실패 출력과 실행 당시 설정 snapshot을 보존하며 최종 실제 명단은 `scene/split_manifest_da3_v2.json`이다.

## 4. 비교 조건과 학습량

모든 지역에 seed 0, anchor 8,000회 + refinement 22,000회 = 총 30,000회를 적용한다. Anchor prior 깊이 계수 0.08, DA3 시작 0.05 및 공식 dual gate를 유지한다. 동적 stage switch와 optional Gaussian completion은 기본 비활성이다. 다른 optimizer·densification·normal·distortion 기본값도 고정 커밋에서 상속하고 실제 CLI/default 전체를 저장한다. 논문과 코드의 수치 근거를 혼합하지 않는다.

| 조건 | refinement prior 깊이 계수 | 구조 보호 | 직접 비교 목적 |
|---|---:|---|---|
| D005_Pnative | 0.005 | 원설정 | ALS 입력 변형의 GeoGS 바닐라 |
| D0005_Pnative | 0.0005 | 원설정 | 깊이 요구 1/10 |
| D0_Pnative | 0 | 원설정 | 깊이 손실만 제거 |
| D005_Prelease | 0.005 | 해제 | 보호의 추가 효과 |
| D0005_Prelease | 0.0005 | 해제 | 낮은 깊이 요구와 해제 조합 |
| D0_Prelease | 0 | 해제 | 두 refinement 제어 해제 |

‘해제’는 위치·회전·크기 gradient 배율 1과 보호 대상 clone/split/prune 제외의 해제를 뜻한다. 다른 densification·opacity 규칙과 DA3 제어는 유지한다. `--protect_bldg`만 끄면 위치 보호가 남으며, `--freeze_onlybldg`를 제거하면 전체 densification을 멈추는 다른 조건이 되므로 그런 우회는 사용하지 않는다. 두 보호 구성요소의 개별 인과 효과는 이 6조건만으로 분리하지 않는다.

계수는 원설정/10배 감소/0이라는 사전 기제 대비이며 최적값 탐색이 아니다. 마지막 조건도 ALS 초기화와 8,000회 anchor가 남아 있으므로 image-only가 아니다. 처음부터 학습하는 보호 없는 비교는 이번 primary matrix가 아니며, 추가하면 다른 실험으로 기록해야 한다.

## 5. 동일 anchor와 공식 실행의 검증

공식 `capture/restore`는 model·optimizer 등을 저장하지만 보호 mask/hook, DA3 controller, RNG, 카메라 순서와 잔여 view stack을 저장하지 않는다. 8,000회 checkpoint 저장은 보호 등록 전이고 일반 PLY 저장은 그 회차 densification 전이다. 따라서 `--start_checkpoint` 또는 일반 8,000 PLY만으로 동일 anchor라고 할 수 없다.

원 source를 보존한 별도 실행 보완본에 완전 상태 저장·복원만 추가한다. 8,000회 optimizer·densification·보호 등록 완료 후 model/optimizer, radii/gradient accumulators, SH/lr scale, mask/hook 적용 상태, stage/DA controller, Python/NumPy/Torch CPU·CUDA RNG, 실제 카메라 순서/잔여 stack을 저장한다. 조건 변경은 이 상태에서만 적용한다. anchor 표면도 이 정확한 상태에서 렌더·추출한다.

원본 연속 실행 → 상태 기록만 추가한 연속 실행 → 같은 상태 재개 바닐라의 파라미터·optimizer·mask·렌더 배열을 대조한다. CUDA 누적 비결정성은 실제 오차와 함께 기록하고 복원 상태 자체의 불일치를 수치 허용오차로 숨기지 않는다. 이 검증 실패 시 6조건 결과를 동일 anchor의 인과 효과로 보고하지 않는다.

실제 검사에서 독립 전체 궤적과100회 연속/재개는 exact하지 않았고, **optimizer 실행 전 복원 상태·보호 hook·같은 checkpoint에서 저장한 PLY의 렌더 비교는 exact 검사를 통과**했다. 이어진 한 native step은 예상 회차·카메라/잔여 stack·Python RNG, Adam step counter의1 증가, Gaussian/보호 개수 유지와 모델/loss 유한성을 확인한 `PASS_ONE_NATIVE_STEP`이다. **갱신 후 모델·Adam tensor 전체를 독립 연속 실행의 같은 step과 대조한 검사가 아니므로 한-step bitwise parity를 입증하지 않는다.** [상태 검증 기록](STATE_VALIDATION_ko_v1.md)의 세 지역 gate와 검사 소스에 범위를 구분했다. 같은 anchor gate는 정확한 출발 상태와 한-step 실행 건전성을 확인하며 이후 궤적의 bitwise 동일성을 뜻하지 않는다. 작은 조건 차이에 수치 실행 변동이 포함될 가능성을 남기고 안정적 인과/성능 효과로 승격하지 않는다.

**UAS 평가 전 추가한 동일 조건 반복 진단:** P1의 보존된 원 시도와 allocator_v2 재실행을8100–14400회 공통 구간에서 비교했다. 카메라 순서는 같지만 같은 조건의 Gaussian 수 차이는 원 가중치에서 최대10.59%, 1/10 가중치에서11.73%였다. 이는 allocator 및 연속/재개 이력 차이도 포함한 학습 궤적 진단이며, 표면·렌더 품질의 변동 폭 또는 allocator의 단독 인과 효과가 아니다. 원자료와 실제 그림은 외부 `runtime/p1_common_prefix_14400_v1/`에 봉인했다.

이 관찰을 근거로 **P1/P2/P3 각각 바닐라를 동일 allocator·동일8000 anchor·동일seed에서 한 번 추가 실행**한다. 여섯 primary 조건은 그대로 두고 별도 반복 경로와 계약에 기록한다. 바닐라 첫 실행과 반복 실행의 최종 원/후처리 표면 및 평가뷰 지표를 같은 방식으로 비교하며, 더 좋은 실행을 선택하거나 primary 바닐라를 교체하지 않는다. 두 실행의 차이는 제한된 반복 관찰이며 통계적 잡음 상한·신뢰구간·다중 seed 안정성으로 부르지 않는다. 반복 세 결과도 평가 전에 봉인한다. 이 추가 검증은 UAS 또는 평가뷰 품질 점수를 보기 전에 결정했으며, 추가 학습비용을 별도로 기록한다.

## 6. 실행 순서와 자원

1. 보존 ledger, 공식 코드/submodule/PDF hash, 입력·CRS·split·깊이 단위 감사.
2. 별도 Docker 환경에서 CUDA 모듈 import와 렌더 gradient preflight. 기존 서비스는 유지한다.
3. 사전 확보 공식 예제를 새 경로에 검증 추출하고 원 학습→render.py→TSDF→metrics.py 실행을 확인한다. 제공된 참조는 평가에만 별도 연결한다. 원 예제의 완전 전처리 재현 여부는 별도 표시한다.
4. ALS/카메라/DA3 변환과 depth·투영 검사. 참조 없는 입력 검증을 통과한 후 입력 패키지와 실제 설정을 봉인한다.
5. 지역별 P1→P2→P3 순서로 바닐라 연속 anchor·완전 상태 저장 후 조건표 순서로 분기한다. parity 재개 검증을 선행한다. 초기 원설정 실행은 GPU1 한 개다. 입력 생성 완료 후 GPU0도 사용할 수 있으며, 참조 없는 메모리 검사와 호스트 여유 확인을 통과하면 GPU당 한 학습, 최대 두 학습까지 병렬 실행한다. 같은 지역의 공유 anchor와 조건·학습량은 변하지 않는다.
6. 모든 조건의 원/후처리 mesh와 실제 평가뷰 렌더를 봉인한 후 UAS 평가를 수행한다. 결과에 따라 조건을 재조정하지 않는다.
7. 기계 판독 표·원자료, 동일시점 뷰어·단면·사례 그림, 원인 분석과 다음 세션 인계를 작성한다.

현재 GPU는 RTX3090 24GiB 2장이고 조회 시 학습 점유가 없었다. Host RAM 가용 약54GiB, 외부 디스크 약2.3TiB, Docker root 디스크 여유 약31GiB다. 초기 CPU 8·RAM 32GiB·GPU1로 제한한다. 저자 RTX4090 시간은 우리 예상 시간으로 옮기지 않는다. 실제 예제의 단계별 wall time·peak CUDA/RSS·출력 크기로 세 지역 자원을 산정한다. 공간/메모리 부족 시 실패 receipt를 남기며 기존 container/image/volume을 정리하지 않는다.

**P1 OOM 후 실행 자원 revision `allocator_v2`:** 원설정과 깊이 계수0.0005 조건이 GPU 메모리 부족으로 종료되어 기존 `runs/`, `parity/`, `queue/`를 보존했다. [별도 실행 경로 계약](../../../../configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json)은 모든 새 조건에 `PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128`을 적용하고 `runs_allocator_v2/`에 기록한다. 과학 설정·입력 seal·학습 source·해상도·densification·학습량은 그대로다. P1의 새 바닐라를 포함한 여섯 조건 모두 기존 정확한8000 anchor에서 재개하므로, P1 바닐라의 완료 결과는 처음부터 연속 학습한 결과와 구분한다. P2/P3 바닐라는 새 자원 설정으로 처음부터 학습한다. 복원/한 단계 검증은 통과했으나 이후 OOM 해소는 실제 완료 여부로 확인한다. 실패 시도 비용은 성공한 조건의 refinement 비용과 별도 기록한다.

지역 표면 추출을 시작하기 전에 `render`와 `auxiliary` phase는 호스트 전체에서 task-local lock으로 한 건씩 실행하도록 정했다. 두32GiB 상한을 동시에 모두 사용한다고 가정하면 기존 서비스의 여유 메모리를 침범할 수 있기 때문이다. 실제 동시 TSDF OOM이 발생한 것은 아니다. 학습은 기존 최대 두 건을 유지한다. 새 잠금 파일은 task의 metric weights 디렉터리에 별도로 생성하며 기존 weight 파일은 변경하지 않는다. `runtime/prepare_execution_lock.sh`가 기존 inode를 교체하지 않고 준비한다. native CLI·해상도·mesh 파라미터는 같고, 잠금 대기 시간은 실제 phase 계산 시간과 따로 기록한다.

## 7. 정량 평가

최종 기하의 primary는 **실제 렌더 깊이를 공식 bounded TSDF로 융합한 raw mesh**다. 공식 postprocessed mesh도 별도 보고해 component 제거 효과를 드러낸다. `mesh_res=1024`, depth truncation=공식 train-camera radius×2, voxel=truncation/1024, sdf=5voxel을 사용하며 같은 지역의 모든 arm에 같은 값을 적용한다. 원·후처리 결과를 모두 보존한다. 512/2048 추출 민감도는 모든 최종 조건에 같은 규칙으로 수행한다. 구현 오류 수정이 필요하면 패치와 영향 범위를 공개한다.

| 평가 대상 | 지표와 통제 |
|---|---|
| 원 ALS / 파생 prior mesh / 영상 기하 / anchor / 6조건 최종 mesh | 각 source의 생산 계보를 표시하고 같은 공간 범위·참조로 비교 |
| 기하 정확도·완전성 | 양방향 거리의 mean/median/P95/RMSE, precision/recall/F1@0.1/0.2/0.25/0.5/1/2m. 참조→mesh는 삼각형 표면 거리, mesh→참조는 면적 비례 표본과 동일하게 voxel한 참조 거리. pointset baseline의 NN과 연속 표면 거리는 유형을 구별 |
| 밀도 민감도 | mesh 면적 비례 0.1m 상당 표본밀도, 참조 voxel 0.1m. 양쪽 0.05/0.2m 민감도. 원 ALS·MVS점 자체도 별도로 보존. 표본 수와 seed를 저장 |
| 결손·잔존·다중층 | 참조 지원 0.5m XY셀의 출력 결손, 같은 XY에 여러 높이층, 참조에서 먼 표면 면적과 단면. 과거 구조 잔존의 시간적 해석은 실제 사진·계보와 대조. NN 임계값으로 변화 정답을 자동 생성하지 않음 |
| 실제 렌더 | 이번 최적화와 DA3에서 제외한 평가 RGB의 PSNR/SSIM/LPIPS, 이미지별 원자료 및 평균. 전체 원사진과 입력 prism을 투영한 고정 ROI를 병기하여 주변 배경이 점수를 지배하는 효과를 확인 |
| 자원 | 전처리·anchor·refinement·렌더·추출·평가 각각 wall time, CUDA peak allocation/reservation, peak RSS, 출력 bytes. 공유 anchor 비용과 조건 추가 비용을 분리 |

참조 피복이 없는 곳은 `NOT_ASSESSED_REFERENCE_ABSENT`, 참조가 있는데 결과가 없으면 `RECONSTRUCTION_FAILURE`다. 가림과 참조의 센서 지원이 불명확한 예측점은 단순 오차 정답으로 처리하지 않는다. 참조 지원 지도·경계 제외 규칙과 분모를 함께 제공하며, 전체 프레임/ROI와 pointset/mesh 지표를 섞어 한 순위를 만들지 않는다.

기존 개발 사례를 고정한 단면과 함께 모든 영역의 수치를 보고한다. ‘수정 필요/유지/관측 부족’은 사후 진단 층이며 학습 weight나 조건 선택에 사용하지 않는다. 실제 사진 및 입력 자체의 관측 지원과 독립 평가 참조를 구분하여 근거·불명확 상태를 기록한다. 영역 전체 평균과 층별 개선·악화를 모두 보고한다. 단일 F1 개선으로 전체 품질 개선을 선언하지 않는다.

## 8. 정성 결과와 검증

동기화된 비교 화면에 prior·영상 기하·anchor·GeoGS 바닐라·변경 결과·UAS를 같은 3D 카메라/축척으로 표시한다. raw/post surface 전환, 표시용 감축률, 원자료 경로를 제공한다. 실제 평가 사진과 동일 pose의 렌더를 나란히 보여주고, 표시용 점군을 GS 렌더라고 부르지 않는다.

기존 개발 단면 P1 X=-8/Y=-6, P2 X=134/Y=109와 P3 기존 단면을 고정 폭0.5m·같은 축 범위로 재사용한다. 참조 거리 지도, anchor→refinement, native→변경의 개선/유지/악화/판단불가 사례를 모두 포함한다. 사전에 고정한 위치와 체계적으로 선택한 최상·최악·중앙 사례를 구별하고 각 선택 이유를 저장한다. P1/P2 과거 상부면 잔존과 낮은 현재 표면, P3 곡면 피복·아래쪽 오류면·세부를 확인한다.

새 포트 또는 파일 경로와 조작법을 제공한다. 브라우저에서 실제 로드, 지역/조건 전환, 3D 동기화, 렌더/단면 이미지, 누락 표시를 확인하고 screenshot·console/network 오류를 기록한다. HTTP 200만으로 표시 검증을 대체하지 않는다.

## 9. 보고와 완료 기준

분석은 **관찰 현상 → 구현/입력 변환/제어 영향 → 원문과의 관계 → 추가 수정 필요성 → 후속 검증 질문** 순서다. 보호 완화로 회복해도 반복 재판단의 필요성이나 우위가 입증된 것은 아니다. 추후 같은 판단을 한 번 적용한 조건과 반복한 조건을 비교해야 한다.

완료하려면 세 지역×6조건과 평가 전에 추가한 세 바닐라 반복의 실제 학습·표면·평가뷰 렌더, 정량 CSV/JSON/거리 원자료, 단면/거리 지도/사례 그림, 표시 확인된 뷰어, 편차·실패 기록, 분석, 재현 명령과 다음 세션 인계가 모두 있어야 한다. 계획·문헌 감사·공식 예제 성공만으로 이 완료 조건을 충족하지 않는다. 일부 gate가 막히면 완료 상태를 `PARTIAL`로 두고 실행한 것과 빠진 결과를 명시한다. 모든 영수증의 `scientific_verdict`는 null이다.
