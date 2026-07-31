# JointBuildGS — repository instructions

> `AGENTS.md` is the repository's only canonical agent instruction file.
> Root `CLAUDE.md` is a byte-identical compatibility mirror. Do not add nested
> `AGENTS.md` or `CLAUDE.md`; phase history belongs in README and evidence documents.
> Human reviewer: 김휘영.

## Project

JointBuildGS studies whether the structural stability of incomplete but reusable
existing 3D assets can complement the currentness and fine observations of current
aerial imagery, expanding the set of buildings for which automatic LoD2 generation
is usable. The program compares five reconstruction conditions: current UAS LiDAR,
current-image MVS, image-only GS, image + existing-LiDAR-prior GS, and image +
independent-LoD1-prior GS. For the three GS conditions, the reusable pipeline is:

1. Stage 1: SfM/MVS + 2D segmentation + gravity estimation.
2. Stage 2: image-only or single-prior optimization on planar 2D Gaussian primitives
   with **gsplat**.
3. Stage 3: Roofer-style evidence-to-CityGML read-out without an external roofprint.

The direct LiDAR and MVS baselines enter the same controlled Stage 3 read-out without
becoming GS training runs.

The durable five-condition research definitions are the ordered contract set
`docs/research/00_RESEARCH_CHARTER.md` through
`docs/research/06_DECISION_LOG.md`. The full legacy four-condition records are archived
under `docs/evidence/archive/pre_c1c5_research/`; the former paths under
`docs/research/` are compatibility notices only. Archived context and plans are not
execution authority for new work unless an exact historical-reproduction task names
them. Agents produce measurements, artifacts, gates, and issues; the human reviewer
makes scientific verdicts.

## Repository ownership

Only seven top-level directories permanently own repository information:

| Directory | Owns |
|---|---|
| `src/` | Reusable implementation and browser applications under `src/apps/` |
| `configs/` | Reusable, reviewed configuration |
| `scripts/` | Reusable execution, inspection, and repository-maintenance drivers |
| `tests/` | Automated verification for all workstreams |
| `docs/` | Research contracts, promoted reports/tables/metrics, and frozen evidence |
| `phases/` | Phase-local locked procedures/configs and compact run receipts only |
| `artifacts/` | Manifests and resolvers for payloads stored outside Git |

Root Docker/Compose/requirements files own the shared execution environment. Do not
reintroduce top-level result, report, dataset, cache, or tool-owner directories.
Reusable code must be promoted out of `phases/` into `src/`, `scripts/`, or `configs/`.

## Program status

- **P0 input-substitution audit: complete.** Its history and replay index are in
  `phases/p0-audit/README.md`; promoted evidence is in `docs/evidence/p0-audit/` and
  `docs/evidence/p0_g1_20260613/`. Completed P0 task prompts are historical records,
  not current agent instructions.
- **Five-condition program: Gate S0 evidence review pending; remediation preparation active.** The
  technical evidence package is closed at
  `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md` with proposed status
  `BLOCKED_FOR_GATE_S0_REVIEW`, `scientific_verdict: null`, and no human Gate decision.
  Before the first new
  baseline result, Gate S0 must freeze the exact AOI, `U_target`, `E_paired`, input
  identities, eligibility rule, split mode/IDs, and bounded cost from outcome-free
  evidence. No C1–C5 performance run is authorized while the recorded blockers remain.
- **Legacy P2 GS-JSO / Fusion W1: protected historical capability evidence.** Its
  phase-locked controls and compact receipts remain under `phases/p2-gsjso/`; promoted
  reports remain under `docs/experiments/pilots/fusion_w1/`. Do not execute, modify,
  relabel, or use held-out Fusion results unless an exact task explicitly names that
  legacy scope. `phases/p2-gsjso/README.md` is a status/index document, not an
  instruction override.

## Artifact resolution

Large runtime payloads are outside Git in sibling `../JointBuildGS-artifacts`.
Containers resolve the same backend as `JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`.
Git-owned resolver metadata lives in `artifacts/manifests/`; start with
`artifacts/manifests/README.md` and `artifacts/manifests/local_workspace_20260730.yaml`.

The sibling directory is local external storage, not a durable-backup claim. Do not
assume an absent repo-local `data/`, `results/`, `reports/`, or phase payload directory
means the scientific payload was deleted. Use the manifest and canonical
`JBGS_ARTIFACT_ROOT`; compatibility mounts exist only where an explicit phase Compose
declares them. Never delete or rewrite raw inputs, canonical results, or active run
payloads without an explicit, exact-target retention review and receipt.

## Repository-wide invariants

1. **Docker-based execution** — run project tools and tests in containers; do not
   install or execute project dependencies in a host conda environment.
2. **Reproducibility** — processing must be represented by a script plus config, with
   tool versions, commit, parameters, inputs, and outputs recorded for each run.
3. **One task, one commit** — use a task identifier in the commit message when a
   commit is authorized. Do not stage, commit, or overwrite unrelated user work.
   Each immutable two-host handoff event is one operational task/commit; a stable
   research `task_id` may span its ordered offered/accepted/verified/closed event
   commits, whose messages also name the event state.
4. **Failure visibility** — record and report failures and exceptions in the owning
   phase/workstream issue log; do not hide them.
5. **CRS** — P0 and geospatial outputs use EPSG:25832 and explicitly record CRS.
6. **Implementation vocabulary** — use the gsplat library, not the official 2DGS fork;
   use the canonical term “미분 가능 렌더링” (“differentiable rendering”), never
   “뉴럴 렌더링” (“neural rendering”).
7. **Gravity** — estimate gravity once from terrain MVS normals; never hardcode it.
   Wall normals are horizontal, hence perpendicular to gravity.
8. **Stage 3** — use Roofer-style evidence-to-CityGML read-out without an external
   roofprint.
9. **GT separation** — building IDs may support per-building E1/E3 oracle sanity
   splits. Footprints, roof type, final roof model, and semantic evaluation labels are
   evaluation-only inputs; E4 receives no GT. The sole first-wave exception is the
   approved lock
   `docs/research/preregistration/quality_axis/사전등록서_품질축본선_승인잠금v4_20260721.md`,
   which permits LoD2 `GroundSurface` XY as the shared standard footprint for the
   specified C001/E5 scope. Record its GT provenance; do not pass LoD2 Z,
   `RoofSurface`, roof type, semantic class, or final roof model into the honest arm.
10. **P0 data handling** — P0 `data/raw` is immutable. Create derived data only under
    external P0 `data/work`. Roofer input LAZ classification is ground=2 and
    building=6.
11. **Two-host handoff** — Work Host and Experiment Host must transfer write ownership
    with an immutable manifest that passes
    `scripts/repository/validate_two_host_handoff.py`. Never treat Git-only review as
    artifact verification. A technical handoff always keeps `scientific_verdict` null;
    any human verdict belongs in a separate approval document.

## Instruction maintenance

- Change agent policy only in root `AGENTS.md`, then update root `CLAUDE.md` to the
  exact same bytes.
- Do not put agent commands, task prompts, or rule overrides in phase README files.
- Validate the contract in Docker:

  ```bash
  python scripts/repository/validate_agent_instructions.py
  python -m unittest tests.repository.test_agent_instruction_sync
  ```
