# P1 GS Native Artifact Audit

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- scope: source, checkpoint schema, renderer, export surfaces
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

## Native representation

| Field/output | Evidence | Status | Notes |
|---|---|---|---|
| Center `means` | `src/stage2/model.py:107-108` | READY | Learnable 3D center. |
| Quaternion/frame | `src/stage2/model.py:110-113,193-200` | READY | Normal and tangents are derived from the learned frame. |
| Planar scale | `src/stage2/model.py:115-122,184-187` | READY | Two in-plane scales; near-zero third scale establishes 2DGS planarity. |
| Opacity | `src/stage2/model.py:133-146,189-191` | READY | Stored as raw logits, activated with sigmoid. |
| Appearance SH | `src/stage2/model.py:160-167,232-234` | READY | DC and higher-order coefficients are retained. |
| Semantic logits | `src/stage2/model.py:169-177` | READY | Four classes: background, roof, wall, terrain. |
| Prior confidence | fixed search in `src/stage2` and checkpoint schema | MISSING | No first-class per-primitive C4/C5 prior-confidence field. |
| View support | same scope | MISSING | No lossless per-primitive support-count field. |
| Image/prior conflict | same scope | MISSING | No native conflict diagnostic field. |

The core `G_native` state is `READY`; the larger diagnostic contract is
`PARTIAL` because the three missing audit fields cannot be reconstructed
losslessly from a final checkpoint.

## Renderer contract

`src/stage2/renderer.py:23-94` exposes RGB, expected depth, alpha,
world-frame rendered normal, depth-derived normal, distortion, median depth,
and renderer metadata. `renderer.py:97-151` alpha-composites semantic logits
and can isolate or release geometry gradients. This is `READY` as a renderer
capability. It does not itself provide a georeferenced surface artifact or
building assignment.

## Checkpoint contract

`src/stage2/train.py:4637-4675` writes an inference `final.pt` state dictionary;
Stage 2 group IDs/representatives are a best-effort optional addition inside a
try/except and may be absent. Separately, `src/stage2/checkpoint.py:185-266`
defines the atomic resumable schema with shape/dtype/optimizer/strategy
bindings. Atomic save/discovery/restore behavior is exercised in
`tests/stage2/test_p1w_resume_checkpoint.py:247-375,377-455` including
exact-resume tests. These schemas must be named separately in receipts. The full model
state is the only currently identified lossless native payload; optional group
exports must not be claimed unless present and hashed.

Before C3–C5 final runs, a receipt must additionally bind:

- coordinate frame, offset, horizontal CRS, vertical datum, and gravity source;
- images/cameras and split manifest;
- training config and exact code/image hashes;
- extraction method/config and method-specific `R_derived` polygon hash;
- optional prior input, derivative lineage, and confidence semantics.

## Export surfaces

| Export | Evidence | Status | Loss |
|---|---|---|---|
| Geometry PLY | `scripts/input_and_alignment/visualization_and_export/export_ply.py:18-54` | PARTIAL | Center, derived normal, DC color only. |
| Semantic PLY | `scripts/input_and_alignment/visualization_and_export/export_ply_semantic.py:19-55` | PARTIAL | Center and argmax class; logits and native frame omitted. |
| Web surfel | `scripts/input_and_alignment/visualization_and_export/export_2dgs_surfels.py:119-162` | PARTIAL | Center, axes, normal, RGB, alpha; no full checkpoint/provenance. |
| ksplat | `scripts/input_and_alignment/visualization_and_export/export_2dgs_ksplat.py:104-148` | PARTIAL | Native geometry plus one selected color mode; not a canonical audit payload. |
| Canonical lossless exchange bundle | fixed search under `src/`, `scripts/`, `tests/` | MISSING | No tested export retaining full SH, logits, opacity, frame, CRS/offset, and provenance. |

These exporters are visualization or downstream adapters. None may be labeled
as a complete native artifact without an accompanying checkpoint and receipt.

## Gravity and semantic invariants

The audit found no authorization to hard-code gravity for the new experiment.
Any new C3–C5 run must bind the once-estimated terrain-MVS gravity vector and
show that wall normals are constrained perpendicular to it. Existing local
frame or Z-up constants in historical scripts are not a substitute for this
receipt.

## Gate consequence

The current core is sufficient to design a C3 baseline, but Gate S0/P2 entry
remains blocked by the campaign input/split contract and the missing
campaign-wide artifact/diagnostic schema. No scientific fitness claim is made.
