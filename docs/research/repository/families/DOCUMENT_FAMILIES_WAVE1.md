# Document families wave 1

Review date: 2026-07-29  
Migration: `DOC-IA-05`

This decision record covers 70 tracked files moved from flat or mixed document paths into role-based owner folders. It is an information-architecture decision only: source bytes, measurements, scientific conclusions, frozen manifests, and run receipts were not rewritten.

## Owner folders

| Owner | Families |
|---|---|
| `docs/research/` | research context, experiment plan, and the approved quality-axis preregistration lock |
| `docs/experiments/<family>/reports/` | current or supporting human-readable reports |
| `docs/experiments/<family>/tables/` | compact evidence CSV/JSON inputs and outputs |
| `docs/experiments/<family>/manifests/` | provenance records |
| `docs/evidence/archive/<family>/<version>/` | superseded material retained for reproducibility |

The wave includes Claude Web briefs, attribute regression, bucket crosswalk, datum tie, degradation curve, E5 pilot support, footprint-conditioned design, P0 completeness, point-cloud attributes, population auxiliary tables, primary-4 validation, projection gates, projection zeta, QS baseline/refine/rescore, and the quality-axis preregistration lock.

## Compatibility boundary

Four scientific contract/input root copies were initially retained because active or hash-bound consumers named the former path:

- `docs/pointcloud_attributes_v1_3.csv`
- `docs/qs_baseline178_scores.csv`
- `docs/qs_rescore_pairs.csv`
- `docs/사전등록서_품질축본선_승인잠금v4_20260721.md`

They are not canonical owner paths. Active clean consumers now use the target path recorded in the migration manifest, and the byte-identical former root copies are preserved under `docs/evidence/archive/compatibility/root-mirrors/`. Historical strings remain unchanged.

## Frozen references

Historical manifest and run-receipt strings continue to describe the path used when the experiment ran. The inventory resolves those strings through [`DOCUMENT_FAMILIES_WAVE1_PATHS.csv`](../migrations/DOCUMENT_FAMILIES_WAVE1_PATHS.csv). Current repository rules, navigation, and canonical-document configuration use the new owner paths.

## Deferred families

The E5 C001 staged chain and the evidence-card/judgment-kit packages are not part of this wave. Their internal manifests embed package paths and hashes, so they require a separate canonical-lineage decision before movement.
