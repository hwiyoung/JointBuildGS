# C1/C2/C3 presentation v5 기술 Return

- artifact: `artifact://JointBuildGS/phase-payloads/p2/c1_c2_c3_consolidated_results_v1/P2-C1-C2-C3-CONSOLIDATED-RESULTS-v5-RECOVERY-v2`
- state: `300-CLOSED_LOCAL_PRESENTATION_V5`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

3개 사례 각각에 C1/C2 한 페이지, C3-1 한 페이지, C3-2 한 페이지를 생성해
총 9페이지로 닫았다. 별도 principal-section 페이지는 만들지 않았다. 모든 TOP
패널에는 footprint-PCA canonical section band와 A/B, VIEW 화살표가 직접 들어가고,
모든 네 번째 열은 건물별 2022 LoD2에 +45.7 m를 적용한 동일 Z 범위로 다시
렌더했다. legacy blue/red dual section 표시는 사용하지 않았다.

C2 Roofer output이 봉인돼 있는 4906975와 108580336은 exact 2024 RGB common-base
camera로 OBJ/MTL/atlas texture를 생성하고, 각 face의 camera, vertex coverage,
incidence 및 MVS depth consistency를 JSONL receipt로 기록했다. texture 관측 face는
각각 1,628/1,813과 1,009/2,477이다. 4907177에는 봉인 C2 Roofer output이 없으므로
빈 geometry를 결과처럼 보이지 않고 `NOT_RUN_NO_SEALED_C2_ROOFER_OUTPUT` receipt로
남겼다.

첫 실행은 이 NOT_RUN 사례의 빈 receipt를 허용하지 않은 self-check로 실패했고,
첫 recovery는 직접 화상 검토에서 header overlap을 발견해 중단했다. 두 namespace와
실패/중단 receipt를 보존한 뒤 recovery-v2를 최종 산출물로 닫았다. 이 작업에서 GS
학습, checkpoint extraction, Poisson, TSDF, Roofer, G2, metric 재계산 또는 C4/C5
access는 수행하지 않았다.
