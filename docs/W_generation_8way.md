# W_generation_8way — 생성 8-way (실패 모집단, 버킷별; 재학습 없음·기존 arm 평가, 판정 금지)

> **실험 2 / Phase B.** 브랜치 `feat/p2-structure-learn`. EPSG:25832. Docker. **재학습/재구성 없음** — 기존 gs_seed_{sparse,dense,acmp} ckpt + raw_{sparse,dense,acmp,lidar} npz를 P0 실패 모집단(64)에 평가 확대. 동일 Roofer 전역설정. 관찰만, 판정 = 김휘영. 무인 런(작업 B).
> 모델 생성 = roofer_ok AND roof_surfaces>0(orig). 재현 `run_overnight.sh`(Task B)·`d12_buckets.py`·`gen_8way_aggregate.py`. CSV `overseg_lever/gen_8way.csv`.

## §1 버킷별 8-way 생성 카운트 (모델 y / val3dity 유효 y / 버킷 n)

| bucket (n) | GS-sparse | GS-dense | GS-acmp | raw-sparse | raw-dense | raw-acmp | raw-lidar |
|---|---|---|---|---|---|---|---|
| ① textureless (5) | 0/5 | 1/5 | 1/4 | 0/5 | 0/5 | 2/5 | 5/5 |
| ② assembly(missing_lod22) (16) | 5/14 | 6/11 | 4/12 | 1/16 | 1/16 | 7/15 | 14/15 |
| ③ coverage(near-nadir gap) (36) | 0/0 | 0/0 | 0/0 | 0/23 | 0/19 | 7/35 | 36/35 |
| ④ impossible/other (7) | 0/0 | 0/0 | 0/0 | 0/6 | 1/6 | 4/7 | 6/7 |
| **TOTAL model-y (64)** | 5 | 7 | 5 | 1 | 2 | 20 | 61 |

## §2 버킷별 서사 (판정 금지)

- **② 조립(16)** [방법-관련, dense 점 有]: GS-dense 6/16·GS-acmp 4·GS-sparse 5 vs raw-dense 1·raw-acmp 7·LiDAR 14. → GS가 raw-MVS 0면 실패를 회복(공동최적화 조립).
- **① 무텍스처(5)** [방법-관련, dense=0]: GS-sparse 0/5·GS-acmp 1 vs raw 0·LiDAR 5. → 씨앗 점 부재로 GS 일부 생성(생성됨≠충실, D6 슬랩).
- **③ 커버리지(36)** [취득 한계, 방법 기여 아님]: baseline+LiDAR만. LiDAR 36/36 = near-nadir 취득 결손은 영상계열 공통(재촬영 필요).
- **④ 불가/기타(7)**: 신호 부재.

**상한/대비**: LiDAR(raw_lidar) 61/64 = 점군-가용 상한; raw-ACMP 20·raw-dense 2 = MVS baseline; GS-dense 7·GS-acmp 5·GS-sparse 5 = 공동최적화. (val3dity 유효는 표 우측값.)

## §3 종합 (판정 금지)
관측: 방법-관련 버킷(①②)서 GS 공동최적화의 생성 회복을 baseline 대비 카운트. ③ 커버리지는 취득 한계(방법 무관), ④ 불가. **생성됨 ≠ 충실**(무텍스처=저편향 슬랩[D6], 조립=위상 회복이나 표면 미달[assembly-fidelity]). 버킷별 대표 정성은 `docs/figs/`(가용 시). 커밋 `gen-8way-fail`.

> 재현: `run_overnight.sh` Task B(버킷 라벨→arm별 chunked extract+eval→집계). 데이터 재사용·재학습 없음.