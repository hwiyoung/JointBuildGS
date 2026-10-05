# P1 꺾쇠형 윤곽 잔존과 P2 지붕 골 손실: 기대 미충족과 논문 성과의 관계

2026-09-10 · PHD-GEOGS-EXPECTATION-BOUNDARY-v1 · scientific_verdict: null

**P1과 P2는 우리의 기대가 국소적으로 충분히 충족되지 않은 사례로 함께 볼 수 있다. P1은 수정·제거가 필요한 형상의 잔존, P2는 유지할 국소 형상의 약화라는 서로 다른 결과다. 동일한 원인이라고 아직 묶을 수는 없다.** 이는 GeoGS 논문이 보고한 희소 영상 조건의 평균 상대 성능 개선과 양립한다.

앞선 [기대 감사](EXPECTATION_AUDIT_ko_v1.md)의 “네 기대의 상당 부분 실현”은 기능별 성공 사례와 평균 이득을 뜻한다. 네 기대가 각 표면에서 함께 충족됐다는 의미로 확대하면 부정확하다. 반대로 P1/P2의 잔여로 P3 측벽 보완이나 P2 큰 윤곽 개선까지 부정하지 않는다.

## 1. 이번에 직접 다시 본 P1

같은 512 raw 고정 단면에서 확인했다. X=−8m, Y≈−21…−5m에서 prior의 경사진 상부 윤곽은 local Z≈−37m에 있고, 현재 UAS는 대체로 Z≈−42m의 낮은 면이다. 사용자 지적의 낮은 지붕/꺾쇠에 대응하는 높은 윤곽은 D005_Pnative에서 변형·분리되지만 넓게 남는다.

D0005_Pnative에서는 이 높은 윤곽이 크게 낮아진다. 그러나 Y≈−13…2m 일부 구간은 현재 UAS보다 대략 0.5–1.5m 높고, 결과가 현재의 평탄면에 정확히 수렴하지 않는다. D0_Prelease에서도 중앙의 들뜸과 북측 상승·추가 띠가 남는다. “전혀 바뀌지 않았다”보다 **“수정은 되었지만 현재 면 복원이 충분히 이루어지지 않았다”**가 실제 결과에 맞다.

직접 본 자료:

