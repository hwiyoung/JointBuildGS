# W_gssem_requal — D·D4 gssem read-out 재정합 (gssem | smrf 병기, 관찰만·판정 없음)

> 배경: eval 이 arm 당 **gssem→smrf 순차**라 per-building cityjson/las/val3dity 가 smrf 로 덮였었음 → D·D4 의 RMS·면수·val3dity 가 smrf 기하였음.
> 본 작업(PART 1)은 그 산출물을 **gssem(thesis 정본 read-out)으로 재생성**하고 smrf 는 백업 보존. EPSG:25832 · Docker · 학습/D5 무중단(CPU만). 관찰만·해석 금지.
> 출처: `gssem_requal_numbers.py` → `numbers_{smrf,gssem}.json`; smrf 원본 = `gssem_requal_backup/perbuilding_smrf.tar`(cityjson+val3dity) + `ref_rms_{D,d4}_smrf.csv`. 디스크 최종 = **gssem**.

## §0 생성(assembled/valid-solid, REC 8동) — gssem 재-eval 불변 확인
| arm | assembled/8 (gssem) | valid-solid/8 (gssem) | (참고) smrf assembled/valid |
|---|---:|---:|---:|
| D dense | 7 | 4 | 3 / 2 |
| D acmp | 7 | 3 | 2 / 2 |
| D4 dense | 7 | 2 | 2 / 2 |
| D4 acmp | 7 | 3 | 3 / 3 |

(gssem 생성수치는 재-eval 전후 동일 — `gssem_requal.log` [verify] 라인 참조. smrf 는 read-out 차이로 다름, 대조용.)

## §1 RMS→ref (m, orig) — gssem | smrf · mean(11동 中) + 초점 4906972·4906969·4908023
| arm | mean gssem | mean smrf | 4906972 g\|s | 4906969 g\|s | 4908023 g\|s |
|---|---:|---:|---:|---:|---:|
| D dense | 2.12(n11) | 2.83(n7) | 3.09\|2.79 | 1.28\|0.96 | 0.94\|0.94 |
| D acmp | 2.50(n10) | 2.94(n8) | 3.02\|2.74 | 7.42\|7.64 | 1.09\|0.48 |
| D4 dense | 1.81(n10) | 2.25(n7) | 2.47\|2.41 | 1.13\|0.76 | 0.88\|0.67 |
| D4 acmp | 1.88(n10) | 1.65(n9) | 2.92\|2.81 | 0.90\|0.63 | 0.92\|0.45 |

출처: gssem = `ref_rms_{D,d4}_gssem.csv`; smrf = `ref_rms_{D,d4}_smrf.csv`.

## §2 target-only 지붕 면수 (11동) — gssem | smrf · ref
| bid | ref | D dn g\|s | D ac g\|s | D4 dn g\|s | D4 ac g\|s |
|---|---:|---:|---:|---:|---:|
| 4906972 | 3 | 3\|3 | 5\|4 | 3\|3 | 5\|4 |
| 4907182 | 2 | 1\|0 | 4\|0 | 1\|0 | 2\|0 |
| 4906969 | 3 | 19\|19 | 15\|10 | 14\|13 | 10\|8 |
| 4908023 | 1 | 2\|2 | 1\|1 | 2\|2 | 5\|2 |
| 4907510 | 1 | 4\|1 | 4\|0 | 6\|0 | 6\|1 |
| 42364659 | 2 | 5\|6 | 8\|6 | 6\|5 | 7\|1 |
| 42364663 | 1 | 2\|1 | 1\|1 | 1\|2 | 1\|1 |
| 42364609 | 1 | 1\|0 | 1\|0 | 1\|0 | 1\|0 |
| 4908050 | 1 | 1\|0 | 1\|0 | 1\|0 | 1\|0 |
| 4908166 | 1 | 0\|0 | 1\|0 | 1\|0 | 1\|0 |
| 4908176 | 1 | 1\|0 | 0\|0 | 0\|0 | 0\|0 |

