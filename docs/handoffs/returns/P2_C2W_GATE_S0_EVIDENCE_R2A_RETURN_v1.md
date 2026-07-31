# Codex-to-Work Return Packet — Gate S0 Evidence R2A v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-EVIDENCE-R2A-v1`
- task_id: `P2-GATE-S0-EVIDENCE-R2A-v1`
- phase: `P2 / pre-result Gate S0 evidence completion`
- direction: `Codex→Work`
- status: `READY_FOR_REVIEW`
- proposed_status: `BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW`
- input_commit: `cc316024238b1db4a3f15ff6a30b31d5ebae6612`
- output_commit: `SELF`
- run_ids: `R2A-LOD1-690_5334`, `R2A-LOD1-690_5336`
- completed_at: `2026-08-01T02:15:58+09:00`
- scientific_verdict: null

## Executive summary

The bounded R2A technical task is complete. The exact Git compact source candidate
replayed without contradiction at 962 image members, 937 image/pose pairs and 25
no-pose exclusions. R1 sparse member evidence is reusable, but the exact common-base
derivative package remains incomplete: sparse canonical consumption is unresolved,
dense MVS is `AMBIGUOUS`, and depth/normal/confidence are `MISSING`. The 1,104-image
vendor MVS remains ineligible context-only evidence.

Both approved LoD2 tiles were consumed once. Their expected SHA-256 values were
computed in the same XML processing streams, and deterministic LoD1 diagnostic outputs
were published add-once for all 12,049 unique stable building IDs. The outputs contain
GroundSurface footprint rings and a single ground/top height envelope only. Every
record is `REFERENCE_DERIVED_DIAGNOSTIC_ONLY`,
`REFERENCE_DERIVED_SELF_CONDITIONED`, `primary_c5_eligible=false`.

This return does not approve Gate S0, primary C5, `U_target`, `E_paired`, a split,
component enablement or performance execution.

## Completed tasks

1. Built `reuse_ledger_v1.json` before external payload access and fixed the byte budget.
2. Replayed `B_CURRENT_CANDIDATE_c205892c390997b5` from Git compact evidence.
3. Reused exact sparse member evidence and resolved manifest-named plus bounded
   metadata-only derivative candidates.
4. Published one shared idempotent preprocessing DAG with deferred decisions left null.
5. Parsed and digested each LoD2 source in one stream and produced neutral prism JSONL
   plus reproducibly serialized/parsed `cjio==0.10.1` CityJSONSeq candidates.
6. Recorded per-building lineage, compact hashes, coverage, blockers and guards.

## Required outputs

| Output | Path |
|---|---|
| Answer-first report | `docs/research/preregistration/gate_s0/common_base_r2a/B_CURRENT_EVIDENCE_R2A_REPORT_v1.md` |
| Source replay | `artifacts/manifests/gate_s0/common_base_r2a/source_candidate_replay_v1.json` |
| Derivative matrix | `artifacts/manifests/gate_s0/common_base_r2a/derivative_provenance_matrix_v1.json` |
| Reuse ledger | `artifacts/manifests/gate_s0/common_base_r2a/reuse_ledger_v1.json` |
| Shared preprocessing DAG | `artifacts/manifests/gate_s0/common_base_r2a/preprocessing_dag_v1.json` |
| LoD1 diagnostic manifest | `artifacts/manifests/gate_s0/common_base_r2a/lod2_derived_lod1_diagnostic_manifest_v1.json` |
| Per-building lineage | `artifacts/manifests/gate_s0/common_base_r2a/lod2_derived_lod1_lineage_v1.csv` |
| Issue log | `docs/research/preregistration/gate_s0/common_base_r2a/issue_log_v1.md` |
| Output manifest | `artifacts/manifests/gate_s0/common_base_r2a/output_manifest_v1.json` |

## External diagnostic outputs

Namespace:
`artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/common_base_r2a/P2-GATE-S0-EVIDENCE-R2A-v1/`

| Output | Bytes | SHA-256 from serialized creation bytes |
|---|---:|---|
| `690_5334.lod1-prisms.jsonl` | 5,970,206 | `17478671077d58545e5cc1affe2c91153abe62d4616df27b782423e386fefe19` |
| `690_5334.lod1.city.jsonl` | 8,121,585 | `e369726c2bae54fb28807c9ecb31bb7dbcc790aa1dbeb232ece94a55d86a6980` |
| `690_5336.lod1-prisms.jsonl` | 6,912,597 | `19f64387f676a95f84e39e5faba94cd1008b57d394a383b526c9a7ca65c2ab49` |
| `690_5336.lod1.city.jsonl` | 7,468,585 | `190616b81ed125bd48990cefe56d321b9026ffe7bd00a18a4571e4b05470f372` |