- [prior 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/prior_mesh.sections.png)
- [원설정 final512 raw](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.mesh_512.raw.sections.png)
- [깊이 완화 final512 raw](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.mesh_512.raw.sections.png)
- [깊이0·보호 해제 final512 raw](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Prelease.mesh_512.raw.sections.png)
- [영상 MVS 비교군](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/mvs_points.sections.png)
- [실제 평가 사진·원설정 렌더](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [같은 사진·깊이 완화 렌더](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)

사진에는 포장된 평탄한 바닥이 보인다. 다만 이 평가 사진과 단면의 정확한 표면 투영 대응·해당 학습 사진들의 충분한 다중시점 증거는 이번에 새로 계산하지 않았다. MVS도 이 GeoGS 조건의 직접 dense 입력이 아니며 all-view 산출물이므로 “MVS가 잘 복원했으니 동일 학습 정보가 반드시 충분했다”고 단정하지 않는다.

단면은 폭 0.5m의 평가 표본 투영이다. 높이는 그림에서 읽은 근삿값이다. 잘못된 상부 형상이 실제 시간 변화로 생겼는지, ALS 오류·표면화·정합에서 생겼는지는 이 관찰로 구분하지 않는다. 현재 참조와 불일치하는 형상의 잔존이라는 진단은 원인의 이름이 확정되기 전에도 가능하다.

## 2. P1과 P2를 어느 수준에서 묶는가

| 항목 | P1 | P2 |
|---|---|---|
| 기대한 변화 | 현재 낮은 면과 불일치하는 높은 꺾쇠형 윤곽을 수정·제거하고 현재 면 복원 | 현재 참조와 가까운 반복 지붕 골의 국소 형상 유지 |
| 관찰한 결과 | 원설정은 높은 형상을 상당 부분 남김. 완화는 크게 낮추지만 들뜸·형상 차이 잔여 | 큰 상단·추가 윤곽은 개선되지만 일부 깊은 골은 최종 메쉬에서 얕게 남음 |
| 기대와의 관계 | **필요한 수정이 부족** | **필요한 보존이 부족** |
| 입력 정보 확인 수준 | prior의 잘못된 높은 형상과 현재 UAS/MVS의 낮은 면 확인. 정확한 train 영상·깊이의 반증력 미확인 | 골 높이대 원 prior 표본 52개 중 50개가 실제 초기점으로 전달. train 사진에 반복 형상 존재. 골별 충분성은 미확인 |
| 원인 | 초기화·anchor 이력, prior/DA3 감독, 관측 모호성, 정합·추출 등 경쟁 설명 | 같은 경쟁 설명이 가능하나 발생 단계·기제가 P1과 같다는 증거 없음 |

공통 상위 문제는 **입력의 유효한 형상을 유지하고 불일치 형상을 수정하는 요구가 최종 복원에서 함께 달성되는가**이다. 이것만으로 명시적 소스 판단이나 반복 공동 추정이 필요하다고 결론내리지 않는다.

## 3. 논문에서는 왜 잘됐다고 하는가

검토 원문: Qilin Zhang, Olaf Wysocki, Boris Jutzi, *GeoGS*, ISPRS JPRS 240 (2026), 184–201, [DOI](https://doi.org/10.1016/j.isprsjprs.2026.07.011). 확보 PDF SHA256은 이전 감사와 같은 `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`다. 공식 [방법 설명](https://github.com/zqlin0521/GeoGS)은 LoD2를 구조 기준, visual depth를 국소 정제 정보로 사용한다고 기술한다.

| 논문의 실제 증거 | 지지하는 결론 | 우리의 기대와의 차이 |
|---|---|---|
| §4.1–4.3 pp191–192, Tables1–4: TUM2TWIN 9개 영역·egenioussBench 5개 영역. 주 비교는 15장 중 13장 학습. 평가 영상과 전체 기하 거리/F1 | 희소 영상에서 비교 방법 대비 복원 품질 개선 | 처음부터 정확한 면·잘못된 면·없는 세부를 구분해 전후 성공을 각각 평가하지 않음 |
| Table3(b) p195: 평균 mesh F1@.5 GeoGS .678, 2DGS .640 | 이 자료에서 평균 성능이 더 좋음 | 같은 표 R9은 GeoGS .531, 2DGS .748. 모든 지역의 우위가 아님 |
| Table6B p198: 보호 제거 시 M3C2 .378→.389m, F1@.5 .788→.775 | 구조 보호가 해당 비교에 도움 | 보호할 정확한 면과 수정할 잘못된 면을 구분해 적절히 처리했다는 증거와 다름 |
| §5.5 Table7 p199: 높이·수평 이동과 일부 입력 표면 삭제, 전체 최종 TSDF 평가 | 시험한 prior 교란에 대한 최종 결과의 상대적 강건성 | **입력 표면 삭제는 결손을 만드는 조작**이다. 현재 사라진 객체를 prior에 남겨 놓고 최종 결과가 제거하는지 시험한 것이 아님 |
| §6 p200: 큰 pose·model 오정합, 건물 prior 밖의 덜 완전한 복원·artifact 기술 | 저자도 적용 한계와 잔여를 인정 | P1을 자동으로 “건물 밖이라 범위 밖”으로 분류할 수 없음. 실제 입력·보호 상태 확인 필요 |

공식 추상/README의 평균 PSNR +1.13dB, 메쉬 M3C2 14.3% 개선은 서로의 최상 비교군 대비 수치다. 저자가 모든 입력 면에서 완전한 보존·수정·세부 생성·외관 일치를 입증한 수치가 아니다. 논문의 서술이 넓게 읽힐 수 있어도 실제 표와 평가 설계가 뒷받침하는 범위로 제한해 인용해야 한다.

또한 공식 연구는 LoD2 기반 건물 구조를 사용하고 우리 P1/P2는 ALS 파생 표면 입력을 사용했다. P1의 잘못된 높은 면을 없애는 요구와 P2의 prior 자체에 들어 있는 정밀 골 유지 요구가 논문의 교란 실험으로 분리 검증되지는 않았다. 이 조건 차이가 곧 실패 원인 또는 신규성이라는 뜻은 아니다.

## 4. 현재 내릴 수 있는 결론과 다음 확인

1. **기대 미충족은 인정할 수 있다.** P1의 필요한 수정과 P2의 필요한 보존이 충분하지 않다. 원인을 아직 모른다는 이유로 관측된 미충족까지 유보할 필요는 없다.
2. **GeoGS의 능력이 전혀 없다는 결론은 아니다.** 원설정의 일부 수정·측벽 보완과 단순 깊이 완화의 큰 형상 개선도 실제 성과다. 앞선 P2 F1 하락을 건물 전체 기하 악화로 읽은 해석은 재사용하지 않는다.
3. **동일 원인과 방법론 신규성은 추가 근거가 필요하다.** P1의 현재 저면을 지지하는 실제 train/DA3 깊이와 P2 골의 prior/DA3 깊이를 같은 단계로 추적한다. final 학습 깊이부터 잘못됐는지, raw 추출 이후에 생기는지 구분한다.
4. **새 방법은 두 방향을 함께 평가한다.** P1의 높은 형상을 줄이면서 P2의 골과 이미 성공한 P3 구조·측벽을 유지할 수 있는지 확인한다. 기존 파라미터·입력 보정·추출 설정으로 해결되면 그것을 채택한다. 진행 중 별도 초기화/anchor 비교는 완료된 결과와 혼용하지 않는다.

이번 작업은 기존 그림·문서·공식 원문·저장소의 읽기와 이 추가 기록만 수행했다. 새 학습·장면 렌더·메쉬 추출·평가 계산·서비스 변경은 없다. 기존 보고서와 진행 중 작업을 수정하지 않았다.

