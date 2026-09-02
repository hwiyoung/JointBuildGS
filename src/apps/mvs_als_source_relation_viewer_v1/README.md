# MVS–Existing ALS source-relation viewer v1

Offline WebGL app for qualitative inspection of the five-class whole-space
MVS/Existing-ALS relation map. The app always keeps the two source clouds and
the relation cores as separate layers. It does not infer temporal change or
source correctness.

The reproducible builder is
`scripts/phd/mvs_als_source_relation_viewer_v1/build.py`. Runtime assets and the
self-contained served app are generated under the canonical external artifact
root; do not place generated point-cloud payloads in this source directory.

Viewer controls include:

- simultaneous MVS and ALS visibility, opacity, and point-size controls;
- independent filters for all five relation labels;
- all-label, rendering-queue, and robust-discrepancy presets;
- class, signed-M3C2, and significance-ratio colouring;
- full-scene, top, oblique, and active-tile camera navigation;
- click-to-inspect M3C2, LoD95, support counts, source, and reason fields.

The 1 m source voxel is display-only and may not feed method parameters,
labels, validation, or scientific conclusions. `scientific_verdict` remains
`null`.
