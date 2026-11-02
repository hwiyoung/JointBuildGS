# reply1_photo_timing [이 발주에서 냄]

실험 지역과 사진 점을 공유해 뺀 핵심점: **73개 / 5.442552935831812 m²**. 모든 셈에서 미리 제외했다.

출처: `r1/photo_benchmark/preparation.json and timing_cpu.json / timing_cuda.json; 200 identical points`

| device | points | target_count_types_1_2 | target_type3_pending | preparation_seconds | scoring_seconds | total_seconds | seconds_per_point | linear_estimate_hours | limit_hours | over_limit | score_only_linear_hours | decoding_only_linear_hours | arithmetic_only_linear_hours |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cpu | 200 | 187523 | True | 361.0715266680345 | 184.97573739103973 | 546.0472640590742 | 2.730236320295371 | 142.217251525208 | 72 | True | 48.17667389274992 | 35.76032895276786 | 12.004830505763532 |
| cuda | 200 | 187523 | True | 361.0715266680345 | 192.4228802761063 | 553.4944069441408 | 2.767472034720704 | 144.15684954636959 | 48 | True | 50.116271913911504 | 38.05098584663373 | 11.893952515468705 |
