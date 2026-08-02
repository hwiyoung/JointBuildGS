# Codex-to-Work Return — P2 C1/C2 development feasibility pilot v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-v1`
- source commit: `d5265d9afbe9afcd49e2bedd5900c3026f7a3b2f`
- offered commit: `9b8d7e3a50f32467f86801c8efae2b204b5ecb23`
- accepted commit: `42b6f7b82b4c30948c2339db1eb52765a61fc503`
- output commit: `SELF`
- 200 receipt: `PENDING_SEPARATE_200_BLOCKED_EVENT`
- 300 receipt: `PENDING_DIRECT_CHILD_300_CLOSED_EVENT`
- run_id: `P2-C1-C2-FEASIBILITY-PILOT-v1-20260802T1009KST`
- run_id binding: `HOST_INVOCATION_ARGUMENT_ONLY_NOT_WRITTEN_TO_ZERO_SCIENTIFIC_CONTROL`
- completed_at: `2026-08-02T10:13:52+09:00`
- proposed technical status: `BLOCKED_PRE_SCIENTIFIC_EXACT_CONTRACT`
- scientific_verdict: `null`

## Answer first

The exact committed host wrapper reached no Roofer synthetic execution and no C1/C2
scientific payload mount. Two exact-contract defects require blocked closure.

1. The wrapper revalidated the already artifact-verified `100-accepted` receipt with
   `--artifact-root`, causing one prohibited third full-read pass over the same five
   compact inputs (14,142,585 bytes) after their required pre-push and post-push
   attestations.
2. The immutable project image's CUDA/NGC startup banner preceded the committed
   `RUN`/attempt-number machine lines, causing the wrapper to emit
   `invalid or partial synthetic-smoke state` and exit with code 2 before Roofer.

The task was not rerun or repaired. Development, validation and held-out outcomes
remain unopened. The correct technical close is a blocked Return, artifact-verified
`200-blocked`, and direct-child `300-closed` returning writer ownership.

The `200-blocked` event must inherit the exact five-record `100-accepted` artifact
attestation byte-for-byte and validate only the immutable Git chain, without
`--artifact-root`; it must not perform a fourth input rehash or add the synthetic
records as new receipt-level attestations. The direct-child `300-closed` inherits the
same attestation and also validates without artifact access. Synthetic hashes remain
compact blocked-output manifest and Return evidence.

## Completed lifecycle work

- Read current root instructions and research contracts 00–06; did not use legacy
  `EXPERIMENT_PLAN.md` or `RESEARCH_CONTEXT.md`.
- Fetched and inspected the exact remote packet, human approval, source
  `d5265d9afbe9afcd49e2bedd5900c3026f7a3b2f`, and offered receipt
  `9b8d7e3a50f32467f86801c8efae2b204b5ecb23` before pull.
- Required a clean checkout and used `git pull --ff-only origin main`.
- Validated the offer, passed 20 focused runner tests, 13 instruction-sync tests and
  the zero-scientific preflight in Docker with network disabled.
- Created and pushed artifact-verified `100-accepted` commit
  `42b6f7b82b4c30948c2339db1eb52765a61fc503`; exact five compact input records passed
  live SHA-256 verification before and after push.
- Invoked only the committed host wrapper and Docker runner for the task.
- Preserved the add-once synthetic namespace and stopped before scientific prepare.

## Exact blocker

Before the synthetic decision, `run_pilot_host.sh` calls the accepted-receipt
validator with `--artifact-root`. Because the same five records had already been
live-attested before and after the accepted push, this was a repeated hash forbidden
by the no-repeat contract. The exact-source wrapper did not contain a guard that
stopped on this duplicate. The active handoff does not modify protected runner code;
it records the defect and closes.

The wrapper then captures all container stdout from:

```text
run_pilot.py next-synthetic --machine-lines
```

The immutable project image prints its CUDA/NGC banner before Python output. The
wrapper checks `smoke_decision[0] == RUN` and `smoke_decision[1] == 1`; those array
elements instead contained banner lines. A synthetic `attempt_01.started.json` marker
was written, but the Roofer command branch was never entered. No runtime log or
Roofer output exists.

