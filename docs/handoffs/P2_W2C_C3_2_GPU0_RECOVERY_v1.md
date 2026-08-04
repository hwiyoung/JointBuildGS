# P2 C3-2 GPU0 recovery v1

- task_id: `P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1`
- handoff_id: `P2-W2C-C3-2-GPU0-RECOVERY-v1`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `c8f187f726f2d56f520a352f127aebcfafc5dc5c`
- approval_basis: direct human instruction to continue C1/C2/C3 unattended in this task
- scientific_verdict: `null`

## Incident and preserved result

C3-1 completed normally at iteration 30,000 with 333,738 primitives.  After its
container released the selected GPU1, an unrelated external process acquired 6,516 MiB
on that GPU.  The existing launcher correctly stopped before C3-2 because the frozen
22,000 MiB free-memory gate was no longer satisfied.  This is an orchestration resource
contention event, not a C3-1 failure.

The completed C3-1 final is immutable:

- bytes: `86,802,780`
- SHA-256: `b4f8ce6d97da6d7cef216b4edb3239ac005cc44f4d45cb459a25644ed79b62ea`
- source namespace: `P2-C1-C2-C3-UTARGET199-TORCH-CACHE-RECOVERY-v1`

## Authorized recovery

Use GPU0 only when it has at least 22,000 MiB free.  Copy the exact C3-1 final into the
fresh add-once recovery namespace and verify its byte count, SHA-256, iteration and
primitive count in Docker.  Then run only C3-2 from the same sealed
`371,808 sparse + 103,546 neutral dense` seed, exact 937 views, seed 0 and 30,000
updates.  The recovery config is byte-equivalent to the accepted C3-2 config after YAML
parsing except for `out_dir`.

C3-2 retains image-derived semantic CE and adds only image-derived MVS depth L1 with
the frozen 5k-to-10k ramp to `0.03`.  Structural, mutual, MVC, external-prior and
external-roofprint inputs remain disabled.

## Output and limits

- fresh namespace:
  `phase-payloads/p2/c1_c2_c3_utarget199_v1/P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1`
- required final pair: exact copied C3-1 final plus newly trained C3-2 final
- GPU selection: physical index 0, only after the 22,000 MiB free gate
- project image:
  `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- C1/C2 invocation: 0
- G2 invocation: 0
- C4/C5 access: 0
- external process interruption: prohibited
- official G3/G4/PASS_usable: `null`
- scientific_verdict: `null`

The Work/Experiment roles are recorded through immutable serialized-main receipts in
this same operator workflow.  No physical host visit or external human action is
required.
