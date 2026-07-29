# W_D6 prior-provenance — 단서 출처 코드 점검 A (읽기 전용, 관찰만·판정 금지)

> **읽기 전용 · 코드변경/학습/재구성 없음. 관찰만, 판정 = 김휘영.** 브랜치 `feat/p2-d6-curved`. EPSG:25832. Docker(p0-tools, 데이터 점검만).
> 질문: 생성 raw 0/8 → GS-JSO 7/8(무텍스처 4동 포함)에서 무텍스처 동의 회복이 **"정답(LoD2 지붕)을 쓴 순환"인지** 코드로 확정. 추적 대상 = gs_prior_full / gs_d4 (configs `gs_{prior_full,d4}_dense.yaml`). 모든 근거 file:line.
> 결론 미리: **LoD2 z(높이)·면 값은 seeding·depth·추출·read-out 어디에도 직접 유입되지 않는다**(씨앗=MVS·depth=MVS·ground z=GS데이터·footprint=crop). 단 **LoD2 접점 두 곳**: (i) 의미 라벨 clean_labels = **LoD2 GML 메시 레이캐스트 픽셀 CLASS**(z 없는 픽셀 클래스 라벨); (ii) **`sem_detach_geometry: false`**라 L_sem 그래디언트가 **GS 기하(means 등)로 역전파** → GS 표면이 **LoD2 다시점(occlusion-resolved) 클래스 투영(visual-hull)에 맞게 이동**(특히 MVS 희박한 무텍스처에서 비중↑). 즉 **LoD2 z 값 직접 순환은 아니나, GS geometry가 LoD2-레이캐스트 다시점 클래스 투영 supervision에 부분 결합**(+하류 gssem 분류로 조립 가능화). 판정=김휘영.

## §0 방법

gs_prior_full/gs_d4의 한 건물 표면이 놓이기까지 모든 입력을 코드로 추적(①씨앗 ②깊이·법선 ③평면성·의미 ④footprint ⑤LoD2 GML 읽는 곳). 데이터 파일은 p0-tools 컨테이너에서 읽기만(seed_dense.ply 건물별 점수 독립 확인). 추정 금지 — 출처가 불명이면 불명으로 표기.

## §1 단서별 출처표 (file:line)

| # | 단서 | 출처 | LoD2? | 근거 (file:line · 인용) |
|---|---|---|:--:|---|
| ① | **씨앗(init_pointcloud)** | **DIM/MVS** | **NO** | config `gs_d4_dense.yaml:18`·`gs_prior_full_dense.yaml:15` `init_pointcloud: …/seed/seed_dense.ply`. 빌더 `seed_prep_dense.json`: 입력 `phases/p0-audit/data/work/mvs/dim/**dim_v1.laz**`(DIM) → `filters.crop`(AOI) → `filters.transformation`(−[690953,5336071,604] 순수평행이동) → `filters.expression`(이상치 z-clip) → `filters.voxelcenternearestneighbor cell 0.4` → `writers.ply`. train.py:354-376 `init_pc` 로드(concat). **LoD2/GML 점·z 없음.** |
| ① | **씨앗(런타임 의미 carve + LoD2 높이 band)** | (미사용) | — | `build_semantic_seeds`(`src/stage2/semantic_seed.py`, LoD2-라벨 carve)는 train.py:313 `if cfg.get("seed_semantic")`로만 실행. ⚠ **레포의 유일한 LoD2-z lever(§4-9 oracle 경로)** = `seed_depth_bands.py:5-9`(참조 **HoeheGrund/HoeheDach** → `seed_bands_{range,oracle}.json`) → train.py:321-324 `bands_file`로 carve z-band 주입. **그러나 carve·bands 전체가 `seed_semantic` 게이트(train.py:313) 하위이고, `seed_semantic`·`bands_file`는 `seed_semantic.yaml`·`depth_release_{range,oracle}.yaml`에만 존재 — `gs_d4_dense.yaml`·`gs_prior_full_dense.yaml`엔 둘 다 없음 → D-수트에서 미실행(dead code).** |
| ② | **깊이·법선** | **COLMAP PatchMatch MVS** | **NO** | `prior_full_stereo.sh:3` "COLMAP PatchMatch stereo on the EXISTING P0 colmap_dense … per-view depth+normal (.geometric.bin)"; `:42-48` `colmap patch_match_stereo`(images). dataloader가 `stereo/`에서 로드, L_depth/L_normal(`loss/data_fitting.py`). gs_d4: `w_depth 0.03 · w_normal 0`(:43-44). **LoD2 없음.** |
| ③ | **평면성(structure G2 coplanar/na)** | **GS 프리미티브 내부** | **NO** | config `structure_grouping: g2`·`structure_*`. 그룹 대표 법선/거리 detach(엔진 0e43d37, 메커니즘 2). 참조 읽지 않음(GS 자기 점만). |
| ③ | **의미(L_sem, w_sem 0.1)** | **LoD2 GML 메시 레이캐스트 픽셀 CLASS** → **geometry로 역전파** | **YES (클래스 라벨 + 기하결합)** | 라벨 빌더 `make_clean_labels.py:2,:9`(LoD2 surfaces→픽셀 class, "no geometry imported … only per-pixel class"); 레이캐스트 `:61-92,:216-223`(hit→class, **z 미저장**). ⚠ 단 **`sem_detach_geometry: false`**(`gs_d4_dense.yaml:62`·`gs_prior_full_dense.yaml:58`; train.py:453,615) → `renderer.py:109-117`(docstring)·`127-136`(if/else) 주석대로 "geometry is NOT detached, so L_sem's gradient also flows into means/quats/scales/opacities — semantics can move geometry toward the labelled [surface]". 즉 **클래스 라벨(z 없음)이나 L_sem이 GS 기하를 LoD2 다시점(occlusion-resolved) 클래스 투영에 맞춰 이동**(L_mutual·semcal은 비활성: `w_mutual 0`·`mutual_semcal_enabled` 미설정). |
| ④ | **footprint** | **crop·로그·평가 only** | **NO** | train.py:423-430·758 `seed_log_footprints`→`_load_footprint_boxes_local`/`_log_seed_survival`(씨앗 생존 **로깅**). read-out `_mob_prep_las_gssem.py:11-12` "footprint is used **solely for eval-side metrics + Roofer per-building crop, never to assign the building class**"; building=GS 의미(`C==ROOF|WALL`, :109), z 미사용. **z-init·클래스배정 아님.** |
| ⑤ | **LoD2 GML 읽는 곳 전수** | (학습/추출/read-out에 z·면 없음) | — | 학습 입력에서 GML을 읽는 유일한 곳 = `make_clean_labels.py`(레이캐스트, ③ 클래스). read-out `_mob_prep_las_gssem.py`: building xyz=`npz["P_utm_clean"]`(GS), class=`P_class_clean`(GS argmax), ground=**GS 데이터 유래 z**(terrain median 또는 building z 5%분위 `:126-128`), footprint=crop/metrics. 추출 `tum_mob_tsdf_extract.py`: P_utm_clean/P_class_clean=GS 렌더 기하+GS 의미 logits(체크포인트). **LoD2 z/면 유입 0.** |

