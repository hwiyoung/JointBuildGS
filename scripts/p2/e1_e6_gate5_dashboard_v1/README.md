# P2-E1-E6-GATE5-DASHBOARD-v1 — five-gate E1–E6 judgment dashboard pipeline

Non-confirmatory development viewer. Chain (env `JBGS_GATE5_WORK` = work dir):

1. `gen_lod2_ref.py` — original CityGML LoD2 tiles (P0 raw, EPSG:25832) → per-building
   RoofSurface reference planes for the 199 shared-footprint targets.
2. `gen_visuals.py` — per condition (E1–E6): five-gate metrics vs references
   (G3/normal vs original-LoD2 planes, robust 1:M normal-compatible matching;
   G4 vs current-UAS cells), plus dZ heatmaps, plane overlays, packed meshes.
3. `build_dashboard.py` — self-contained HTML dashboard (judgment map, condition
   summary, cut sweep + E1 quantile anchor, 8-panel synchronized 3D with on-demand
   point clouds when served next to the v16/v22 assets).

Run inside the project container (numpy + shapely required). Reads frozen v16
assets read-only; writes only to `JBGS_GATE5_WORK` and the payload directory.
Cuts are NOT frozen; `scientific_verdict` stays null. Config: `configs/p2/e1_e6_gate5_dashboard_v1/run_v1.json`.
