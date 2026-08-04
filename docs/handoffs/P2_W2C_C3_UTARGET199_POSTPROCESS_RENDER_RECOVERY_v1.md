# P2 C3 U_target=199 postprocess render recovery v1

- task_id: `P2-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1`
- handoff_id: `P2-W2C-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `99450c4c079da59726095a0bf5ca2433fd6dc7e4`
- scientific_verdict: `null`

## Preserved incident boundary

The original `P2-C3-UTARGET199-POSTPROCESS-v1` namespace remains immutable.  Its
geometry freeze, 25 unique Roofer operations, 398 building-condition rows and native
point/mesh exports completed.  The first gsplat qualitative render then stopped before
writing any render panel because gsplat appended the expected-depth feature channel but
the wrapper supplied a three-channel RGB background.  The observed assertion compared
`torch.Size([1, 3])` with the required four feature channels.

This is a qualitative-render implementation defect.  It is not C1, C2, C3 training,
Roofer, G2, or metric failure.  No existing artifact is deleted or modified.

## Exact recovery operation

1. Validate this accepted receipt, the preserved namespace, and a fresh recovery
   namespace.
2. Copy the complete preserved `conditions`, `freeze`, and `results` trees plus the four
   pre-render controls into the recovery namespace.  Hash every copied regular file and
   require byte-for-byte equality, 398 rows, and 25 terminal receipts.
3. Reuse the completed CUDA extension cache only as a non-scientific runtime cache.
4. Render four exact common-base views for each checkpoint with gsplat.  White RGB
   background receives an explicit zero expected-depth background channel.
5. Generate all 199 case sheets and the qualitative HTML index, then write the combined
   recovery completion control.

The recovery invokes C3 training 0 times, Roofer 0 times, G2 0 times, metric
recomputation 0 times, and accesses C4/C5 0 times.

## Bound preserved records

| artifact | bytes | SHA-256 |
|---|---:|---|
| `control/finalized_v1.json` | 1,332 | `1f09216979659b502cbc8447d23a0004517b8cb624dd00d46c15bb277f63f038` |
| `control/population_associated_v1.json` | 970 | `2b8ff5e6efb7e9cb2576caae1601ca4858150b7e7cfa7207835eb8900741fb2a` |
| `control/C3_1_SEM_geometry_frozen_v1.json` | 3,187 | `cf18306d21b9805b66832e3fc89da437ce385fb23d0b404753aa861e77864d6f` |
| `control/C3_2_SEM_DEPTH_geometry_frozen_v1.json` | 3,242 | `ae655567fa3810424bb8db3682194391020a777abe0f481fe7bf2436df80d146` |
| `results/building_condition_metrics_v1.jsonl` | 1,020,259 | `068c59d47403fd0b717b8bdadc3e5920a61d601b5a831e32eb9055dd1b79cd62` |
| `results/method_summary_v1.csv` | 233 | `d0abc6326fbbe75751e1e655f183aea735019190d5d491ee4d71b38aca831781` |
| `freeze/execution_units_v1.jsonl` | 21,099 | `984d2ca050a194b77c8df3387f7908a316f3ef0abf0182afa582492b60459c2b` |

The exact paired checkpoints remain the accepted 30,000-step C3-1 and C3-2 finals:
`b4f8ce6d97da6d7cef216b4edb3239ac005cc44f4d45cb459a25644ed79b62ea`
and `9bda046e2414a841e289f5d9ed0c5eaf18511445f9c52638b543cd4d52ecea12`.

## Output and interpretation boundary

- output namespace:
  `phase-payloads/p2/c3_utarget199_postprocess_render_recovery_v1/P2-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1`
- project image:
  `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- expected combined result: 199 buildings, 398 result rows, 8 gsplat panels, 199 case
  sheets, 25 preserved Roofer operations
- official G3/G4/PASS_usable: `null`
- scientific_verdict: `null`

This remains non-confirmatory technical evidence for human review.  Serialized-main role
receipts are written in this operator workflow without a physical Work Host visit.
