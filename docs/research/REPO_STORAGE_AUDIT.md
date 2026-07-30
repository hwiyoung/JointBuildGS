# JointBuildGS repository storage and Git history audit

## 결론

**최종 권고: 2. existing repo + partial clone/sparse checkout.**

재배치와 Fusion 기술 handoff가 끝난 pushed control tree는 **4,499 files / 729.363 MiB**이고, 대용량 payload는 sibling `../JointBuildGS-artifacts`로 분리되어 있다. 20:20 KST의 normal-clone storage baseline은 working tree 733.447 MiB와 `.git` 1.242 GiB였고, 22:58 KST의 최종 blobless partial clone은 working tree 734.144 MiB와 `.git` 556.986 MiB였다. 단일 giant blob 문제는 없지만, tracked image 집합이 clone 비용의 중심이므로 기본 운영은 blobless partial clone과 역할별 sparse checkout이 적합하다.

History cleanup은 현재 필수가 아니다. commit-bearing history의 최대 blob은 32.341 MiB이고 50 MiB 이상 blob은 0개다. 별도 ResearchControl repo도 지금은 코드·preregistration·compact evidence·manifest의 강한 상호 참조를 끊는 비용이 더 크다.

## 측정 스냅샷과 범위

- storage baseline 측정 시각: **2026-07-30 20:20 KST**.
- final remote/partial-clone verification: **2026-07-30 22:58 KST**, `/tmp/jbgs-remote-final-x8g2KnIY/repo`.
- final verified technical closeout commit: `9dd020e1b7fa95aa6ac2f3fd7e68440d8012cf96`; 이 audit receipt 자체는 그 descendant로 추가될 수 있다. Remote default와 유일한 live head는 `main`이다.
- 원 research checkout은 복구용 local `exp/fusion-w1` @ `c90ef861a50338ef8c57916ef62f74b211912a68`로 보존했고 upstream을 제거했다. staged 19, unstaged 20, untracked 16의 payload bytes는 snapshot과 일치한다.
- The clean clone and active checkout were measured separately so uncommitted Fusion work is not presented as pushed state.
- `.gitignore`, research source data, and experiment result payloads were not modified. `git filter-repo`, `git clean`, `git gc`, repack, and prune were not run.
- 용량은 apparent bytes 기준이며 allocated bytes를 별도로 표기했다. MiB/GiB는 binary 단위다.

## 1–3. Working tree, `.git`, Git objects

| 항목 | 정확한 값 | 사람이 읽기 쉬운 값 |
|---|---:|---:|
| Fresh normal-clone working tree, `.git` 제외, apparent | 769,074,953 bytes | 733.447 MiB |
| Fresh normal-clone working tree, `.git` 제외, allocated | 779,071,488 bytes | 742.980 MiB |
| Fresh normal-clone `.git`, apparent, retained heads/tags fetched | 1,333,592,002 bytes | 1.242 GiB |
| Fresh normal-clone `.git/objects`, apparent | 1,332,224,884 bytes | 1.241 GiB |
| Fresh normal clone checkout + `.git`, apparent | 2,102,666,955 bytes | 1.958 GiB |
| Active long-lived checkout `.git`, apparent | 1,934,700,164 bytes | 1.802 GiB |
| Final blobless partial-clone working tree, `.git` 제외, apparent | 769,806,263 bytes | 734.144 MiB |
| Final blobless partial-clone `.git`, apparent | 584,042,166 bytes | 556.986 MiB |
| Final blobless partial-clone `.git/objects`, apparent | 583,224,248 bytes | 556.206 MiB |

재배치 전의 동결 측정값은 `.git` 제외 491,442,349,247 bytes(457.691 GiB)였다. clean checkout과의 차이는 490,673,274,294 bytes(456.975 GiB)다. 이 차이의 대부분은 sibling artifact workspace로 옮긴 payload이며, 별도 retention review 두 번으로 107.06 GB의 재생성 가능·중복 항목을 추가 제거했다. 현재 sibling의 regular payload는 383,694,408,263 bytes이고 깨진 symlink는 0개다. 이 local filesystem은 off-machine backup으로 간주할 수 없다.

`git count-objects -v` 결과:

