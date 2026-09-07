# SfM 초기화에서 Anchor 없이 refinement하는 대체 경로

2026-09-10 · `PHD-GEOGS-SFM-NO-ANCHOR-v1` · **주 비교 자원 실패 / 별도8k 비교 완료** · `scientific_verdict: null`

SfM 초기 Gaussian에서 Anchor를 생략한 경로를 실제 실행했지만, **기존 전체 GeoGS를 대체할 수 있다는 판단은 아직 할 수 없다.** 세 지역의 고정 마지막 재시도는 모두 CUDA OOM으로 닫혀22k/30k의 완전한 비교 상태가 없다. 별도로 완료한 세 지역의 역사적8k 비교에서는 Anchor8k보다 사진 렌더 품질이 높고 F1@0.5m은 낮았다. 이것을 완주한 기존30k와의 동등성이나 Anchor 생략의 단일 인과 효과로 해석하지 않는다. 아래는 실행 실패와 실제 측정 결과를 함께 보존한 부분 결과 보고다.

## 질문과 실제 비교 조건

사용자의 질문은 “SfM 초기 Gaussian에서 Anchor를 생략하고 바로 refinement해도 기존 전체 GeoGS 경로를 대체할 수 있는가”다. 실제 SfM 점으로 새 optimizer를 시작하고, 첫 update부터 refinement를 적용했다. ALS Gaussian을 초기화에 삽입하지 않았지만 ALS depth 계수0.005와 native 구조 보호는 유지했다. 보호 집합은 첫 optimization 전에 초기 SfM 중 ALS 표본에 가까운 Gaussian으로 등록했다. LR·SH·normal·densification 일정은 global iteration1에서 시작한다.

동일 연속30k 궤적의22k는 기존 refinement 횟수와,30k는 기존 전체 횟수와 맞춘다. 초기화·감독 단계·일정 위치·보호 멤버십을 함께 바꾼 대체 경로이며, 순수 Anchor 단일 요인 ablation 또는 image-only가 아니다. 고정 입력·seed·카메라·평가 범위·공식 TSDF512 raw/post·표면 표본화 조건은 [사전 계획][plan]과 실제 config가 소유한다. UAS는 평가 전용이고, 역사적 전체 영상 SfM 전처리의 영향 때문에 pristine held-out 확증 결과로 해석하지 않는다.

## 현재 실제 산출물

| 지역 | 마지막 자원 재시도 | 새22k/30k | 별도 고정 historical8k |
|---|---|---|---|
| P1 |10,608회 완료 후10,609회 backward CUDA OOM | 생성 실패 | 공식 RGB·TSDF512·정량/정성·viewer 완료 |
| P2 |22,000번째 optimizer update 뒤 정기 평가 렌더 CUDA OOM; 마지막 전체 iteration 경계21,999 | 저장 전 실패, 생성 실패 | 공식 RGB·TSDF512·정량/정성·viewer 완료 |
| P3 |8,541회 완료 후8,542회 backward CUDA OOM | 생성 실패 | 공식 RGB·TSDF512·정량/정성·viewer 완료 |

역사적8k는 실패한 이전 storage-v2 시도에서 사전 고정한 완전 상태다. 마지막 재시도의8k로 교체하지 않았다. 실패한22k/30k 칸을0점으로 채우거나8k로 대신하지 않는다. 현재 실행 근거는 [인계의 현재 절][handoff], 실패 원문·runtime 변경은 [실행 기록][execution]에 있다.

[실제8k 비교 뷰어][prefix-viewer]는③ 기존 ALS Anchor8000과⑤ SfM no-Anchor8000을 비교한다.④ 기존 전체30000은 다른 학습량의 문맥용이다.208개 browser 검사에서 새 raw/post 메시6개와 RGB 갤러리3개의 실제 표시를 확인했다. 과학적 성능 PASS를 뜻하지 않는다.

## 완료된8k가 보여주는 것과 보여주지 못하는 것