출처: target-only = Roofer cityjson(이웃 제외). gssem = 현 디스크(재생성); smrf = `perbuilding_smrf.tar` 스냅샷.

## §3 val3dity — 무효동 오류코드 (gssem | smrf), arm 별 (valid=False 인 동만)

**D dense**
| bid | gssem valid·codes | smrf valid·codes |
|---|---|---|
| 4907182 | INVALID·['302'] | valid·[] |
| 4906969 | INVALID·['303'] | valid·[] |
| 4907510 | INVALID·['306'] | valid·[] |
| 42364659 | valid·[] | INVALID·['104', '302'] |
| 4908176 | INVALID·['405'] | valid·[] |

**D acmp**
| bid | gssem valid·codes | smrf valid·codes |
|---|---|---|
| 4907182 | INVALID·['306'] | valid·[] |
| 4906969 | INVALID·['104'] | valid·[] |
| 4907510 | INVALID·['306'] | valid·[] |
| 42364609 | INVALID·['302'] | valid·[] |
| 4908166 | INVALID·['405'] | valid·[] |

**D4 dense**
| bid | gssem valid·codes | smrf valid·codes |
|---|---|---|
| 4906972 | INVALID·['302'] | valid·[] |
| 4907182 | INVALID·['302'] | valid·[] |
| 4906969 | INVALID·['306'] | valid·[] |
| 4907510 | INVALID·['306'] | valid·[] |
| 42364663 | INVALID·['306'] | valid·[] |
| 42364609 | INVALID·['301'] | valid·[] |
| 4908166 | INVALID·['405'] | valid·[] |

**D4 acmp**
| bid | gssem valid·codes | smrf valid·codes |
|---|---|---|
| 4907182 | INVALID·['302'] | valid·[] |
| 4908023 | INVALID·['302'] | valid·[] |
| 4907510 | INVALID·['306'] | valid·[] |
| 42364659 | INVALID·['303'] | valid·[] |
| 4908166 | INVALID·['302'] | valid·[] |

> ⚠ **clip-level 주의**: valid/codes 는 combined clip(타깃+이웃) 리포트 기준 = eval 의 valid_solid 정의와 동일. 일부 코드는 **클립된 이웃 건물**에서 발생할 수 있음
> (검증 예: gs_d4_dense 4906972 clip=INVALID·302 이나 이는 이웃 `DEBY_LOD2_4906973`의 SHELL_NOT_CLOSED 이고 타깃 4906972 feature 자체는 valid). 타깃-feature 단위 validity 는 동일 리포트의 features[] 에서 추출 가능.

출처: gssem = 현 디스크 val3dity.json(재생성); smrf = `perbuilding_smrf.tar`. 코드: 301·302 비폐합·303 비-다양체·306/405 방향 등(val3dity 2.6.0).

## §4 정성 그림 — gssem 모델 렌더 (`docs/figs/W_gssem_requal/`)
4906972·4906969·4908023 의 gssem 조립모델(면별색) [D-gssem | D4-gssem | LiDAR | ref]. smrf 모델은 `perbuilding_smrf.tar` 에 보존.

## §5 재현/출처
- 재-eval: `phases/p2-gsjso/scripts/run_gssem_requal.sh` (백업→gssem eval→ref_rms→numbers→verify; CPU/도커, NO GPU, gs_d5* 미접촉).
- 숫자: `gssem_requal_numbers.py {smrf,gssem}` → `numbers_{smrf,gssem}.json`. 본 표: `gssem_requal_doc.py`.
- 그림: `gssem_requal_figs.py`. smrf 백업: `gssem_requal_backup/perbuilding_smrf.tar` + `ref_rms_{D,d4}_smrf.csv` + `eval_*_smrf.json`.
- 디스크 최종 read-out = **gssem**(이후 smrf 재실행 금지). 생성 assembled/valid-solid 불변(§0).
