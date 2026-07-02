# projection_datum_fix -- A0 projection-fix

> Observe only. No reconstruction/retraining. Geo CRS EPSG:25832; OPF/COLMAP frame EPSG:32632 with ellipsoidal Z.

## Config

- geo=EPSG:25832 opf=EPSG:32632 input_default=orthometric orthometric_geoid_m=48.000000
- Orthometric image-projection inputs add `orthometric_geoid_m` before the existing base_to_canonical shift.
- Ellipsoidal inputs keep the historical `shift_z=-604` path by passing `input_datum=ellipsoidal`.
- 3D/seed paths are not controlled by this A0 utility.

## Unit Check

| view_class | view_nadir_deg | view | pre_u | pre_v | post_u | post_v | du_px | dv_px | shift_px |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| near_nadir | 4.84 | DJI_20241217084407_0047_D.JPG | 2508.82 | 2088.45 | 2414.82 | 2169.21 | -94.01 | 80.76 | 123.94 |
| strong_oblique | 54.57 | DJI_20241217103413_0016_D.JPG | 3962.65 | 1847.92 | 4786.70 | 574.25 | 824.05 | -1273.67 | 1517.01 |

Interpretation note: near-nadir can have small pixel movement, while oblique movement grows with the vertical datum correction. This is a unit verification of the code path, not a pass/fail judgment.

## Image-Projection Impact Inventory

| path | impact |
|---|---|
| `phases/p2-gsjso/scripts/projection_datum.py` | new shared datum utility; config-driven zeta for orthometric image projection |
| `configs/projection_datum.json` | config parameter for zeta; 45.7/48.0/A1-zeta are replaceable values |
| `phases/p2-gsjso/scripts/evidence_cards_v2.py` | card v2 LoD2/ALS/footprint projection, roof masks, view angle selection |
| `phases/p2-gsjso/scripts/evidence_cards.py` | legacy evidence card projection path |
| `phases/p2-gsjso/scripts/projection_gate.py` | historical retracted gate imports evidence_cards_v2 projection functions |
| `phases/p2-gsjso/scripts/projection_gate2.py` | wide-search projection gate imports evidence_cards_v2 projection functions |
| `phases/p2-gsjso/scripts/gate_diag.py` | clean visual diagnostic imports evidence_cards_v2 projection functions |
| `phases/p2-gsjso/scripts/population_aux_v3.py` | observation geometry projection plus camera-point vectors now use ellipsoidal point Z |
| `phases/p2-gsjso/scripts/texture_anchor_check.py` | texture anchor crops use population_aux_v3.project |
| `phases/p2-gsjso/scripts/add_lowtex_v4.py` | lowtex v4 uses texture_anchor_check/build_crop and population camera parsing |
| `phases/p2-gsjso/scripts/ztest.py` | diagnostic keeps explicit geoid_m=0 pre-fix simulation for old-vs-fix figures |
| `phases/p2-gsjso/scripts/zmultiview.py` | diagnostic keeps explicit geoid_m=0 pre-fix simulation for old-vs-fix figures |
| `phases/p2-gsjso/scripts/zfix_visual.py` | inherits ztest.proj_dz pre-fix simulation |
| `phases/p2-gsjso/scripts/zresolve.py` | inherits ztest.proj_dz pre-fix simulation |

## Missing External Spec

- Root file `원격발주_투영fix·LS정합·재게이트·재계산체인_레시피감사_20260702.md` was not present in this checkout; this A0 follows `CLAUDE.md`, `docs/projection_geoid_rootcause.md`, and the retracted `docs/projection_gate.md` note.

## 판정 필요 지점

- A0 has no 합/불 판정 item; A1 must estimate zeta numerically and may update the config default.
