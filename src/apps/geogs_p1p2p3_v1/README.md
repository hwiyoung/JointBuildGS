# GeoGS P1/P2/P3 local evidence viewer

This task-local app consumes actual exported evidence. It does not reconstruct,
sample or simplify surfaces, compute scientific scores or invent figures. All views share a
camera, target, common region bounds and metric display scale. Gaussian centers
are explicitly rejected as a reconstructed surface. `scientific_verdict` stays
`null`. Point samples and the exact clipped triangle display are `DISPLAY_ONLY`;
evaluation uses the separately recorded full source/surface contract.

Manifest URL: `?manifest=/task/evaluation/viewer/manifest.json`. Relative data,
figure and download URLs resolve against that manifest, not the HTML location.
The app imports the existing local Three.js module. No CDN is required.

## Manifest contract

- `schema`: `geogs_p1p2p3_viewer_v1` or `geogs_p1p2p3_viewer_cases_v2`;
  `scientific_verdict`: `null`. The cases-v2 export also requires a 64-hex
  `previous_manifest_sha256` identifying its preserved original manifest.
  Browser validation checks the field's format; artifact sealing verifies bytes.
- `regions`: nonempty list; optional `default_region`, `downloads`.
- Optional top-level `resolution_modes` and `default_resolution` declare surface
  comparison modes. The resource-v3 export uses
  `{id:'1024',label:'Main final comparison 1024',mesh_res:1024,
  anchor_variant:'anchor',final_variant:'final'}` and
  `{id:'512',label:'Matched anchor/refinement 512',mesh_res:512,
  anchor_variant:'anchor_512',final_variant:'mesh_512'}`, default `1024`.
  The selector changes anchor, native and selected-condition variants together;
  camera, case focus and scale stay unchanged. Legacy manifests without these
  fields retain their candidate IDs and hide the selector.
- Each region: `id`, `label`, `bounds: {min:[x,y,z], max:[x,y,z]}` in one shared
  scene-local metric frame, `frame`, `notes` (strings), `candidates`,
  `panel_candidates`, `conditions`, optional `default_condition`.
- `panel_candidates` maps `prior`, `mvs`, `anchor`, `vanilla`, `reference` to
  candidate IDs. The sixth panel comes from the selected condition.
- Conditions: `{id,label,candidate_id,downloads?}`. Empty conditions are allowed;
  the change panel then remains explicitly pending.
- `*.anchor.raw`, `*.final.raw` candidate suffixes are switched to `.post` by the
  Raw TSDF / official postprocessing selector, synchronously for anchor, vanilla
  and changed panels. Missing postprocessed outputs remain explicitly pending;
  they never silently fall back to raw. Prior display switches `prior_mesh` and
  `als_points` to expose conversion effects. Absent raw-ALS options are disabled.
- With resolution modes, candidates are `D005_Pnative.anchor.raw/post` and
  `CONDITION.final.raw/post` for 1024, or `D005_Pnative.anchor_512.raw/post` and
  `CONDITION.mesh_512.raw/post` for 512. `native_repeat_1` changes the selected
  final candidate only; its anchor panel uses the same primary anchor. Missing
  1024 anchor extraction must be explicitly registered as `status:'failed'` with
  the actual `reason`, including `TECHNICAL_RESOURCE_UNAVAILABLE` and confirmed
  MEMCG OOM when applicable. It never falls back to the available 512 anchor.
- Candidates: `{id,label,role,status,surface_kind,provenance,data?,reason?,
  mesh_data?,source_count?,distance_definition?,downloads?}`. `status` is `available`,
  `pending`, `reference_unavailable`, `reconstruction_failure`, or `failed`. Available candidates require
  actual data and surface/source provenance. `surface_kind` must not identify
  Gaussian centers. Failed extraction and absent reference are distinct states.
  `no_geometry_reference_absent` is a separate nonavailable display status with
  reason `표시 기하 없음 · 참조 부재로 품질평가 불가`. It fetches no geometry and
  never means reconstruction failure or a zero quality metric. Positive geometry
  without an evaluation reference remains `available`.
- `data: {format:'json',url:'points.json'}` points to an object with
  `display_only:true`, flat `xyz` (N*3 finite numbers), optional flat `rgb`
  (N*3 sRGB byte values) and `distance_m` (N unsigned finite values or null).
  RGB absence is shown using a source-specific solid color. An RGB array alone
  never establishes original color provenance.
  Distances use a common 0–2 m display range; values above 2 m saturate.
  Missing distances are gray. Do not serialize Infinity as a reference distance.
- Binary alternative: `data` itself contains `display_only:true`, `xyz_f32`,
  optional `rgb_u8`, `distance_f32` URLs. Float files are little-endian Float32;
  reference absence is NaN. These files are also DISPLAY_ONLY.
- Point JSON exports can provide `display_sample_count`,
  `full_evaluation_sample_count`, `original_points_in_roi`, and
  `sampling_metadata:{evaluation_kind,display_voxel_m,display_cap,
  display_cap_applied,never_used_in_scoring:true}`. The actual array length must
  equal a declared display count. The screen distinguishes displayed points,
  full evaluation samples and original points in the ROI. It never labels the
  candidate's older ambiguous `source_count` as the full evaluation count.
  Missing legacy metadata is explicitly unknown.
