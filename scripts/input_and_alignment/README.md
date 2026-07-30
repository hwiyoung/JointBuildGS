# Input and alignment workflows

Reusable Stage 1 input preparation and alignment workflows are grouped by the
operation they perform:

| Directory | Role |
|---|---|
| `preparation/` | image, COLMAP, semantic-mask, gravity, and seed preparation |
| `diagnostics/` | geometry, rendering, semantic, and TUM quality diagnostics |
| `visualization_and_export/` | selected visual checks and point/scene exports |
| `datum_and_projection/` | CRS, vertical-datum, and image-projection checks |
| `tum_transfer/` | TUM input transfer, seed, baseline, and read-out drivers |
| `tum2twin_rv1/` | the multi-step TUM2Twin R_v1 workflow |

Shared projection code lives in `src/geospatial/`; these executables import it
through the repository namespace instead of a phase-local script directory.
