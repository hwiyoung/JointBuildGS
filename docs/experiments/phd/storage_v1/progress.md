# PHD-STORAGE-v1 progress

Task: phd 산출물 공간 정리(회신 "서버 저장공간 정리와 저장 규칙 변경")와 저장 규칙 변경(회신 "저장 규칙 변경 진행 방식"). `scientific_verdict: null`.

## 1. 공간 정리 보고 (2026-11-13)

### 2절 확인 결과

| 계열 | 진행 중 네 작업(trainunit·trainlog·trainerr·judgecheck_v2)이 읽는가 | 뷰별 맵 종류 |
|---|---|---|
| target | 읽음: `r5/runtime/maxid_build/*.so`, `rfix_speed/builds/*.so`, `r8/meshes` | D 남김이라 판정 안 함 |
| farpull | 안 읽음 | (1) 학습 모델에서 렌더: `final_mesh_gpu.py:33-35`(frames), `renders/…/iteration_30000/train`, `dump/iteration_N` |
| losstrain | 읽음: fork r23·r27 `jbgs_mv_early.py:35` → `direct_stage1_v2/*/evaluation.npz` | 판정 안 함 |
| stage0~3·fixtest | 읽음: stage0 폴더 통째로 실행 중 trainunit 컨테이너가 `/p`·`/s0`로 마운트, stage3 `nojudge_ALS_s0` `iteration_15000`(trainlog `cv2_mesh.py:19`, `cv2_prep.py:15`), stage1 `defs` | 판정 안 함 |
| judgecheck_v1·photocheck·widen0 | 읽음: judgecheck_v2 파일 103개 | 판정 안 함 |
| gtjudge | 읽음: `runs/*/gt_*_s0`, `targets_gt`, `stage1`, `meshes`, `addendum11·12`; 진행 중 폴더의 심볼릭 링크 115개 | 판정 안 함 |
| finaltrain·release | 읽음: finaltrain 폴더를 실행 중 컨테이너가 `/ft`로 마운트, `tu_cause.py:401`이 `jbgs_complete` 체크포인트를 읽음; release `bin/*.so` | 판정 안 함 |
| fill·fix·baselines | 읽음: baselines `imgonly_2dgs_s0` `iteration_7000·30000`, `geogs_ALS_fix1` | 판정 안 함 |
| prep_discard_rule·prep_measure | 읽음: judgecheck_v2가 `residual_samples.npz` | 판정 안 함 |

### 계열별 지운 양 (GiB, inode 기준 블록 크기)

| 계열 | A 중간 반복 | C checkpoint.pth | D | 지운 양 | 정리 전 크기 | 남은 크기 |
|---|---|---|---|---|---|---|
| target | 127.6 | 24.7 | – | 152.3 | 388.9 | 236.6 |
| farpull | 12.8 | 11.3 | 88.6 | 112.6 | 224.2 | 111.6 |
| losstrain | 25.3 | 20.2 | – | 45.5 | 211.5 | 166.0 |
| stage1 | 0 | 40.3 | – | 40.3 | 168.3 | 128.0 |
| stage2 | 0 | 32.6 | – | 32.6 | 128.2 | 95.6 |
| stage3 | 30.6 | 23.9 | – | 54.5 | 144.7 | 90.2 |
| fixtest | 0 | 24.3 | – | 24.3 | 100.7 | 76.4 |
| gtjudge | 46.6 | 22.0 | – | 68.6 | 203.5 | 134.9 |
| release | 2.8 | 4.2 | – | 6.9 | 18.8 | 11.9 |
| fill | 8.3 | 0 | – | 8.3 | 119.7 | 111.4 |
| fix | 3.8 | 5.1 | – | 8.9 | 59.0 | 50.1 |
| baselines | 0 | 0 | – | 0 | 85.0 | 85.0 |
| **합계** | | | | **554.8** | | |

- 8TB 디스크: 사용 4,925G → 4,374G, 여유 2,096G → 2,646G.
- 지운 파일 목록·스크립트·로그: `JointBuildGS-artifacts/maintenance/phd-cleanup-20261113/` (`del_list.tsv`, `do_delete.py`, `delete_log.tsv`, `df_before.txt`, `df_after.txt`).
- 지운 뒤 확인: 대상 계열에서 지우지 않은 파일 342,113개가 모두 그대로 있다(`kept_check.tsv`: ply·메시, 지표·설정, 그림, 기타별 개수). 건너뛴 파일 0개, 빈 폴더 859개 제거.
- 삭제 직전 확인: 대상 경로를 cwd·열린 파일로 쓰는 프로세스 없음(같은 사용자 프로세스 기준), 대상 계열만 따로 마운트한 컨테이너는 stage0·finaltrain뿐(둘 다 이번에 손대지 않음).

### 표와 다르게 처리한 계열과 까닭

- losstrain: D를 남겼다. 진행 중 학습이 쓰는 fork 코드가 이 계열을 읽는다(2절 가).
- stage0: 아무것도 지우지 않았다(A 8.8 + C 8.0). 폴더 통째로 실행 중 컨테이너에 마운트돼 있다.
- finaltrain: 아무것도 지우지 않았다(A 28.7 + C 11.4). 실행 중 컨테이너에 마운트돼 있고 `tu_cause.py`가 체크포인트를 읽는다.
- target·stage·fill·fix·baselines·gtjudge·finaltrain·prep의 D: 2절 가에서 모두 "읽음"이라 남겼다. 회신 예상(지금 약 1,020G)보다 적은 까닭이다.
- 진행 중 코드가 읽는 실행(stage3 `nojudge_ALS_s0` 11.6G, gtjudge gt 실행 32.7G, baselines 비교 실행 1.9G)과 진행 중 폴더의 링크가 가리키는 곳은 A·C라도 남겼다.
- D 범위는 회신의 네 가지(뷰별 맵, TSDF 타일, 메시 병합 임시 파일, 메시 입력 배열)로 좁혔다. C는 `checkpoint.pth`, `chkpnt*.pth`만이다. 하드링크가 둘 이상인 파일은 지우지 않는다.

