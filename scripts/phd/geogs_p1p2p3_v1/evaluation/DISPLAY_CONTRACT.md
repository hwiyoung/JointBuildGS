# GeoGS display geometry and source provenance

`DISPLAY_ONLY` separates viewing artifacts from the geometry and samples used for
scoring. The viewer offers evaluated point/surface samples and, when registered,
the actual clipped triangle surface. Existing input-only manifests remain valid;
without `mesh_data`, the panel explicitly remains a point display.

If both reference and evaluated/displayed geometry are absent, candidate display
status is `no_geometry_reference_absent`, with the explicit reason “표시 기하 없음 ·
참조 부재로 품질평가 불가”. No points or triangles are fetched for that panel. This
is a visibility state: the original metric status remains
`NOT_ASSESSED_REFERENCE_ABSENT`, and metric values stay null. Positive geometry
without reference remains visible with undefined reference distances. Empty
prediction with available reference retains the existing reconstruction-failure
policy. These cases must not be conflated.

Point exports select an existing evaluation sample in each fixed 0.1 m voxel,
then apply a deterministic 200,000-point cap. Mesh evaluation samples were drawn
by triangle area; ALS/MVS/UAS samples are selected original source points after
the fixed evaluation voxel policy. Metadata distinguishes displayed count,
evaluation sample count, and original source points inside the ROI when that
count exists. Surface sampling, source-point voxel size, and reference voxel
size are separate fields. Display selections never enter score calculation.

Color provenance is explicit: fixed source colors are not measured RGB; colors
transferred from the nearest original mesh vertex are not interpolated texture
or official saved renders. Original point RGB is described as such only when a
producer explicitly declares it. Missing legacy provenance remains unknown.
The actual triangle view uses fixed source or height colors; reference-distance
colors belong to the already evaluated samples and are not invented at vertices.

`*.mesh.json`, `*.mesh.vertices.f64`, and `*.mesh.triangles.u32` store the exact
`clipped_vertices` and `clipped_triangles` arrays already returned by the evaluator.
Every vertex and triangle retains its order and connectivity. There is no
simplification, resampling, new clipping, boundary capping, or geometry repair.
The binary coordinates are little-endian float64; triangle indices are
little-endian uint32. WebGL alone receives float32 coordinates, which can cause
small display rounding. These are the existing local XYZ coordinates; no new
origin shift or alignment is applied. Float64 export is a storage statement,
not a claim that all distances use float64: the unchanged UAS-to-triangle BVH
uses `bvh_coordinate_dtype=float32_local_metric`, also carried in display
metadata. Export conversion runs in bounded blocks. Browser
memory still scales with the complete mesh; loading failures remain visible and
must not silently substitute simplified triangles.

Original official raw/post PLY and converted ALS prior PLY links resolve through
the candidate/input seal. They retain the full camera-bounded TSDF extraction or
prior input context, respectively, which can exceed the fixed XYZ evaluation
prism. The displayed triangle mesh is the evaluator's clipped surface portion,
with no added artificial faces at the crop boundary.

Static sections show fixed-width bands of existing evaluated samples, not
triangle-plane intersection curves. Their coordinates, sample membership,
width, axes, reference points, and selection rule remain unchanged. Official
photo/render comparisons remain separate from point and mesh color displays.

Synthetic QA inspects rendered pixels and actual draw calls/triangle counts,
point/mesh switching, raw/post and 512/1024 switching, synchronized cameras,
optional unavailability, old input manifests, and stale asynchronous responses.
The real regional viewer requires separate browser QA after candidate sealing.
A synthetic display PASS is not regional geometry or appearance quality.
`scientific_verdict` remains `null`.