The banner/line ordering was observed live and is corroborated by the immutable
project-image entrypoint `/opt/nvidia/nvidia_entrypoint.sh`, wrapper order, durable
attempt marker, and absence of downstream artifacts. Process-substitution output was
not persisted by the wrapper, so no standalone host stdout/stderr artifact is
claimed. Failure preceded scientific preparation, so the run ID remained a host
invocation argument and was not embedded in the zero-scientific control record.

This is an exact execution-interface contract failure, not a C1/C2 result and not a
Roofer scientific failure.

## Scope and leakage compliance

- required 100-accepted input full-read passes: `2`
- unexpected post-acceptance pre-scientific rehash passes / bytes: `1 / 14,142,585`
- scientific runner payload bytes opened or hashed: `0`
- `project_science_prepare` calls: `0`
- development buildings opened / result rows: `0 / 0`
- validation outcome access: `0`
- held-out outcome access: `0`
- C3/C4/C5 executions: `0`
- Fusion W1 access: `0`
- `R_ext` access: `0`
- raw UAS LAZ, raw `dim_dense`, R1 15.7 GB, `Images.zip`, `OPF.zip` access: `0`
- external `freeze/` scientific namespace: absent
- scientific_verdict: `null`

The artifact-verified acceptance lifecycle performed the required integrity-only
SHA-256 checks of the five compact inputs before execution. The later wrapper
revalidation reread those bytes but still did not mount them into or authorize the
scientific runner.

## Artifacts

- blocked manifest:
  `artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_v1/blocked_run_manifest_v1.json`
- promoted report:
  `docs/experiments/p2/c1_c2_feasibility_pilot_v1/C1_C2_DEVELOPMENT_REPORT_v1.md`
- external add-once namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_v1/P2-C1-C2-FEASIBILITY-PILOT-v1/`
- synthetic LAS: 1,587 bytes,
  SHA-256 `fe34e85a85b76c9b79e8ac80888270d5f9226ad728cc40bf9b51ccb36c61f423`
- synthetic `R_derived`: 872 bytes,
  SHA-256 `db7fffae05394cee8d17f022b24b2e4041706ac48f84236f38e3aeb268eda88b`
- synthetic control record: 531 bytes,
  SHA-256 `216d217010548e86bf378db1471e594b1aa5a1a5d16b8491408ec95bc823348c`
- synthetic attempt marker: 166 bytes,
  SHA-256 `b2a91de89501b106e1c3cfda66df4bbf521e3eea566fed599bee5590133b3757`
- exact config: Git blob `27cfb95f44b2065f98b50d0be6ffe3be9b8bf926`,
  10,772 bytes, SHA-256
  `22e8fc7e572637cab50a63ec9db6d97108dd1e872f24dcb6700c8a9eff5fec4a`
- exact roster: 2,731 bytes, SHA-256
  `c9f6412c4878a2cec3be09e465bb7a2be60f4f8329a473bf4acd44679c6afecc`

## Result contract

No C1/C2 measurement, G0/G1 outcome, canonical G2, G3, G4, `PASS_usable`, qualitative
case or C3-strategy evidence was produced. No threshold, ranking, inference or
population/generalization claim is made.

## Independent reviews before 200

- scientific scope/leakage: `PASS`; confirmed no scientific prepare, protected-split
  access, C3–C5/Fusion/`R_ext` execution or C1/C2 scientific claim.
- reproducibility/no-repeat: `PASS_AFTER_DRAFT_CORRECTIONS`; required the third-rehash
  disclosure, exact four-file inventory, config/roster binding, run-ID limitation and
  live-observation qualification now present in this Return and manifest.
- two-host ownership/closure: `PASS`; confirmed exact ancestry and required
  attestation-inheriting `200-blocked` then direct-child `300-closed`, both without
  `--artifact-root`.

The independent reviewers made no repository edits and did not rerun the task.

## Deviations

The planned synthetic Roofer call and all scientific work were not reached because
the committed exact contract failed. The unexpected third compact-input rehash and
machine-output defect are preserved rather than hidden. The 12-hour, 100 GB and retry
caps were respected; there was no retry, no scientific runner open and no raw/large
input reread.

## Recommended next action

Work Host should draft a new task and add-once namespace that validates inherited
input attestations without rehash, adds a no-repeat regression guard, and hardens the
machine decision channel against immutable-image startup output. It then requires
independent review and reauthorization. The current handoff and namespace must remain
closed and must not be reopened. No C3 strategy can be selected from this blocked run.

`scientific_verdict` remains `null`.
