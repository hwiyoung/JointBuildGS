# T0 판정 단위(region unit) v1 기술 반환

> 지위: `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`.
> 작업 ID `PHD-REGION-UNIT-v1`. 설계 근거: 방법 설계 v2 부록 D-1 r1.1
> (`docs/experiments/phd/mvs_als_surface_patch_v1/SOURCE_DECISION_METHOD_DESIGN_ko_v2.md`).
> 리뷰어: 김휘영. 생성: 2026-09-02.

## 결론

T0는 책임 하나가 붙는 자리(판정 단위)를 **소스 데이터에, 루프 밖에서, 한 번**
정의하는 태스크다. 동결 파일럿 prism(tile `x003_y004`, scene-local
`X[-23,7) Y[-21,9) Z[-44.272,-25.962)` m)에서 MVS 139,033점 → 36,104셀,
Existing ALS 20,189점 → 15,992셀을 214개 단위로 나눴고,
모든 셀이 정확히 하나의 단위에 속한다(미배정 0, 삭제 0). 단위는 전부
연결돼 있고(214/214), 규모 상한 위반은 0건, 최소 면적 미만
55건은 모두 `small`로 표시됐다. 동결 관계 core 610개는 전부 자기 소스 셀 키로
단위에 사상됐다(미해결 0). 두 번 실행한 해시가 같고 입력 행 순서를 섞어도 같다.

T0가 결정하지 않은 것: 소스 authority, 시간 변화, 정합 δ, 책임 `pi`, 가우시안
가중치. pairing·prior 지지 비율 `f_P`·층 분할은 위치 회계일 뿐 판정이 아니다.
current UAS LiDAR, LoD2 Ground/Roof/Z, stable building ID, 93/199 roster는 읽지 않았다.

## 방법(D-1 r1.1 요약)

1. 소스별 작업 셀 0.25 m(D-1.1) → PCA 법선·표면 변동(D-1.2).
2. 결정론적 FIFO 평면 region growing(법선각 15°, 평면 거리 0.15 m, 반경 0.6 m,
   PCA 재적합은 8멤버부터 배가 시점마다·조건수·시드각 보호) + 모서리 띠 흡수
   (거리 검정만, 고리 ≤ 3)(D-1b). 면적은 평면 위 점유 2D 셀 × v²(D-1c), `A_min` 1 m².
3. 규모 상한 8 m: 평면은 평면 내 격자, 거친 성분은 3D 격자, 격자 안 연결 성분을
   자식으로, 소형 자식은 접촉 자식 중 최대 면적에 병합(D-1.4).
4. 잔여 연결 성분 = 거친 단위, 소형 성분은 1 m 안의 단위에 흡수(D-1.5).
5. pairing 창 = 동결 M3C2 투영창을 **ALS 셀 자기 법선 방향**으로(반길이 3 m, 면내
   허용 1 m; 거친 단위는 원통; 무효 법선은 ALS 세그먼트 법선 차용, 없으면 1 m
   유클리드)(D-1e′). 같은 표면의 인접 단위 동률은 면내 거리로.
6. prior 측 층 분할: 한 MVS 평면 단위(부모 세그먼트 단위)의 prior 측에 오프셋이
   0.30 m 넘게 다른 ALS 세그먼트 그룹이 있고 발자국 ≥ A_min이면 잘라 단위 하나 =
   층 하나(D-1k). 창 밖 ALS 셀은 ALS 자체 세그먼트에서 prior-only 단위(D-1f).
   `f_P`는 1 m 지지 격자 기준(D-1g).
7. 정수 정렬 키·입력 결속 uid·인접·관계 core→단위(셀 키)·resolver(전 셀)
   (D-1.7·8·i·j).

기준값 출처는 config `provenance`에, 수식은 D-1.9에 있다. `base`는 결과를 보기
전에 고정했고 fine/coarse는 민감도 진단이다.

## 파일럿 결과

| 항목 | 값 |
|---|---:|
| 단위 수 | 214 |
| MVS-primary 평면 / 거친 | 105 / 68 |
| prior-only 평면 / 거친 | 12 / 29 |
| ALS 셀 paired / prior-only 지대 | 12,642 / 3,350 |
| prior 측이 빈 MVS 단위 | 49 |
| 층 분할된 MVS 단위 / mixed_prior 표시 | 46 / 46 (미표시 위반 0) |
| 셀 역할 평면 core / 거친 / 흡수 | 37,335 / 13,954 / 807 |
| small / 분할 자식 (규모 / 층) | 55 / 89 (43 / 46) |
| 면적 p10 / p50 / p90 / max (m²) | 0.06 / 2.91 / 25.44 / 108.19 |
| `f_P` p10 / p50 / p90 (MVS 단위) | 0.00 / 0.30 / 1.00 |
| pair 거리 p10 / p50 / p90 (m) | 0.01 / 0.08 / 2.32 |
| 관계 core 사상 / 미해결 / core 0 단위 | 610 / 0 / 83 |
| 인접 간선 (같은 primary) | 698 (612) |

