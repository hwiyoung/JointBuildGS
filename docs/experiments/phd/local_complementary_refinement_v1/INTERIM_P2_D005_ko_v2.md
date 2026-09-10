# P2 .005 첫 쌍 중간 관측 v2

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- scientific_verdict: null
- 상태: 새18개 중2개(P2 .005 native/release)의 학습·추출·외관·기하 평가 완료. 나머지16개를 같은 동결 명세로 계속 실행한다.
- 명세: [MAIN_SPEC_ko_v2.md](MAIN_SPEC_ko_v2.md), 진행: [PROGRESS_ko_v2.md](PROGRESS_ko_v2.md).
- 아래는 완료된 두 조건의 관측이다. 전체 방법의 우열·공간 배분 고유 효과·재현성 판정이 아니다.

## 외관 평균의 개선과 관측 기하의 악화가 함께 나타났다

같은 ROI의 원본 UAS2,325,976점에서 고정0.1m voxel로 원본 ID를 보존해 선택한 참조점572,214개, raw TSDF512, 거리0.5m 미만 기준이다. 정확도는 예측 표면 표본→관측 UAS, 완전성은 같은 UAS점→삼각형 표면의 근접 비율이다. 수정·손상은 그 문턱의 교차이며 물리적 정오나 면적을 인증하지 않는다.

| 같은 조건의 G→LC | Native | Release |
|---|---:|---:|
| 정확도 변화 | −0.55%p | +5.31%p |
| 완전성 변화 | −13.70%p | −9.33%p |
| F1 | .53458→.44998 | .50905→.47220 |
| 수정 / 손상 참조점 수 | 32,360 / 110,751 | 51,225 / 104,624 |
| G의 Anchor 대비 수정 중 LC가 잃은 점 | 42,728 | 34,549 |
| G의 Anchor 대비 손상 중 LC가 회복한 점 | 14,129 | 14,451 |
| 같은 XY cell에 수정·손상 공존 | 718 / 8,799 | 719 / 8,799 |
| 9카메라 전체 PSNR 평균 변화 | +0.837dB | +0.959dB |

기존 G도 성공과 손상을 모두 가진다. G native는 Anchor 대비135,222점을 수정하고135,799점을 손상시켰으며, G release는132,840/150,811점이다. 새 LC의 추가 수정만 보고 기존 G의 성공을 지우거나 LC의 손상을 숨기지 않는다.

| P2 전체 기존 대조와 새 결과 | 완전성 | F1 |
|---|---:|---:|
| Anchor8k | 52.19% | .465 |
| G .005 native / release | 52.09% / 49.05% | .535 / .509 |
| G .0005 native / release | 38.04% / 37.60% | .460 / .456 |
| G 0 native / release | 39.09% / 37.77% | .472 / .455 |
| LC .005 native / release | 38.39% / 39.72% | .450 / .472 |

LC .0005/0은 아직 결과가 없다. 이 표에서 유리한 대조를 다시 고르거나 문턱을 바꾸지 않는다. 모든 거리 문턱과 raw/post 비교는 원 평가 CSV에 남아 있다.

같은 post512의0.5m 보조 비교에서도 완전성은 native50.56%→36.99%, release47.22%→39.50%, F1은 .533→.440 / .502→.472였다. 후처리가 제거한 표면 면적은 G native/release271.03/268.54m², LC112.07/77.28m²로 따로 기록한다. 삭제 면적은 잘못된 구조 면적이나 국소 가중의 개선량을 뜻하지 않는다.

## 같은 위치와 같은 카메라에서 본 성공·손상

수정·손상 지도는 같은 원본 참조 ID/XYZ로 세 방향(Anchor→G, Anchor→LC, G→LC)을 다시 계산했다. Release의 동쪽 일부에는 수정 우세 구간이 있으나, 북서 표시 사분면(X110–134/Y109–132)에서는 수정5,347점보다 손상38,544점이 많다. 동일0.5m XY cell은 동일한 3D 표면 패치가 아니며 cell 수를 면적으로 환산하지 않는다.

