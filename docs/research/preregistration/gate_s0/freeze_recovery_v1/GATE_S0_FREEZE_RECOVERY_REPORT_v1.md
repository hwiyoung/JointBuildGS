# Gate S0 freeze recovery technical report v1

- task: `P2-GATE-S0-FREEZE-RECOVERY-v1`
- exact accepted/source commit: `853f52c8d843fa8c9bc8d79f62e3e24e1eef10c7`
- operation ID: `48d4ad4393b42ce49e2cca1aed70b2de18558be14c1e475dfcf17559f23d4e1a`
- technical status: `BLOCKED_ROOFER_SYNTHETIC_RUNTIME_PERMISSION`
- Gate S0 decision: `null`
- scientific_verdict: `null`

## B_current and universe

The exact common source remains 962 images, 937 included image/pose pairs and 25
excluded images. The first-wave `B_current` component contract is:

| Component | Freeze state |
|---|---|
| camera/pose model | ON / READY |
| sparse points | ON / READY; 371,808 points |
| dense MVS | ON / READY |
| gravity | ON / READY |
| depth | OFF / READY_OFF |
| normal-map supervision | OFF / READY_OFF |
| confidence | OFF / READY_OFF |
| segmentation | OFF / READY_OFF |

The four common consumers are `cameras.bin`, `images.bin`, `points3D.bin` and
`dim_dense.ply`, totaling exactly 807,030,928 bytes. Context-only `rigs.bin`,
`frames.bin`, `scene.mvs` and `dim_v1.laz` were not consumed.

The canonical AOI has 199 candidates. `U_target` contains all 199 IDs, with ID-set
SHA-256 `047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5`.
`E_paired` contains 10 IDs, with ID-set SHA-256
`91b1b5c76726a3c20efba8f7b268d9598103e7faba7a5b95f7cb3d3f5bf1a777`.
The split is development 4, validation 3 and held-out 3; held-out outcomes were not
opened. The exact 199-row ledger is promoted beside this report.

## Gravity and vertical alignment

Gravity was estimated once from 8,013 dense-MVS terrain normals and was not
hardcoded:

- gravity: `[0.0022003022295437485, -0.0038866451918428023, -0.9999900262798882]`
- up: `[-0.0022003022295437485, 0.0038866451918428023, 0.9999900262798882]`
- angular median / p95: `0.33476087033589746 / 13.599275413721086` degrees

C4 and C5 input alignment used MVS terrain only. The applied Z translations were
`+45.162254791259784 m` for C4 and `+45.36964263916013 m` for C5. UAS roof geometry
was not used for C3--C5 registration, and absolute-Z metrics remain disabled.

## Independent reference and C5 prior

The independent UAS reference was frozen before the evaluation-only candidate
crosswalk and C5 input load. It contains four `UASREF_*` components and 1,184 unique
XY cells, crossing to 11 canonical buildings. Its SHA-256 remained
`42b712e637b87befceed0b90d509f035acdea477a29168da4fa45a087f6df5d3`
before and after C5, with zero changed cells. Construction used only UAS XYZ and the
frozen config. The historical AOI selection did use the approved LoD2
`GroundSurface` overlay, but neither LoD2 roof geometry nor semantic/performance
labels constructed the reference.

C1 remains a self-reference upper baseline and cannot support an independent G3/G4
accuracy claim. C2--C5 use the independent UAS reference. C5 loaded exactly 199
authorized LoD2-derived coarse LoD1 priors from the two R2A JSONL inputs, all within
the fixed 10 m availability buffer. Their inventory SHA-256 is
`f88506474ef251550451feefbfe1434dcb5c2aa2fef385fd6f9fdacddf0300d2`.
Every prior remains same-lineage diagnostic-only, with independent primary reference
required; source LoD2 reads and same-lineage primary scoring were both zero.

## Read, attempt and prohibited-access accounting

Each of the 11 scientific source stages recorded exactly one durable pre-open attempt
and one completed checkpoint: four common consumers, one C1 source, four C4 tiles and
two C5 JSONL inputs. Common-base read/hash was 807,030,928 bytes in the consumer
passes. C1 used one decode and zero full hashes; C4 used four decodes and zero full
hashes; C5 used two processing/digest passes. No checkpoint was reused at executor
start, and no incomplete output required recovery.

R1, `Images.zip` and `OPF.zip` rehashes were zero. Source LoD2 reads, failed-namespace
reads, stereo enumeration, common-base context-only bytes, performance, quality,
held-out outcomes, Fusion W1 and `R_ext` access were all zero.

## Bounded blocker

The committed five-label Stage-3 interface generated only synthetic non-performance
inputs and a non-GT `R_derived`. The only authorized host orchestrator then ran the
exact pinned Roofer image. Its single completed attempt is immutably sealed as FAIL:
exit code 139, zero JSON outputs and runtime log SHA-256
`a34591d1630d611619a7b9832e2aa3a1ae33df4afeece09fbfbd6e2bef000c41`.
The log states `Failed opening file roofer.log.json for writing: Permission denied`.
The committed invocation provides no writable current working directory for that log.
It read or hashed zero scientific source bytes.

The attempt is complete and sealed, so the checkpoint/retry contract does not permit
another Roofer invocation. The protected orchestrator was not patched, no substitute
image was used and compact promotion was not labeled successful. Resolving this
runtime-interface defect requires a separately authorized task.

This document records technical evidence and the exact technical blocker for
immutable receipt closure.
It does not make a Gate S0 decision, authorize C1--C5 performance or state a
scientific verdict.
