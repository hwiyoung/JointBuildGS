# C1/C2 oracle 및 C3-1/C3-2 비교판 Technical Return v1

## 결론

`P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v13`은 `FINALIZED_TECHNICAL`이다. C1/C2 3개
case sheet 72 panels와 C3 건물별 비교 sheet 3개 144 panels를 생성했다. C3 sheet는
current RGB+2022 roofline, C3-1 Gaussian RGB/semantic·fused point·roof-only Poisson
mesh·GT-footprint oracle Roofer, C3-2의 같은 다섯 행, 2022 LoD2 epoch-context 행을
같은 4열에 배치한다.

artifact manifest 208 records의 크기와 SHA-256을 전부 다시 검증했고 실패는 0건이다.
세 C3 sheet는 모두 4140×8740 원본 해상도로 직접 검토했다.

## C3 Roofer 진단 입력과 결과

C3 class 6은 계승된 rendered-depth fused point 중 semantic class `1=roof`이고 exact GT
GroundSurface XY 내부인 점을 0.2 m deterministic voxel로 정리한 것이다. class 2는 두
condition 모두 exact common-image C2 MVS terrain support를 공유한다. LoD2 RoofSurface,
LoD2 Z, roof type과 final model은 Roofer 입력에 사용하지 않았다.

| building | condition | class 6 | shared class 2 | Roofer | RoofSurface |
|---|---|---:|---:|---|---:|
| `4907177` | C3-1 semantic | 45 | 3,808 | `INSUFFICIENT_C3_ROOF_SEMANTIC_EVIDENCE` | null |
| `4906975` | C3-1 semantic | 35,404 | 51,225 | `COMPLETED` | 25 |
| `108580336` | C3-1 semantic | 621 | 97,372 | `COMPLETED` | 1 |
| `4907177` | C3-2 semantic+depth | 0 | 3,808 | `INSUFFICIENT_C3_ROOF_SEMANTIC_EVIDENCE` | null |
| `4906975` | C3-2 semantic+depth | 4,342 | 51,225 | `COMPLETED` | 1 |
| `108580336` | C3-2 semantic+depth | 644 | 97,372 | `COMPLETED` | 2 |

네 completed output은 recovery-v11에서 각 1회 실행됐고 recovery-v13에서는 hash 검증 후
계승했다. `4907177` 두 condition은 Roofer를 실행하지 않았으며 Roofer 실행 실패가 아니다.
이 read-out은 GT footprint를 사용한 oracle diagnostic이고 official honest Stage 3가 아니다.

## fused points와 roof-semantic mesh의 관계

Rendered-depth fused points는 선택한 current camera들에서 GS median depth를 렌더하고
world 3D로 back-project한 뒤 multi-view voxel fusion한 point cloud다. 투영에서 시작하지만
산출물은 3D point cloud다. Roof-semantic Poisson mesh는 그 3D fused point에서 roof class와
footprint buffer를 적용한 뒤 3D Poisson reconstruction한 후속 surface다. 따라서 둘의 차이는
단순한 2D 대 3D가 아니라 `render/back-project/fuse` 대 `roof-select/3D-surface-fit`이다.

## 원본 해상도 관찰

- `4907177`: 2022 roofline이 2024 RGB의 대상 footprint 및 current evidence와 시각적으로
  일치하지 않는다. C1/C2 footprint 안 class 6 부재와 C3 class-6 45/0점은 “철거됨”을
  확정하지 않는다. 실제 변화, 건물 ID 대응, XY/epoch association을 독립 검토해야 하는
  `REFERENCE/ID ALIGNMENT REVIEW` 대상이다. C3 oblique/principal이 이상한 직접 원인은
  대상 footprint 내부보다 바깥에 치우친 sparse/vertical Gaussian과 fused geometry다.
- `4906975`: fused point와 roof mesh의 완전성은 C3-1이 C3-2보다 높다. 반면 C3-1 Roofer는
  25개 RoofSurface로 과분할·요철이 많고, C3-2 Roofer는 1개 RoofSurface로 단순하다. 즉
  `C3-1=더 완전`, `C3-2=더 단순`이라는 기술 관찰은 가능하지만 단일 우열 판정은 아니다.
- `108580336`: C3-2 fused geometry가 지붕 slab를 조금 더 연속적으로 보이게 하지만 두
  condition 모두 semantic이 분절되고 roof evidence가 621/644점으로 작다. Roofer도
  RoofSurface 1/2개에 그쳐 명확한 품질 승자를 정할 근거가 부족하다.

2022 LoD2 행은 epoch-context reference일 뿐 C3 학습 또는 정량 평가 reference가 아니다.
현재 GS와 LoD2 Z는 이 판에서 vertical datum을 정량 정합하지 않았고 45.7 m 보정을 적용하지
않았다. 따라서 별도 행의 절대 Z 차이를 높이 오차나 성능 차이로 해석하면 안 된다.

## 실행 계수와 해석 경계

- recovery-v13: Roofer 0, G2 0, GS training 0, rendered-depth extraction 0,
  roof-mesh postprocess 0, metric recomputation 0, C4/C5 access 0
- lineage: C1/C2 Roofer 4 + C3 Roofer 4 = 8 completed invocations
- C3 successful historical training: C3-1 seed0 1회 + C3-2 seed0 1회 = 2회
- `official_G3_G4_PASS_usable: null`
- `scientific_verdict: null`

`scientific_verdict: null`은 기술 산출물, 실행 계수와 관찰을 반환했지만 C3-1/C3-2의 과학적
승패, 연구 성능 합격/실패, 일반화 또는 confirmatory 결론은 내리지 않았다는 뜻이다.

## 산출물

- artifact root: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/c1_c2_oracle_c3_extract_recovery_v13/P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v13`
- manifest: `artifact_manifest_v1.json`, SHA-256
  `c21d104b1c0cc279ad5ea6637c00e674395fea16d659054e3e28bc9b2880a5c5`
- C3 CSV: `tables/c3_oracle_roofer_operation_summary_v1.csv`
- qualitative index: `qualitative/index.html`
- artifact technical report: `reports/technical_report_ko_v1.md`