최대 고정 prism 투영 면적 규칙으로 선택된 원사진 `DJI_20241217084503_0075_D.JPG`의 동일681×623 crop에서는 G가 Anchor의 흐린 지붕·외벽·도로 표현을 회복한 부분이 보인다. LC에서는 도로·차량 질감이 더 번진다. 원사진과 저장 PNG로 독립 계산한 해당 ROI PSNR 변화는 native −0.514dB, release +0.061dB다. 작은 총 MSE 개선도 특정 도로의 국소 손상을 없애지는 않는다.

9카메라 ROI의 dB 산술 평균은 +5.155/+5.190dB이나, 개선/악화 카메라는 native7/2, release8/1이다. 선택 crop은424,263pixel이고 큰 양의 차이가 난 일부 crop은 약24,000–29,000pixel이다. 각 카메라가 같은 가중치를 가지므로 이 평균은 전체 pixel을 모은 PSNR이 아니며 큰 영역의 국소 악화를 가릴 수 있다. ROI SSIM/LPIPS는 미측정이다.

고정 X134/Y109의 폭0.5m 단면 표본에서는 LC의 중복·이격 층 감소와 일부 지붕 높이 접근이 보이는 한편, 지붕 골의 높이 차이·지면 offset·낮은 Z 관측점 부근의 표면 표본 부족도 남는다. 이는 해당 band 관측이며 정확한 mesh-plane 교선이나 전체 건물의 현재성 판정이 아니다.

## 원인 설명과 기여의 현재 경계

Source proxy별 G→LC 수정·손상은 다음과 같다. Prior 근접은 prior 삼각형까지0.5m 미만, DA3 근접은 strict 대응의 world-Z 잔차 절댓값0.5m 이하다. 이는 source의 물리적 정오 label이 아니다.

| Prior / strict DA3 proxy | 참조점 수 | native 수정 / 손상 | release 수정 / 손상 |
|---|---:|---:|---:|
| near / near | 28,250 | 1,329 / 3,606 | 2,055 / 3,366 |
| near / far | 124,054 | 7,367 / 31,750 | 4,896 / 37,023 |
| far / near | 27,213 | 1,650 / 6,354 | 3,094 / 3,128 |
| far / far | 89,802 | 7,600 / 10,328 | 28,689 / 6,522 |
| strict 지원 없음 | 302,895 | 14,414 / 58,713 | 12,491 / 54,585 |

Prior-near/DA3-far 집합에서 G가 근접하던 점의 손상률은46.35%/64.93%이며, 그중 Anchor와 G가 함께 유지했던 점의 추가 손상은31,256/36,521개다. 반대로 release의 both-far 집합에는 순증22,167점이 있다. 전체 release 순감53,399점과 함께 해석해야 한다. Strict 지원이 없는52.93%를 DA3-far나 원사진 관측 불가로 바꾸지 않는다. ±1m target 편향과 multiview spread 등의 중첩 집합은 원 CSV로 보존하며 임의로 합산하지 않는다.

최종 trace의8100–30000 비교440개 각각에서 G와 LC의 학습 카메라가 일치했다. 이 표본에는 서로 다른 카메라56개가 있다. Native의 lambdaV 불일치는0/220, release는185/220(첫 관측11600)이다. 두 LC의 표본평균 prior/visual 배율은 .11294/.95041이다. 평균 raw prior L1은 G 약9.23/10.45m에서 LC 약82.89/82.62m로 높아졌고, 평균 raw DA3 L1은 약6.76/6.90m에서4.49/4.43m로 낮아졌다. 학습 target 적합과 관측 기하의 개선은 같은 주장이 아니다.

