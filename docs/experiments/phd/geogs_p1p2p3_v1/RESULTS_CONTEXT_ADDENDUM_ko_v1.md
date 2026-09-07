# 기존 native 30k를 포함한 Anchor 생략 결과의 해석

2026-09-10 · `SUPPLEMENTARY_PREFIX_DIAGNOSTIC` · `scientific_verdict: null`

**SfM 8k가 기존 Anchor 8k보다 낮다는 사실만으로 Anchor의 필요성을 입증할 수 없다.** P1/P3에서는 Anchor를 실제로 수행한 기존 경로도 뒤의 refinement를 거치면서 0.5m raw 표면 F1이 낮아졌다. 따라서 기존 최종 결과를 포함해 읽어야 한다. 아래 기존 native 30k는 이 실험의 ALS 적용 `D005_Pnative`이며, 논문의 원 LoD2 입력 실험을 뜻하지 않는다.

| 지역 | 기존 ALS Anchor 8k | 역사적 SfM no-Anchor 8k | 기존 native 전체 30k — **CONTEXT** |
|---|---:|---:|---:|
| P1 | 0.640809 | 0.483900 | 0.499435 |
| P2 | 0.465087 | 0.377779 | 0.534577 |
| P3 | 0.701764 | 0.554260 | 0.588058 |

값은 각 지역의 동일 고정 ROI, raw TSDF512, 표면 표본 0.1m/UAS voxel 0.1m에서 측정한 **거리 <0.5m의 F1**이다. 예측 표면→관측 UAS의 precision과 관측 UAS→예측 삼각형의 recall을 결합한다. 후처리 post, 1024 추출 또는 다른 threshold를 섞지 않았다. 기존 30k는 `Anchor 8000 + refinement 22000`, 신규 8k는 `SfM 초기화 + refinement 8000`이므로 최종 열의 처리량은 같지 않다.

P1은 기존 Anchor 0.640809가 기존 native 최종에서 0.499435로, P3은 0.701764가 0.588058로 낮아졌다. **Anchor를 유지한 경로에서도 이 감소가 발생했다.** SfM 8k의 0.483900/0.554260과 비교할 때, 높은 Anchor 중간 상태만을 기준으로 손실 전체를 “Anchor 생략 때문”이라고 귀속할 수 없다. 이 수치만으로 기존 refinement의 어떤 loss·보호·일정이 감소를 만들었는지도 분리하지 못한다.

P2는 기존 Anchor 0.465087에서 native 30k 0.534577로 높아졌고, SfM 8k는 0.377779였다. 세 지역 모두 이 지표에서 SfM 8k가 기존 native 30k보다 낮지만, **서로 다른 업데이트 수를 비교한 결과이므로 동등 예산의 최종 성능 차이 또는 수렴 한계로 해석하지 않는다.** P1/P3에서 두 값이 가까워 보이는 것도 동등성이나 실용적 충분성의 판정은 아니다.

사용자의 “기존 전체 vanilla 경로 대신 Anchor 없이도 충분한가”라는 질문에는, 현재 다음까지 답할 수 있다. Anchor 없는 경로에서도 외관 개선과 일부 국소 구조 보완은 실제로 생겼지만, 고정 8k 진단만으로 전체 경로의 대체 충분성은 확인되지 않았다. 반대로 Anchor 8k 대비 표면 F1 감소만으로 Anchor가 반드시 필요하다는 결론도 성립하지 않는다. 초기화·감독 단계·일정·보호 멤버십의 동시 변화와 원 22k/30k 실행의 완료 여부를 함께 유지해야 한다. 다른 거리 임계값·raw/post·RGB·국소 보존과 손실은 [본 결과 문서][main]의 근거를 함께 읽는다. 이 부록은 추가 학습이나 설정 선택을 제안하지 않는다.

## 원자료와 보존

기존 완료된 `geometry_comparison.csv`의 `sensitivity=sample0.1_reference0.1`, `threshold_m=0.5`, `candidate`가 `.raw`로 끝나는 행만 읽었다. 후보는 `D005_Pnative.anchor_512.raw`, `SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.raw`, `D005_Pnative.mesh_512.raw`다. 마지막 후보의 원 `comparison_role`은 `CONTEXT_DIFFERENT_30000_BUDGET`이다. 새 scoring·표면 계산·학습·테스트는 수행하지 않았다. CSV 읽기는 Docker CPU 2개/RAM 2GiB/네트워크 없음/GPU 없음에서 실행했다.

| 실제 비교 CSV | SHA256 |
|---|---|
| [P1 geometry_comparison.csv][p1] | `b75ae2054418e145b5b5ec4ae54019f2e09f351af9381419c9ded8c1d75d121b` |
| [P2 geometry_comparison.csv][p2] | `fcc34f978a4c355517669dabb5e2b072b201c54855aec76c004669deb89bc40a` |
| [P3 geometry_comparison.csv][p3] | `9529d90f4715ca7f9054b3f68a58fa50fa6240741e6eabd8bc8177c0038e17a9` |

본 결과 문서와 모든 기존 측정값은 변경하지 않았다. 이 부록이 보완하는 본문 SHA256은 `f6480611976aec11eed0906f30d49d7d1433fcbfbb00d2dfe1d6798b30905491`이다. 표는 표시 자릿수로만 반올림했으며 원 CSV가 전체 정밀도를 소유한다. `scientific_verdict: null`을 유지한다.

[main]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_PREFIX8000_RESULTS_ko_v1.md
[p1]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P1/R8000/geometry_comparison.csv
[p2]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P2/R8000/geometry_comparison.csv
[p3]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P3/R8000/geometry_comparison.csv
