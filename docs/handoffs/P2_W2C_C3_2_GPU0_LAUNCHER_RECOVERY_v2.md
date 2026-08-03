# P2 C3-2 GPU0 launcher recovery v2

- task_id: `P2-C3-2-GPU0-LAUNCHER-RECOVERY-v2`
- handoff_id: `P2-W2C-C3-2-GPU0-LAUNCHER-RECOVERY-v2`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `37f13426582a2abebe37b0e87420ab565dd86422`
- scientific_verdict: `null`

## Exact correction

The v1 launcher stopped before creating an artifact namespace because a host `-d` test
could not traverse the inherited semantic payload's mode-0700 parent.  The 937-mask
directory exists and the project Docker can read it through the already approved
read-only direct bind.  V2 replaces only that host permission probe with the same
Docker inventory gate used by the accepted pair launcher.

The C3-1 final, C3-2 config/losses, seed, views, GPU0 22,000 MiB free-memory gate,
fresh output namespace and all scientific boundaries are unchanged from v1.  The
invalid v1 closure attempt is preserved as failure evidence and is not execution
authority.

## Execution boundary

- reuse exact C3-1 final: 86,802,780 bytes,
  `b4f8ce6d97da6d7cef216b4edb3239ac005cc44f4d45cb459a25644ed79b62ea`
- train only C3-2 at seed 0 for exactly 30,000 updates on GPU0
- exact common base: 937 views, 371,808 SfM sparse + 103,546 neutral dense seed
- output namespace:
  `phase-payloads/p2/c1_c2_c3_utarget199_v1/P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1`
- C1/C2, G2 and C4/C5 invocation/access: 0
- external GPU1 process interruption: 0
- official G3/G4/PASS_usable: `null`
- scientific_verdict: `null`

The serialized-main role receipts are created in this operator workflow without a
physical host visit.
