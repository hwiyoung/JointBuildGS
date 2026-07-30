## Phase 0 §3-3 — P0 plane-fit baseline and MVS hole check

> Measurement only. Learning 0; new MASt3R inference 0. LoD2 is score/overlay only.

### P0 plane-fit + footprint fill

| building | FM N | inlier | fill N | coverage | median abs dz (m) | RMS (m) | read-out |
|---|---:|---:|---:|---:|---:|---:|---|
| DEBY_LOD2_4907199 | 373 | 0.731903 | 448 | 1.000000 | 0.154905 | 0.194579 | `measured_point_evidence_derived_roofprint` |
| DEBY_LOD2_8568391 | 456 | 0.993421 | 265 | 1.000000 | 0.100236 | 0.107120 | `measured_point_evidence_derived_roofprint` |
| DEBY_LOD2_8568392 | 6 | 1.000000 | 37 | 1.000000 | 1.055800 | 1.179759 | `measured_point_evidence_derived_roofprint` |

The repository's original adapter is blocked because it passes the supplied footprint directly. This run instead derives Roofer roofprints from the 0.5 m occupied cells of the P0 point evidence. The supplied footprint itself is not passed to Roofer; this fragment is finalized after Roofer and val3dity.

![P0 plane fill](docs/figs/e5_c001_s3ap_phase0/p0_planefit_baseline.png)

### Existing DIM/MVS support

| building | all in footprint | class-6 support | class-6 coverage | direct zero | canonical Roofer reason | has_lod22 |
|---|---:|---:|---:|---|---|---|
| DEBY_LOD2_4907199 | 57 | 2 | 0.004464 | false | `pointcloud_unusable_no_points` | False |
| DEBY_LOD2_8568391 | 14 | 0 | 0.000000 | true | `pointcloud_unusable_no_points` | False |
| DEBY_LOD2_8568392 | 49 | 0 | 0.000000 | true | `pointcloud_unusable_no_points` | False |

![MVS support](docs/figs/e5_c001_s3ap_phase0/mvs_hole_check.png)

### Roofer read-out adapter

- supplied footprint passed to Roofer: `false`
- point-evidence-derived roofprint passed to Roofer: `true`
- derived roofprint rule: union of P0 fill-point 0.5 m occupied cells
- indirect dependency: the P0 fill points use the supplied footprint as the permitted fill mask
- substantive filter: requires canonical Roofer success, non-fallback extrusion, roof planes, raw LoD2.2 geometry, val3dity, completeness and roof RMS

| building | Roofer reason | raw geometry LoD2.2 | accepted has_lod22 | val3dity | completeness | roof RMS (m) | substantive filter |
|---|---|---|---|---|---:|---:|---|
| DEBY_LOD2_4907199 | `lod11_fallback` | True | False | True | 1.000000 | 0.076000 | False |
| DEBY_LOD2_8568391 | `lod11_fallback` | True | False | True | 1.000000 | 0.120000 | False |
| DEBY_LOD2_8568392 | `lod11_fallback` | True | False | True | 1.000000 | 1.380000 | False |

![P0 Roofer read-out](docs/figs/e5_c001_s3ap_phase0/p0_roofer_readout.png)
