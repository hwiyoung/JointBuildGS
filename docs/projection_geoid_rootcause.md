# projection_geoid_rootcause — 투영 오정합 근본원인: 수직 datum(지오이드) 누락 (읽기·판정 금지)

> **박사연구 GS-JSO.** 브랜치 `feat/p2-structure-learn`. EPSG:25832(지오)/32632(OPF). **읽기+진단, 재구성 없음.**
> 관찰·결론만, **적용/판정=김휘영**. 김휘영이 "footprint/lidar는 XY 맞는데 사진투영시 안맞음 → 높이체계 불일치?" 지적으로 규명.
> 진단 재현 `phases/p2-gsjso/scripts/{ztest,zmultiview,zfix_visual,zresolve}.py`(tools:t0). 그림 `docs/figs/projection_gate2/`.

## 0. 한 줄 결론

**공유 투영 코드 `base_to_canonical`가 정사고(orthometric) GML/ALS/footprint에 타원체용 `shift_z=−604`를 적용 → 지오이드
(~48 m) 누락 → 투영이 상수 ~48 m 낮음.** near-nadir≈0(그래서 projection-gate가 거짓합격)·off-nadir 대(지붕이 도로/외벽에 투영).
**수정: 정사고 입력엔 `shift_z=−556`(=−604+geoid) 사용**(입력 Z에 지오이드 더함). **파이프라인은 이미 이 규약을 씀**(GS-LOCAL/seed bands 전부 −556); **내가 만든 이미지-투영 경로만 누락**.

## 1. 근본원인 (원론적 — try&error 아님)

| 프레임 | Z 기준 | 근거 |
|---|---|---|
| 카메라 포즈(OPF/COLMAP, GS-LOCAL) | **타원체고(WGS84 ellipsoidal)** | base_Z 중앙 604.7 ≈ geolocation altitude 604.5(드론 GPS) |
| GML·ALS·footprint | **정사고(DHHN2016 normal/orthometric)** | ALS ground-class 중앙 ≈ ref HoeheGrund ~514 m (독일 공식 수직망) |
| 차이 | **지오이드 undulation ζ** | h_ellip = H_ortho + ζ |

**변환**: 정사고→타원체(카메라 프레임) = **+ζ**. `canonical_Z = H_ortho + ζ − 604`. ζ≈48이면 `= H_ortho − 556`.
**내 투영은 `H_ortho − 604`**(타원체용 shift를 정사고에 오적용) → **+ζ(~48 m) 누락** = 근본 버그.

**이미지 효과**: 수직 오차 ΔZ의 이미지 이동 = `f·ΔZ·sin(뷰천정각)/거리`. **천정각 0(nadir)서 0**(→gate 거짓합격), **오블리크서 성장**(52°서 수백 px). 결정증거 `zfix_4906972.png`(oblique 32°: ΔZ=0 지붕이 도로·+지오이드 지붕에 정확)·`nn_multi.png`(near-nadir 3동)·`oblchk_4907520.png`(20° hip선 정렬).

## 2. 파이프라인이 이미 규명·사용 중 (권위 출처)

- `phases/p2-gsjso/scripts/seed_depth_bands.py`: `--geoid default=48.0 ("Munich ~48")`; datum 판정(ground≈514 ortho vs +48 ellip);
  **orthometric → `H_ortho + geoid(48) − 604 = H_ortho − 556`**.
- `seed_bands_meta.json`: `{"datum":"ortho","geoid":48.0,"shift_z":604.0}`.
- 다수 GS run `versions.txt`: `datum: …−604; acmp seed **−556 (geoid)**`; `labels: clean_labels_geoidfix (geoid-corrected, shift_z=556)`.
→ **파이프라인의 3D/깊이/seed 경로는 −556(지오이드 반영)으로 이미 정확.** 누락된 곳은 **내가 새로 만든 이미지-투영 스크립트**(P0 투영 유틸 기반, geoid 미적용).

## 3. 정확값 — 두 원론값, ~2 m 불확실(눈대중 불가)

- **파이프라인 파라미터 48.0 m**("Munich ~48", GS-LOCAL 전반 사용) — **일관성상 채택 권장**(shift −556).
- **GCG2016 파일 45.7 m**(`de_bkg_gcg2016.tif` AOI lon/lat 11.57/48.15 직접판독; 공식 준지오이드).
- 차이 ~2.3 m 원인(2차): GCG2016 격자보간(0.0125°×0.0083°=코스)·파이프라인 반올림·GPS고도 bias·WGS84↔ETRS89 타원체고 실현차·**per-building LoD2 지붕고 오차**(~1–2 m).
- **⚠ 이 ~2 m는 오버레이 눈대중으로 결정 불가**(near-nadir 무감·오블리크선 LoD2 모델오차와 혼재). 서브미터 필요시 **ALS↔포즈 최소자승 정합**으로 산출(눈대중 금지).

## 4. 영향 (투영-기반 산출; near-nadir 경미·off-nadir 대)

- **projection-gate**: 철회됨(near-nadir 중심뷰만 측정 → Z오차 은폐 → 거짓 0.058 m 합격). 근본원인 = 본 건.
- **evidence-cards-v2**: 카드뷰 중앙 68°(오블리크) → 사진패널·지붕마스크 대량 오정합("off-roof 9동"의 상당수 = 이 Z오차).
- **lowtex_v4(199)**: near-nadir 동 ~경미·off-nadir/nn0 동 잘못픽셀 샘플링.
- **population_aux_v3 관측기하**: 입사/시차각이 카메라(ellip)–표본(ortho) Z 불일치로 계산 → 부분 오차.

## 5. 결론·권고 (판정=김휘영)

1. **근본원인 확정**: 이미지-투영 경로의 **지오이드 누락**(정사고 입력에 −604 오적용). 순수 상수 수직오프셋 ~48 m. 눈대중/추정 아님 — 파이프라인 문서·GCG2016으로 원론 확인.
2. **수정(원론적)**: 공유 투영에서 **정사고 입력 Z에 지오이드 ζ 추가**(= shift −556). ζ = 파이프라인 규약 **48.0**(GS 일관) 또는 GCG2016 **45.7**(공식). ~2 m 잔차는 2차요인, 서브미터는 LS 정합.
3. **재검증 필요**: fix 적용 후 projection-gate(전각도 ~0 확인)·evidence-cards-v2·lowtex_v4·population_aux_v3 재실행.
4. **여기서 실험 중지**(김휘영 지시). 다음 = fix 적용·재실행 범위 = 김휘영 결정.

> 재현: `docker run … jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/zmultiview.py 4906972` 등. 진단만·재구성 없음.