- 문제 차별성: 같은 부위에서 기존의 성공·새 수정·새 손상이 공존한다는 개발 사례를 남긴다. ALS 사용 자체를 독자성으로 삼지 않는다.
- 원인 설명: 평균 prior 약화, 불일치에 따른 배분, controller 반응, target 오류·가시성, 표면 추출이 경쟁 설명이다. 이번 두 결과만으로 하나를 확정하지 않는다.
- 방법 신규성: 상보 함수의 최초성이나 새 복원 원리의 증거가 아니다. 현재 두 조건의 악화도 방법 기여 검토에 포함한다.
- 검증 기여: 같은 Anchor·입력·조건·원본 참조점에서 기존 성공과 새 손상을 함께 검사한 추적 가능한 비교다. 평균 배율 전역 대조·controller replay·반복이 없어 공간 배분 고유 효과나 작은 차이의 재현성은 미확정이다.

GT는 평가 전용이다. Prior 근접도·strict DA3 world-Z 잔차는 source 평가 proxy이며 원사진 O/X·시간적 진실과 구분한다. 피복 밖 형상과 절대 높이 datum은 인증하지 않는다. LambdaP=0도 prior를 사용한 a/Anchor/보호 이력이 남으므로 image-only가 아니다.

## 실제 산출물 계보

외부 root는 [main_v2 resolver](../../../../artifacts/manifests/local_complementary_refinement_v2.yaml)를 따른다. 다음 경로는 그 payload root에 상대적이다. 로컬 외부 저장은 durable backup 주장과 다르다.

- 평가: `main_v2/evaluation/attempt_20260910T153659_593789Z/receipt.json`, SHA256 `4881176bb57d2548bb0a49ad1165d7377b09e04dfca0803314b87471732b5004`. 63.793초, peak RSS1,282,555,904bytes. 선택 P2의 미완료4행과 전체 행렬의 미완료16개는 범위가 다르다.
- 수치 요약: `main_v2/summary/attempt_20260910T153836_652430Z/` — 전체 G6·Anchor·LC2, 모든 문턱/raw/post, 수정·손상 및 외관 분모·계산량 원표.
- 같은 카메라·단면: `main_v2/figures/attempt_20260910T153834_683312Z/`. 독립 crop/PSNR/단면 수 검증: `main_v2/figures_review/review_20260910T154100Z/`.
- 수정·손상 지도: `main_v2/maps/visual_qa_v2_2/attempt_20260910T153659_593789Z/`. 최초 글자 겹침 그림과 중간 수정은 별도로 보존했고, 수치 CSV는 동일하다.
- 최종 P2 .005 trace: `main_v2/trace_monitor/attempt_20260910T153454Z_final_P2_D005/`. 전체 행렬은 PARTIAL_MATRIX2/18이다.
- Source proxy 층: `main_v2/strata_diagnostic/attempt_20260910T155253Z_P2_D005/receipt.json`, SHA256 `7b5d0020ad0c7877d542126f7f200c14ebba6ff458ae11de224fc00f8b2a08f6`. 원 CSV hash·동일 분모·8상태·집합 분할 검증, Docker4개 테스트 PASS.
- 조건별 지표 변화·수정/손상 비율 그림: `main_v2/matrix_figures/attempt_20260910T163843_120697Z/receipt.json`, SHA256 `14e41d70ab77c6045d2d8f9edac39ea67fdc38181f7736c2ea4cd459746e146d`. 실제2/18과 미표시16개를 명시하고, source CSV·config·script와 결박했다. 최초 겹침 그림은 보존했으며 Docker11개 및 실제2행·합성18행 layout QA가 통과했다. 합성은 결과로 사용하지 않는다.

현재 wall/RAM/VRAM은 checkpoint 일정·과거1024/보조512와 새512의 렌더 범위·타이머·병행 작업이 달라 순수 방법 효율 차이로 해석하지 않는다. 실패·보완은 [이슈](ISSUES_ko_v2.md)에 남긴다.

문서 대조에서 G release raw DA3 평균6.904891m의 이중 반올림 표기6.91을6.90으로 수정하고, 참조점 선택·카메라 대응·단면 관측의 범위를 명확히 했다. 원 평가 수치·실행은 바꾸지 않았으며 전후 문서는 `main_v2/evaluation_preflight/interim_report_review_p2_d005_v2/`에 보존한다.
