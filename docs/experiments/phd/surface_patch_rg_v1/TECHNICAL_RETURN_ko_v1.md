# 교과서 표면 패치 추출 v1 기술 반환 (모든 객체, 소스별)

> 지위: `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`. 작업 ID `PHD-SURFACE-PATCH-RG-v1`.
> 리뷰어: 김휘영. 생성: 2026-09-02. 사용자 지시(2026-09-03): "패치 추출은 바이블적 방법부터, 건물 외 모든 객체 대상".

## 결론

동결 파일럿 prism의 MVS 139,033점과 Existing ALS 20,189점을 소스별로, 건물 prior 없이, 원 점 위에서
교과서 방법으로 패치화했다. 방법은 두 단계다. ① **표면 성장**(Vosselman et al. 2004; Vosselman & Maas 2010 2장;
Rabbani et al. 2006과 PCL `RegionGrowing`의 골격에 평면 잔차 기준을 더한 형태): 곡률 오름차순 시드, 영역 평면 법선과의 각
≤ 15°, 점–평면 거리 ≤ 0.15 m, 멤버 배가 시점의 보호된 PCA 재적합, 최소 크기(MVS 50점 / ALS 15점). ② 잔여 점의
**Euclidean 군집**(PCL `EuclideanClusterExtraction`): 허용 0.5 m / 1.0 m, 최소 20 / 8점, 그 미만은 명시적 잡음(라벨 0, 삭제 없음).
패치 유형은 평면 RMSE ≤ 0.15 m → PLANAR, 그 외 선형/산재(Weinmann 2015 고유값 특징).

| 소스 | 표면 영역 | Euclidean 군집 | 영역 점 비율 | 군집 점 비율 | 잡음 점 | 유형(평면/선형/산재) | 최대 패치 점 |
|---|---:|---:|---:|---:|---:|---|---:|
| MVS | 267 | 30 | 86.0 % | 13.4 % | 874 | 279/4/14 | 72,783 |
| ALS | 57 | 12 | 82.3 % | 17.2 % | 97 | 65/1/3 | 6,257 |

건물 외 객체도 패치가 된다. MVS 지면은 영역 하나(72,783점, RMSE 6.9 cm, 648 m²), 옛 건물 자리의 ALS 경사 지붕면은
RMSE 2~3 cm의 영역들(17~21°), 현재 건물 지붕·벽은 평면 영역, **수목은 산재형 Euclidean 군집**(MVS 15,581점·308 m²,
ALS 2,928점)이다. 매끄럽지 않은 객체는 영역이 아니라 군집으로 잡히는 것이 이 방법의 정상 동작이며, 군집도 라벨을 갖는
패치다.

## 순수 smoothness 기준의 실측 한계(MVS)

PCL 튜토리얼 그대로의 기준(이웃–현재점 법선각 + 곡률 게이트)은 MVS 잡음(지면 RMS ≈ 7 cm, k=60 곡률 중앙값 0.07)에서
양쪽으로 실패한다. 엄격(k60·15°·곡률 0.05)이면 지면이 51k점 영역과 38k점 잔여 군집으로 갈라지고, 느슨(k100·10°·0.10)이면
지면·저층 수목·지붕이 한 영역(111k점, 평면 RMSE 1.33 m)으로 샌다(k 30/60/100 × 10/15/20° × 0.03/0.05/0.10 스윕은
내부 통계만으로 판단했고 참조 자료는 쓰지 않았다). 평면 잔차 기준(표면 성장)이 이를 해결한다. 이 기준은 앞선
`region_unit_v1`의 성장 단계와 같으며, 그 워크스트림의 추가 규칙(격자 상한·층 분할·흡수·pairing)은 여기 포함하지 않는다.

## 검증·산출물

Docker unittest 4개(곡면 포함 매끄러운 표면의 영역화, 산재 점의 군집/잡음, 유형·결정론, config 계약) 통과.
validator: `coverage_every_point_labelled_or_explicit_noise`, `determinism_rerun`, `input_hashes`, `output_hashes`, `patch_integrity`, `prohibited_inputs`, `scientific_verdict_null` 전부 PASS.
산출물 `$JBGS_ARTIFACT_ROOT/phase-payloads/phd/surface_patch_rg_v1/PHD-SURFACE-PATCH-RG-v1/`: `points_{mvs,als}.npy`
(점별 patch_id·kind·곡률·법선), `patches_{mvs,als}.npy`(패치 레코드), `point_rows_*.npy`(원 행 계보),
`surface_patch_preview.png`, `technical_return.json`, `artifact_manifest.json`, `validation_receipt.json`.
SHA-256은 `artifacts/manifests/phd/surface_patch_rg_v1/technical_result_manifest_v1.json`.

## 결정하지 않은 것과 다음

소스 간 pairing, 판정 단위 크기(지면 한 장 648 m²를 그대로 둘지), 책임·가중치. 다음은 이 패치를 그대로 두고 T1 증거를
패치별로 붙일지, 아니면 pairing 규칙을 먼저 정할지의 결정이다. 8892 뷰어 층은 아직 `region_unit_v1`(214 단위)을 보여 준다.