pair 규칙별 ALS 셀 수:

| 규칙 | 셀 |
|---|---:|
| ABSORBED_SMALL_PRIOR_COMPONENT_INTO_MVS_UNIT | 211 |
| NONE_PRIOR_ONLY_ZONE | 3,350 |
| PLANAR_ALONG_ALS_SEGMENT_NORMAL | 15 |
| PLANAR_ALONG_OWN_ALS_NORMAL | 6,355 |
| PLANAR_EUCLIDEAN_FALLBACK_NO_NORMAL | 24 |
| ROUGH_CYLINDER_ALONG_ALS_NORMAL | 6,013 |
| ROUGH_EUCLIDEAN_FALLBACK_NO_NORMAL | 24 |

관계 core 클래스 × pairing 상태 교차표(D-1.10 행 4; 클래스 4 core의 셀이 paired인
비율과 클래스 1/2 core의 단위가 prior 측 없음인 비율이 "창 일치"의 실측이다):

| 클래스 | core | MVS core: 단위에 prior 측 있음 / 없음 | ALS core: 셀 paired / prior-only | 미해결 |
|---|---:|---:|---:|---:|
| 1 | 53 | 49 / 4 | 0 / 0 | 0 |
| 2 | 325 | 310 / 15 | 0 / 0 | 0 |
| 3 | 107 | 33 / 74 | 0 / 0 | 0 |
| 4 | 95 | 0 / 0 | 12 / 83 | 0 |
| 5 | 30 | 7 / 8 | 13 / 2 | 0 |

정성 판독(뷰어 8892 `T0 판정 단위` 층; 물리 범주로 다시 센 표는 아래). prism 안에는
서로 다른 세 상황이 있다. ① **남동쪽(x −12~7, y −21~−3 m)**: ALS(2022)에 기울기
17~21°의 경사 지붕 평면 7개(prior-only 단위 174~180, 약 145 m², z ≈ −37.7)가 있고,
같은 발자국의 MVS(2024)는 z ≈ −41.9의 수평 지면(셀 12,351 중 10,258 수평 평면)이다.
옛 지붕이 현재 지면 4~5 m 위에 떠 있는 이 서명은 철거(H_chg 소실)의 전형이다.
② **서쪽(x −22~−13, y −10~2 m)**: MVS는 z −41~−32 m의 거친 덩어리(수목), ALS도
같은 자리에 거친 셀(2022 수관)이며, 그 아래 ALS 지면 조각 두 개(단위 181·182, z −41.6)는
MVS에 지면이 없어 prior-only가 됐다(H_M 계열: MVS 결손). ③ **북쪽 가장자리**: 현재
건물의 평지붕·경사면·벽(MVS 평면 단위 13·16·18·20 등)에 ALS 셀이 짝지어져 있다
(양립 후보). T0는 이 세 자리를 **단위로 분리해 둘 뿐** 어느 것도 판정하지 않는다.
지면은 8 m 격자 자식 단위(62개)로 나뉘고, `f_P`는 ALS 지면 표본이 없는 곳에서
떨어진다(prior 결손의 연속 표현).

214 단위를 물리 범주로 다시 세면(설명용 분류: 기울기·높이·kind로 자동 분류):

| 범주 | 단위 | 그중 small(< 1 m²) | 면적 합 m² |
|---|---:|---:|---:|
| MVS 지면(8 m 격자 자식) | 62 | 8 | 872 |
| MVS 평지붕·고가 수평면 | 5 | 0 | 56 |
| MVS 경사 지붕면 | 27 | 2 | 141 |
| MVS 벽 | 11 | 0 | 52 |
| MVS 거친(수목·잡동사니, 3D 격자 자식) | 68 | 24 | 670 |
| prior-only 평면(2022 ALS 지붕·지면 조각) | 12 | 0 | 165 |
| prior-only 거친 | 29 | 21 | 17 |