| 지역 | raw 표면 F1@0.5m: Anchor8k → SfM8k | 사진 ROI PSNR: Anchor8k → SfM8k |
|---|---:|---:|
| P1 |0.640809 →0.483900 |14.5845 →17.1127dB |
| P2 |0.465087 →0.377779 |13.7391 →14.8572dB |
| P3 |0.701764 →0.554260 |15.3667 →19.1870dB |

세 지역의 평균 RGB 개선과 엄격한 표면 근접도 감소가 함께 나타났다. P2에서는1m/2m의 F1은 높아졌지만 해당 recall은 낮아져, 큰 편차의 예측 성분 감소와 관측 표면 피복의 개선을 구별해야 한다. 고정 단면에서 일부 부유 성분 감소와 곡면 추종 손실을 함께 확인했다. P3에서는 일부 외벽 보완과 지붕 아래 추출 성분의 증가가 함께 보였다. 동일 참조점의 근접도 전이는 시간적 유효/낡은 자산 분류가 아니다. 정확한 raw/post·임계값·표본화 민감도·사진별 값·단면·거리 지도는 [완료된8k 결과][prefix-results]가 소유한다.

또한 P1/P3의 **기존 Anchor 수행 경로도** refinement 후 F1@0.5m이 각각0.640809→0.499435,0.701764→0.588058로 낮아졌다. Anchor 중간 상태만을 기준으로 새8k의 손실 전체를 Anchor 생략 탓으로 귀속할 수 없다. 기존30k와 새8k의 비슷한 수치를 동등성으로 해석할 수도 없다. 이 비교의 동일512 근거와 역할은 [30k 문맥 보완][context]에 명시했다.

아래는 주 비교에 사전 지정된 **기존30k 조건의 실제 값**이다. 새8k와는 학습량이 다른 문맥이고, 새22k/30k 결과가 아니다. 기존 두 조건끼리는 같은 Anchor 이후 깊이 계수만0.005→0.0005로 낮춘 비교다. 보호는 유지했다. 특히 기존 native30k의 ROI PSNR/SSIM은 세 지역 모두 새8k보다 높아, 앞 표의 Anchor 대비 RGB 개선을 기존 전체 방법에 대한 우위로 옮겨 해석할 수 없다.

| 지역 | 기존30k 조건 | raw F1@0.5m | ROI PSNR(dB) | ROI SSIM | ROI LPIPS signed |
|---|---|---:|---:|---:|---:|
| P1 | 원설정 D005_Pnative |0.499435 |19.1807 |0.6987 |0.3460 |
| P1 | 깊이 완화 D0005_Pnative |0.375917 |23.2129 |0.7971 |0.2720 |
| P2 | 원설정 D005_Pnative |0.534577 |16.4402 |0.4466 |0.5252 |
| P2 | 깊이 완화 D0005_Pnative |0.459758 |21.9023 |0.7099 |0.3258 |
| P3 | 원설정 D005_Pnative |0.588058 |21.2664 |0.7026 |0.3610 |
| P3 | 깊이 완화 D0005_Pnative |0.625704 |22.7495 |0.7479 |0.3350 |

이 표도 하나의 지표로 전체 개선을 판정하지 않는다. 예를 들어 깊이 완화의 F1@0.5m 변화는 P1/P2에서 하락하고 P3에서 상승했다. [기하 원 CSV][baseline-geometry] SHA는 `42a0576a20a25a57dcd59161de5d3b5df8a9fdbef3380115f165b8cd67b0b48a`, [RGB 원 CSV][baseline-rgb] SHA는 `2fbac52479548f0a25185301f1ab7786053c7fe8bd780bfb63df2790f46489bb`다. 기하는 `.mesh_512.raw`, `sample0.1_reference0.1`, threshold0.5m 행이고 RGB는 `stage=final`, `domain=fixed_prism_projected_bbox`의 지역별 사진 단순 평균이다. Docker CPU1/RAM512MiB/네트워크·GPU 없음에서 기존 CSV만 읽었다. 새 측정이나 품질에 따른 설정 선택은 하지 않았다.

## 원문에도 초기화 제거 ablation은 있다

확보한 [GeoGS 전문][paper]의 §5.4, PDF p15/인쇄 p198, Table6 PartB에는 `w/o LoD Initialization`이 있다. 아래는 **논문 Region1, K=13의 보고값**이며 이번 P1/P2/P3 측정치가 아니다.

