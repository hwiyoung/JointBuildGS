# Codex-to-Work Return — P2 C1/C2 feasibility pilot recovery v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-RECOVERY-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-v1`
- source commit: `8443d49df9e019cd21aad328f834479d56ab49cd`
- activation commit: `ccb804c5058033e07a0ca545426cc18c281aa4ca`
- offered commit: `e542745b8ca5045870817b430098df8502a47589`
- accepted commit: `56f5455ab6800fb61ad52fffa2189febb48c337c`
- output commit: `SELF`
- 200 receipt: `PENDING_SEPARATE_200_BLOCKED_EVENT`
- 300 receipt: `PENDING_DIRECT_CHILD_300_CLOSED_EVENT`
- requested run_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-RUN-v1`
- run_id binding: `HOST_INVOCATION_ARGUMENT_ONLY_NOT_WRITTEN_BECAUSE_AUTHORITY_GUARD_FAILED_BEFORE_NAMESPACE_CREATION`
- completed_at: `2026-08-02T10:54:24+09:00`
- proposed technical status: `BLOCKED_PRE_SCIENTIFIC_ACTIVATION_GUARD_MISMATCH`
- scientific_verdict: `null`

## Answer first

The exact recovery wrapper reached neither synthetic preparation nor scientific
processing. The activated packet and the protected wrapper disagree on one exact
authority field:

- the packet contains `- status: APPROVED_FOR_EXECUTION` but no separate
  `- user_approval: APPROVED_FOR_EXECUTION` metadata line;
- `run_pilot_host.sh` requires both exact lines with `grep -Fxq` and therefore exits
  with `packet is not explicitly activated for execution` before input stat,
  task-root creation, smoke or scientific mounts.

This is a new pre-scientific implementation/activation contract blocker. It is not a
C1/C2 result, Roofer failure or scientific finding. The packet, runner, config,
schema, tests and canon are protected and were not modified or bypassed. The recovery
namespace was not created and the same namespace was not rerun.

The correct close is this honest Return, an artifact-attestation-inheriting
`200-blocked`, and a direct-child `300-closed` returning writer ownership to Work
Host. Both receipts must validate without `--artifact-root` and without any payload
reread.

## Completed lifecycle work

- Read root `AGENTS.md` and every canonical research contract from
  `00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`; did not use legacy
  `EXPERIMENT_PLAN.md` or `RESEARCH_CONTEXT.md` as execution authority.
- Recorded the clean pre-fetch local state at prior closed commit
  `896fe284bc4d496e6e9c79720f4e75396a41d0b2`, fetched `origin/main`, and inspected
  the exact remote recovery packet and `000-offered` blob before pull.
- Proved the remote chain implementation `8443d49` → activation `ccb804c` → offered
  `e542745`, then used `git pull --ff-only origin main` from a clean checkout and
  proved `HEAD == origin/main == e542745`.
- Revalidated the prior task's exact `300-closed` as `closed`,
  `artifact_verified`, writer-returned. Its Git blob SHA-256 is
  `705348ecde9d139254bdd24e59ed02312d5321c20f802649f1ce4ca19f5b9bda`
  and its five-record canonical identity digest is
  `f63d5d4405157615d807d6babd4a9bf74a16ab13818193945ed9bbfc02532db3`.
- Confirmed the exact local project image
  `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`.
  The committed `/opt/conda/bin/python` preflight passed with 51 buildings, five
  groups, and `scientific_payload_bytes_read_or_hashed=0`.
- Created and pushed add-once `100-accepted` commit `56f5455`; pre-push and post-push
  validators passed without artifact-root access. Its five records use
  `closed_attestation_reuse`, preserve the source 300 verifier/timestamp, preserve
  source availability, and carry config-exact reuse metadata.
- Invoked the exact committed wrapper with the requested artifact root, image,
  source commit and immutable run ID. The tracked wrapper is mode `100644`; a direct
  path invocation stopped at shell exit 126 before wrapper entry. The subsequent
  `bash` invocation entered the exact wrapper and failed at its authority guard with
  exit 2. Neither event created or opened the task namespace.

## Exact blocker

The packet at activation commit `ccb804c` and offered commit `e542745` has this
metadata line:

```text
- status: `APPROVED_FOR_EXECUTION`
```

It has no `user_approval` metadata line. The exact protected wrapper at source commit
`8443d49` requires:

```text
grep -Fxq -- '- status: `APPROVED_FOR_EXECUTION`' "$PACKET_REL"
grep -Fxq -- '- user_approval: `APPROVED_FOR_EXECUTION`' "$PACKET_REL"
```

The wrapper orders this check before all five input existence checks and before
`mkdir -p "$TASK_ROOT"`. Live evidence after the failure confirmed the external
recovery namespace is absent. No safe in-scope workaround exists because changing
the packet or wrapper, substituting a parser, or bypassing the guard would modify or
circumvent protected exact-source authority.

## Smoke and result completeness

- synthetic prepare calls: `0`
- synthetic machine-decision calls: `0`
- synthetic Roofer operations: `0`
- smoke status: `NOT_STARTED_PRE_AUTHORITY_GUARD`
- scientific prepare calls: `0`
- development buildings opened/processed: `0 / 51`
- C1 `SELF_REFERENCE_UPPER_BASELINE` rows produced: `0 / 51`
- C2 `INDEPENDENT_UAS_SCORE_ONLY` rows produced: `0 / 51`
- expected result rows produced: `0 / 102`
- C1/C2 quantitative and qualitative summary:
  `NOT_AVAILABLE_PRE_SCIENTIFIC_BLOCKER`
- partial C1/C2 rows hidden or salvaged: `0`
- finalized result surface: `absent`
- promote interface calls: `0`

The exact result grain is 51 development buildings × the two separately interpreted
conditions above = 102 condition rows. The five group sizes are 47/1/1/1/1, so even a
complete result would not represent 51 independent repetitions. The required
51-building/102-row completeness gate was not met. No C1 or C2 quantitative value,
qualitative case, G0/G1/G2 outcome, G3/G4 value,
`PASS_usable`, ranking, threshold, inference, coverage expansion or C3-strategy
evidence exists.

## Scope, leakage and input-read ledger

- acceptance-time five-input full-read/hash passes: `0`
- post-acceptance artifact-root validator calls: `0`
- five compact input stat calls by the wrapper: `0`
- scientific processing-and-digest streams: `0`
- scientific payload bytes read or hashed: `0`
- Prior R1 15.7 GB, `Images.zip`, `OPF.zip`, raw UAS LAZ or raw `dim_dense` access: `0`
- validation outcome access: `0`
- held-out outcome access: `0`
- C3/C4/C5 executions or payload access: `0`
- LoD1/LoD2 input access: `0`
- Fusion W1 access: `0`
- `R_ext` access: `0`
- external recovery namespace writes/files/bytes: `0 / 0 / 0`
- duplicate scientific computation or repeated namespace execution: `0`
- scientific_verdict: `null`

Only Git-owned contracts/config/rosters, Git receipt blobs and Docker image metadata
were read during authority, preflight and receipt validation. The artifact root
directory's existence and the new task namespace's absence were checked; no
scientific payload path was opened, statted or hashed.

## Artifacts and promotion

- external namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-v1/`
  — `ABSENT`
