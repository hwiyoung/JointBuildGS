# RETRACTED — dense baseline qualitative v1 사진 투영 행

> 공지 상태: 회수 확정
> 대상 run: `20260728_fusion_w1_dense_baseline_qualitative_v1`
> 기록일: 2026-07-28
> 산출물 보존: 삭제·수정·덮어쓰기 금지

## 회수 범위

이 run의 `manifest.json`에는 패널 9개와 패널당 3개씩 총 **27개 photo receipt**가 기록돼 있다.
각 receipt는 DIM class 6 점의 단일 `locator_z_m`에 승인 GroundSurface XY를 평평하게 올린
사진 투영을 포함하며, source provenance에는 역사 재현용
`phases/p0-audit/scripts/07_failure_diagnosis.py`가 직접 기록돼 있다.

따라서 아래 표현은 정성·정량 근거로 **사용 금지**한다.

- `panels/*.png` 첫 번째 사진-풋프린트 행
- `dense_baseline_qualitative_v1.pdf` 각 페이지의 동일 행
- `overview.png`에 축소 포함된 동일 행
- `manifest.json`의 `photo_receipts`를 이용한 지붕 경계 또는 영상 정합 주장

이 행의 선은 실제 3D 지붕 경계가 아니며, 영상과 DIM/카메라의 독립 정합 검증값도 아니다.
선정 CSV·selection audit와 나머지 3D 행은 역사 산출물로만 보존하며, 이 공지는 해당 값의
재계산이나 과학적 판정을 수행하지 않는다.

## 대체 경로

활성 대체판은 별도 namespace의 v2 구현이다.

- config: `phases/p2-gsjso/configs/fusion_w1_dense_baseline_qualitative_v2_20260728.json`
- renderer: `phases/p2-gsjso/scripts/fusion_w1_dense_baseline_qualitative_v2_20260728.py`
- 검증 output: `phases/p2-gsjso/runs/20260728_fusion_w1_dense_baseline_qualitative_v2/`

v2는 실제 DIM/MVS class 6 XYZ로 만든 필터 TIN의 incidence-one support edge를 사용하고,
수직 datum을 명시하는 공용 projector를 사용한다. 또한 corrected `cameras.bin`과 같은
1400×1013 COLMAP-bound 이미지만 허용한다. v2 `manifest.json`은 `state=COMPLETE`, 패널 9개,
출력 13개와 `output_set_sha256=d6850ae48a2142242143ae3ee0d95041752051b17513d5208cf968245329ab90`을
기록했고 별도 `verify`가 이를 재검증했다.