The successor `200` receipt is the first `artifact_verified` promotion. It must verify
only these four outputs once before push and once after push. The direct-child
`300-closed` receipt must inherit the attestation without another output rehash.

## Verification evidence

Docker commands used for the final compact package:

```bash
python scripts/repository/validate_agent_instructions.py
python scripts/input_and_alignment/gate_s0/build_b_current_source_candidate.py --check
python scripts/input_and_alignment/gate_s0/common_base_r2a/validate_r2a_evidence.py
python -m unittest \
  tests.repository.test_agent_instruction_sync \
  tests.repository.test_repo_inventory \
  tests.repository.test_two_host_handoff \
  tests.repository.test_work_readiness \
  tests.repository.test_research_canon_common_base \
  tests.input_and_alignment.gate_s0.test_b_current_source_candidate \
  tests.input_and_alignment.gate_s0.common_base_r2a.test_r2a_evidence
```

The R1 `300-closed` predecessor was validated without `--artifact-root`, so its 15.7 GB
input records were not rehashed. Exact scope validation is part of the R2A compact
validator. New external output live verification is deliberately deferred to the first
`200` receipt safety passes above.

Final results: agent-instruction contract `OK`; source-candidate `--check` passed;
R2A compact evidence `PASS`; repository/R2A regression suite `91 tests, 0 failures`.

## Findings

| Finding | State |
|---|---|
| B_current source membership replay | `REPLAY_EXACT_FROM_GIT_COMPACT_EVIDENCE` |
| SfM sparse member evidence | `REUSED_EXACT`; canonical consumption still unresolved |
| `data/work/mvs/openmvs/scene.mvs` | `AMBIGUOUS`; metadata-only discovery, lineage unbound |
| 1,104-image vendor MVS | `INELIGIBLE_SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY` |
| Exact-base depth / normal / confidence | `MISSING / MISSING / MISSING` |
| LoD2-derived LoD1 diagnostic | `EXECUTED_ADD_ONCE`; 12,049/12,049 IDs unique |
| Primary C5 readiness | remains `MISSING`; diagnostic does not change it |
| Gate S0 / performance | blocked / prohibited |

## Changes made

- Added R2A config, reusable preparation/validation scripts and targeted tests.
- Added all required compact evidence, report, issue log and this Return Packet.
- Added four external outputs only below the approved add-once namespace.
- Did not change canonical research documents, prior receipts/evidence or raw inputs.

## Deviations

The manifest-named evidence initially indicated no exact dense-MVS derivative. Bounded
metadata discovery found one unbound `scene.mvs`, so the final matrix uses `AMBIGUOUS`
rather than `MISSING`. Its bytes were not read or hashed. No scientific or processing
substitution was made.

Because `cjio==0.10.1` is pinned and its CityJSONSeq serialize/parse round-trip preserved
all stable IDs, the optional standards-oriented candidate was produced in addition to
the required neutral prism records.

## Frozen-decision compliance

- `scientific_verdict` remains null.
- No C1-C5 performance, GS training, Roofer comparison or result access occurred.
- No held-out, Fusion W1 or `R_ext` path was opened.
- No `U_target`, `E_paired`, AOI, split, cost, algorithm, loss, adapter or threshold was frozen.
- No missing common-base derivative was generated.
- No raw/existing external file was overwritten or deleted.

## Unresolved issues

1. Resolve or reject the unbound `scene.mvs` lineage against the exact 937-member base.
2. Bind one canonical sparse consumption path without repeating the R1 sparse hash pass.
3. Produce exact shared dense/depth/normal/confidence derivatives only in a new approved
   idempotent preprocessing task.
4. Independent LoD1 remains unavailable for primary C5.
5. Human Gate S0 decisions and all other existing blockers remain pending.

## Recommended next action

Work Host should fast-forward to the direct-child `300-closed` commit, cross-review this
compact evidence and decide whether to authorize one shared common-base preprocessing
lineage task. Do not prepare a performance packet until Gate S0 is explicitly frozen.

## Launcher prompt for Work

```text
Fetch origin/main and fast-forward-only pull the exact R2A 300-closed commit. Validate
the direct-child closed receipt without rehashing the four inherited output records.
Review the source replay, derivative matrix, shared preprocessing DAG, LoD1 diagnostic
manifest/lineage and Return Packet. Keep scientific_verdict null. Treat scene.mvs as
AMBIGUOUS, the vendor MVS as context-only, and the LoD2-derived LoD1 as self-conditioned
diagnostic-only. Decide whether a separate bounded shared-preprocessing packet should
resolve/bind the exact common-base derivatives; do not authorize performance implicitly.
```