## §2 무텍스처 동에서 표면 z는 무엇으로 결정되나

무텍스처 동도 **MVS 씨앗이 0이 아니다**(seed_dense.ply, GT footprint 폴리곤 내, 독립 확인):

| 동 | 분류 | seed_dense(DIM) 점수 | mob DIM class6(참고) |
|---|---|---:|---:|
| 42364609 | 무텍스처 R | **99** | 48 |
| 4908166 | 무텍스처 R | **205** | 13 |
| 4908176 | 무텍스처 R | **230** | 260 |
| 4907182 | 무텍스처 R | **712** | 502 |
| 4908050 | 무텍스처 R | **825** | 108 |
| 4906969 | (관측 곡면) | 6849 | 43896 |
| 42364663 | 복합 | 7671 | 96621 |
| 4906972 | (박공) | 12841 | 154558 |

→ **무텍스처 동 표면 = 희박 MVS 씨앗(~100~825점, DIM) + L_photo + (있으면)MVS depth + GS densification/구조 평면성 + L_sem 기하결합(③)**. **LoD2 z 값은 직접 안 들어오나**(①②④⑤ 비모델), **`sem_detach_geometry=false`로 L_sem이 GS 기하를 LoD2 다시점 클래스 투영(visual-hull)으로 당긴다 — MVS 증거가 희박할수록 이 항의 상대 비중↑**(무텍스처에서 최대). 이어 gssem이 roof로 분류 → Roofer 조립. z 정밀도 낮음(소수 MVS 점 + 실루엣 결합; D-수트 위상 잔여와 정합).

## §3 한 줄 관찰 — 순환 여부 (판정 금지)

**LoD2 z(높이) 값 직접 순환은 없다** — 씨앗·depth·read-out ground z·footprint 모두 비모델(MVS/GS데이터, ①②④⑤). **그러나 표면 기하가 LoD2-레이캐스트 다시점(occlusion-resolved) 클래스 투영 supervision에 부분 결합**한다(③): L_sem(w_sem 0.1)이 **`sem_detach_geometry=false`**로 GS 기하(means 등)에 역전파 → roof-라벨 픽셀에 맞게 Gaussian 이동(다시점 visual-hull; 라벨은 LoD2 3D 메시 레이캐스트라 occlusion 반영, 단 t_hit/z는 미저장). **MVS 증거가 희박한 무텍스처일수록 이 참조-실루엣 항의 비중이 커지므로, 무텍스처 회복은 부분적으로 참조(LoD2 클래스-실루엣)-의존**이다 — 단 **LoD2 z 값을 복사하는 순환은 아님**(라벨에 z 없음). 설계문서의 "footprint=crop only"는 정확하나, "비모델 단서"는 **z에 대해서만** 정확 — 의미 단서 라벨은 LoD2 레이캐스트 클래스이고 sem_detach_geometry=false로 기하에 영향. **순환 정도 판정 = 김휘영.**

> ⚠ **D6 shape-audit 정정**: 그 보고가 무텍스처 회복을 "LoD2-band prior/seeding로 보임"이라 추정했으나, **코드상 gs_d4/gs_prior_full엔 LoD2 높이 band도 LoD2 seeding도 없다**(`seed_semantic` 미설정·seed=DIM·read-out ground z=GS데이터). 실제 기전 = 희박 MVS 씨앗 + **L_sem이 LoD2-레이캐스트 다시점 클래스 투영(visual-hull)으로 기하 견인**(`sem_detach_geometry=false`). (관찰 정정; 판정=김휘영.)

## §4 재현 / 출처
- 읽기 전용 추적: configs `gs_{d4,prior_full}_dense.yaml` · `src/stage2/{train.py:288-377·423-430·613-620·758, semantic_seed.py, renderer.py, loss/data_fitting.py:48-81, dataloader.py}` · scripts `seed_prep_dense.json`·`tum_mob_seed_prep.sh`·`prior_full_stereo.sh`·`make_clean_labels.py`·`tum_mob_tsdf_extract.py`·`_mob_prep_las_gssem.py`.
- seed_dense.ply 점수 = p0-tools에서 PLY 직독(float64 x/y/z) + footprint 폴리곤 point-in-polygon(GS-local→UTM +[690953,5336071,604]). 코드/디스크 무변경.
- EPSG:25832 · Docker · 읽기 전용 · 관찰만.
