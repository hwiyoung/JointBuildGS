# C1/C2 development feasibility pilot v1 — blocked pre-scientific report

- task: `P2-C1-C2-FEASIBILITY-PILOT-v1`
- handoff: `P2-W2C-C1-C2-FEASIBILITY-PILOT-v1`
- run: `P2-C1-C2-FEASIBILITY-PILOT-v1-20260802T1009KST`
- completed_at: `2026-08-02T10:13:52+09:00`
- proposed technical status: `BLOCKED_PRE_SCIENTIFIC_EXACT_CONTRACT`
- development outcomes opened: `0`
- validation outcomes opened: `0`
- held-out outcomes opened: `0`
- scientific_verdict: `null`

## Answer first

The pilot stopped before Roofer synthetic execution and before any development
scientific mount. Two pre-scientific exact-contract defects were observed.

First, the committed host wrapper revalidated the already artifact-verified
`100-accepted` receipt with `--artifact-root`. This reread the same five compact inputs
after their required pre-push and post-push acceptance attestations: one prohibited
duplicate pass over 14,142,585 bytes. The current exact-source wrapper did not stop on
that duplicate.

Second, the wrapper expected `next-synthetic --machine-lines` to place `RUN` and `1`
in the first two captured lines. The exact immutable project image emitted its
CUDA/NGC banner first, so the wrapper returned:

```text
invalid or partial synthetic-smoke state
```

The banner/line ordering was observed live and is corroborated by the immutable image
entrypoint `/opt/nvidia/nvidia_entrypoint.sh`, wrapper order and durable partial-state
artifacts. The wrapper did not persist its process-substitution stdout/stderr, so no
separate host-output log is claimed.

Under the no-repeat and stop contracts, this exact interface failure is not repaired
or rerun in the active task. No C1 or C2 development result exists, and no evidence
about a C1/C2 gap, Stage-3 scientific stability, or a C3 strategy may be inferred.

## Activation and preflight evidence

- Remote `origin/main` was exactly the offered commit
  `9b8d7e3a50f32467f86801c8efae2b204b5ecb23` before fast-forward-only pull.
- The approved source was exactly
  `d5265d9afbe9afcd49e2bedd5900c3026f7a3b2f`; human approval and `DEC-P1-013`
  authorized only C1/C2 on 51 development buildings.
- Offer validation, 20 focused C1/C2 tests, 13 repository instruction-sync tests,
  and the zero-scientific committed preflight passed in Docker with network disabled.
- Artifact-verified `100-accepted` commit
  `42b6f7b82b4c30948c2339db1eb52765a61fc503` passed before and after push. Its
  lifecycle validator read and verified exactly the five authorized compact input
  records in the two protocol-required passes. This integrity verification was not a
  scientific execution.

## Exact failure boundary

The committed wrapper then completed these pre-scientific operations:

1. revalidated the accepted handoff with `--artifact-root`, creating the prohibited
   third full-read pass over the five immutable compact inputs;
2. ran the zero-scientific preflight;
3. wrote the deterministic synthetic LAS and `R_derived` GeoJSON;
4. invoked the committed `next-synthetic --machine-lines` decision command.

The authority revalidation did not interpret geometry or outcomes and did not mount
the inputs into the scientific runner, but it violated the no-repeat attestation
contract. The five duplicate records total 14,142,585 bytes.

The decision subprocess did return a synthetic attempt marker, but its stdout was
preceded by the immutable image banner. The wrapper therefore did not enter the
Roofer launch branch. There is no synthetic Roofer runtime log or output model.
The wrapper exited before `project_science_prepare`; the external `freeze/` namespace
does not exist.

| Counter | Observed |
|---|---:|
| Synthetic attempt markers | 1 |
| Synthetic Roofer attempts | 0 |
| Unexpected post-acceptance input rehash passes / bytes | 1 / 14,142,585 |
| Scientific prepare calls | 0 |
| Scientific operation attempts | 0 |
| Development buildings opened | 0 |
| Development result rows | 0 |
| Validation outcome accesses | 0 |
| Held-out outcome accesses | 0 |
| C3–C5 executions | 0 |
| Fusion / `R_ext` accesses | 0 / 0 |

## Preserved synthetic artifacts

The add-once namespace contains four files totaling 3,156 bytes. Its exact inventory
is:

- `control/synthetic_inputs_v1.json`: 531 bytes,
  SHA-256 `216d217010548e86bf378db1471e594b1aa5a1a5d16b8491408ec95bc823348c`
- `smoke/attempt_01.started.json`: 166 bytes,
  SHA-256 `b2a91de89501b106e1c3cfda66df4bbf521e3eea566fed599bee5590133b3757`
- `smoke/work/input.las`: 1,587 bytes,
  SHA-256 `fe34e85a85b76c9b79e8ac80888270d5f9226ad728cc40bf9b51ccb36c61f423`
- `smoke/work/r_derived.geojson`: 872 bytes,
  SHA-256 `db7fffae05394cee8d17f022b24b2e4041706ac48f84236f38e3aeb268eda88b`

The namespace is preserved and is not overwritten or reused for another attempt.

The exact config is Git blob `27cfb95f44b2065f98b50d0be6ffe3be9b8bf926`,
10,772 bytes, SHA-256
`22e8fc7e572637cab50a63ec9db6d97108dd1e872f24dcb6700c8a9eff5fec4a`.
The 2,731-byte roster SHA-256 is
`c9f6412c4878a2cec3be09e465bb7a2be60f4f8329a473bf4acd44679c6afecc`.
Because failure preceded scientific preparation, the supplied run ID was only a host
invocation argument and was not persisted by the zero-scientific control record; the
blocked manifest and Return bind it without claiming a prepared operation.

## Result and interpretation contract

There is no 51×2 table, G0/G1 row, runtime distribution, group summary, qualitative
case output, or continuous geometry metric because the scientific stage did not open.
Canonical G2, G3, G4 and `PASS_usable` remain null. C1 self-reference and C2
independent-reference results do not exist and are not ranked.

This blocked run says nothing about C1, C2, MVS quality, Roofer scientific stability,
or population/generalization. It also provides no empirical basis for selecting a C3
representation, loss, threshold, or schedule.

## Required Work Host action

Prepare a new reviewed task and namespace that (1) validates inherited input
attestations without `--artifact-root` rehash and adds an exact no-repeat regression
guard, and (2) makes the machine decision channel unambiguous while keeping the image,
scientific inputs, parameters, roster and caps fixed. Examples for review include
suppressing the container startup banner for machine-mode calls or parsing an
explicitly delimited final response.
The current task must not be reopened or salvaged.

`scientific_verdict` remains `null`.
