# C1/C2 oracle 및 C3 roof-semantic 결과판 Technical Return v1

## 결론

`P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v9`는 `FINALIZED_TECHNICAL`이다. C1/C2
3개 case sheet 72패널, C3 6개 case sheet 120패널, C1/C2 source CSV 6행을 생성했고
manifest record 38개의 크기와 SHA-256을 다시 검증했다. 9개 case sheet를 4140 px 원본
해상도로 직접 검토했다.

C1/C2의 모든 3D 행과 C3의 Gaussian/fused/mesh 행에는 동일한 GT `GroundSurface` XY
footprint가 주황 점선으로 표시된다. RGB 행의 2022 LoD2 `RoofSurface` 투영은 검정 12 px
casing과 노랑 6 px 선으로 표시된다. 이 roofline은 현재 RGB 문맥 확인 전용이고 C1/C2
Roofer 또는 C3 mesh 입력이 아니다.

## C1/C2 6행

| building | condition | status | class-6 | RoofSurface | output SHA-256 |
|---|---|---|---:|---:|---|
| `4907177` | C1 UAS LiDAR | `PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE` | 0 | null | null |
| `4906975` | C1 UAS LiDAR | `COMPLETED` | 133,335 | 13 | `c0b7a8ef0b81cca0d39d8e2f3bb2aa3518dd2755e7c38bd97886798cfacde585` |
| `108580336` | C1 UAS LiDAR | `COMPLETED` | 254,266 | 29 | `b1b85ee69c6785a9473864a4eeab20f0601bdd9931acdac84c210c479b681450` |
| `4907177` | C2 current MVS | `PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE` | 0 | null | null |
| `4906975` | C2 current MVS | `COMPLETED` | 148,079 | 51 | `553af51efb4993dc20788278bbd5ea7fd4b76433798c20b75b8022dd66972da4` |
| `108580336` | C2 current MVS | `COMPLETED` | 440,867 | 73 | `2bff991d30894f6da186e766236d975276f6aef221487f26eddfe5b566314ab5` |

이 수치는 기존 exact C1/C2 operation record를 계승한 source 행이다. 이번 recovery에서
정량 metric을 다시 계산하지 않았다. C1/C2는 GT GroundSurface XY를 Roofer footprint로
사용한 oracle diagnostic이며 official honest Stage 3가 아니다.

## C3 roof-only mesh 후처리

v7의 Poisson mesh는 semantic label을 색상에만 사용하고 roof/wall/ground/background가 섞인
fused point 전체를 입력으로 사용했다. v9은 exact fused PLY를 다시 렌더하지 않고
`semantic_class=1 (roof)`이면서 GT GroundSurface XY의 1 m buffer 안에 있는 점만 선택했다.
선택점이 100점 이상일 때만 CPU Poisson mesh를 만들었다.

| building | condition | selected roof points | triangles | status |
|---|---|---:|---:|---|
| `4907177` | C3-1 semantic | 126 | 2,346 | `COMPLETED_ROOF_SEMANTIC_MESH` |
| `4906975` | C3-1 semantic | 51,390 | 133,146 | `COMPLETED_ROOF_SEMANTIC_MESH` |
| `108580336` | C3-1 semantic | 857 | 6,600 | `COMPLETED_ROOF_SEMANTIC_MESH` |
| `4907177` | C3-2 semantic+depth | 1 | 0 | `INSUFFICIENT_ROOF_SEMANTIC_EVIDENCE` |
| `4906975` | C3-2 semantic+depth | 5,331 | 31,076 | `COMPLETED_ROOF_SEMANTIC_MESH` |
| `108580336` | C3-2 semantic+depth | 1,174 | 6,208 | `COMPLETED_ROOF_SEMANTIC_MESH` |

`4907177/C3-2`는 mesh를 꾸며내지 않고 네 고정 시점 모두에 선택 지붕점 1점과 미생성
상태를 표시한다. 이전 all-semantic mesh는 lineage 보존 파일로 남지만 최종 case sheet의
mesh 행에는 사용하지 않는다.

## 원본 해상도 시각 검토

- `4906975`: RGB roofline과 현 건물이 시각적으로 대응한다. roof-only mesh는 기존 fused
  행의 지붕 외 수직 잡음을 제외하고 목표 roof evidence에 집중한다.
- `108580336`: footprint가 긴 대상 건물을 명확히 주소화한다. roof-only mesh에도 분절과
  높이 편차가 남아 있으며 이는 선택된 semantic/depth geometry 관찰이지 renderer 실패가 아니다.
- `4907177`: 2022 roofline과 2024 RGB/footprint의 불일치가 계속 보인다. C1/C2는 Roofer
  미실행 precondition failure이고, C3-1 mesh도 126점의 제한적·offset 형상이다. C3-2는
  roof evidence 1점으로 mesh 미생성이다. 계속 `REFERENCE/ID ALIGNMENT REVIEW` 대상이다.

## 실행 계수와 해석 경계

- 이번 recovery: Roofer 0, G2 0, GS training 0, rendered-depth C3 extraction 0,
  metric recomputation 0, C4/C5 access 0
- lineage: 완료 Roofer operation 4, 완료 C3 extraction 2
- 이번 roof-only CPU mesh postprocess: 6 attempts, 5 completed, 1 insufficient evidence
- `official_G3_G4_PASS_usable: null`
- `scientific_verdict: null`

`scientific_verdict: null`은 기술 산출물·계수·관찰을 반환했지만 연구 성능의 합격/실패,
일반화 또는 confirmatory 결론을 내리지 않았다는 뜻이다.

## 산출물

- artifact root: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_oracle_c3_extract_recovery_v9/P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v9`
- manifest: `artifact_manifest_v1.json`, SHA-256
  `8b9fc56778e2cd2b069f7f76794bc799cacc03c6f599be4f0d25219954842878`
- CSV: `tables/c1_c2_oracle_operation_summary_v1.csv`
- qualitative index: `qualitative/index.html`
- artifact technical report: `reports/technical_report_ko_v1.md`

