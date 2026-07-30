# Proposed repository and artifact storage policy

## Status

This policy now governs local organization. It does not authorize deletion, `.gitignore` edits, Git LFS migration, artifact upload, or history rewriting. The sibling local artifact workspace is not yet an approved durable backup.

## Policy objective

Keep JointBuildGS's control plane—code, preregistration, configs, manifests, compact evidence, and scientific lineage—reviewable in Git while keeping bulk data and reproducible runtime material out of normal clone paths. Ignore rules are a workspace hygiene mechanism, not a backup strategy.

Implementation status (2026-07-30): `../JointBuildGS-artifacts` and [`../../artifacts/manifests/local_workspace_20260730.yaml`](../../artifacts/manifests/local_workspace_20260730.yaml) now provide local role separation and byte accounting. Off-machine durability, access control, and retention remain future backend requirements.

## Decision order

Classify each artifact by role before considering its extension or size:

1. If it is reproducible runtime material, mutable state, or cache, classify **D**.
2. If it is raw data, a checkpoint, a dense geometry/array payload, or at least 100 MiB, classify **C**.
3. If it is canonical binary evidence that must accompany the repository, changes rarely, and has an explicit allowlist owner, classify **B**.
4. Otherwise, if it is source/control-plane text or a compact deterministic fixture, classify **A**.

When uncertain, default to C for irreplaceable data and D for reproducible output. Do not force-add a file merely because a deadline requires sharing it.

## A–D contract

| Class | Storage | Typical content | Required metadata | Default retrieval |
|---|---|---|---|---|
| **A. regular Git** | Ordinary Git blob | Code, configs, tests, Markdown, compact CSV/JSON/YAML, manifests, receipts, small deterministic fixtures | Commit, producer/config reference where relevant | Normal or sparse checkout |
| **B. selected Git LFS** | Git LFS object plus pointer | Curated final figures/panels, approved PDFs, fixed binary fixtures that must be path-addressable in Git | LFS pointer, provenance, license/access note, reviewer/owner | LFS fetch for selected paths |
| **C. external artifact storage + manifest** | Immutable institutional or S3-compatible object storage | Raw datasets, checkpoints, dense LAS/LAZ/PLY, meshes, full-resolution imagery, large NPZ/NPY, run archives | Durable URI, SHA-256, bytes, producer, source inputs, Git commit, container digest, CRS, access class | Explicit manifest-driven hydration |
| **D. raw/generated/ignored data** | Local scratch/work volume | Caches, TensorBoard, preprocess intermediates, runtime env, locks/PIDs, mutable logs, rerunnable renders and panels | Producer run/config in nearby tracked record; no durability promise | Regenerate |

## Size gates

Size is a guardrail, not the sole classifier.

| Size | Proposed gate |
|---|---|
| Below 10 MiB | A is allowed for text/compact fixtures; binary collections still need aggregate review. |
| 10–50 MiB | Binary files require an explicit A/B/C/D decision in review. Prefer B only for curated canonical evidence. |
| 50–100 MiB | Block ordinary Git by default. Require B or C plus owner and provenance. |
| At least 100 MiB | C by default; do not add to ordinary Git. This also avoids GitHub's single-blob hard-limit class of failure. |
| At least 1 GiB | C only. Prefer chunked or archival packaging with checksums; never ordinary Git or routine LFS. |

Add an aggregate gate as well: a directory proposed for A/B must be reviewed when its tracked binary total would grow by 100 MiB or more. The audit shows why: 945 individually modest PNGs already total 553.596 MiB.

## Path-oriented defaults

| Path/artifact | Default class | Notes |
|---|---|---|
| `src/`, `scripts/`, `configs/`, `tests/`, root build files | A | Keep implementation and reproducibility controls in Git. |
| `docs/**/*.md`, compact tables, manifests, receipts | A | Prefer summarized evidence and stable links over payload duplication. |
| Approved final figures under a curated evidence allowlist | B | Do not blanket-track every `*.png`; select final panels only. |
| Third-party PDFs | B or C | Retain in-repo only when licensing and scientific need are documented; otherwise manifest the canonical source. |
| `data/`, phase raw data, downloaded archives | C | Current ignored local copies need a durable external source and checksums. |
| Model checkpoints and optimizer state | C | Preserve exact environment/config/commit plus model hash. |
| Dense point clouds, meshes, full-resolution imagery, large arrays | C | Small deterministic test fixtures may be A or B by explicit exception. CRS must remain EPSG:25832 where repo rules apply. |
| Canonical run reports, aggregate metrics, failure records | A | Keep concise, immutable, and tied to run IDs. |
| Raw run payloads, runtime logs, TensorBoard, caches, temp panels | D | Ignore and regenerate; promote only a curated subset to A/B/C. |
| `reports/.../cache` | D | Current tree is untracked but not ignored; propose a dedicated later ignore-policy change after owner review. |

