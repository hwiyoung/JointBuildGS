# JointBuildGS repository storage and Git history audit

## 결론

**최종 권고: 2. existing repo + partial clone/sparse checkout.**

현재 main checkout은 재배치 전 457.691 GiB에서 **734.054 MiB**(`.git` 제외)로 줄었고, 대용량 payload는 sibling `../JointBuildGS-artifacts`로 분리되어 있다. 그러나 실제 원격 branch tree는 아직 **6,016 files / 732.360 MiB**이고 로컬 Git object database도 **1.797 GiB**다. 단일 giant blob 문제는 없지만, 940개의 tracked image가 547.948 MiB를 차지하므로 normal clone보다 blobless partial clone과 역할별 sparse checkout이 적합하다.

History cleanup은 현재 필수가 아니다. commit-bearing history의 최대 blob은 32.341 MiB이고 50 MiB 이상 blob은 0개다. 별도 ResearchControl repo도 지금은 코드·preregistration·compact evidence·manifest의 강한 상호 참조를 끊는 비용이 더 크다.

## 측정 스냅샷과 범위

- 측정 시각: **2026-07-30 16:57:05 KST**.
- checkout: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS`.
- branch: `exp/fusion-w1`.
- local `HEAD`: `8b20d17550885c1a6365f0abd0d126f34d826a95` (`POLICY-IA2-01 restore pre-audit gitignore bytes`).
- live `origin/exp/fusion-w1`: `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`.
- 측정 전후 porcelain-v2 상태 hash가 동일하여 아래 수치는 한 상태에서 얻은 stable snapshot이다.
- current index는 진행 중인 구조 재배치와 사용자의 Fusion 작업을 포함한다. `HEAD`, index, working copy, live remote를 혼합하지 않고 별도로 표기한다.
- 이 감사 갱신은 이 문서와 두 CSV 및 두 계획서만 편집했다. `.gitignore`, 연구 원본, 실험 결과, history, object store는 변경하지 않았다. `git filter-repo`, `git clean`, `git gc`, repack, prune를 실행하지 않았다.
- 용량은 apparent bytes 기준이며 allocated bytes를 별도로 표기했다. MiB/GiB는 binary 단위다.

## 1–3. Working tree, `.git`, Git objects

| 항목 | 정확한 값 | 사람이 읽기 쉬운 값 |
|---|---:|---:|
| Working tree, `.git` 제외, apparent | 769,712,016 bytes | 734.054 MiB |
| Working tree, `.git` 제외, allocated | 779,767,808 bytes | 743.645 MiB |
| `.git`, apparent | 1,931,369,988 bytes | 1.799 GiB |
| `.git`, allocated | 1,948,221,440 bytes | 1.814 GiB |
| `.git/objects`, apparent | 1,929,310,992 bytes | 1.797 GiB |
| Checkout + `.git`, apparent | 2,701,082,004 bytes | 2.516 GiB |

재배치 전의 동결 측정값은 `.git` 제외 491,442,349,247 bytes(457.691 GiB)였다. 현재 값과의 차이는 490,672,637,231 bytes(456.975 GiB)다. 이는 삭제량이 아니라 sibling artifact workspace로 옮겨진 bulk payload와 격리 항목을 checkout 집계에서 제외한 결과다. 현재 `../JointBuildGS-artifacts` 자체는 490,795,136,169 apparent bytes(457.089 GiB)이며, off-machine backup으로 간주할 수는 없다.

`git count-objects -v` 결과:

| 통계 | 값 |
|---|---:|
| Loose objects | 5,655 |
| Loose-object disk size | 269,956 KiB / 263.629 MiB |
| Packed objects | 14,819 |
| Pack count | 10 |
| Pack disk size | 1,629,295 KiB / 1.554 GiB |
| Prune-packable | 0 |
| Garbage objects / bytes | 0 / 0 |

Commit-bearing refs(`refs/heads/*`, `refs/remotes/*`, `refs/tags/*`)에는 13,781 reachable objects와 8,380 unique blobs가 있으며 blob uncompressed 합은 1,587,745,983 bytes(1.479 GiB)다. 별도로 Codex가 만든 6개의 `refs/codex/turn-diffs/*` tree ref까지 literal `--all`로 포함하면 17,044 objects, 10,839 blobs, 2,767,647,935 bytes(2.577 GiB)가 된다. 이 tree refs는 commit history나 pushed origin 범위가 아니므로 history CSV에서는 제외했다. 어느 범위에서도 최대 blob은 동일한 33,911,867 bytes다.

## 4–6. 현재 tracked files와 전체 commit history의 큰 blob

| 범위 | 파일/blob 수 | bytes | 크기 |
|---|---:|---:|---:|
| Current index | 4,449 files | 762,646,194 | 727.316 MiB |
| Current working copies of tracked paths | 4,444 existing / 5 missing | 762,632,574 | 727.303 MiB |
| Local `HEAD` tree | 4,433 files | 762,411,814 | 727.093 MiB |
| Live `origin/exp/fusion-w1` tree | 6,016 files | 767,935,421 | 732.360 MiB |
| Commit-bearing history unique blobs | 8,380 blobs | 1,587,745,983 | 1.479 GiB |

5개의 missing tracked path는 격리된 placeholder에 대한 아직 unstaged deletion이다. 데이터 유실로 계산하지 않았으며 index blob 크기에는 포함했다.

- 현재 index의 큰 파일 100개: [`TRACKED_LARGE_FILES.csv`](TRACKED_LARGE_FILES.csv).
- commit-bearing history의 큰 unique blob 100개: [`HISTORY_LARGE_BLOBS.csv`](HISTORY_LARGE_BLOBS.csv).
- 현재 최대 tracked file은 `phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/sources/GS4Buildings_arXiv_2508.07355v1.pdf`, 10,471,726 bytes(9.987 MiB)다.
- history 최대 blob은 historical `results/phase1_depth_normal/figures/comparison_4views.png`, 33,911,867 bytes(32.341 MiB)다.
- current index와 commit history에서 Git LFS pointer는 0개다. 현재 `.gitattributes`도 없다. CSV의 B 분류는 **제안**이지 현재 LFS 사용을 뜻하지 않는다.

## 7. Tracked / ignored / untracked 주요 디렉터리

Current index blob 기준:

| 소유자 | Files | Bytes | 크기 |
|---|---:|---:|---:|
| `docs/` | 1,923 | 590,301,993 | 562.956 MiB |
| `phases/` | 1,840 | 152,153,639 | 145.105 MiB |
| `src/` | 69 | 10,774,170 | 10.275 MiB |
| `scripts/` | 377 | 7,422,472 | 7.079 MiB |
| `tests/` | 99 | 1,666,436 | 1.589 MiB |
| `configs/` | 122 | 272,169 | 265.790 KiB |
| `artifacts/` | 11 | 21,939 | 21.425 KiB |
| Root build/index files | 8 | 33,376 | 32.594 KiB |

특히 `docs/figs/`만 604 files / 379,066,196 bytes(361.506 MiB)다. 경로가 정리되었어도 clone 비용의 중심은 선별되지 않은 binary evidence 집합이라는 뜻이다.

최종 P0 evidence 이동으로 `docs/evidence/`는 482 tracked files / 162,603,068 bytes(155.070 MiB)가 되었고, `phases/p0-audit/`에는 실행 control과 receipt 229 files / 4,820,390 bytes(4.597 MiB)만 남았다. `phases/p0-audit/docs/`의 tracked file은 0개다.

Ignored와 untracked는 working-copy file 크기 기준이다.

| 상태/소유자 | Files | Bytes | 설명 |
|---|---:|---:|---|
| Ignored total | 5 | 1,502,468 | cache 3개, local setting 1개, compiled helper 1개 |
| `src/` ignored | 1 | 1,472,816 | `src/stage3/polyfit_cli` compiled binary |
| `scripts/` ignored | 3 | 27,753 | `__pycache__` |
| `.claude/` ignored | 1 | 1,899 | local setting |
| Untracked total | 25 | 341,919 | active Fusion/control work, 새 manifest와 새 semantic README |
| `phases/` untracked | 12 | 300,934 | Fusion configs/scripts/wrappers |
| `tests/` untracked | 4 | 35,559 | Fusion tests |
| `artifacts/` untracked | 2 | 2,838 | relocation manifests |
| `docs/` untracked | 6 | 1,901 | P0 evidence semantic README |
| `scripts/` untracked | 1 | 687 | semantic script index |

따라서 main checkout 내부의 ignored bulk dataset/run tree는 더 이상 주 저장 위치가 아니다. 실제 대용량은 `../JointBuildGS-artifacts`에 있고 `artifacts/manifests/`가 이동·검증 정보를 소유한다. 실행 중인 오래된 `jointbuildgs-dev` 컨테이너는 이전 compatibility mount를 repo 내부처럼 보이게 하므로 용량 측정에서 제외했다. 최신 Compose 정의로 생성한 일회성 컨테이너는 repo root, `/data`, `/artifacts/JointBuildGS` 세 mount만 사용하며 위 수치는 그 clean view에서 측정했다.

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
| Reports | `docs/**/reports/` 등 222 tracked files / 1,633,948 bytes. compact scientific report는 Git에 남고 bulk run payload는 sibling workspace에 분리됨 | A; payload는 C/D |
| Checkpoints | tracked `.pt/.pth/.ckpt` 0개. checkpoint 이름을 가진 tracked manifest/metric/receipt는 33개 / 1,159,146 bytes | binary는 C, compact metadata는 A |
| Datasets | tracked dataset root 0개. raw/downloaded data는 `../JointBuildGS-artifacts`와 manifest로 관리 | C |
| Point clouds | tracked LAS/LAZ/PLY 27개 / 37,601,381 bytes. 대부분 작은 historical evidence지만 ordinary Git 상태 | 원칙 C; 명시적 tiny fixture만 A/B 예외 |
| Meshes | tracked OBJ/STL/OFF/GLB/GLTF 1개 / 261,177 bytes | 작은 정본 evidence는 A/B, bulk는 C |
| Images | tracked PNG/JPG/TIFF/WebP/SVG 940개 / 574,565,333 bytes. `docs/figs`와 evidence package가 중심 | 현재 regular Git, 향후 selected B |
| Logs | tracked `.log/.jsonl` 206개 / 7,709,092 bytes. compact failure/receipt와 historical raw log가 섞임 | compact immutable record A, mutable/raw D |
| Caches | main checkout ignored cache 3개 / 27,753 bytes. 별도 compiled helper 1개 / 1,472,816 bytes도 ignored | D |

Externalization evidence는 `artifacts/manifests/local_workspace_20260730.yaml`, `fusion_w1_run_payloads_20260730.yaml`, `p2_run_payloads_semantic_relocation_20260730.yaml`, `p2_compact_payloads_20260730.yaml`, `p2_driver_payloads_20260730.yaml`에 있다. 이 manifest들은 local filesystem 이동과 byte/inode 검증을 증명하지만 durable URI·off-machine replication을 아직 증명하지 않는다.

## 10. 현재 branch와 실제 pushed 범위

Read-only `git ls-remote --heads --tags origin`으로 live origin을 확인했다. local tracking ref 11개는 live head 11개와 모두 일치했다.

| 항목 | 값 |
|---|---|
| Local branch / `HEAD` | `exp/fusion-w1` / `8b20d17550885c1a6365f0abd0d126f34d826a95` |
| Live current-branch remote | `origin/exp/fusion-w1` / `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8` |
| Ahead / behind | **42 / 0** |
| Pushed remote tree | 6,016 files / 767,935,421 bytes |
| Local `HEAD` tree | 4,433 files / 762,411,814 bytes |
| Same path + same blob in both trees | 947 files |
| Local `HEAD` only or path/blob changed | 3,486 files |
| Remote only or path/blob changed | 5,069 files |
| Working state beyond `HEAD` at snapshot | 524 staged entries, 305 unstaged entries, 25 untracked files |

즉 **현재 새 구조는 아직 remote에 push되지 않았다.** 실제 pushed tree는 다음 legacy top-level 범위를 포함한다.

| Live remote top-level owner | Files | Bytes |
|---|---:|---:|
| `docs/` | 1,197 | 522,688,201 |
| `phases/` | 4,110 | 210,264,621 |
| `results/` | 323 | 17,153,398 |
| `tools/` | 30 | 9,920,754 |
| `scripts/` | 131 | 5,142,619 |
| `src/` | 37 | 850,255 |
| `reports/` | 9 | 840,828 |
| `fair-pilot/` | 32 | 463,945 |
| `legacy/` | 7 | 207,903 |
| `configs/` | 112 | 237,416 |
| `runs/` | 14 | 24,122 |
| `env/` | 1 | 1,712 |
| `data/` | 1 | 0 |
| `tests/` | 1 | 4,087 |
| Root files | 11 | 135,560 |

14개 local head 중 live same-name branch가 없는 것은 `fc/current-baseline-cleanup`, `feature/p0-input-audit`, `feature/p2-seed-protect` 3개다. same-name remote보다 앞선 다른 branch는 `exp/3b-surface-restore` +2, `feat/p2-fidelity` +3, `feat/p2-structure-learn` +3, `feature/p2-semantic-seed` +9다. 이들은 current branch의 pushed 범위와 별개다.

## A–D 잠정 분류

| 등급 | 소유 내용 | 현재 상태 |
|---|---|---|
| **A. regular Git** | `src/`, `configs/`, `scripts/`, `tests/`, root build files, compact Markdown/CSV/JSON/YAML, manifest, receipt | 이미 주 관리 방식이며 계속 유지 |
| **B. selected Git LFS** | checkout과 함께 있어야 하는 승인된 final figure/panel/PDF 및 고정 binary fixture의 작은 allowlist | 아직 LFS 미구성. CSV는 후보만 표시 |
| **C. external artifact storage + manifest** | raw dataset, checkpoint, dense point cloud/mesh, full-resolution imagery, large arrays, irreplaceable run bundle | sibling workspace와 tracked manifest로 local 분리 완료; durable backend는 미완료 |
| **D. raw/generated/ignored data** | cache, mutable log, TensorBoard, PID/lock, reproducible render/intermediate, compiled local helper | main checkout에는 소수만 남음; 재생성 또는 임시 보존 대상 |

## 최종 판단

**2. existing repo + partial clone/sparse checkout**을 추천한다.

- Option 1 normal clone은 가능하지만 pushed tree 732.360 MiB와 누적 object cost를 모든 사용자에게 부담시킨다.
- Option 2는 commit ID, 연구 lineage, branch/tag를 보존하면서 코드·설정·필요한 문서만 먼저 checkout할 수 있다.
- Option 3 separate ResearchControl repo는 현재 강한 cross-reference를 분할하고 이중 manifest/version coordination을 만든다.
- Option 4 history cleanup required later는 현재 수치로는 요구되지 않는다. 최대 history blob 32.341 MiB, 50 MiB 이상 0개다. partial/sparse clean-clone 실측 후에도 비용이 허용 불가일 때만 별도 승인 과제로 재검토한다.

실행 계획은 [`WORK_SPARSE_CHECKOUT_PLAN.md`](WORK_SPARSE_CHECKOUT_PLAN.md), 저장 정책은 [`PROPOSED_STORAGE_POLICY.md`](PROPOSED_STORAGE_POLICY.md)를 따른다. 이 감사에서는 clone, LFS 도입, ignore 정책 변경, cleanup, push를 실행하지 않았다.

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