| 논문 조건 | PSNR | SSIM | LPIPS | Mesh M3C2(m) | F1@0.2m | F1@0.5m |
|---|---:|---:|---:|---:|---:|---:|
| Vanilla2DGS |14.001 |0.468 |0.285 |0.411 |0.463 |0.713 |
| w/o LoD Initialization |15.879 |0.509 |0.267 |0.389 |0.457 |0.782 |
| Full GeoGS |16.654 |0.527 |0.266 |0.378 |0.469 |0.788 |

초기화 제거 조건의 F1@0.5m은 Full보다0.006 낮다. 초기화 제거의 평가 자체를 미연구 문제로 주장할 수 없다. 그러나 해당 PartB에 대체 초기점 선별·stage0 설정·첫 step 보호 등록 명령이 명시돼 있지 않으며, 독립적인 `w/o Anchoring Stage` 행도 없다. 그 행을 이번 SfM→즉시 refinement 조건과 동일하게 취급하지 않는다.

Table6 PartA는3DGS/2DGS/PGSR의 SfM 초기화를 같은 LoD 표본으로 교체하고 각 방법의 architecture·loss·hyperparameter를 유지한 별도 실험이다(§4.3, PDF p9/인쇄 p192). 여기서는 LoD 초기화만으로2DGS/PGSR의 기하가 개선되지 않았다. 논문의 저자는 전체 GeoGS의 개선을 초기화 하나로 설명할 수 없다고 해석한다. 이는 초기화·감독·보호·refinement를 구분해야 한다는 근거이지 이번 경로의 우열을 대신하는 증거가 아니다.

사용자 PDF SHA256은 `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`다. 이번 재확인은 기존 추출 전문 `/tmp/jbgs-geogs-attached-fulltext-20260907.txt` SHA`26c5ba1f743803ca16cf03953a58c57c23e70e8c5fc171b5a07285bba8a577f2`와 p15 이미지 SHA`fa66cf6a662dfc34552bd2af9eda3395dd3a5199fe0820e25914eefa2c26c624`를 직접 대조했다. 기존 Docker 이미지의 PDF 도구 부재로 재추출 시도는 실패했고 원 PDF를 새로 추출했다고 기록하지 않는다. 원문 확보와 기본 방법의 전체 감사는 [PAPER_AUDIT][paper-audit]에 있다.

## 마지막 P2 실패와 실행 가능성의 한계

P2의 마지막 native receipt는 `FAIL`, native/validated exit1, driver13,834.020003초(약3시간50분)다. 마지막 일반 trace21900의 Gaussian 수는10,334,149개, 보호1,437개다. 오류는22,000번째 optimizer update가 반환한 뒤 `training_report`의 rasterizer forward에서 발생했다. 요청11.04GiB에 당시 GPU 여유는8.62GiB였다. CPU offload로 보관하던 Adam moments가 정기 평가 때는 `GPU_READY` 상태였고, 현재 gradient도 다음 학습 forward 전까지 남는 구현이었다. 따라서 학습 중 최대 메모리만을 다룬 자원 보완이 정기 평가까지 해결했다고 볼 수 없다. 이는 소스와 lifecycle 기록으로 확인한 보관 상태이며 전체 GPU 메모리 원인의 측정 분해는 아니다.

기존 실행 순서는 `optimizer → 정기 평가 → 일반 PLY 저장 → iteration 경계 → trace → complete checkpoint·PLY·receipt`였다. 평가 실패로22k의 저장·trace가 실행되지 않았다. 최신 완전 저장은15k이며, 일부 남은 평가 PNG는 순서가 섞인 학습 평가의 부분 출력이다. 예정한 고정9장 조기 RGB preview와 갤러리는 **필수22k 상태가 없어 실행하지 않았다**.22k 결과를 얻었다고 기록하지 않으며15k나 부분 사진으로 대체하지 않는다. 해당 개발 코드와 사전 정책은 [조기 preview 기록][preview-policy]에 미실행으로 보존한다.

