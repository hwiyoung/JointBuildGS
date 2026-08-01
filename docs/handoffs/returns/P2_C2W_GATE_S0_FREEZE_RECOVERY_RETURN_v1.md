# Codex-to-Work Return — Gate S0 Freeze Recovery v1

## Return metadata

- handoff_id: `P2-W2C-GATE-S0-FREEZE-RECOVERY-v1`
- task_id: `P2-GATE-S0-FREEZE-RECOVERY-v1`
- accepted commit: `853f52c8d843fa8c9bc8d79f62e3e24e1eef10c7`
- output commit: `SELF`
- verified receipt commit: `PENDING_SEPARATE_200_EVENT`
- closed receipt commit: `PENDING_SEPARATE_300_EVENT`
- proposed technical status: `BLOCKED_ROOFER_SYNTHETIC_RUNTIME_PERMISSION`
- Gate S0 decision: `null`
- P2 performance: PROHIBITED
- scientific_verdict: `null`

## Scope completion

The Experiment Host accepted writer ownership through an immutable metadata-only
artifact and `100-accepted` receipt, pushed the acceptance before source access, and
ran the committed recovery executor in the accepted project image. The executor
completed and fsync-checkpointed all bounded common-base, C1, C4, C5, reference,
universe, split and synthetic Stage-3-interface stages. The only authorized Roofer
orchestrator then produced a sealed runtime failure. Compact evidence is therefore
promoted with an explicit blocked status rather than a successful promotion claim.

No C1--C5 performance, GS training, quality scoring, held-out outcome, Fusion W1 or
`R_ext` run was executed. No protected path or previous packet, Return or receipt was
modified.

## Exact recovered freeze evidence

The exact source remains 962 images / 937 included pairs / 25 excluded images.
`B_current` is camera/pose ON, sparse ON, dense MVS ON and gravity ON; depth, normal
map supervision, confidence and segmentation are OFF. All eight component states are
technically bound as READY or READY_OFF. The common consumer graph contains four
files and 807,030,928 bytes; sparse point count is 371,808.

The measured gravity vector is
`[0.0022003022295437485, -0.0038866451918428023, -0.9999900262798882]`,
estimated from 8,013 dense-MVS terrain normals with `hardcoded_gravity=false`.

The canonical candidate population and `U_target` both contain exactly 199 stable
IDs. `E_paired` contains 10: development 4, validation 3 and held-out 3. Protected
held-out outcomes were not accessed. The exact promoted ledger records all 199 units,
exclusions, spatial groups and assignments.

## Independent UAS isolation and C5

The independent UAS reference was frozen before the candidate crosswalk and C5 load.
It contains four components and 1,184 cells, with 11 canonical buildings having
reference support. The reference digest was unchanged before/after C5 and zero cells
changed. It was constructed only from UAS XYZ and the frozen config. The approved AOI
selection retains its historical LoD2 `GroundSurface` influence, but LoD2 roof
geometry, roof type and semantic/performance labels did not construct or score the
reference.

C1 is explicitly a self-reference upper baseline. C2--C5 use the independent UAS
reference. C3--C5 registration did not use UAS roof geometry. C4 and C5 alignment are
MVS-terrain-only, with applied translations `+45.162254791259784 m` and
`+45.36964263916013 m`; primary evaluation remains terrain-normalized/relative and
absolute-Z metrics are disabled.

C5 contains exactly 199 authorized R2A LoD1-derived priors, all available within the
fixed 10 m buffer. Inventory SHA-256 is
`f88506474ef251550451feefbfe1434dcb5c2aa2fef385fd6f9fdacddf0300d2`.
Every prior retains diagnostic/self-conditioned same-lineage status and requires an
independent primary reference. Source LoD2 reads and same-lineage scoring were zero.

## Read and no-repeat accounting

- common-base consumers: 4 opens/passes, 807,030,928 read/hash bytes;
- C1: 1 decode/open attempt, 0 full hashes;
- C4: 4 decode/open attempts, 0 full hashes;
- C5: 2 JSONL processing/digest passes and 2 open attempts;
- every one of the 11 source stages: exactly 1 durable attempt and completed
  checkpoint; configured maximum remains 2;
- context-only common-base bytes, R1/`Images.zip`/`OPF.zip` rehashes, source LoD2
  reads, failed-namespace reads and stereo enumeration: all 0;
- executor-start reused checkpoints and recovered pending outputs: 0.

## Exact bounded blocker

The only committed host Roofer orchestrator ran the pinned digest
`3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`
with observed image ID
`sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba`.
The completed attempt is sealed with exit code 139 and zero CityJSON/JSON outputs.
Its log records `Failed opening file roofer.log.json for writing: Permission denied`:
the committed container working directory is not writable for the runtime user. The
smoke used only synthetic inputs, a non-GT `R_derived`, and zero scientific source
bytes.

Because the attempt is complete and sealed, the retry contract does not authorize a
second invocation. The protected orchestrator was not patched and the result is not
reported as a Roofer pass. This is the sole blocking condition; resolving it requires
a new bounded Work-to-Codex task.

## Operational deviations and failure evidence

1. The packet's historical `implementation_commit`
   `1687432a586a5a924e17e556860171bc83e64cad` did not contain the current packet blob,
   so its initial zero-payload preflight stopped on that Git binding mismatch before
   scientific access. The preflight was rerun against the exact offered/accepted
   commit and passed; executable blobs were unchanged.
2. The first acceptance helper text had a Python parse-time syntax error before any
   `lstat`, output or source access. The corrected add-once helper created the exact
   11-path metadata-only artifact.
3. The pinned Roofer image was initially absent locally. The exact digest was pulled,
   its image ID matched the frozen config, and only then did the committed
   orchestrator make its single sealed attempt.

These deviations added no scientific payload read, retry or scope expansion.

## Independent reviews

The scientific-leakage/reference-isolation review passes the completed recovery
evidence and separately confirms that the Roofer failure prevents a full technical
pass. The checkpoint/read-accounting review confirms one attempt per source stage and
prohibits another sealed Roofer attempt. The ownership/receipt review is applied to
the immutable 200/300 closure sequence.

## Writer return contract

After this output commit is pushed and verified against exact `origin/main`, the
Experiment Host will add immutable `200-verified` and direct-child `300-closed`
events. Those receipts verify this honest blocked Return without converting it into a
successful Roofer result. `300-closed` will not reread external artifacts and will
return exclusive writer ownership to the Work Host. `gate_decision` and
`scientific_verdict` remain null.
