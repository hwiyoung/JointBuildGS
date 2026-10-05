# RGB geometry comparison

Read-only seven-panel viewer: prior, MVS, Anchor8k, vanilla GeoGS, GeoGS variants,
MVS/PGSR GeoGS variants, and current Drone LiDAR reference. The backend serves
`/data/manifest.json` (`geogs_rgb_comparison_v1`) and the local Three module at
`/vendor/three.module.min.js`. No remote library or reconstruction process runs.

Assets are little-endian Float32 XYZ, Uint8 sRGB, and Uint32 triangle indices.
Every candidate uses the region's common local coordinate frame. Binary lengths
and array counts are checked. SHA256 is also checked where `crypto.subtle` is
available; insecure LAN origins without that API explicitly report bytes-only
verification in provenance details.

Automatic representation uses a supplied native triangle mesh when available,
otherwise the candidate's supplied RGB points. Explicit mesh mode never creates
a proxy for a point-only candidate. Missing/pending data remain empty. Gaussian
centers/SH color and RGB projected onto unchanged prior geometry are labelled.

One shared orthographic orbit/pan/zoom state drives all seven cameras. A region
change fits its frozen bounds. A 60-second manifest refresh preserves selected
conditions and camera state, and loads only changed selected assets. Every card
has an expanded view; Escape closes it. Keyboard arrows orbit, Shift+arrows pan,
`+`/`-` zoom, and `0` fits the region.

Browser QA: `window.__GEOGS_RGB_QA__` contains `ready`, `errors`, `panels`,
`cameras`, `selected`, numeric `frames`, current region/frame/bounds/run status,
and `refresh()`, `setRegion(id)`, `resetCamera()` helpers. `settled` means every
panel load and manifest refresh has settled. `verifyBuffers(role)` hashes the
exact raw buffers used by the displayed object without fetching data, and reports
RGB sample variation and sRGB conversion correspondence. Pending candidates are
normal states and do not add errors. This viewer does not assign scientific
verdicts, source authority, currentness, or reconstruction success.
