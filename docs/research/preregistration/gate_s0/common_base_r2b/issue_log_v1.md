# Gate S0 R2B Issue Log

- task_id: `P2-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- proposed status: `BLOCKED_FOR_GATE_S0_TECHNICAL_AND_HUMAN_FREEZE`
- P2 performance: PROHIBITED
- scientific_verdict: null

| ID | Class | State | Evidence | Required closure |
|---|---|---|---|---|
| R2B-I01 | retained digest | OPEN / bounded | Exact path/count/bytes and producer chain match, but no durable retained sparse/dense payload digest exists. | After human candidate acceptance only, perform one approved pass over four paths, ceiling 986,484,109 bytes. |
| R2B-I02 | depth/normal producer | OPEN | Four exact-937 member sets exist; their 2026-06-24 producer invocation/config/log is not durably bound. | Recover an exact immutable invocation record or classify the files ineligible before deciding reuse. Do not regenerate merely to close lineage. |
| R2B-I03 | coordinate frame | OPEN | EPSG:32632 source, local shift and EPSG:25832 LAZ translation are recorded; vertical datum remains UNKNOWN. | Bind the vertical datum and approved canonical transform contract. |
| R2B-I04 | component enablement | HUMAN DECISION | Depth, normal, confidence and segmentation ON/OFF remain null. | Human Gate decision; no generation before selection. |
| R2B-I05 | gravity | OPEN / REQUIRED LATER | No frozen gravity artifact exists. | After terrain-MVS-normal source selection, estimate once reproducibly; never hardcode. |
| R2B-I06 | C5 reference independence | OPEN | R2A LoD2-derived LoD1 is self-conditioned relative to its source LoD2. | Bind an exact evaluation reference independent of the input LoD2 before primary C5 eligibility. |
| R2B-I07 | remaining Gate contract | OPEN | AOI, `U_target`, `E_paired`, eligibility, split IDs/mode, toolchain and bounded cost are not all human-frozen. | Complete the Gate S0 freeze packet and obtain a separate human Gate decision. |

## Closed technical findings

- `R2B-C01`: exact 962/937/25 common-source membership is carried from DEC-P1-012.
- `R2B-C02`: retained images, COLMAP mapping/configs, OpenMVS log and all depth/normal
  member sets reproduce the same exact-937 set hash.
- `R2B-C03`: the P0 producer identity is corrected to executable blob
  `bf5cd4...` in containing commit `252ea1dc...`; recorded run commit `6d924793...`
  is preserved as its parent/logger snapshot.
- `R2B-C04`: completed-ledger exact reuse and conflict paths both resolve before
  external access; the observed exact second invocation was a zero-byte/no-write
  no-op.
- `R2B-C05`: LF/CRLF-only working-tree rewrites are normalized for scope comparison;
  real protected-scope changes remain visible.
- `R2B-C06`: a pre-output-commit recheck of the immutable accepted receipt returned
  `dirty_wip=false but working tree has 12 changed paths`. This was the expected
  visibility guard for the authorized R2B output WIP, not a receipt mismatch. The
  check must be rerun after the output commit is pushed and the tree is clean.

No issue closure here is a Gate S0, primary C5, phase, or scientific approval.
