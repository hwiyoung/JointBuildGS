# MVS refinement의 수치 개선과 정성적 잔여 문제

`PHD-GEOGS-MVS-PGSR-v1` · 2026-09-15 · `scientific_verdict: null`

대상은 P1/P2, prior 0.005, native 보호, 동일 Anchor8k에서 30k까지 진행한
MVS-only/MVS+PGSR 네 실행이다. 아래는 기존 코드·loader 기록·trace·동일 조건
단면을 읽은 개발 진단이다. 새 학습, 표면 추출, threshold 선택은 하지 않았다.
MVS 감독을 넣었다는 사실이 해당 MVS의 국소 정확도나 현재성 판단을 검증한 것은 아니다.

**감독 범위와 결손.** 실제 MVS 항은 고정 건물 ROI가 아니라 1400×1013 전체
영상에서 유효한 depth 픽셀의 평균 절대오차다. 호출에 ROI mask가 없으며,
`finite(target) & finite(prediction) & target>0`을 사용한다. confidence weighting,
scale alignment, hole filling은 꺼져 있다. 따라서 관심 지붕·바닥을 별도로
우선하는 감독은 아니며, depth가 없는 픽셀에는 MVS 항이 적용되지 않는다.
근거: 동결 [train.py:278](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/train.py:278)의 mask/평균과
[호출부:839](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/train.py:839),
[loader 기록 생성:121](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/jbgs_mvs_pgsr.py:121).

| 영역 | Train 영상 | 전체 픽셀 기준 무효 비율 | 영상별 무효 비율 범위 |
|---|---:|---:|---:|
| P1 | 98 | 24.58% | 1.84–61.93% |
| P2 | 57 | 29.80% | 1.26–77.01% |

각 `mvs_depth_loaded.json`의 `rows`에서 전체 무효 비율은
`1 - sum(valid_pixels) / sum(pixels)`, 영상별 비율은
`1 - valid_pixels / pixels`로 계산했다. 네 실행을 확인했으며 같은 영역의
MVS-only/PGSR 값은 동일하다. evaluation depth load는 0개다.
[P1 loader 원본](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P1/mvs_0.005/attempt.lQtLPxeE/model/mvs_depth_loaded.json),
[P2 loader 원본](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P2/mvs_0.005/attempt.8Te3xw1C/model/mvs_depth_loaded.json).
**이 수치는 전체 영상의 결손이며, 관심 지붕·바닥 ROI의 결손율은 미확인이다.**

**prior와 보호의 지속.** 실제 `training_lod.txt`에는 prior 0.005,
XYZ gradient scale 0.01, rotation/scale gradient scale 0.01,
`Freeze only building: True`, `Gaussian completion enabled: False`가 기록되어 있다.
보호 Gaussian은 split/clone/prune 대상에서도 제외된다. 비보호 Gaussian의
densify/prune는 15k 미만에서만 가능하며, trace에서 14,900 이후 개수가 유지된다.
opacity는 이 geometry gradient hook의 대상이 아니어서 감소할 수 있다.
이는 기존 구조의 삭제·변형을 제한하는 실제 조건이다. 다만 optimizer가 Adam이므로
**gradient ×0.01을 실제 이동량 ×0.01로 해석할 수는 없다.**
[실행 요약](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P1/mvs_0.005/attempt.lQtLPxeE/model/training_lod.txt),
[gradient hook:603](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/train.py:603),
[densify 조건:1083](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/train.py:1083),
[보호 대상 제외:397](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/scene/gaussian_model.py:397),
[Adam 설정:165](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/scene/gaussian_model.py:165).

**후반 손실의 실제 크기.** 각 `mvs_pgsr_trace.jsonl`에서
`20000 <= iteration <= 30000`인 101개 기록을 선택하고, 각 기록의
`prior_loss * prior_weight`, `mvs_loss * mvs_weight`를 먼저 계산한 뒤 각각의
중앙값을 구했다. 전체 iteration 평균이나 두 중앙값의 곱이 아니다.
고정 Docker runtime의 CPU에서 원본을 읽었으며, 아래 링크가 네 실행의 trace다.

| 영역·실행 원본 | Weighted prior 중앙값 | Weighted MVS 중앙값 | 후반 MVS weight |
|---|---:|---:|---:|
| [P1 MVS-only](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P1/mvs_0.005/attempt.lQtLPxeE/model/mvs_pgsr_trace.jsonl) | 0.06814 | 0.04835 | 0.0475 |
| [P1 MVS+PGSR](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P1/mvs_pgsr_0.005/attempt.zns2OSUG/model/mvs_pgsr_trace.jsonl) | 0.07672 | 0.04683 | 0.0475 |
| [P2 MVS-only](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P2/mvs_0.005/attempt.8Te3xw1C/model/mvs_pgsr_trace.jsonl) | 0.02737 | 0.09308 | 0.0500 |
| [P2 MVS+PGSR](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P2/mvs_pgsr_0.005/attempt.GtMb91C1/model/mvs_pgsr_trace.jsonl) | 0.02653 | 0.09206 | 0.0500 |

P1에서 prior 항은 손실값 기준으로도 사라지지 않았다. 그러나 이 표는
**scalar loss의 크기이며 gradient 우위·실제 이동량·원인 지배력의 증거가 아니다.**
각 항의 유효 픽셀 모집단도 다르다. 기록 생성은
[adapter:200](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/jbgs_mvs_pgsr.py:200),
실제 합산은 [train.py:988](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/train.py:988)에 있다.

**관측과 해석.** 감독 대상은 Gaussian XYZ와 MVS XYZ의 직접 대응이 아니라,
여러 Gaussian이 미분 가능 렌더링으로 합성한 expected camera-Z depth다.
위치·크기·opacity의 여러 조합이 같은 depth를 만들 수 있으므로 이 목표만으로
단일 표면이나 낡은 상부층 삭제를 식별하지는 못한다.
[expected-depth 구현:143](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1/gaussian_renderer/__init__.py:143).

실제 [P1 동일 조건 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/matched_comparison_v1/attempt.uWs3ytqy/regions/P1/sections.png)에서는
MVS 계열의 Z≈−42m 바닥 표면이 늘었지만 Z≈−37~−39m 상부 잔여층도 남았다.
이는 관측이다. 전체영상 평균 감독, prior 유지, 보호·삭제 제한,
expected-depth의 비유일성이 이 잔여 문제에 기여했다는 설명은 **가설**이며,
이 요인들을 각각 바꾼 비교로 원인을 분리하지는 않았다.

기하 recall은 UAS 점에서 가장 가까운 예측 삼각형까지의 거리로 계산한다.
따라서 올바른 바닥이 추가되면 잘못된 지붕을 남겨도 recall이 좋아질 수 있다.
상부 잔여층은 반대 방향의 precision에서 불이익을 받지만, 올바른 표면이 늘면
그 비율도 함께 개선될 수 있다. **관측 reference와의 근접성·지원 개선은 실제
개선이지만, stale 구조 삭제와 단일층·연결성·roof topology 정리는 별도 결과다.**
[지표 정의:204](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_p1p2p3_v1/evaluation/geometry.py:204),
[동일 조건 결과 문서](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_mvs_pgsr_v1/MATCHED_RETURN_ko_v1.md).
