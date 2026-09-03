# 표면 패치의 XY 컬럼 pairing v1 기술 반환 (2.5D + 벽 예외)

> 지위: `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`. 작업 ID `PHD-PATCH-PAIRING-XY-v1`.
> 리뷰어: 김휘영. 생성: 2026-09-02. 사용자 결정(2026-09-03): 주 규칙 = XY 발자국(2.5D 컬럼), 벽은 3D 근접 예외, 다층은 층마다 별도 짝.

## 결론

`PHD-SURFACE-PATCH-RG-v1`의 소스별 표면 패치를 0.5 m XY 셀로 짝지었다. 셀마다 각 소스의 **위층 표면**(패치 중앙 z가 가장 높은 것)을 짝짓고,
한 소스가 1 m 넘게 떨어진 아래 표면을 가지면 **아래층**을 두 번째 짝으로 둔다. 기울기 70° 넘는 평면 패치(벽)는 컬럼에서 빼고
3D 근접(1 m, 점의 30 % 이상, 상대는 30° 이상 기울었거나 산재 군집인 패치만)으로 짝짓는다. 짝 상태는 높이 차
dz = z_prior − z_current의 **서술 분류**이고(허용 0.3 m), 소스 authority·변화·정합의 판정이 아니다.

| 위층 셀 상태 | 면적 m² | 그중 산재(거친) 짝 |
|---|---:|---:|
| COMPATIBLE (양립, \|dz\| ≤ 0.3) | 310 | 25 |
| PRIOR_ABOVE (옛 것이 위) | 407 | 100 |
| CURRENT_ABOVE (지금 것이 위) | 163 | 118 |
| PRIOR_ONLY (옛 것만) | 8.5 | 0.0 |
| CURRENT_ONLY (지금 것만) | 11.5 | 2.8 |

위층 셀 3,600개(900 m²), 아래층 짝 342셀. 양쪽이 있는 셀의 dz 분위 p10/p50/p90 =
-1.13 / 0.05 / 4.24 m. 패치 짝 162개(양립 41, 옛 것 위 66,
지금 것 위 55). 벽: MVS 35, ALS 8, 3D 짝 16, 단독 27.

사진 위 판독(`pairing_preview.png`, 현재 TOP 영상은 표시 전용). 빨강(옛 것이 위)의 대부분은 2022 ALS 경사 지붕면
1·4·5·8·9(합계 약 375 m², dz 중앙값 1.6~3.8 m)가 2024 MVS 광장 지면 위에 놓인 자리다. 즉 2022에 있던 건물 자리가 지금은
포장 광장이다. 주황(지금 것이 위)은 대부분 거친 짝(수목: MVS 수관 군집이 ALS 지면·낮은 수관 위)이고, 초록은 광장 지면과
남쪽 곡면 건물 지붕(양 시기 존재), 보라는 수관 아래 MVS 결손 지면, 청록은 ALS 결손이다.
앞선 패치 기술 반환의 "옛 지붕 약 145 m²"는 0.25 m 셀 점유 면적(희소 ALS의 과소 추정)이며, XY 셀 기준 발자국은 약 375 m²다.

## 검증·산출물

Docker unittest 3개(상태 5종·창고 짝·아래층·벽 예외(지면은 벽의 짝이 아님, 맞은편 벽은 짝)·결정론·config) 통과. validator:
`cell_state_consistency`, `determinism_rerun`, `input_hashes_and_upstream_receipt_binding`, `output_hashes`, `patch_pair_integrity`, `prohibited_inputs`, `scientific_verdict_null` 전부 PASS. 입력은 패치 워크스트림의 manifest·receipt 결속과 파티션 해시를 먼저 확인했다.
산출물: `pair_cells.npy`(셀·층별 짝 레코드), `pair_pairs.npy`(패치 짝 집계), `pair_walls.npy`, `pairing_preview.png`,
`technical_return.json`, `artifact_manifest.json`, `validation_receipt.json`. SHA-256은
`artifacts/manifests/phd/patch_pairing_xy_v1/technical_result_manifest_v1.json`.

## 결정하지 않은 것과 다음

책임·가중치·δ·변화 판정은 하지 않았다. 다음은 T1 증거 은행: 이 짝(셀 또는 패치 짝)을 단위로 3D-a(관계 core 집계), 3D-b(광선),
2D-a(뷰간 warp), 2D-c·r을 붙이는 일이다. 8892 뷰어에는 아직 이 층이 없다(사진 오버레이가 현재의 표준 확인 방법).