P1/P3는 각각 backward 중 실패했다. 세 지역 모두 추가 fresh1회 상한을 소진해 학습을 닫았다. 이 실패는 현재 구현·일정·Gaussian 수·24GiB GPU의 실행 한계를 보여준다. 기존 GeoGS 추가 반복에서도 OOM이 있었으므로 “Anchor가 없으면 항상 실패한다”거나 “Anchor가 반드시 필요하다”는 근거가 아니다. CPU moment 이동으로 인한 추가 전송 시간도 있어 실행 시간을 순수 Anchor 생략 효과로 비교할 수 없다.

P2 실패 증거는 `no_anchor_sfm_gradient_memory_v3_P2/runs/P2/SFM_noanchor_D005_Pnative/`의 `receipt.json` SHA`65ed9d68de101e693f5d2f3b3a636085286d61b6a0ef22f541af291ce05ed9af`, `native.log` SHA`175e501ff29aa6e46d5dd1c11e2bacf3125b287f7961fe451926d5060a56f462`, `model/jbgs_memory_recovery/receipt.json` SHA`8e63749ab5d480ba3692a5faadbea20717305e264ed39f10b621459518c6014b`다. supervisor와 queue의 exit1 및 native 컨테이너 종료를 확인했다. 남은 `TRAINING`/`RUNNING_FIXED_FINAL_RETRY` 문구는 과거 단계 표시이고 실행 중이라는 증거가 아니다.

## 개선점과 다음 검증 질문

1. **매끈한 외관과 현재 표면의 정확성을 함께 확인해야 한다.** P2의 고정 단면에는 큰 부유 성분 감소와 지붕 곡면 추종 손실이 함께 있다. 따라서 소스 전체를 고르는 것만으로 충분한지보다, 현재 관측이 지지하는 면의 위치·곡률을 유지하면서 잘못된 성분을 줄일 수 있는지가 후속 질문이다. 영상에 맞는 색·opacity 조정이 기하 오차를 가리는지 별도로 확인할 필요가 있다. 이 원인 가설은 현재 결과로 확정되지 않았다.
2. **회복과 손실을 같은 위치에서 분리해야 한다.** P1/P3의8k 비교는 같은 UAS 참조점에서 새로 가까워진 지지보다 잃은 지지가 많았다. 전역 F1만으로는 어느 유효 구조가 손상됐는지 알 수 없으므로 원 영상의 다중 시점 지지·단면·참조 피복을 함께 조사해야 한다. UAS 근접 전이만으로 과거 자산의 유효/낡음 라벨을 만들지 않는다.
3. **초기화·단계·보호를 분리할 인과 비교가 필요하다.** 이번 경로는 실제 SfM 초기화, Anchor 생략, 새 일정, 작은 초기 보호 집합이 함께 달라졌다. 동일 초기화에서 Anchor만 생략한 비교, 동일 단계에서 초기화만 바꾼 비교가 있어야 역할을 더 좁힐 수 있다. 이번 실패 이후 해당 조건을 추가 구현하거나 실행하지 않았다.
4. **표현의 증가와 표면 추출까지 제어 대상에 포함해야 한다.** Gaussian 수 증가, 관측이 약한 공간의 성분, TSDF raw/post의 성분 제거가 최종 복원과 실행 비용에 영향을 준다. 수를 제한하면 메모리가 줄 수 있지만 품질·밀도 제어를 바꾸는 별도 실험이다. 현재 실패를 없애기 위해 사후 cap이나 해상도 변경을 적용하지 않았다.
5. **다음 실행은 결과를 잃지 않는 평가·저장 경계를 먼저 검증해야 한다.** 완료 상태를 저장한 뒤 별도 process에서 평가하거나, 평가 전에 optimizer/gradient 보관 상태를 조정하는 방안은 운영 개선 후보다. 작은 fixture 통과를 전체 장면 완주의 증거로 삼지 말고 실제 정기 평가와 저장 최대 메모리를 검증해야 한다. 이는 연구 기여나 기하 개선을 대신하지 않는다.

