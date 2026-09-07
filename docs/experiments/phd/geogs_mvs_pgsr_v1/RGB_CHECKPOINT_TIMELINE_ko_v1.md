# 저장 체크포인트로 확인한 RGB 형성 경과

2026-09-15 · `PHD-GEOGS-RGB-CHECKPOINT-TIMELINE-v1` · `scientific_verdict: null`

## 결과

기존 P1/P2/P3의 DA3·MVS × prior .005/.0005, 12개 본 실험의 저장 상태와 로그를 조사했다. P1의 기존 고정 학습뷰 `P1_train_1`에서 공통 Anchor8k, DA3 두 가중치의 8.1k·30k, MVS 두 가중치의 30k를 같은 카메라로 렌더했다. **새 학습/optimizer update 0회**, 성공 실행 182.355초, `PASS_SAVED_CHECKPOINT_TIMELINE`이다. PGSR 조건의 시간별 분석은 이번 범위에 포함하지 않았다.

이 P1 영역의 바닥 줄눈·작은 물체·지붕 경계는 **8k에서도 이미 흐리다**. 최종 30k에서 .005는 세부를 더 복원하고 .0005는 상대적으로 덜 복원한다. 모든 최종 ROI SSIM은 8k보다 높으므로, 전체 경과를 ‘선명한 질감이 먼저 형성됐다가 refine에서 파괴됐다’고 설명할 증거는 없다. 다만 작은 물체 등 일부 세부가 이후 약해질 수 있으며, 저장되지 않은 시점에서 잠시 더 좋았을 가능성을 배제하지 않는다. 8k는 중간 상태이므로 그때의 흐림 자체가 최종 실패의 원인을 증명하지도 않는다.

| 저장 상태 | Gaussian 총수 | ROI SSIM | 큰 비보호 Gaussian 기여¹ | 큰 보호 Gaussian 기여¹ |
|---|---:|---:|---:|---:|
| 공통 Anchor8k | 1,136,384 | .4179 | 2.50% | .074% |
| DA3 .005 / 8.1k | 1,125,327 | .4149 | 2.70% | 3.30% |
| DA3 .0005 / 8.1k | 1,125,394 | .3977 | 3.73% | 10.04% |
| DA3 .005 / 30k | 6,033,926 | .6844 | 17.60% | 5.51% |
| DA3 .0005 / 30k | 5,714,579 | .5281 | 49.17% | 6.36% |
| MVS .005 / 30k | 2,026,814 | .6748 | 27.14% | 7.78% |
| MVS .0005 / 30k | 1,897,116 | .5017 | 62.39% | 5.84% |

¹ ‘큰’은 native rasterizer의 투영 AABB 반경 >100px이다. Gaussian 수의 비율이 아니라 alpha≥.95인 ROI 픽셀에서 전체 alpha 합성 가중치로 나눈 집단 기여의 평균이다. 상태별 해당 픽셀 집합은 다르며, 전체 ROI의 비정규화 기여 평균에서도 같은 경향이다. MVS .0005의 전체 ROI 평균은 큰 비보호 .6044, 큰 보호 .0846, 합 .6889이고, .005는 각각 .2731, .0730, .3461이다.

약한 prior의 최종 흐린 화면을 주로 담당하는 집단은 **보호 대상이 아닌 큰 Gaussian**이다. 보호된 Anchor가 화면 대부분을 덮었다는 설명은 이 사례에 맞지 않는다. 비보호에는 8k 이전부터 존재한 Gaussian과 그 이후의 복제·분할 후손이 모두 포함되므로 생성 시점을 의미하지 않는다. 보호 여부의 기여 분석만으로 보호 정책의 간접 영향을 배제하지 않는다.

8k에는 >100px 집단의 전체 ROI 기여가 약 2.6%인데도 흐리다. 따라서 이 임계값 하나로 초기 흐림까지 설명하지 않는다. 8k→8.1k의 보호 집단 기여 변화 역시 위치·회전·크기·가림·임계값 통과의 영향을 모두 받으므로 개별 Gaussian의 물리적 scale 증가로 단정하지 않는다. 앞선 [기여/제외 진단](RGB_RADIUS_PROBE_ko_v1.md)과 [색상/gradient 진단](RGB_COLOR_FIT_PROBE_ko_v1.md)을 합쳐도, 세부 배치·크기·분할이 충분히 형성되지 않은 학습 중 원천 원인은 아직 미확정이다.

## 역추적 가능한 범위

