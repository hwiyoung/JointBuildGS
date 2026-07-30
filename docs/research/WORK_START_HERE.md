# ChatGPT Work start here

This is the authoritative entry point for a remote ChatGPT Work checkout of
JointBuildGS.  It limits context deliberately: repository inventory is not a
scientific authority, and a newer filename is not evidence that a document is
canonical.

## Authority order

Read and obey these sources in order:

1. [`../../AGENTS.md`](../../AGENTS.md) — repository-wide rules and protected scopes.
2. This file — remote Work allowlist and exclusions.
3. [`RESEARCH_CONTEXT.md`](RESEARCH_CONTEXT.md) — durable method definition.
4. [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md) — experiment sequence and gates.
5. [`../../phases/p2-gsjso/README.md`](../../phases/p2-gsjso/README.md) — active phase status and navigation only.
6. The exact preregistration, config, report, manifest, or receipt named by the task.

If two sources conflict, stop at the higher source and record the conflict.  A
phase README, run prompt, log, candidate map, or archive file cannot override
root `AGENTS.md`.

## Exact default allowlist

The following files may define current repository context without additional
canonical review:

- [`RESEARCH_CONTEXT.md`](RESEARCH_CONTEXT.md)
- [`EXPERIMENT_PLAN.md`](EXPERIMENT_PLAN.md)
- [quality-axis approved lock](preregistration/quality_axis/사전등록서_품질축본선_승인잠금v4_20260721.md)
- [quality-axis implementation appendix lock](preregistration/quality_axis/품질축본선_1파_구현부록잠금v1_20260722.md)
- [Fusion W1 Gate A v2/SE3 lock](preregistration/fusion_w1/사전등록_관문A_v2·SE3채택재판정_20260725.md)
- [Fusion W1 Gate A diagnostic owner](../experiments/pilots/fusion_w1/reports/W_관문A진단_20260725.md) — observations only, not a success verdict
- [Fusion W1 WIP technical disposition](reproducibility/FUSION_W1_WIP_DISPOSITION_20260730.md) — reproducibility handoff and exclusions, not a scientific verdict
- [Work–Codex two-host handoff contract](reproducibility/CHATGPT_WORK_CODEX_HANDOFF.md) — write ownership, commit, scope, and artifact-claim protocol
- [P0 audit evidence index](../evidence/p0-audit/README.md)
- [P0 G1 frozen package index](../evidence/p0_g1_20260613/README.md)
- [boundary-map family index](../experiments/input-and-alignment/boundary_map/README.md)

Purpose-specific E5 C001 reports listed under **Explicit canonical seeds** in
[`repository/CANONICAL_MAP.md`](repository/CANONICAL_MAP.md) may be used only for
their stated purpose.  They do not combine into an inferred single final verdict.

## Default exclusions

Do not use the following as current truth or instructions unless the task names
an exact path and role:

- `docs/evidence/archive/**` and compatibility mirrors;
- `docs/research/repository/migrations/**` as scientific evidence;
- past prompts, logs, or receipts under `phases/**` as agent instructions;
- `canonical_candidate`, `orphan_candidate`, `superseded_candidate`,
  `superseded`, `temporary`, or `retracted` documents;
- a `supporting` document as a current conclusion;
- the inferred target paths in the canonical map's review queue;
- archive branches or tags.

For reproduction, an exact version or hash pinned by a preregistration, config,
manifest, or receipt takes precedence over a family-wide current canonical.  In
particular, do not replace a Fusion run's locked boundary-map v2 input with v4.1.

## Artifact and missing-reference contract

Large payloads are not present in a remote clone.  Resolve reviewed references
through [`repository/DOCUMENT_REFERENCE_RESOLUTIONS.csv`](repository/DOCUMENT_REFERENCE_RESOLUTIONS.csv)
and [`repository/REFERENCE_RESOLUTION_POLICY.md`](repository/REFERENCE_RESOLUTION_POLICY.md).

- `artifact://JointBuildGS/...` means the payload was verified in the local
  external artifact backend but is not available to remote Work.
- `missing://JointBuildGS/...` means the exact evidence was absent from both Git
  and the reviewed local backend.  Never substitute a same-named file from a
  different run or experiment.

## Fusion W1 handoff boundary

Fusion W1 now has a committed technical disposition rather than an unnamed
local exception. Code, configs, wrappers, compact receipts, and tests are Git
content; large run payloads and exact historical receipt sources remain external.

Remote Work may inspect and modify Fusion code only for an exact named task. It
must preserve these distinctions:

- 157 passing Docker tests establish technical consistency, not a scientific verdict;
- completed Dense V5 and A′ V6/V7 outputs are `integrity_verified_external_unpromoted`;
- receipt-era reproduction uses source-lock v4, never the current worktree as a silent substitute;
- the superseded V2 manual-QA document is recoverable from the WIP snapshot but is intentionally not Git evidence;
- without the external artifact backend, Work must not claim to have regenerated or revalidated payloads.

Start with
[`reproducibility/FUSION_W1_WIP_DISPOSITION_20260730.md`](reproducibility/FUSION_W1_WIP_DISPOSITION_20260730.md)
and the exact task's config/receipt. Any new run gets a new namespace and receipt;
existing completed artifacts are never overwritten.

## Two-host write handoff

ChatGPT Work and the local Experiment Host do not edit the same task concurrently.
Every cross-host write transfer uses an immutable manifest conforming to
[`two_host_handoff.schema.json`](../../artifacts/manifests/schemas/two_host_handoff.schema.json)
and must pass [`validate_two_host_handoff.py`](../../scripts/repository/validate_two_host_handoff.py).

- The current default is serialized ownership of durable branch `main`.
- Work Host may claim `git_only`; only the artifact-aware Experiment Host may claim
  `artifact_verified` after reading the declared payloads.
- A stale base SHA, overlapping allowed/protected scope, or missing snapshot for dirty
  WIP fails closed.
- Technical verification never supplies a scientific verdict.

Start with
[`CHATGPT_WORK_CODEX_HANDOFF.md`](reproducibility/CHATGPT_WORK_CODEX_HANDOFF.md)
before the first write intended for the Experiment Host.

## Catalog interpretation

[`repository/DOCUMENT_CATALOG.csv`](repository/DOCUMENT_CATALOG.csv) is an
inventory.  Its heuristic status and filename-version candidates are review
queues, not approvals.  Only `explicit_repo_rule`, `reviewed_family_map`, or
explicit metadata backed by a named decision may establish lifecycle status.