| 통계 | 값 |
|---|---:|
| Loose objects | 6,285 |
| Loose-object disk size | 275,044 KiB / 268.598 MiB |
| Packed objects | 14,819 |
| Pack count | 10 |
| Pack disk size | 1,629,295 KiB / 1.554 GiB |
| Prune-packable | 0 |
| Garbage objects / bytes | 0 / 0 |

Retained commit-bearing refs(`refs/heads/*`, `refs/remotes/*`, `refs/tags/*`)에는 14,352 reachable objects와 8,753 unique blobs가 있으며 blob uncompressed 합은 1,610,553,665 bytes(1.500 GiB)다. 최대 blob은 33,911,867 bytes다. Codex internal tree refs are not commit history or pushed origin scope and remain excluded from the history CSV.

## 4–6. 현재 tracked files와 전체 commit history의 큰 blob

| 범위 | 파일/blob 수 | bytes | 크기 |
|---|---:|---:|---:|
| Pushed `main` tree | 4,499 files | 764,792,759 | 729.363 MiB |
| Active checkout index after protected Fusion staging | 4,469 files | 764,304,021 | 728.897 MiB |
| Active working copies of tracked paths | 4,469 existing / 0 missing | 764,306,560 | 728.899 MiB |
| Commit-bearing history unique blobs | 8,753 blobs | 1,610,553,665 | 1.500 GiB |

Active checkout 수치는 `c90ef86` 기반 원 WIP의 복구 snapshot이며 현재 pushed tree와 같은 기준선이 아니다. 분류·수정된 기술 handoff는 `main`에 포함됐고, 원 checkout의 working copy에서 누락된 tracked path는 0개다.

- 현재 pushed tree의 큰 파일 100개: [`TRACKED_LARGE_FILES.csv`](TRACKED_LARGE_FILES.csv).
- commit-bearing history의 큰 unique blob 100개: [`HISTORY_LARGE_BLOBS.csv`](HISTORY_LARGE_BLOBS.csv).
- 현재 최대 tracked file은 `phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/sources/GS4Buildings_arXiv_2508.07355v1.pdf`, 10,471,726 bytes(9.987 MiB)다.
- history 최대 blob은 historical `results/phase1_depth_normal/figures/comparison_4views.png`, 33,911,867 bytes(32.341 MiB)다.
- pushed tree와 commit history에서 Git LFS pointer는 0개다. 현재 `.gitattributes`도 없다. CSV의 B 분류는 **제안**이지 현재 LFS 사용을 뜻하지 않는다.

## 7. Tracked / ignored / untracked 주요 디렉터리

Pushed tree blob 기준:

| 소유자 | Files | Bytes | 크기 |
|---|---:|---:|---:|
| `docs/` | 1,930 | 590,319,746 | 562.973 MiB |
| `phases/` | 1,829 | 151,910,728 | 144.873 MiB |
| `src/` | 68 | 10,759,820 | 10.261 MiB |
| `scripts/` | 382 | 7,520,970 | 7.172 MiB |
| `tests/` | 94 | 1,633,611 | 1.558 MiB |
| `configs/` | 122 | 273,303 | 266.897 KiB |
| `artifacts/` | 20 | 1,615,981 | 1.541 MiB |
| Root build/index files | 8 | 35,482 | 34.650 KiB |

특히 `docs/figs/`만 604 files / 379,066,196 bytes(361.506 MiB)다. 경로가 정리되었어도 clone 비용의 중심은 선별되지 않은 binary evidence 집합이라는 뜻이다.

최종 P0 evidence 이동으로 `docs/evidence/`는 488 tracked files / 162,605,065 bytes(155.072 MiB)가 되었고, `phases/p0-audit/`에는 실행 control, replay index, compact receipt 229 files / 4,781,545 bytes(4.560 MiB)만 남았다. `phases/p0-audit/docs/`의 tracked file은 0개다.

Ignored와 untracked는 working-copy file 크기 기준이다.

| 상태/소유자 | Files | Bytes | 설명 |
|---|---:|---:|---|
| Ignored total | 1 | 1,472,816 | compiled helper 1개 |
| `src/` ignored | 1 | 1,472,816 | `src/stage3/polyfit_cli` compiled binary |
| Untracked total | 16 | 336,493 | 보호된 active Fusion work |
| `phases/` untracked | 12 | 300,934 | Fusion configs/scripts/wrappers |
| `tests/` untracked | 4 | 35,559 | Fusion tests |

