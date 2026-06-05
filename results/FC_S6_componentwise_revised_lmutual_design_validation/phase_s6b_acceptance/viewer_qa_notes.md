# FC-S6b Viewer QA Notes

Scope: saved Stage3 preview screenshots only. No retraining, Stage3 rerun, Metric-v1 rerun, or interactive 3D viewer manipulation was performed.

Saved screenshot matrices:

- `B104`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B104__candidate_matrix.png`
- `B6`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B6__candidate_matrix.png`
- `B3`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B3__candidate_matrix.png`
- `B123`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B123__candidate_matrix.png`
- `B126`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B126__candidate_matrix.png`
- `B2`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B2__candidate_matrix.png`
- `B0`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B0__candidate_matrix.png`
- `B1`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B1__candidate_matrix.png`

Automated QA notes from Metric-v1 and Stage3 topology:

- `B104` (GroundSurface and wall-ground closure): A8 F=`1.0`, ground_cov=`1.0`, h_err=`0.2357723600732995`, open/nonmanifold=`0/0`, roof-wall adjacency=`4`, wall-ground adjacency=`4`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B6` (height issue): A8 F=`0.9225605636347215`, ground_cov=`1.0`, h_err=`2.9283915134027474`, open/nonmanifold=`0/0`, roof-wall adjacency=`12`, wall-ground adjacency=`12`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B3` (roof-complex case): A8 F=`0.4609974701843152`, ground_cov=`0.92`, h_err=`3.5447672319911128`, open/nonmanifold=`0/0`, roof-wall adjacency=`42`, wall-ground adjacency=`42`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B123` (roof-complex case): A8 F=`0.5929870786516854`, ground_cov=`0.9513333333333334`, h_err=`0.6299571971661422`, open/nonmanifold=`0/0`, roof-wall adjacency=`28`, wall-ground adjacency=`28`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B126` (roof-complex case): A8 F=`0.5498362307886118`, ground_cov=`0.9816666666666667`, h_err=`1.056427976713632`, open/nonmanifold=`0/0`, roof-wall adjacency=`25`, wall-ground adjacency=`25`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B2` (easy/control sanity): A8 F=`0.929390657222272`, ground_cov=`1.0`, h_err=`0.5866236444250852`, open/nonmanifold=`0/0`, roof-wall adjacency=`6`, wall-ground adjacency=`6`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B0` (easy/control sanity): A8 F=`0.97403182479254`, ground_cov=`1.0`, h_err=`0.5067804532344056`, open/nonmanifold=`0/0`, roof-wall adjacency=`12`, wall-ground adjacency=`12`, shell=`CLOSED_BY_EDGE_INCIDENCE`.
- `B1` (easy/control sanity): A8 F=`0.9369399679829242`, ground_cov=`0.9946666666666667`, h_err=`0.4352806628834678`, open/nonmanifold=`0/0`, roof-wall adjacency=`6`, wall-ground adjacency=`6`, shell=`CLOSED_BY_EDGE_INCIDENCE`.

Saved-preview review observations:

- `B104`: no visible GroundSurface collapse or wall-ground closure break in the saved candidate matrix.
- `B6`: no topology break is visible, but the height error remains high and is not solved by A8.
- `B3`/`B123`/`B126`: roof-complex cases remain low-F diagnostic cases; saved previews do not show a new open-shell artifact for A8.
- `B2`/`B0`/`B1`: easy/control previews remain visually sane for A8, with no saved-preview sign of GroundSurface removal.

Limitations:

- Per-face rejection reasons are not present in the available Metric-v1 logs; only per-face matching coverage is available.
- The saved previews are sufficient for audit traceability, but a human interactive 3D viewer pass is still recommended before treating this as final publication evidence.