- `color_provenance:{kind,description,...}` is read from the loaded point JSON.
  Supported labels distinguish `FIXED_SOURCE_COLOR`,
  `NEAREST_ORIGINAL_MESH_VERTEX_COLOR` and `ORIGINAL_POINT_RGB`. Missing or
  unrecognized provenance is shown as unknown, even when an RGB array exists.
- Optional `mesh_data:{format:'json',url:'P1/id.mesh.json'}` enables the actual
  triangle display. The JSON requires
  `schema:'geogs_exact_clipped_display_mesh_v1'`, `display_only:true`,
  `representation:'EXACT_EVALUATION_CLIPPED_TRIANGLES'`, `vertex_count`,
  `triangle_count`, `vertices_f64:{url,bytes,sha256}` and
  `triangles_u32:{url,bytes,sha256}`. Binary URLs resolve against the viewer
  manifest. Vertices are little-endian float64 XYZ; indices are little-endian
  uint32 triples. The app verifies sizes/counts/indices and finite coordinates,
  then converts positions to float32 solely for WebGL. Where Web Crypto is
  available it also verifies binary SHA256. On insecure LAN HTTP where that API
  is unavailable, `mesh_binary_integrity` explicitly reports bytes-only checks;
  it never claims browser hash verification.
- Mesh JSON retains `source_mesh:{path,sha256,scope}`, `bounds_half_open`,
  coordinate-storage and GPU-conversion metadata. `topology_simplified:false`,
  `artificial_clip_caps:false` and `distance_mode_requires_points:true` are
  required. The viewer draws every provided triangle using a double-sided
  `MeshBasicMaterial`; no decimation, normals-based reconstruction or artificial
  caps are generated. `color:{kind:'FIXED_SOURCE_COLOR',rgb_u8:[r,g,b],...}` is
  used for the uniform source color. Height mode colors actual mesh vertices by
  the same shared local-Z range. Distance mode deliberately keeps triangles in
  uniform source color with a visible instruction to use point mode for distance.
- `3D 표시` switches points and actual triangles for all panels together.
  Raw/post, 512/1024 and the shared camera remain independent controls. Input
  points and legacy exports without `mesh_data` remain points with an explicit
  no-registered-triangles note. Optional unavailable extraction retains its
  failure/resource reason; another resolution is never substituted.
- `sections` / `renders`: actual image records `{id,label,url,caption,
  selection_reason,condition_id?,width_m?,image_name?,split?,domain?}`. An optional
  `condition_id` filters the gallery with the selected change condition. Omit it
  for a figure comparing all conditions. The viewer never synthesizes a figure.
  Optional `comparison_family:'primary_1024'|'anchor_refinement_512'` is displayed
  in both the figure selector and caption. Gallery selection is independent of
  the 3D resolution selector; each figure retains its declared comparison family.
  Render galleries filter by condition, domain and image_name. Only the selected
  render and section image receive a `src`; hundreds of unselected figures are
  not fetched or instantiated. `domain` can be `whole_original_frame` or
  `fixed_projected_region_ROI`; other explicit values remain visible verbatim.
- `downloads`: `{label,url}` records on manifest, region, condition or candidate.
  Export a full source/surface file link and provenance receipt link where
  available. Absolute filesystem paths are provenance, not browser URLs.
- `case_selection_note` and `case_selection` record selection reasoning, including
  failure and uncertain cases. No best-result selection is performed here.
- Optional `cases: [{id,label,center:[x,y,z],extent_m,description,condition_id?}]`
  records actual cases chosen by the evaluation export. Selecting a case targets
  its scene-local center in all panels, sets the common vertical view extent in
  meters, and switches its condition when specified. The viewer invents no cases
  and performs no distance-based selection. Case selection does not change data.

## Run and inspect

Run `scripts/phd/geogs_p1p2p3_v1/viewer/serve.sh` after the actual manifest exists.
It starts a separate read-only Docker server on free loopback port 8902 and
preserves existing services. Only this app, the local Three module and the new
GeoGS task payload are exposed. The printed URL opens the actual manifest.

Drag any panel to rotate all six; Shift/right drag moves the shared target;
wheel zooms all six. Region and condition selectors retain a matched display.
Source color, reference distance and common local-Z modes are available.
Choose `실제 삼각형 (메시)` to inspect surface connectivity and holes. Choose
`표시 표본 (점)` for the registered distance-colored samples. Counts and color
provenance describe the loaded display metadata, not an inferred source type.
Click actual section/render figures to inspect their original resolution.

`window.__GEOGS_QA` records ready/error status, actual display counts, candidate
IDs, camera positions/targets and meters per pixel. The browser check must run
against actual exports; scaffold syntax validation is not a result-display pass.
`resolution_mode` and `mesh_res` identify the active surface comparison; both are
`null` for legacy manifests. Failed panels also retain their exact `reason`.
`representation_mode` is the requested point/mesh mode. Each QA panel includes
`representation`, `rendered_triangles`, `rendered_points`, `draw_calls`,
`renderer_info`, point/evaluation counts, mesh vertex/triangle counts,
`color_provenance` and `loaded_metadata`. The provenance details on screen also
include loaded point and mesh metadata; large inline arrays are omitted there.
Selection changes abort previous fetches and advance a generation token. Only
the current six panel entries retain CPU arrays; old geometry/materials and
renderer draw-list references are disposed, with no historical region cache.

Pure display contract checks (synthetic data only):
`docker run --rm --network none --read-only -v "$PWD:/repo:ro" node:22-alpine node /repo/src/apps/geogs_p1p2p3_v1/display_data.test.mjs`.