따라서 main checkout 내부의 ignored bulk dataset/run tree는 더 이상 주 저장 위치가 아니다. 실제 대용량은 `../JointBuildGS-artifacts`에 있고 `artifacts/manifests/`가 이동·검증 정보를 소유한다. `jointbuildgs-dev`는 최신 Compose로 force-recreate했으며 repo root, `/data`, `/artifacts/JointBuildGS` 세 mount만 사용한다. 과거 repo-local payload compatibility mount는 0개다.

## 8. 50 MiB / 100 MiB / 1 GiB threshold

| Threshold | Current tracked files | Commit-history blobs |
|---|---:|---:|
| `>= 50 MiB` | 0 | 0 |
| `>= 100 MiB` | 0 | 0 |
| `>= 1 GiB` | 0 | 0 |

나열할 qualifying path는 없다. 다만 aggregate binary budget은 별도 문제다. tracked image 940개가 574,565,333 bytes(547.948 MiB)를 차지한다.

## 9. Reports, checkpoints, datasets, geometry, images, logs, caches

| 종류 | 현재 관찰 | 잠정 관리 등급 |
|---|---|---|
| Reports | `docs/**/reports/` 등 249 tracked files / 1,787,906 bytes. compact scientific report는 Git에 남고 bulk run payload는 sibling workspace에 분리됨 | A; payload는 C/D |
| Checkpoints | tracked `.pt/.pth/.ckpt` 0개. checkpoint 이름을 가진 tracked manifest/metric/receipt는 33개 / 1,159,146 bytes | binary는 C, compact metadata는 A |
| Datasets | tracked dataset root 0개. raw/downloaded data는 `../JointBuildGS-artifacts`와 manifest로 관리 | C |
| Point clouds | tracked LAS/LAZ/PLY 27개 / 37,601,381 bytes. 대부분 작은 historical evidence지만 ordinary Git 상태 | 원칙 C; 명시적 tiny fixture만 A/B 예외 |
| Meshes | tracked OBJ/STL/OFF/GLB/GLTF 1개 / 261,177 bytes | 작은 정본 evidence는 A/B, bulk는 C |
| Images | tracked PNG/JPG/TIFF/WebP/SVG 940개 / 574,565,333 bytes. `docs/figs`와 evidence package가 중심 | 현재 regular Git, 향후 selected B |
| Logs | tracked `.log/.jsonl` 206개 / 7,709,092 bytes. compact failure/receipt와 historical raw log가 섞임 | compact immutable record A, mutable/raw D |
| Caches | main checkout의 ignored cache file은 0개다. 별도 compiled helper 1개 / 1,472,816 bytes는 ignored | D |

Externalization evidence는 `artifacts/manifests/local_workspace_20260730.yaml`, `fusion_w1_run_payloads_20260730.yaml`, `p2_run_payloads_semantic_relocation_20260730.yaml`, `p2_compact_payloads_20260730.yaml`, `p2_driver_payloads_20260730.yaml`, and the paired `artifact_*symlink*_{plan,receipt}_20260730.json` files에 있다. 이 manifest들은 local filesystem 이동과 byte/inode 검증을 증명하지만 durable URI·off-machine replication을 아직 증명하지 않는다.

## 10. 현재 branch와 실제 pushed 범위

`git ls-remote --symref`로 live origin을 확인했다. Remote default와 유일한 live head는 `main`이다.

| 항목 | 값 |
|---|---|
| Audited clean branch / technical snapshot `HEAD` | `main` / `9dd020e1b7fa95aa6ac2f3fd7e68440d8012cf96` |
| Live retained remotes | `origin/main` only |
| Ahead / behind at snapshot | **0 / 0** |
| Pushed remote tree | 4,499 files / 764,792,759 bytes |
| Local recovery branch | `exp/fusion-w1` @ `c90ef86`; no upstream, original dirty state preserved |
| Protected Fusion state beyond `HEAD` | 19 staged entries, 20 unstaged entries, 16 untracked files |
| Archive tags | 2 unique retired tips preserved; see `BRANCH_RETIREMENT_20260730.md` |

즉 **새 구조와 storage cleanup은 실제 remote에 push되었다.** Pushed tree의 top-level owner는 일곱 디렉터리와 root environment files뿐이다.