| 자료 | 실제 남은 기록 | 가능한 분석 |
|---|---|---|
| 공통 Anchor | P1/P2/P3의 정확한 8k checkpoint+PLY | 시작 상태의 위치·크기·회전·opacity·SH·보호 마스크·동일 카메라 RGB |
| DA3 본 실험 | 양쪽 가중치 모두 8.1k와 30k; 공통 8k 별도 존재 | 저장 시점 사이의 분포·화면 기여 변화 |
| MVS 본 실험 | 공통 8k 입력과 본 실험 최종 30k | 시작/끝 상태 비교; 본 실험 8.1k/10k/15k 형상은 저장되지 않음 |
| 본 실험 trace | 100 step 간격 총 Gaussian/보호 수, RGB·기하 손실/가중치, 카메라 등 | 전역 개수의 순증감과 손실 경과; 지역별 세부 형성·소멸은 직접 복원 불가 |
| 생성·분할·삭제 이력 | 지속 ID·parent ID·birth step·개별 이벤트 없음 | 최종 행 번호를 과거 Gaussian ID로 취급할 수 없음 |

별도 MVS preflight의 8.1k는 본 실험의 실제 중간 저장본이 아니므로 이어 붙이지 않았다. 초기 seed PLY도 완전한 iteration0 Gaussian 상태는 아니다. P1의 이전 중단 run에서 8k 이후 로그를 현재 allocator run의 이력처럼 붙이지 않았다.

총수는 모두 15k 이후 일정하지만 전역 총수만으로 해당 바닥의 세부 Gaussian 형성 여부를 판단할 수 없다. P1 MVS .0005의 기록은 8.1k 1,147,527 → 10k 847,364 → 12k 1,532,080 → 15k 1,897,116이다. 이는 순증감이며 clone/split/prune별 횟수가 아니다. 현재 코드는 분할/복제에서 행을 추가하고 삭제에서 압축하므로 일반 Gaussian의 행 번호 대응은 유효하지 않다.

저장 상태만으로 가능한 분석을 먼저 수행하는 데 30k 재학습은 필요 없다. 저장되지 않은 시점의 개별 생성·분할·삭제 사건까지 확인하려면 필요한 구간만 별도로 재실행하고 기록해야 한다. 그 재실행은 과거 이력을 그대로 복구한 결과가 아니며, 이번에는 수행하지 않았다.

## 절차와 검증

- 기존 진단에서 정한 사진 `DJI_20241217084553_0100_D.JPG`, bbox `[602,259,1258,915]`와 정확한 K/R/t를 사용했다. 영역을 결과에 맞춰 다시 선택하지 않았다.
- 각 저장본의 receipt SHA를 확인하고, 자체 checkpoint와 자체 PLY의 XYZ·DC/고차 SH·scale·rotation·opacity **모든 tensor 값의 동일성**을 검사한 뒤 그 checkpoint의 보호 마스크를 적용했다. 서로 다른 시점의 행을 대응시킨 분석은 아니다.
- 저장 active SH degree=3과 동일 rasterizer를 사용했다. 집단 지시 색상으로 alpha 합성 기여를 측정했으며 opacity·정렬·alpha는 유지됐다. 기여의 부분집합 관계와 alpha 대비 범위를 검사했다.
- 최종 네 상태의 재렌더는 기존 저장 PNG와 최대 1/255 차이였다. 7개 상태의 RGB·기여 배열·지표와 원 사진을 함께 보존했다.
- 원본 source·checkpoint·입력은 read-only mount이고 optimizer를 복원하거나 실행하지 않았다. Docker image ID·PyTorch 버전·Git HEAD·실행 명령·GPU 전후 상태·스크립트/config snapshot 및 SHA는 attempt에 있다.
- 첫 `attempt.xzJqH7Ws`는 PyTorch2.1 `mmap=True`에 `Path`를 넘겨 첫 로드에서 실패했다. 실패 자료를 보존하고 문자열 경로로 수정한 새 `attempt.35V1kE74`에서 통과했다. 실패 시점에도 새 학습은 없었다.

## 산출물

- [같은 카메라의 저장 상태 비교 이미지](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_checkpoint_timeline_v1/attempt.35V1kE74/timeline.png)
- [receipt.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_checkpoint_timeline_v1/attempt.35V1kE74/receipt.json), SHA256 `b19538e22c71f41f6339b1727f6f1f09fecfe50cd8e1f1c0ba3201c99fbf2a6b`
- [inventory.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_checkpoint_timeline_v1/attempt.35V1kE74/inventory.json)
- [실행 스크립트](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_mvs_pgsr_v1/rgb_checkpoint_timeline.py), [config](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/geogs_mvs_pgsr_v1/rgb_checkpoint_timeline_v1.json)

P1 한 학습뷰의 기술 진단이며 다른 ROI·평가뷰·P2/P3·PGSR에 일반화하거나 논문 수준 재현 여부를 판정하지 않는다.