- result manifest directory: no file created
- promoted result directory: no file created
- Return: this document only

Because finalize was never reached, the committed promote interface was correctly
not called. No result manifest or report is fabricated for a run that never opened.
The wrapper guard terminated before it could persist a task-owned runtime log, so the
exit-2 message and post-failure namespace-absence check are live Experiment Host
observations recorded in this Return rather than independently hashed Git-owned run
artifacts. Their evidence class is `SELF_ATTESTED_AND_STATICALLY_CONSISTENT`; the
packet/runner ordering that makes those observations pre-scientific is independently
inspectable at the exact commits.

## Independent reviews before 200

- scientific scope/leakage and 102-row semantics: `PASS_WITH_FINDINGS`; confirmed
  static guard ordering, 0/102 scientific result meaning, protected-scope access 0,
  and null verdict; required the row-grain/group-independence and live-evidence
  qualification now incorporated above.
- two-host ownership and receipt chain: `PASS_WITH_FINDINGS`; confirmed prior closed
  source identity, exact offer/accept chain, byte-equal receipt records and config
  reuse metadata, current Experiment Host writer, and mandatory Return-only R →
  `200-blocked` → direct-child `300-closed` order. The validator does not itself
  require source/current `verified_by` and `verified_at` equality, but this receipt's
  independently compared values are exact.
- reproducibility, path isolation and no-repeat: `PASS_WITH_FINDINGS`; confirmed zero
  exact-source implementation drift, authority-before-stat/mkdir ordering, new-path
  isolation, no artifact-root reuse validation, and no scientific rerun. Required the
  artifact-root existence and operator-observed evidence qualifications now included.

The reviewers are required to make no repository edits and not rerun the task.

## Deviations

The exact wrapper is stored as mode `100644`, so the first direct path invocation
exited before entering it. Invoking that same committed file through `bash` reached
the fail-closed authority check. The committed zero-scientific preflight also had one
initial container invocation error because the read-only mount lacked a Git
`safe.directory` setting; rerunning only that zero-payload preflight with the required
container Git setting passed. Neither deviation created the namespace or accessed
scientific payload.

The scientific task, smoke and promote steps were not retried after the exact
authority mismatch. The result absence and failure are preserved rather than hidden.

## Recommended next action

After the direct-child close returns writer ownership, Work Host should create a new
reviewed activation and new add-once namespace whose packet metadata and exact wrapper
authority parser agree. It must independently review the exact immutable source and
repeat the full offered/accepted lifecycle. This recovery packet and receipt chain
must remain closed and must not be reopened. No C3 strategy can be chosen from this
blocked run.

`scientific_verdict` remains `null`.