## 2. r29 fork

- r29 = `src/phd/forks/GeoGS-conf-guided-v1-r28` 작업 사본 복사(117개 파일). 작업 사본은 커밋본과 같았고(`git status` 변경 없음), `JointBuildGS-wt-trainunit`·`JointBuildGS-wt-judgecheck2`의 r28과도 같다.
- 복사한 r28 파일 sha256: `r28_sha256.txt` (이 파일 자체 sha256 `78e29c7cf7cc5f4f864d91fa66ec1456dc051137a02efccd2642c890cb10450b`; `train.py` `6f9b3600…6408`, `jbgs_state.py` `b93698e3…abf3`). 복사 직후 r29가 이 목록과 117개 모두 일치.
- 바꾼 파일과 줄(r29 기준, 전체 차이 `r29_vs_r28.diff`):
  - `train.py:1428-1429`: `--save_iterations` 기본값 `[8_000, 30_000]` → `[]`. 마지막 반복은 기존 `train.py:1500`(`args.save_iterations.append(args.iterations)`)이 그대로 붙인다.
  - `jbgs_state.py:25`: `NON_METHOD_ARGS`에 `jbgs_keep_checkpoints` 추가(이어하기 검사에서 방법 인자로 보지 않음).
  - `jbgs_state.py:38-41`: `--jbgs_capture_iterations` 기본값 `[8000, 30000]` → `[]`, 새 인자 `--jbgs_keep_checkpoints`(기본 1, 0 = 모두 남김).
  - `jbgs_state.py:48-51`(`validate_args`): 마지막 반복이 capture 목록에 없으면 붙인다. 음수 keep은 오류.
  - `jbgs_state.py:182-195`(새 함수 `prune_checkpoints`), `jbgs_state.py:223`(전체 상태 저장 직후 호출): 마지막 N개를 뺀 `jbgs_complete/iteration_*/checkpoint.pth`를 지우고 그 폴더에 `removed.json`을 남긴다. `point_cloud.ply`, `receipt.json`(체크포인트 sha256 포함)은 남는다.
- 기록 판은 launch에서 지금처럼 `--jbgs_capture_iterations`, `--save_iterations`를 명시하고, 중간 체크포인트가 필요하면 `--jbgs_keep_checkpoints 0`을 준다.
- 뷰별 맵: r28의 `jbgs_target.py:187`, `jbgs_target_r6.py:142`, `jbgs_mv_early.py:46`가 이미 `np.savez_compressed`·float32라 바꾸지 않았다.

### 300회 확인

- 방법(`scripts/phd/storage_v1/check_r29.py`): TRAINERR 단위 점검과 같은 작은 예제(R1rep_b10 × ALS, 씨앗 0).
  1. TRAINERR `te_replay.py dump`를 `/source`=r28, r29로 한 번씩(시작 = TRAINERR probe `r28off_a`의 200회 전체 상태, 결정적 재생 300회) → `compare`로 가우시안 수, 꼬리표, 묶인 패치, 위치·크기·불투명도, Adam·밀도 통계 바이트 비교.
  2. 실제 300회 학습 셋: r29 기본값(저장 인자 없음), r29와 r28에 TRAINERR probe 인자(capture 100 200 300). 저장된 파일 목록과 체크포인트 유지 여부를 비교한다. 실제 학습끼리의 바이트 비교는 하지 않는다: TRAINERR 규칙 B대로 같은 설정 두 판도 GPU에서 이미 다르다(`r28off_a`·`r28off_b` ply sha256이 다름).
- 실행: GPU 두 장 모두 trainunit 학습이 쓰고 있어, 작업마다 계산 프로세스가 없는 GPU를 기다리는 사용자 서비스 `phd-storage-check-r29`로 걸었다(2026-11-13 23:20 대기 시작). 결과: `JointBuildGS-artifacts/phase-payloads/phd/storage_v1/PHD-STORAGE-v1/verification/check_r29.json`, 로그 `logs/`.
- 결과: **대기 중** (나오면 여기에 적는다).

## 3. 메시 정리 스크립트

- `scripts/phd/storage_v1/mesh_cleanup.py RUN_DIR [--metrics FILE …] [--dry-run]`. 기존 메시 코드(`streamed_tsdf.py`, `bounded_merge.py`, `mesh_pipeline.py`)는 고치지 않는다.
- 순서: 지표 json(기본 `RUN_DIR/final.json`)이 읽히고 `status`가 있으면 `PASS`, `mesh_sha256`이 있으면 `final.ply`와 일치 → 아니면 지우지 않고 `storage_cleanup.json`에 까닭을 적는다. 그 뒤 RUN_DIR 안의 `tiles/tile*.npz`, `bounded_merge/*.bin`, `inputs/depth_masked.npy`·`inputs/rgb.npy`만 지운다(단일 링크 일반 파일만). 지운 경로·크기는 `RUN_DIR/storage_cleanup.json`.
- 미리보기(컨테이너, 읽기 전용 마운트): `main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/meshes/R1rep_b10__ALS__always_keep_mesh` → 16개 1.99 GiB(병합 임시 13, 메시 입력 2, TSDF 타일 1), `final.ply` sha256 일치. 목록 `preview_gtjudge_R1rep_ALS.tsv`.
- 실제 삭제는 아직 하지 않았다. gtjudge는 2절 가에서 "읽음"이라 D를 진행 중 작업이 끝난 뒤 지운다.