small 단위 55개는 면적의 0.5 %이며 커버리지 규칙(모든 셀이 정확히 한 단위) 때문에
존재하는 회계 조각이다. 뜻이 있는 단위는 면적 ≥ 1 m² 159개다.

profile 민감도(선택 근거 아님):

| profile | 단위 | 거친 셀 | prior-only 단위 | ALS paired | 층 분할 | small |
|---|---:|---:|---:|---:|---:|---:|
| base | 214 | 13,954 | 41 | 12,642 | 46 | 55 |
| coarse | 239 | 5,632 | 76 | 12,366 | 50 | 115 |
| fine | 269 | 19,866 | 58 | 12,689 | 61 | 53 |

## 셀 크기 민감도(D-1.9 규칙 · D-1.11)

`v`는 희소 소스(ALS ≈ 22 pt/m², 평균 간격 0.21 m)의 점 간격을 올림한 값이며 물리
척도(`r_n`, `r_g`, `A_min`, `L_max`, pairing 창)는 m 단위로 `v`와 무관하다. 남는
의존성을 `cell_size_sensitivity.json`으로 잰다(점 단위 배정의 ARI, 기준 v = 0.25):

| v (m) | 셀 | 단위 | MVS 평면/거친 | prior-only | 평면 면적 합 m² | ALS paired | 거친 셀 비율 | ARI 최종 단위 MVS/ALS | ARI 원시 세그먼트 MVS/ALS | 평면 역할 일치 MVS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.15 | 104,057 | 181 | 90/54 | 37 | 1055 | 0.78 | 0.21 | 0.41/0.65 | 0.59/0.79 | 0.92 |
| 0.2 | 73,199 | 187 | 89/53 | 45 | 1071 | 0.79 | 0.26 | 0.43/0.69 | 0.53/0.81 | 0.90 |
| 0.25 | 52,096 | 214 | 105/68 | 41 | 1122 | 0.79 | 0.27 | 1.00/1.00 | 1.00/1.00 | 1.00 |
| 0.3 | 39,467 | 219 | 95/73 | 51 | 1114 | 0.78 | 0.28 | 0.39/0.68 | 0.56/0.77 | 0.91 |
| 0.4 | 23,823 | 218 | 103/66 | 49 | 1087 | 0.79 | 0.31 | 0.40/0.56 | 0.52/0.79 | 0.89 |
| 0.5 | 15,690 | 240 | 121/69 | 50 | 1196 | 0.78 | 0.31 | 0.40/0.60 | 0.66/0.89 | 0.88 |

읽는 법. 집계 지표(단위 수·평면 면적·ALS paired 비율)는 `v`에 둔감하지만 **최종
단위의 점 단위 배정은 둔감하지 않다**. 원시 세그먼트 ARI와 평면 역할 일치가 최종
단위 ARI보다 높으면 차이의 주인은 규모 상한 격자(세그먼트 최소 모서리 기준)다.
단위 경계는 정본 객체가 아니라 성가신 변수이며, T4 책임 지도의 결론은 `v`에
불변이어야 한다(절제 축). 개선 후보는 D-1.11 참조.

## 설계 검증과 구현 중 정정(설계 문서 D-1 r1.1에 반영)

적대적 설계 검증(4관점 20에이전트, 확정 13건)과 합성 시험에서 나온 정정:

- resolver 도메인이 prior-only 셀뿐이어서 H_M 구제 가우시안(MVS 평면에서 1~3 m)이
  미해결이 됨 → 전 셀(paired ALS 포함) 위의 resolver(D-1h) + 관계 core→단위
  사상(D-1j).
- MVS 단위 법선 방향 창이 MVS 지붕이 빠진 자리에서 벽 단위에 ALS 지붕을 가로채게
  함 → ALS 셀 법선 방향 창(D-1e′); 무효 법선의 거리 전용 대체도 같은 결함을
  재현(합성 지붕 34 % 벽에 귀속) → ALS 세그먼트 법선 차용.
- 한 MVS 단위의 prior 측에 오프셋이 다른 ALS 층이 섞임(헐린 창고) → 부모 세그먼트
  단위의 층 분할(D-1k; 격자 자식별로 하면 창고가 5조각).
- 같은 평면의 인접 자식 단위가 `|t|` 동률로 경계 띠를 뺏음(`f_P` 0.28) → 전역
  argmin + 면내 거리 동률 규칙.
