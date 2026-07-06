# E5 Seed Constant Gate (A2)

- CRS: EPSG:25832
- Branch: `feat/p2-structure-learn`
- HEAD before A2 commit: `8237380b479279a79098dd1d7b1c41b2f76d6f4c`
- Phase run: `phases/p2-gsjso/runs/e5p_const_20260706_235710/versions.txt`
- Scope: new execution-path files from `docs/recipe_registry.md` §5. Historical run outputs are not scanned.

## Transition Diff Table

| linked constant | files | before | after |
|---|---|---:|---:|
| ACMP seed transform | `seed_prep_acmp.json` | `-556` | `-558.3` |
| ACMP seed prep comment | `tum_mob_seed_prep.sh` | `-556` | `-558.3` |
| semantic seed/label shift | `seed_semantic.yaml; semantic_seed.py` | `604-48=556` | `604-45.7=558.3` |
| seed band geoid | `seed_depth_bands.py; seed_material_audit.py` | `48.0` | `45.7` |
| raw unification geoid | `tum_mob_raw_to_npz.py` | `+48.0` | `+45.7` |

## Gate A: Old Constant Grep

- Old constant hit count in scoped new execution paths: 0
- Scoped grep result: 0 hits.

## Gate B: ACMP Z Distribution

ACMP source is orthometric. Old local formula was `z - 556`; E5 canonical is `z - 558.3`.

| formula | p05 local z | p50 local z | p95 local z |
|---|---:|---:|---:|
| old `z-556` | -43.990 | -36.240 | -21.240 |
| new `z-558.3` | -46.290 | -38.540 | -23.540 |

| delta new-old | p05 | p50 | p95 |
|---|---:|---:|---:|
| m | -2.300 | -2.300 | -2.300 |

Observation: the new formula lowers ACMP local z by 2.300 m, matching the preregistered `-604 + 45.7 = -558.3` camera-world frame relation. This records the offset removal material only.
