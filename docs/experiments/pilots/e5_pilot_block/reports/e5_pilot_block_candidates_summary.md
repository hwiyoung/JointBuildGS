# E5 Pilot Block Candidates (A1)

- CRS: EPSG:25832
- Run fingerprint: `phases/p2-gsjso/runs/e5p_prep_20260706_235306/versions.txt`
- Existing GS stage exclusion: 79 buildings (D4 make-or-break + D12 71-stage union)
- Buildings outside stage: 120
- Rule-satisfying candidate blocks: 412

## Seed Source Availability

| seed source | file | source points | xy bounds | global status |
|---|---:|---:|---|---|
| sparse | `phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt` | 371808 | 688418.5,5334234.6 to 694544.2,5338187.8 | present |
| dense | `phases/p0-audit/data/work/mvs/dim/dim_v1.laz` | 43942554 | 687815.7,5335223.9 to 692967.6,5338416.5 | present |
| acmp | `results/tum_transfer/mob_analysis/p0c_step2/acmp_aoi_utm.laz` | 159358391 | 690766.0,5335839.0 to 691180.0,5336379.0 | present |

## Recommended Candidate

- Candidate: `C001`
- Buildings: 18
- Dense success/failure: 10 / 5
- Dense no-points/no-planes/assembly: 5 / 0 / 0
- Manual labels: 무텍스처:2;복합(소형+가림):1;복합(소형+재질):1;복합(저조도+가림):1
- Ref-mismatch IDs: none
- Note: ref-mismatch excluded; includes dense no-points lens; compact among rule-satisfying blocks

## Cost Estimate For Decision

| item | estimate | basis |
|---|---:|---|
| GS learning runs | 6 | three seed sources x two random seeds |
| GPU time | 6 x 4-8 h | prior D4-style 30k-iter full-scene runs; block clipping may reduce IO but not yet benchmarked |
| GPU count | 1-2 | prior D4 dense/acmp used two GPUs in parallel; sparse can run independently |
| read-out + assembly | <1 h per learned run | TSDF read-out + Roofer per block is lower cost than training |

Observation only: this is cost material for the human A-stage decision, not a gate verdict.
