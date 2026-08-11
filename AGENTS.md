# JointBuildGS — repository instructions

> `AGENTS.md` is the repository's only canonical agent instruction file.
> Root `CLAUDE.md` is a byte-identical compatibility mirror. Do not add nested
> `AGENTS.md` or `CLAUDE.md`; phase history belongs in README and evidence documents.
> Human reviewer: 김휘영.

## Project

JointBuildGS studies whether the structural stability of incomplete but reusable
existing 3D assets can complement the currentness and fine observations of current
aerial imagery, expanding the set of buildings for which automatic LoD2 generation
is usable. The current program uses six experiment conditions: `E1` current UAS
LiDAR, `E2` current-image MVS, `E3` image-only/no-external-prior GS, `E4` the same
GS base + unweighted Existing ALS prior, `E5` the same GS base + conflict-aware
Existing ALS prior, and `E6` the same GS base + LoD prior diagnostic. For the GS
conditions, the reusable pipeline is:

1. Stage 1: an exact Gate-S0-frozen current image/pose base and its image-derived
   SfM sparse, dense MVS, depth, normal, confidence, segmentation, and gravity evidence.
   `E2` uses its MVS geometry directly; `E3`–`E6` share the exact same GS base.
2. Stage 2: no-external-prior or single-external-prior optimization on planar 2D
   Gaussian primitives with **gsplat**. `E4` and `E5` use the same Existing ALS
   bytes, with `E4` retaining the prior without conflict attenuation and `E5`
   applying frozen conflict/currentness confidence. `E6` uses only the LoD prior.
3. Stage 3: Roofer-style evidence-to-CityGML read-out with one exact shared standard
   2D building footprint for every condition. The footprint supplies XY support and
   identity only; LoD2 Z, RoofSurface, roof type, semantic class, and final roof
   geometry remain evaluation-only.

The direct LiDAR and MVS baselines enter the same controlled Stage 3 read-out without
becoming GS training runs. `E2` sends common-base MVS geometry directly to Roofer;
`E3` reoptimizes the same image-derived geometry/support through GS first. The existing
1,104-image vendor MVS is not the common base or primary `E2` unless Gate S0 binds its
exact image/pose lineage; otherwise it remains context-only sensor-processing evidence.

The durable six-condition research definitions are the ordered contract set
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
- **Six-condition E1–E6 program: P2 technical development entered; confirmatory performance
  remains blocked.** Gate S0 preparation, remediation, exact common-base recovery and
  UAS-reference coverage promotion are technically closed. `DEC-P1-012` freezes the exact
  962/937/25 source membership. `DEC-P1-013` first authorized the 51-building C1/C2
  development pilot; `DEC-P1-014` then authorized a bounded sealed-checkpoint C3 Stage-3
  technical diagnostic; and `DEC-P1-015` opened a non-confirmatory `U_target=199`
  C1/C2/C3 technical census. That census means the former validation/held-out memberships
  are no longer untouched confirmatory sets. `DEC-P1-016` now governs the single-building
  qualitative–quantitative presentation matrix. `DEC-P1-017` authorizes one bounded,
  non-confirmatory C4 technical-development run on the exact C3-2 base with only the
  Existing ALS depth/normal prior added, after its registration/confidence and gradient/
  memory preflights pass. `DEC-P1-019` supersedes the footprint-free Stage-3 rule:
  exact LoD2 `GroundSurface` XY is now the shared standard Roofer footprint for all
  experiment conditions and all 199 target buildings. `DEC-P1-023` establishes `E2`
  current-image MVS→Roofer as the first-journal product baseline and `E3` no-prior GS
  as the mechanism ablation; product rescue/non-degradation is therefore `E2→E4/E5`,
  while `E3→E4/E5` isolates the prior-incremental effect. Historical `C1`–`C5` artifact
  IDs remain immutable lineage labels; new research design and future runs use
  `E1`–`E6`. `E6` primary interpretation, official frozen G3/G4/`PASS_usable`, confirmatory
  inference and population/generalization claims remain prohibited pending separate
  decisions and an independent test design. `DEC-P1-024` permits only the additive,
  non-confirmatory `ROOFER_REFERENCE_AUTO_OX_DEVELOPMENT_v3_NOT_OFFICIAL` viewer:
  exact stable-ID LoD2 RoofSurface plus current UAS evaluate binary O/X at
  O50/O60/O70/O80, missing prediction is X, NA is reference-absence only, and no
  official pass claim is made. Roofer/LoD2 and semantic textured mesh
  are separate output contracts. Technical Returns and receipts keep
  `scientific_verdict: null`.
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
8. **Stage 3** — use Roofer-style evidence-to-CityGML read-out with the exact same
   LoD2 `GroundSurface` XY footprint and stable building ID for every `E1`–`E6`
   condition. This
   shared control is not a condition-specific external prior. Preserve its GT-derived
   provenance and never substitute a method-derived component hull in the formal
   building-level comparison.
9. **GT separation** — building IDs may support per-building E1/E3 oracle sanity
   splits. Under `DEC-P1-019`, LoD2 `GroundSurface` XY and stable ID are the sole
   shared standard Roofer control inputs permitted across `E1`–`E6`; they may support a
   fixed per-building crop/buffer but may not classify outcomes or select parameters.
   All other reference geometry and semantic evaluation labels are evaluation-only;
   E4 receives no other GT. Record the footprint's GT-derived provenance; do not pass LoD2 Z,
   `RoofSurface`, roof type, semantic class, or final roof model into the honest arm.
10. **P0 data handling** — P0 `data/raw` is immutable. Create derived data only under
    external P0 `data/work`. Roofer input LAZ classification is ground=2 and
    building=6.
11. **Two-host handoff** — Work Host and Experiment Host must transfer write ownership
    with an immutable manifest that passes
    `scripts/repository/validate_two_host_handoff.py`. Never treat Git-only review as
    artifact verification. A technical handoff always keeps `scientific_verdict` null;
    any human verdict belongs in a separate approval document.
12. **Output separation** — Roofer/LoD2 O/X and semantic textured-mesh O/X are
    independent building-by-condition outcomes. A result may pass one and fail the
    other; neither field may be copied or inferred from the other. In changed buildings,
    a usable prior reproduction must record temporal status and cannot be claimed as
    current geometry without current evidence.

## Instruction maintenance

- Change agent policy only in root `AGENTS.md`, then update root `CLAUDE.md` to the
  exact same bytes.
- Do not put agent commands, task prompts, or rule overrides in phase README files.
- Validate the contract in Docker:

  ```bash
  python scripts/repository/validate_agent_instructions.py
  python -m unittest tests.repository.test_agent_instruction_sync
  ```