## Manifest minimum schema for class C

Every externally stored artifact or atomic bundle should have one tracked manifest containing at least:

```yaml
schema_version: 1
artifact_id: <stable project/run/artifact identifier>
role: <dataset|checkpoint|pointcloud|mesh|image-bundle|run-bundle>
uri: <durable immutable URI, not a workstation path>
bytes: <integer>
sha256: <hex digest of file or canonical archive>
created_at: <ISO-8601 timestamp>
source:
  license_or_access_class: <public|restricted|internal plus terms>
  upstream_uri: <if applicable>
producer:
  git_commit: <40-hex commit>
  script: <repository path>
  config: <repository path>
  container_image: <tag and immutable digest>
spatial:
  crs: EPSG:25832
dependencies:
  - artifact_id: <input artifact>
validation:
  expected_files: <count>
  checks: <format, schema, or domain checks>
retention: <canonical|recovery|temporary and review date>
```

For directories, prefer a deterministic archive or a manifest containing a sorted per-file path/size/hash list and a manifest hash. Do not hash hundreds of GiB repeatedly without a corruption/copy reason; preserve verified hashes at creation and validate size/path/dependency during routine reuse.

## Report and run promotion workflow

1. Runs write to D-class local ignored locations.
2. At completion, freeze a compact A-class record: config, commit, image digest, metrics, issues, status, and references to payloads.
3. Upload irreplaceable payloads to C and record immutable URIs/checksums.
4. Curate only final visual evidence into B; reject debug frames, duplicate panels, and full render sweeps.
5. Verify a clean/partial clone can read the A record and resolve C artifacts without relying on the original workstation path.

`reports/` should have a two-layer structure in policy terms even if paths are not changed immediately:

- A/B: final summary, metric table, manifest, and a small reviewed figure set.
- C/D: per-building JSON, dense caches, raw panels, driver state, and temporary plots.

## Git LFS adoption constraints

Git LFS is not currently configured or installed in the development container. A later LFS task must therefore:

1. install and pin the client in developer/CI environments;
2. add an explicit `.gitattributes` allowlist, not blanket patterns such as all PNG or all NPZ;
3. verify server quota, retention, access, and backup behavior;
4. test clone, checkout, `GIT_LFS_SKIP_SMUDGE=1`, and selected fetch;
5. establish ownership for obsolete LFS objects.

Adding LFS now would only control new versions. It would not remove existing ordinary blobs from old commits without a coordinated history rewrite. No such rewrite is justified by the present audit.

## Proposed automated gates

A future CI/pre-commit audit may fail closed when:

- an ordinary Git blob is at least 50 MiB;
- a staged binary causes an allowlisted directory to exceed its aggregate budget;
- an LFS pointer lacks an approved path rule;
- a C-class manifest lacks URI, bytes, SHA-256, commit, producer/config, or access metadata;
- a runtime/cache path appears as staged content;
- a report references only an absolute workstation path;
- a geospatial artifact manifest omits CRS.

The checker should report only; cleanup or migration should remain an explicit human-approved task.

## Retention and recovery

- **Canonical:** keep externally with at least two independent copies where policy permits; manifest in Git.
- **Recovery checkpoint:** retain for a declared window and purpose, then review; do not silently delete.
- **Regenerable:** D-class local storage, with reproducible script/config and no durability claim.
- **Restricted/raw:** C-class storage with access controls and license/provenance metadata; never infer that ignored means safely backed up.

## Adoption sequence

1. Approve the A–D rules and owners without changing files.
2. Choose and validate the external C backend and manifest resolver on one small pilot bundle.
3. Add size/classification reporting to CI in report-only mode.
4. Curate one B allowlist and validate LFS quota/clients before changing `.gitattributes`.
5. Address unignored runtime paths, including the nightly report cache, in a separate reviewed `.gitignore` task.
6. Run a fresh partial/sparse clone acceptance test.
7. Re-audit before considering any cleanup or history migration.

No step above was executed in this audit.
