# P1 Repository Map

- handoff: `P1-W2C-REPO-AUDIT-R2`
- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- audit time: `2026-07-31T16:50:24+09:00`
- host: Experiment Host
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

## Status semantics

`READY` means the exact capability or live object stated in the row was
observed with the metadata needed for that statement. `PARTIAL` means that
code, a manifest, or a narrower locked implementation exists but the
campaign-wide contract is incomplete. `MISSING` means the named object was
not found in the stated search scope. `UNKNOWN` means the resolver, authority,
lineage, or scope prevents a safe determination.

## Ownership and entry points

| Area | Canonical path | Evidence | Status | P1 conclusion |
|---|---|---|---|---|
| Agent contract | `AGENTS.md` | lines 17–26, 42–77 | READY | Root policy is the only agent authority; P2/Fusion W1 remains active and protected. |
| Research contract | `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md` | packet lines 42–56 | READY | The P1 audit contract is authorized, but the five-condition program has not yet replaced the durable four-condition context. |
| Reusable GS | `src/stage2/` | `src/stage2/model.py:86-200`, `src/stage2/renderer.py:23-151`, `src/stage2/checkpoint.py:185-266` | READY | gsplat-backed native model, renderer, and lossless checkpoint core are present. |
| Reusable read-out | `src/stage3/` | `building_instance.py:20-131`, `citygml_export.py:23-163` | PARTIAL | Reusable CityJSON construction exists; the filename does not imply a trusted CityGML serializer. |
| Drivers | `scripts/` | `scripts/stage3_readout/`, `scripts/pilot_1wave/` | PARTIAL | Several locked or historical drivers exist; not all use the canonical artifact resolver or the new C1–C5 contract. |
| Reviewed configuration | `configs/` | root and input/alignment configs | PARTIAL | Shared configs exist; no approved campaign-wide C1–C5/G0–G4 config bundle exists. |
| Active phase locks | `phases/p2-gsjso/` | `phases/p2-gsjso/README.md` and locked configs | READY | Evidence is readable but remains protected; it was neither run nor modified by P1. |
| Automated verification | `tests/` | `tests/stage2/`, `tests/stage3_readout/`, `tests/fusion_w1/`, `tests/e5_c001/` | PARTIAL | Many unit/contract paths run; the E5 entry point is stale and an end-to-end five-condition test is absent. |
| Artifact metadata | `artifacts/manifests/` | `README.md:1-20`, `local_workspace_20260730.yaml` | READY | Git owns resolver metadata, not payload bytes. |
| External payload | host sibling `../JointBuildGS-artifacts`; container `/artifacts/JointBuildGS` | root Compose and live mount | READY | Canonical root was reachable read-only. Only exact P1 candidates were inspected; no directory-wide hash was computed. |

## Artifact resolver

`src/artifact_paths.py:52-111` resolves declared paths without a broad basename
search. It detects ambiguity among repository candidates or among external
candidates, but `:95-110` returns a repository candidate before checking the
external tier. Repository/external shadowing is therefore not detected and
must be guarded by receipts. Historical scripts that hard-code `results/` or
phase-local compatibility paths remain `PARTIAL` until their input/output
declarations are moved behind the canonical resolver.

## Execution environments

| Environment | Evidence | Status | Limitation |
|---|---|---|---|
| Main development image | `Dockerfile:27-37`; live image `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774` | READY | Live packages include torch 2.4.1+cu121, gsplat 1.4.0, laspy 2.6.1, cjio 0.10.1, Open3D 0.18.0, trimesh 4.4.9, Shapely 2.0.6. |
| P0 tools image | `phases/p0-audit/env/Dockerfile.tools:37-48` | PARTIAL | val3dity/citygml-tools are defined in a separate historical environment, not the live main image. |
| Roofer image | `phases/p0-audit/env/docker-compose.p0.yml:31-33` and locked P2 configs | PARTIAL | A digest-pinned route exists, but Roofer is not installed in the live main image and there is no approved C1–C5 campaign driver. |
| Live main CLI set | read-only `command -v` audit | MISSING | `roofer`, `val3dity`, `cjval`, `ogr2ogr`, and `pdal` were absent. |
| CRS parsing | live Python package audit | MISSING | `pyproj` is absent; `laspy.header.parse_crs()` failed with `ModuleNotFoundError`. No installation was attempted. |

## Protected state and boundaries

- No source, configuration, dependency, data, result, active Fusion W1 file,
  held-out assignment/result, or external `R_ext` was modified or executed.
- Existing active Fusion W1 implementations are capability evidence only. They
  are not automatically the new C1–C5 implementation.
- The older `scripts/stage3_readout/run_stage3.py:107-151,240-255` assigns
  primitives using GT scene building boxes. It is oracle/diagnostic code and
  must not be used for an honest `R_derived` production arm.
- The older `scripts/stage3_readout/tum_mob_tsdf_extract.py:21-60` defaults to
  selected LoD2 footprint boxes. It is not an admissible common extractor for
  the new contract without an independently derived crop/instance protocol.
- `tests/e5_c001/test_e5_c001_s3ap_phase3.py:21-26` attempts to import a
  sibling `tests/e5_c001/e5_c001_s3ap_phase3.py`, which does not exist after
  the implementation moved under `phases/p2-gsjso/scripts/e5_c001/`. The
  E5 occupied-cell adapter therefore has static test intent but its
  current test entry point is not runnable.
- The E5/C001 occupied-cell roofprint function does not directly open a
  supplied footprint, but its upstream ground-region input is derived under
  the approved C001/E5 `GroundSurface` XY exception. It is an exception-bound
  candidate, not a campaign-wide footprint-independent adapter.

## Contract drift finding

The R2 task itself is valid, but repository status indexes are stale:
`docs/handoffs/HANDOFF_INDEX.md:8-20` still describes R2 as offer-pending, and
`docs/research/01_MASTER_ROADMAP.md:170-182,246-260,280-296` retains the
pre-activation preparation state. More importantly, `AGENTS.md:17-19` still
names `RESEARCH_CONTEXT.md` and `EXPERIMENT_PLAN.md` as durable research
definitions, while `docs/research/06_DECISION_LOG.md:261-268` leaves their
four-condition relationship to the five-condition audit program unresolved.
This is a `PARTIAL` scientific-canon finding, not an R2 activation mismatch.

## Downstream gates

- Gate S0 and P2 entry remain blocked until exact input identities, the
  campaign-wide common adapter, `U_target → E_paired`, split mode, and costs are
  frozen.
- P1 documentation can be reviewed now. `READY_FOR_REVIEW` here does not mean
  data-ready or phase-approved.
