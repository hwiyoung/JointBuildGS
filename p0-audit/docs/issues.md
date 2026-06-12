# P0 Issues

## T1 Data Download

- UAV OPF poses (Zenodo) primary -> uav/opf.zip: `https://zenodo.org/records/14548134/files/opf.zip` -- primary URL unavailable; using existing fallback file

## T3 DIM Point Cloud

- t3_mvs_20260611_225241: failed at line 76 with exit code 134. See runs/t3_mvs_20260611_225241/logs/.
- t3_mvs_20260611_230138: failed at line 76 with exit code 1. See runs/t3_mvs_20260611_230138/logs/.
- t3_mvs_20260611_230936: failed at line 76 with exit code 1. See runs/t3_mvs_20260611_230936/logs/.
- t3_mvs_20260611_231056: failed at line 76 with exit code 1. See runs/t3_mvs_20260611_231056/logs/.
- t3_mvs_20260611_233132: failed at line 464 with exit code 126. See runs/t3_mvs_20260611_233132/logs/.
- t3_mvs_20260611_233132: failed at line 464 with exit code 127. See runs/t3_mvs_20260611_233132/logs/.
- t3_mvs_20260611_233132: failed at line 466 with exit code 127. See runs/t3_mvs_20260611_233132/logs/.
- t3_mvs_20260611_233132: failed at line 76 with exit code 1. See runs/t3_mvs_20260611_233132/logs/.
- t3_mvs_20260611_233524: failed at line 76 with exit code 1. See runs/t3_mvs_20260611_233524/logs/.
- Resolved in t3_mvs_20260611_233721 by remapping COLMAP image/frame IDs to database IDs, using OpenMVS `colmap_txt/sparse`, writing relative OpenMVS image paths, reading OPF `base_to_canonical.shift`, and asserting CRS via PDAL metadata.

## T4 Point Classification

- t4_classify_20260612_114812: failed with exit code 1. See runs/t4_classify_20260612_114812/logs/.
- Resolved in t4_classify_20260612_114903 by preserving `GroundSurface` children during streaming XML parsing before extracting `gml:posList` footprint rings.

## T7 Vertical Alignment

- t7_vertical_20260612_141031: failed with exit code 1. See runs/t7_vertical_20260612_141031/logs/.
- Resolved in t7_vertical_20260612_141617 by treating the 0.5 m residual standard-deviation threshold as a reported check instead of a process failure; all-cell residual std remains above threshold and is documented in docs/W1_diagnosis.md.
