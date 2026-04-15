# Legacy: PlanarSplatting Reference

이 디렉토리는 PlanarSplatting 예비 실험의 핵심 코드를 참고용으로 보존합니다.
전체 PlanarSplatting 리포지터리: `/media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting`

## 포함 파일

| 파일 | 원본 경로 | 참고 용도 |
|------|----------|----------|
| `planarsplat_ref/loss_util.py` | `planarsplat/utils/loss_util.py` | L_mutual, L_sem 구현 |
| `planarsplat_ref/trainer.py` | `planarsplat/run/trainer.py` | 학습 루프, warmup, gradient check |
| `planarsplat_ref/net_planarSplatting.py` | `planarsplat/net/net_planarSplatting.py` | Semantic head 구조 |
| `planarsplat_ref/building_to_citygml_v4.py` | `scripts/building_to_citygml_v4.py` | Stage 3 원본 (분리 전) |
| `planarsplat_ref/build_2_5d.py` | `scripts/build_2_5d.py` | 2.5D solid 대안 |
| `planarsplat_ref/generate_segmentation.py` | `scripts/generate_segmentation.py` | Grounded SAM + depth 하이브리드 |

## 예비 실험 결과 요약

- L_mutual 효과 (Synthetic B): Clean wall normal 8.9 -> 3.8 deg, Noisy 9.0 -> 4.3 deg
- 항공 밀착 실패: coverage 6-26% -> gsplat 변경 근거
- 법선 지배성 (Synthetic A): normal 20 deg -> val3dity -53%p
- 성수동: mIoU=0.81, 11 instance
