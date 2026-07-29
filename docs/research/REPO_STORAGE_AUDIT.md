# JointBuildGS repository storage and Git history audit

## Executive decision

**Recommendation: 2. existing repo + partial clone/sparse checkout.**

The repository does not currently require history cleanup. The largest committed-history blob is only 32.341 MiB and there are no current tracked or committed-history blobs at or above 50 MiB. The practical cost comes from accumulation: the current index contains 945 PNG files totaling 553.596 MiB, the current branch tree is 732.360 MiB, and the local Git object database is 1.794 GiB. A blob-filtered sparse clone gives a useful control-plane checkout without changing history or splitting research governance into another repository.

The much larger 457.691 GiB working tree is a different problem: 456.544 GiB is ignored local data and generated artifacts. Sparse checkout does not remove or manage those ignored files. They need an external artifact contract and manifests, not Git history surgery.

## Scope and safety

- Measurement window: 2026-07-29 19:53–19:59 KST.
- Main snapshot for file-state counts: 2026-07-29 19:55:51 KST.
- Current checkout: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS`.
- Branch at snapshot: `exp/fusion-w1`.
- No file was deleted, moved, renamed, or modified during measurement.
- `.gitignore` was not modified.
- No history rewrite, `git filter-repo`, `git clean`, `git gc`, repack, prune, or artifact cleanup was run.
- Original data and experiment results were not changed.
- The only repository writes made by this task are the five requested audit deliverables under `docs/research/`.

Measurements used apparent bytes unless explicitly labeled allocated bytes. Tracked size means the sum of current index blob sizes. Ignored and untracked sizes mean the sum of `lstat(2)` sizes for file paths returned by `git ls-files`; directory metadata and symlink targets are excluded. The overall `du` measurement and the status-derived sums therefore answer slightly different questions.

## 1–3. Checkout, `.git`, and object database

| Measure | Exact bytes / count | Human value | Interpretation |
|---|---:|---:|---|
| Current working tree, excluding `.git`, apparent | 491,442,349,247 | 457.691 GiB | Checkout files only |
| Current working tree, excluding `.git`, allocated | 491,674,292,224 | 457.907 GiB | Filesystem blocks |
| `.git`, apparent | 1,928,849,670 | 1.796 GiB | Shared Git directory |
| `.git`, allocated | 1,952,739,328 | 1.819 GiB | Filesystem blocks |
| `.git/objects`, apparent | 1,926,469,462 | 1.794 GiB | Almost all `.git` storage |

This repository has a second linked worktree, `JointBuildGS-aprime-report-v2`, at detached commit `647794a5a84e1b599e9c5e9170b62148500cc206`. Its separate checkout is 762,250,343 apparent bytes (726.939 MiB) and is excluded from the 457.691 GiB main-working-tree figure. It shares the `.git` object database; `.git/worktrees/JointBuildGS-aprime-report-v2/index` is about 0.90 MiB.

`git count-objects` reported:

| Git object statistic | Value |
|---|---:|
| Loose objects | 8,006 |
| Loose-object disk size | 625,632 KiB / 610.97 MiB |
| Packed objects | 9,514 |
| Pack count | 9 |
| Pack disk size | 1,277,705 KiB / 1.21 GiB |
| Prune-packable | 0 |
| Garbage objects / bytes | 0 / 0 |

The commit-history scope `refs/heads/* + refs/remotes/* + refs/tags/*` contains 10,997 reachable objects, including 6,913 unique blobs totaling 1,498,722,205 uncompressed bytes (1.396 GiB). This is not the same as packed disk size because Git delta-compresses objects and the local object store also contains non-commit refs and loose index/worktree objects.

There are five local `refs/codex/turn-diffs/*` tree refs. If those non-commit snapshot refs are included through a literal `git rev-list --objects --all`, the scope rises to 14,253 reachable objects, 9,372 unique blobs, and 2.495 GiB of uncompressed blob content. Some such blobs represent uncommitted runtime/cache files. They are neither commit history nor pushed origin content, so the history CSV deliberately uses commit-bearing branch/remote/tag refs. No ref was removed or altered.

## 4–6. Current tracked files and history blobs

| Scope | File/blob count | Uncompressed bytes | Human value |
|---|---:|---:|---:|
| Current index | 6,032 files | 768,169,741 | 732.584 MiB |
| Current working copies of index paths | 6,032 files | 768,171,430 | 732.585 MiB |
| Current `HEAD` tree | 6,016 files | 767,935,421 | 732.360 MiB |
| Live `origin/exp/fusion-w1` tree | 6,016 files | 767,935,421 | 732.360 MiB |
| All commit-history unique blobs | 6,913 blobs | 1,498,722,205 | 1.396 GiB |

The 234,320-byte (228.828 KiB) index-versus-`HEAD` increase is the current staged work, not pushed history. The small working-copy-versus-index difference comes from two unstaged tracked files.

- Current tracked top 100: [`TRACKED_LARGE_FILES.csv`](TRACKED_LARGE_FILES.csv). The largest is `GS4Buildings_arXiv_2508.07355v1.pdf`, 10,471,726 bytes (9.987 MiB). The top-100 range ends at 1.776 MiB.
- Commit-history top 100: [`HISTORY_LARGE_BLOBS.csv`](HISTORY_LARGE_BLOBS.csv). The largest is a historical `comparison_4views.png`, 33,911,867 bytes (32.341 MiB).
- `path_hint` in the history CSV is the path emitted for that blob by `git rev-list --objects`; a blob may occur at another path. `same_blob_at_path_in_HEAD` distinguishes exact current-path presence from object reachability elsewhere.
- No Git LFS pointer was found in the current index or commit history. There is no current or historical `.gitattributes`, and `git lfs` is not installed in the development container. All CSV-listed blobs are ordinary Git blobs.

## 7. Tracked, ignored, and untracked storage by major directory

Status-derived apparent file sizes at the snapshot:

| Status | Files | Apparent bytes | Human value |
|---|---:|---:|---:|
| Tracked/index paths | 6,032 | 768,171,430 | 732.585 MiB |
| Ignored | 100,235 | 490,210,628,828 | 456.544 GiB |
| Untracked, not ignored | 2,250 | 328,688,384 | 313.462 MiB |

Major top-level owners:

| Directory | Tracked | Ignored | Untracked |
|---|---:|---:|---:|
| `docs/` | 1,197 files / 498.474 MiB | 0 | 0 |
| `phases/` | 4,125 / 200.735 MiB | 41,202 / 185.169 GiB | 1,136 / 150.556 MiB |
| `data/` | 1 / 0 B (`.gitkeep`) | 37,916 / 161.670 GiB | 0 |
| `results/` | 323 / 16.359 MiB | 21,024 / 107.581 GiB | 0 |
| `fair-pilot/` | 32 / 453.071 KiB | 81 / 2.123 GiB | 0 |
| `reports/` | 9 / 821.121 KiB | 0 | 1,114 / 162.905 MiB |
| `tools/` | 30 / 9.461 MiB | local assets covered by ignore rules | 0 |
| `scripts/` | 131 / 4.904 MiB | 2 / 101.896 KiB | 0 |
| `src/` | 38 / 844.351 KiB | 8 / 1.930 MiB | 0 |

The largest second-level ignored owners are:

| Path | Files | Size |
|---|---:|---:|
| `data/matrixcity/` | 37,912 | 161.670 GiB |
| `phases/p0-audit/` | 35,780 | 127.151 GiB |
| `results/tum_transfer/` | 15,599 | 85.648 GiB |
| `phases/p2-gsjso/` | 5,422 | 58.019 GiB |
| `results/phase2_ablation_citygml/` | 407 | 5.906 GiB |
| `results/phase2_synthesis/` | 2,806 | 3.349 GiB |
| `results/stage3_rendered_evidence/` | 990 | 2.710 GiB |
| `fair-pilot/runs/` | 80 | 2.123 GiB |

The largest tracked aggregate is `docs/figs/`: 587 files and 351.948 MiB. This is why normal clones are heavy even though no single current file is large.

## 8. Current tracked threshold audit

Thresholds are binary MiB/GiB thresholds (`50 * 1024^2`, `100 * 1024^2`, `1024^3`).

| Threshold | Current tracked files | Commit-history blobs |
|---|---:|---:|
| At least 50 MiB | 0 | 0 |
| At least 100 MiB | 0 | 0 |
| At least 1 GiB | 0 | 0 |

Therefore there is no list of qualifying tracked paths to enumerate. This does not mean the checkout is storage-light: ignored files include individual 14.917 GiB ZIP, 12.105 GiB TAR, 4.026 GiB PLY, and 3.972 GiB LAZ payloads.

## 9. How research artifacts are managed now

The current arrangement is path-specific and mixed. `.gitignore` has extensive rules for downloadable data, checkpoints, raw runs, caches, logs, and many experiment-specific intermediates. It also intentionally keeps compact reports, manifests, aggregate tables, and selected figures. There is no repository-wide DVC, git-annex, MLflow artifact store, object-store URI contract, or Git LFS layer. Provenance is strong but decentralized: 157 tracked filenames contain `manifest`, 49 contain `inventory`, and 41 contain `receipt`.

| Artifact family | Current evidence | Current management assessment |
|---|---|---|
| Reports | 9 tracked `reports/.../post_analysis` summaries/figures (821 KiB); 1,114 untracked nightly files (162.905 MiB) | Canonical post-analysis is regular Git; raw nightly report tree is untracked. Root `reports/.../cache` is **not ignored**, creating accidental-add risk. |
| Checkpoints | 0 tracked `.pt/.pth/.ckpt`; ignored: 530 `.pt` / 79.387 GiB and 6 `.pth` / 2.519 GiB | Payloads are local ignored data. Small checkpoint metrics/manifests are tracked. There is no external durable location declared repo-wide. |
| Datasets | `data/.gitkeep` only is tracked; `data/matrixcity` alone is 161.670 GiB ignored; P0 raw datasets live under ignored phase paths | Downloadable/local data are excluded from Git. Source and checksum evidence exists in per-run documents, but no uniform external artifact resolver exists. |
| Point clouds | Tracked: 25 LAZ / 35.555 MiB plus 2 LAS / 0.305 MiB; ignored: LAS 57.749 GiB, LAZ 10.110 GiB, PLY 10.605 GiB | Most raw/dense geometry is ignored; a small set of experiment evidence/fixtures is ordinary Git. Global `*.ply` is ignored, but LAS/LAZ policy is path-specific. |
| Meshes | 1 tracked OBJ / 0.249 MiB; 404 ignored OBJ / 3.612 MiB | Mostly ignored/generated, with one small regular-Git artifact. |
| Images | 945 tracked PNG / 553.596 MiB; ignored PNG+JPG 33.847 GiB; 47 untracked PNG / 129.572 MiB | Curated evidence figures are regular Git and dominate the current branch tree. Raw/render images are usually ignored; current untracked panels still require curation. |
| Logs | Tracked: 335 `.log` / 6.758 MiB and 33 `.jsonl` / 0.865 MiB; ignored: `.log` 302.744 MiB and `.jsonl` 147.607 MiB | Canonical measurement/failure logs are sometimes committed; mutable driver/TensorBoard/runtime logs are mostly ignored via experiment-specific rules. |
| Caches | Path classifier: 0 tracked; 405 ignored / 8.050 MiB; 890 untracked / 160.081 MiB | Python/runtime caches are ignored, but the current nightly `reports/.../cache` tree is untracked rather than ignored. |

Important nuance: ignore rules do not affect already tracked files. Some tracked logs, LAZ files, figures, or generated-looking outputs remain ordinary Git because they were intentionally or historically added. Classification must be based on artifact role and provenance, not extension alone.

## 10. Current branch and actually pushed scope

At 2026-07-29 19:58:43 KST, host-side `git ls-remote --heads origin` returned:

- Local `HEAD`: `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`
- Live `origin/exp/fusion-w1`: `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`
- Ahead/behind: `0 / 0`
- Exact pushed tree: 6,016 entries, 767,935,421 blob bytes (732.360 MiB)

Thus every file in the current `HEAD` tree is pushed to the live current-branch ref, and the local commit range versus that ref is empty. All 100 paths in `TRACKED_LARGE_FILES.csv` are already present at the same path and blob ID on that remote tree.

The working/index delta is not pushed:

| Local-only state at snapshot | Count / size implication |
|---|---|
| Staged tracked paths | 17: 16 additions and 1 modification, 234,320 bytes (228.828 KiB) net index growth |
| Unstaged tracked paths | 2 |
| Untracked, not ignored | 2,250 files / 313.462 MiB |
| Ignored | 100,235 files / 456.544 GiB |
| Requested audit deliverables | Created after the measurement snapshot; not part of remote-tree figures |

Across all branches there are 14 local heads and 11 live origin heads. Four matching local branches contain unpushed commits (`exp/3b-surface-restore` +2, `feat/p2-fidelity` +3, `feat/p2-structure-learn` +3, `feature/p2-semantic-seed` +9), and three local branches have no same-named origin head (`fc/current-baseline-cleanup`, `feature/p0-input-audit`, `feature/p2-seed-protect`). This does not change the current branch result above. All 11 local `refs/remotes/origin/*` values matched the live `ls-remote` values.

The development container could not resolve the host-only SSH alias `github-hwiyoung`; remote verification was therefore performed read-only from the host, where that alias is configured. Local storage and object measurements ran through the repository development container with a per-command `safe.directory` override. An initial output-formatting wrapper failed before producing a measurement and was rerun; it changed no state.

## Provisional A–D classification

| Class | Intended content | Current state |
|---|---|---|
| **A. regular Git** | Source, configs, scripts, tests, small Markdown/CSV/JSON/YAML, compact manifests/receipts, small deterministic fixtures | This is the existing mechanism for all tracked content. Textual control-plane content fits well. |
| **B. selected Git LFS** | A curated allowlist of canonical binary evidence that must travel with a checkout: final figures/panels, approved PDFs, or small fixed binary fixtures | No LFS is configured today. Candidate classification in the CSVs is prospective and does not claim current LFS storage. |
| **C. external artifact storage + manifest** | Raw datasets, checkpoints, dense point clouds/meshes, full-resolution imagery, large arrays, irreplaceable run bundles; default for any file at least 100 MiB | No common external backend is wired today. Most such content is local ignored data with decentralized manifests. |
| **D. raw/generated/ignored data** | Reproducible renders, preprocess intermediates, TensorBoard, runtime environments, caches, locks, PIDs, mutable logs, temporary panels | This is already the dominant local policy, but several rules are experiment-specific and the current root nightly cache is an unignored gap. |

Per-file provisional classes in the CSVs are path/role heuristics for review. They are not migration instructions. In particular, history-only generated result figures are marked D, while current curated binary evidence is generally marked B; geometry/array payloads are generally C unless explicitly justified as tiny test fixtures.

## Recommendation and rationale

Choose **2. existing repo + partial clone/sparse checkout**.

1. **Existing repo + normal clone** works, but every fresh clone pays for roughly 1.4 GiB of uncompressed committed blobs and checks out a 732 MiB tree even when a contributor needs only code/config/docs.
2. **Partial clone + sparse checkout** directly targets the observed cost without changing commit IDs, branches, tags, research lineage, or the data checkout.
3. **Separate ResearchControl repo** is premature. The code, preregistration, manifests, and evidence are tightly cross-referenced, and the current history has no giant blobs forcing a split. Reassess only if access control, publication boundaries, or independent release cadence becomes a real requirement.
4. **History cleanup later** is not currently required. There are no 50 MiB committed blobs, no GitHub-size-limit emergency, and no garbage objects. Reconsider only after a measured clean-clone test shows unacceptable transfer/storage and after an immutable backup plus coordinated migration plan is approved.

See [`PROPOSED_STORAGE_POLICY.md`](PROPOSED_STORAGE_POLICY.md) and [`WORK_SPARSE_CHECKOUT_PLAN.md`](WORK_SPARSE_CHECKOUT_PLAN.md). No recommendation in those documents was executed by this audit.

## Reproduction notes

Core read-only commands used were equivalent to:

```bash
du -sb --exclude=.git .
du -sB1 --exclude=.git .
du -sb .git
git count-objects -v
git count-objects -vH
git ls-files -s -z
git ls-files --others --ignored --exclude-standard -z
git ls-files --others --exclude-standard -z
git rev-list --objects --branches --remotes --tags
git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'
git ls-tree -r HEAD
git ls-remote --heads --tags origin
```

The CSV sizes are raw Git blob sizes and use binary MiB/GiB conversions.
