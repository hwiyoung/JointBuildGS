# P2 C3 full-scene TSDF → semantic roof → texture v1 closure / next-session handoff

## Current closed result

- task: `P2-C3-FULL-SCENE-TSDF-SEMANTIC-TEXTURE-v1`
- execution source commit: `51d568051165ed69219f7670056e8366edd6e312`
- resolver commit before this handoff: `85ec24dafd30bdf5f80d72ced4627a647e926ce1`
- artifact URI: `artifact://JointBuildGS/phase-payloads/p2/c3_full_scene_tsdf_semantic_texture_v1/P2-C3-FULL-SCENE-TSDF-SEMANTIC-TEXTURE-v1`
- absolute path: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c3_full_scene_tsdf_semantic_texture_v1/P2-C3-FULL-SCENE-TSDF-SEMANTIC-TEXTURE-v1`
- status: `300-CLOSED_LOCAL_FULL_SCENE_TSDF_SEMANTIC_TEXTURE`
- scientific_verdict: `null`

The executed order was full-scene building AOI GS rendered median depth → 0.15 m TSDF →
depth-consistent multi-view semantic posterior → roof extraction → current RGB texture.
Semantic class was not used before TSDF integration.

## Result summary

| condition | building | full TSDF triangles | extracted roof triangles | footprint coverage | texture |
|---|---|---:|---:|---:|---|
| C3-1 | 4906975 | 517,668 | 249,582 | 91.61% | complete |
| C3-2 | 4906975 | 539,226 | 245,943 | 91.14% | complete |
| C3-1 | 4907177 | 13,923 | 0 | 0.00% | skipped: empty roof |
| C3-2 | 4907177 | 56,347 | 0 | 0.00% | skipped: empty roof |
| C3-1 | 108580336 | 991,300 | 19,839 | 4.60% | complete but sparse |
| C3-2 | 108580336 | 864,073 | 11,404 | 1.92% | complete but sparse |

Execution counters: GS training 0, checkpoint render extraction 2, full-scene TSDF 6,
semantic roof extraction 6, texture attempt/completion 6/4, Roofer 0, G2 0, metric
recomputation 0, C4/C5 access 0.

## 4907177 interpretation boundary

The displayed RGB roofline already projects the 2022 LoD2 RoofSurface as orthometric input
with the configured `+45.7 m` conversion. Its nearly line-like, non-roof-aligned projection
therefore cannot be attributed to an omitted vertical shift alone. Keep this case in
`REFERENCE/ID/ALIGNMENT REVIEW`; possible temporal change, demolition, ID/XY mismatch, and
visibility remain unresolved.

The closed full-scene C3 result used the C2-local ground anchor `581.193449 m`, not the prior
LoD2-derived diagnostic anchor `559.97 m`. A read-only post-processing what-if on the exact
closed TSDF and semantic arrays produced:

| condition | 581.193 m roof triangles / coverage | 559.97 m roof triangles / coverage |
|---|---:|---:|
| C3-1 | 0 / 0.00% | 1,924 / 17.93% |
| C3-2 | 0 / 0.00% | 2,025 / 14.73% |

These what-if surfaces are not a finalized artifact and must not be described as a recovered
current building. The earlier separate C1 diagnostic used the 559.97 m anchor, obtained 740
class-6 and 71 class-2 points, and completed Roofer, but its geometry remained qualitatively
poor.

## 108580336 interpretation boundary

Within the footprint buffer, above ground+2.5 m, and with at least two-view support, semantic
argmax was dominated by wall/terrain:

| condition | roof | wall | terrain |
|---|---:|---:|---:|
| C3-1 | 1.24% | 82.46% | 16.31% |
| C3-2 | 1.47% | 79.30% | 19.22% |

The immediate roof-extraction bottleneck is semantic assignment, but the class-agnostic TSDF
is also not a clean building mesh: C3-1 has 7,524 connected components (largest 23.3%) and
C3-2 has 4,062 (largest 36.0%); both are non-watertight. The current pale panels also
understate the existing triangles because they use light RGB faces on white, no solid
lighting, and a display face cap.

## Fixed next-board contract

If work continues in a new session, do not retrain GS and do not reconstruct the six closed
TSDF meshes. Re-render from the exact closed PLY/NPZ sources with solid, readable shading.

The comparison row for C1 must be **C1 Roofer output**, not C1 LiDAR input.

Recommended rows per building/condition:

1. 2024 RGB + 2022 LoD2 roofline projection context
2. C1 Roofer output
3. 2022 LoD2 epoch reference
4. class-agnostic full TSDF, opaque neutral/normal shading
5. largest connected TSDF component
6. full TSDF semantic class
7. continuous roof-probability heat map
8. thresholded semantic roof mesh
9. current RGB textured roof with display-only footprint wall

For 4907177, place the 581.193 m closed result and the 559.97 m post-processing diagnostic
side-by-side, while keeping `REFERENCE/ID/ALIGNMENT REVIEW` visible. For 108580336, use a
tighter footprint-centered camera and solid shading so geometry fragmentation can be judged
separately from semantic filtering.

## Pasteable next-session request

```text
Continue from docs/handoffs/P2_C3_FULL_SCENE_TSDF_SEMANTIC_TEXTURE_v1_CLOSURE.md.
Do not retrain GS, rerun Roofer/G2, recompute official metrics, or reconstruct the six closed
TSDF meshes. Produce a clearer diagnostic board from the exact closed full-scene TSDF PLY/NPZ
sources. C1 must be represented by C1 Roofer output, not the C1 LiDAR input. Use opaque solid
shading, largest connected component, semantic class, roof-probability heat map, extracted
roof, textured roof, RGB+LoD2 roofline, and LoD2 reference. Show 4907177 current 581.193 m vs
559.97 m post-processing anchors side-by-side and keep it as REFERENCE/ID/ALIGNMENT REVIEW.
Keep scientific_verdict=null.
```
