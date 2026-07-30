# TUM2TWIN R_v1 metric contract

Run: `20260728_2327`

> R_v1 is a relative, provisional stratification for experiment selection.
> It is not a final scientific readiness or quality certification.

## Scope and non-verdict rule

R_v1 ranks the canonical 178-building population for later experiment selection. It is not a literature-standard pass threshold, a readiness gate, or a scientific quality certification. Appearance is kept outside the R axis. Missing values remain `NaN` with a machine-readable reason.

## Surface representation and distances

- Reconstruction: canonical `w2_1` classified DIM/MVS, class 6 points inside the approved footprint. The footprint plus `crop_buffer_m` is used only for memory-safe cache extraction; the metric domain is the unbuffered building footprint.
- Reference: the repository's canonical `raw_lidar` fallback `als_aoi.laz`, class 6, already in EPSG:25832 and the same orthometric frame. The co-acquired ULS derivatives found in `results/tum_transfer/mob/b2/` are not used because the repository proves XY reprojection and decimation but not a completed vertical tie to the canonical baseline.
- Both sides are independently voxel-centroid downsampled at the configured 0.1 m resolution. No ICP or other automatic alignment is applied.
- Precision is the fraction of reconstruction samples whose nearest reference sample is within a threshold. Recall reverses the direction. F-score is their harmonic mean. Thresholds 0.1/0.2/0.5 m are all reported; 0.2 m is only this experiment's provisional primary choice.
- Directional median/p90/p95 distances are reported. `bidirectional_distance_p95_m` is the conservative maximum of the two directional p95 values.
- Surface thickness p90 is a diagnostic vertical-span statistic over occupied XY voxels. Maximum hole radius is the maximum reference-to-reconstruction nearest distance and is explicitly a point-sampled proxy, not a polygonal unsupported-region area.
- Normal angular and point-to-plane median/p95 metrics are unavailable when local-normal estimation is disabled or unsafe. Their fields stay `NaN` with a reason; the batch continues.

## LoD2 roof-plane correspondence

The adapter reuses the existing `scripts/e5_c001/p2_gsjso/e5_c001_8way.py` CityGML/CityJSON roof parser, plane fitting, and RMSZ sampling implementation. It extends that evaluator with a strict 50% XY-overlap correspondence graph:

- a reference/reconstruction pair is eligible when the intersection covers at least 50% of each polygon;
- eligible pairs are greedily made one-to-one by descending IoU for plane completeness/correctness/F1;
- completeness = matched reference planes / reference planes;
- correctness = matched reconstructed planes / reconstructed planes;
- quality/F1 is the harmonic mean;
- degree patterns in the pre-greedy bipartite graph provide 1:M, N:1, and N:M diagnostic counts/rates;
- RMSZ reuses the existing 0.5 m XY sampling and nearest reference roof-plane vertical residual definition;
- RMSXY is the RMS of matched-polygon XY Hausdorff distances and is secondary;
- ridge position error is `NaN` because no repository evaluator exposing explicit ridge correspondences was found.

This is an ISPRS-style approximation, not a claim of byte-for-byte reproduction of an external benchmark implementation. A reference-derived footprint is never scored as an independent footprint-boundary achievement.

## Relative score and R labels

Average-tie percentile ranks are computed only over finite values in the full processed population. Surface score averages F-score@0.2 rank and inverse bidirectional-p95 rank. LoD2 score averages roof-plane-F1 rank and inverse-RMSZ rank; Roofer failure, missing LoD 2.2, or invalid val3dity forces it to zero. A single available component yields low axis confidence; no available component yields an unknown axis.

For q=0.40/0.50/0.60, scores at or above the population quantile are high. R0/R1/R2/R3 map surface/LoD2 high-low pairs. Missing primary F-score@0.2 or roof-plane F1, an unknown axis, or label instability yields final RX. Diagnostics never override an R label.

## Appearance and qualitative PDF

No held-out rendering split, final textured-mesh protocol, or texture-atlas coverage protocol was found for the canonical baseline. Appearance is therefore `not_evaluated` with a reason and does not block R_v1. The nine qualitative PDF IDs are parser/sanity targets only; no expected label is encoded.