| Live remote top-level owner | Files | Bytes |
|---|---:|---:|
| `docs/` | 1,934 | 590,365,875 |
| `phases/` | 1,850 | 152,415,904 |
| `src/` | 70 | 10,778,507 |
| `scripts/` | 386 | 7,563,613 |
| `tests/` | 105 | 1,725,119 |
| `artifacts/` | 24 | 1,632,656 |
| `configs/` | 122 | 275,332 |
| Root files | 8 | 35,753 |

Branch retirement는 unique tip 두 개를 annotated archive tag로 먼저 보존한 뒤 수행했다. Fusion WIP snapshot·source-lock·technical gate와 새 `main`의 ancestry를 확인한 뒤 마지막 remote `exp/fusion-w1`도 제거해 live remote head를 `main` 하나로 줄였다. 삭제·보존 근거와 exact refs는 [`BRANCH_RETIREMENT_20260730.md`](repository/BRANCH_RETIREMENT_20260730.md)에 기록했다.

## A–D 잠정 분류

| 등급 | 소유 내용 | 현재 상태 |
|---|---|---|
| **A. regular Git** | `src/`, `configs/`, `scripts/`, `tests/`, root build files, compact Markdown/CSV/JSON/YAML, manifest, receipt | 이미 주 관리 방식이며 계속 유지 |
| **B. selected Git LFS** | checkout과 함께 있어야 하는 승인된 final figure/panel/PDF 및 고정 binary fixture의 작은 allowlist | 아직 LFS 미구성. CSV는 후보만 표시 |
| **C. external artifact storage + manifest** | raw dataset, checkpoint, dense point cloud/mesh, full-resolution imagery, large arrays, irreplaceable run bundle | sibling workspace와 tracked manifest로 local 분리 완료; durable backend는 미완료 |
| **D. raw/generated/ignored data** | cache, mutable log, TensorBoard, PID/lock, reproducible render/intermediate, compiled local helper | main checkout에는 소수만 남음; 재생성 또는 임시 보존 대상 |

## 최종 판단

**2. existing repo + partial clone/sparse checkout**을 추천한다.

- Option 1 normal clone은 가능하지만 실측 fresh clone도 working tree 733.447 MiB와 `.git` 1.242 GiB를 사용해, 모든 사용자에게 전체 binary evidence 비용을 부담시킨다.
- Option 2는 commit ID, 연구 lineage, branch/tag를 보존하면서 코드·설정·필요한 문서만 먼저 checkout할 수 있다.
- Option 3 separate ResearchControl repo는 현재 강한 cross-reference를 분할하고 이중 manifest/version coordination을 만든다.
- Option 4 history cleanup required later는 현재 수치로는 요구되지 않는다. 최대 history blob 32.341 MiB, 50 MiB 이상 0개다. partial/sparse clean-clone 실측 후에도 비용이 허용 불가일 때만 별도 승인 과제로 재검토한다.

실행 계획은 [`WORK_SPARSE_CHECKOUT_PLAN.md`](WORK_SPARSE_CHECKOUT_PLAN.md), 저장 정책은 [`PROPOSED_STORAGE_POLICY.md`](PROPOSED_STORAGE_POLICY.md)를 따른다. 이 closeout에서 normal clone baseline, blobless partial clone, reviewed artifact verification, resolver repair, push, and branch retirement were executed and verified. Sparse checkout activation, Git LFS introduction, `.gitignore` changes, history rewrite, and Git object cleanup were not executed.

## 재현 명령

최신 Compose 정의의 새 일회성 컨테이너에서 다음 read-only 명령을 사용했다.

```bash
du -sb --exclude=.git .
du -sB1 --exclude=.git .
du -sb .git
du -sb .git/objects
git count-objects -v
git ls-files -s -z
git ls-files --others --ignored --exclude-standard -z
git ls-files --others --exclude-standard -z
git rev-list --objects --branches --remotes --tags
git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'
git ls-tree -r -z HEAD
git ls-remote --heads --tags origin
```

CSV size는 raw Git blob size이며 history CSV의 `path_hint`는 해당 blob에 대해 `git rev-list --objects`가 반환한 한 경로다. 동일 blob이 다른 경로에도 존재할 수 있다.
