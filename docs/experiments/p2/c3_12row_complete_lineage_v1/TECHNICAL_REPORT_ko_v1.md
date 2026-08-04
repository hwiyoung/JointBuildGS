# C3 12행 complete lineage 비교판 — promoted summary

## 상태

- 기술 상태: `300-CLOSED_LOCAL_COMPLETE_LINEAGE_DIAGNOSTIC`
- 대상: 대표 3건물, `C3_1_SEM`과 `C3_2_SEM_DEPTH`
- 판 구성: 건물당 12행, 조건당 4시점, 총 8열
- 실행 권한: 사용자 직접 지시에 따른 single Experiment Host local execution
- two-host handoff event: 아님
- `official_G3_G4_PASS_usable: null`
- `scientific_verdict: null`

전체 보고서와 case HTML은 외부 artifact에 있고 Git-owned resolver는 `artifacts/manifests/p2_c3_12row_complete_lineage_report_recovery_v2.json`이다.

## 12행 구성

| 행 | 의미 | 계보 |
|---:|---|---|
| 1 | 2024 RGB + 2022 roofline | 영상 context |
| 2 | GS 3D Gaussian RGB | checkpoint proxy |
| 3 | GS 3D Gaussian semantic | checkpoint proxy |
| 4 | GS 3D Gaussian world-Z height | depth proxy, camera depth 아님 |
| 5 | GS 3D Gaussian plane normal | checkpoint quaternion 기반 |
| 6 | rendered-depth direct-fusion 3D points | GS surface extraction |
| 7 | 실제 C3 Roofer input LAS | class 6 roof + class 2 terrain |
| 8 | C3 Roofer output | GT-footprint oracle technical diagnostic |
| 9 | 24-view roof-only consensus | 병렬 mesh 진단 입력 |
| 10 | Poisson mesh | 9행 입력 사용 |
| 11 | TSDF mesh | 9행 입력 사용 |
| 12 | 2022 LoD2 | 비교 context |

1–8행은 본 Roofer Stage-3 진단 흐름이다. 9–11행은 같은 checkpoint에서 새로 추출한 병렬 mesh 진단이며 Roofer 입력·출력의 전후 단계가 아니다.

## Roofer 결과 계보

4906975와 108580336의 C3-1/C3-2, 총 4개 Roofer operation은 앞선 v11에서 완료됐다. v13은 해당 input LAS와 output을 exact hash로 상속했다. 이번 12행 작업은 그 봉인 결과를 재배열했으며 Roofer를 실행하지 않았다.

4907177은 C3-1 class-6 45점, C3-2 0점으로 두 조건 모두 Roofer 미실행 상태다. 판의 7행은 부족한 실제 입력을, 8행은 `NOT RUN — insufficient roof evidence`를 표시한다.

## 24-view roof-only consensus

이 포인트는 Roofer 입력이 아니다. 대표 건물을 덮는 최대 24개 공통 카메라에서 checkpoint depth와 semantic을 렌더링하고, roof pixel을 3D로 역투영한 뒤 최소 2개 서로 다른 view가 지지하는 voxel만 유지한 것이다. Poisson과 TSDF에 동일 evidence를 주기 위한 후속 진단 입력이다.

## 108580336 해석

실제 Roofer class-6 입력은 C3-1 621점, C3-2 644점이다. 0.3m point-buffer 기준 footprint coverage는 1.51%와 1.35%지만 convex-hull span은 66.53%와 54.68%다. 따라서 Roofer 외곽이 그럴듯한 것은 GT footprint만의 효과도, 촘촘한 roof recovery의 증거도 아니다. 넓은 XY에 성기게 분산된 class-6 point, GT footprint clipping, plane fitting이 결합된 결과다.

## 실행 및 해석 경계

- GS training: 0
- checkpoint render extraction: 0
- mesh generation: 0
- Roofer invocation: 0
- G2 invocation: 0
- metric recomputation: 0
- C4/C5 access: 0

이번 판은 봉인 결과의 비교 배치와 기술 진단이다. `scientific_verdict: null`은 C3-1/C3-2의 과학적 우열, 모집단 일반화, 공식 G3/G4/`PASS_usable` 판정을 하지 않았다는 뜻이다.