- 자식·단위 프레임의 무보호 PCA가 한 줄짜리 지면 조각을 벽으로 읽음(파일럿 3셀
  조각 tilt 85°) → 부모 세그먼트 법선 기준의 보호 재적합을 모든 단위 프레임에
  적용, validator 가 8셀 미만 평면 조각의 tilt > 60° 거부.
- D-1f 로 MVS 단위에 흡수된 소형 ALS 성분이 셀 레코드에 안 적힘 → pair_rule
  `ABSORBED_SMALL_PRIOR_COMPONENT_INTO_MVS_UNIT` + 숙주 거리 기록.
- `mixed_prior` 를 spread 로 정의하면 3b 검사가 공허 → "탐지됐으나 자르지 못한
  층" 으로 재정의(잘린 부모의 모든 조각은 PRIOR_LAYER).
- 성장 중 2멤버 PCA 재적합이 벽 평면을 파괴 → k_n부터 재적합 + 조건수·시드각 보호.
- 법선 반경 1 m 때문에 지붕–벽 모서리 띠가 탈락 → 거리 검정만의 2단계 흡수.
- 거친 성분 규모 상한 없음(수목 180 m²·21 m) → 3D 격자 분할, validator 강제.
- `f_P` 지지 척도를 작업 셀로 재면 ALS 밀도에 종속 → 1 m(M3C2 반경).

## 검증

Docker unittest 17개(`tests/phd/test_region_unit_v1.py`: 커버리지·결정론·행 순서
치환 불변·평면/벽 분리·모서리 띠 회복·면적·분할·거친 상한·얇은 조각 법선 보호·
pairing 창·벽의 ALS 지붕 비포획·층 분할·resolver·core 사상·ARI·config 금지 토큰)
통과. validator 검사:
`adjacency_integrity`, `criterion_1_connected_units`, `criterion_2_complete_coverage`, `criterion_3_scale_flags_and_extent_cap`, `criterion_3b_prior_layer_split_or_flagged`, `criterion_6_determinism_rerun`, `criterion_6_point_cell_unit_lineage`, `criterion_6_relation_core_lineage`, `d1b_unit_frames_within_theta_of_parent`, `input_hashes_and_gravity_not_hardcoded`, `output_hashes`, `prohibited_inputs`, `resolver_all_cells_self_and_unresolved`, `scientific_verdict_null`, `scope_contract` 전부 PASS. 입력은 partition receipt·MVS/ALS 파티션
bytes·관계 지도(core 사상 전용, 되먹임 없음)·Gate-S0 중력 체크포인트
(`hardcoded_gravity=false`, 서술용 기울기에만)의 크기·SHA-256을 먼저 확인했다.

## 산출물

Canonical external root:

```text
$JBGS_ARTIFACT_ROOT/phase-payloads/phd/region_unit_v1/PHD-REGION-UNIT-v1/
```

`cells.npy`(셀 레코드), `units.npy`(단위 레코드), `unit_adjacency.npy`,
`unit_cores.npy`(core→단위), `point_rows_*.npy`/`point_cell_*.npy`(원 점 → 셀 계보),
`unit_prior_composition.json`, `units.csv.gz`, `region_unit_map.ply`,
`region_unit_preview.png`, `profile_sensitivity.json`, `cell_size_sensitivity.json`,
`technical_return.json`
(`unit_set_sha256` 포함), `artifact_manifest.json`, `validation_receipt.json`,
`resolved_input_manifest.json`. SHA-256은
`artifacts/manifests/phd/region_unit_v1/technical_result_manifest_v1.json`에 기록했다.

뷰어: 기존 8892(`scripts/phd/mvs_als_surface_patch_viewer_v1`)에 `T0 판정 단위 ·
pilot prism` 층을 추가했다(unit UID / kind / primary / pairing / `f_P` / pair
distance / tilt / role / pair rule / prior layer / relation cores 색 모드, 단위 클릭 →
레코드·멤버 강조·bbox·인접, 커버리지 회계, prism 카메라). 뷰어 빌드 validator에
T0 자산 stride·커버리지 검사를 더했다.

## 미결(D-1.11)과 다음

D-1.11 그대로: 항공 ALS 벽 희소, 거친 면적 과대, 분할 격자 임의성, `v` 이하 구조,
전체 장면 확장, `A_min` 대 core 간격, 거친 단위의 층 혼합 기록만. 다음 태스크
T1(증거 은행)은 `units.npy`/`cells.npy`/`unit_cores.npy`를 색인으로 3D-a 표본 집계,
3D-b 광선 통계, 2D-c·`r`을 단위별로 만든다.