현재 증거는 “무조건 Anchor를 없애자”와 “변화가 있으면 무조건 Gaussian 소스를 바꿔야 한다” 중 어느 주장도 지지하지 않는다. 후속 연구의 대상은 관측으로 확인되는 수정·유지 영역에서 회복과 손실을 함께 통제하는 것이며, 소스 판단이 실제로 필요한지와 반복 판단의 추가 효과는 별도 비교로 검증해야 한다. `scientific_verdict: null`을 유지한다.

## 결과의 완료 범위

세 지역의 실제8k 메시·렌더·정량 표·단면·참조 거리 지도와 비교 화면은 완료됐다. 주22k/30k는 세 지역 모두 자원 실패로 미제공이다. [최종 실패 상태 profile][main-viewer]은12개 미제공 후보(raw/post×22k/30k×3지역)와 원 baseline을 구별해 표시한다. 새 품질이 있는 화면은 앞의 [8k 비교 뷰어][prefix-viewer]다. 최종 발행·자원 집계·실제 표시 근거는 인계의 종료 절에 기록한다. 기존 결과·서비스·dirty 연구 문서와 E1–E6 정본은 보존했다.

최종 실패 profile의 실제 browser QA는 `PARTIAL_NO_ANCHOR_BROWSER_QA`,867검사·12스크린샷이다. 미제공12개와 실제 기존 baseline을 확인한 기술 검사이며 새22k/30k 결과가 있다는 뜻이 아니다.8k profile의208검사는 실제 새 raw/post6개와 RGB3개를 확인했다. 두 QA의 역할을 구분한다.

최종 producer 비용은 원실행·의도적 자원 구현 교체·OOM·초기화 scheduling 실패를 포함한 **서로 다른12건**이다. 원 receipt 경로+SHA를 key로 중복 없이 집계했다. 이 집합은 모두 학습 phase이며 main export는 시작되지 않았다.

| 지역 | 서로 다른 실행 수 | 합산 driver 작업시간(초) | 시간 |
|---|---:|---:|---:|
| P1 |4 |10,794.356968 |2.9984 |
| P2 |4 |24,185.330415 |6.7181 |
| P3 |4 |6,955.133649 |1.9320 |
| 합계 |12 |41,934.821031 |11.6486 |

동시 실행을 포함하므로11.65시간은 달력 경과시간이 아니다. 역사적8k의 별도 추출·평가, 입력 준비, 작은 검증, viewer·문서 작성 비용도 이 합계에서 제외했다. 원 quality0이나 성공 횟수로 해석하지 않는다. [원 phase별 CSV][cost-phases], [지역 합계 CSV][cost-totals]와 `closed_costs_v1/receipt.json` SHA`6fcb2cecdc7d50af7524cd8b7ee8a6535b224247b2ba01c589621f3cb96cadce`가 범위·원 receipt·명령을 연결한다.

원 resource v1의 보조 host-memory flag가 CUDA 오류 문자열에도 일치하던8행은 별도 `resource_flag_correction_v1/`에서 정정했다. 원인 우선 분류·비용·품질값은 변하지 않았고 이 비용 집계는 해당 flag를 쓰지 않는다. 원 CSV를 보존한 정정 근거는 [인계][handoff]와 이슈 기록에 있다.

[plan]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_PLAN_ko_v1.md
[handoff]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_HANDOFF_ko_v1.md
[execution]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_EXECUTION_ko_v1.md
[prefix-viewer]: http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json&color=height
[prefix-results]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_PREFIX8000_RESULTS_ko_v1.md
[context]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/RESULTS_CONTEXT_ADDENDUM_ko_v1.md
[preview-policy]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_PREFIX22000_RGB_PREVIEW_ko_v1.md
[main-viewer]: http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_v1/profiles/main_final_partial_v1/manifest.json&color=height
[cost-phases]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_v1/closed_costs_v1/unique_producer_phases.csv
[cost-totals]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_v1/closed_costs_v1/regional_totals.csv
[paper-audit]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/PAPER_AUDIT_ko_v1.md
[paper]: /home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf
[baseline-geometry]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/summary/geometry_anchor_refinement_512.csv
[baseline-rgb]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/summary/render_summary.csv
