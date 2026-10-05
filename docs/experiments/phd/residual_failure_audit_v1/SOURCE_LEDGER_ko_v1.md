# 논문별 잔여 오류 근거 원장

2026-09-09 · 원문 재열람 · `scientific_verdict: null`

`관찰`은 원문 그림/표/사례 기술, `해석`은 저자의 원인 설명이다. `진술`은 구체적인 독립 실패 그림/수치를 이번에 확인하지 못한 저자 한계 보고다. `미확인`은 오류가 없다는 뜻이 아니다. 아래 버전은 검토한 원문 버전이며 모두의 최신판이라는 주장은 하지 않는다. 서로 다른 입력의 수치를 합산하지 않는다.

## 1. 외부 기하와 영상·갱신에 가까운 문헌

| 문헌·버전·근거 위치 | 실제 잔여와 수준 | 원인·최종 출력의 경계 | 가까운 해결과 제외할 주장 |
|---|---|---|---|
| [SRDM2018 저자 원고](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=20), §5 p20 | 균일 강도·깊이 급변 영역의 시차 오정합: **진술** | 작은 시차 변화 가정이라는 저자 해석. 최종 표면 손상량 미제시 | 경계/segmentation 제약을 저자도 제안. LGSM이 이 특정 잔여를 직접 해결했는지는 미확인 |
| [Zhou2020 저자 PDF](https://repository.tudelft.nl/file/File_5e70c9f8-1674-49ab-b4a5-fa3085f3dd77#page=23), §4.2.3·4.3.1, Tables2–3·Figs12–13, PDF23–27 | 신축·철거 누락/피복 부족, 비건물 오탐: **full 검출 관찰**. Assen 신축 누락12 중 second matching 실패10. overlap80%에서 신축 TP163→127, 철거9→1 | 가림→조각화→면적 필터 제거의 철거 누락 Fig12(c)는 구체 경로. matching 실패의 관측 부족/알고리즘 기여는 미분리 | NDVI·지도·면적 정제는 이미 포함. multi-view는 저자 제안. ‘prior 제외’는 동작이며 최종 표면 손상 자체가 아니다 |
| [Wu2023 arXiv v1](https://arxiv.org/html/2303.07182v1), §V-A·VI | 오래 주차한 차량의 제거 어려움: **진술**. 해당 독립 실패 그림/빈도 미확인 | 다중 시기 LiDAR mesh 선택·접합 조건. 항공 RGB와 외부 prior 조합 원형은 아님 | ray-only 오류는 distance 결합으로 개선한 문제. full 잔여에서 제외 |
| [Wu–Vallet2026 출판 PDF](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf#page=5), §4.3.2·5, Fig15(b)·16 | 작은 영역 정제 뒤에도 벽 주변 변화 오탐: **관찰** | LiDAR/image 벽 불일치를 저자가 설명. Fig15는 sensor mesh 변화표시, Fig16은 fused point cloud. 최종 점군의 잘못된 삭제·추가 및 기하 정확도 손상량은 독립 검증하지 않음 | Fig8 낡은 label에 의한 stereo 오류는 정제·재학습으로 개선. 독립 변화 GT/갱신 품질 평가는 future |
| [Qin2014 저자 원고](https://rongjunqin.weebly.com/uploads/2/3/2/3/23230064/3d_change_detection_based_on_lod2_3d_models_and_very_high_resolution_spaceborne_stereo_pairs_v5.pdf#page=18), §5.1–5.2, Fig8(f)·9 | 교량의 신규 건물 오탐, 작은 건물/face의 오탐·누락: **full 검출 관찰** | 작은 대상의 대응 연속성·텍스처·잡음은 저자 해석. 고가 철도의 오탐 가능성은 별도 저자 설명. 최종 복원 기하/텍스처는 범위 밖 | Zhou 등의 직접 같은 사례 해결은 미확인. parameter sensitivity를 별도 기본 실패로 합산하지 않음 |
| [GS4Buildings arXiv v1](https://arxiv.org/html/2508.07355v1), §4.4·Fig6·Tables1–3; [출판판](https://doi.org/10.5194/isprs-annals-X-4-W6-2025-249-2025) | 얇은 형상·창/문 부정확, 일부 scene 지표 열세: **관찰/결과 설명** | coarse prior/정규화는 저자 해석. Scene6 CD .857 대 2DGS .728, M3C2 .161 대 .059. 관측 피복과 completeness 참조 범위도 다름 | 국소 적응 가중은 이미 제안. GeoGS가 가까운 후속 방법. GS4B 잔여를 GeoGS 잔여로 이월 불가 |
| [GeoGS 출판판](https://doi.org/10.1016/j.isprsjprs.2026.07.011), Table3·4·7, §5.5–6, PDF12·13·16·17 | 지역·허용치별 **비교 열세**, pose/prior 교란에서 외관 악화: **관찰**. 비건물 결손/동적 artifact: **한계 진술** | Region9 mesh F1@.5 .531 대 .748, 평균 .678 대 .640. 같은 Region9 F1@.2는 .468 대 .133. 지역 원인은 미분리. Table7 nominal PSNR16.654→rotation noise14.488 | 기하 안정과 세부 복원, 구조 보호 및 prior/pose 교란은 이미 평가. currentness 미평가는 stale 잔류 관찰이 아님. 큰 오정합과 비건물 한계 진술을 검증된 빈도처럼 쓰지 않음 |
| [ARSGaussian arXiv v2 PDF](https://arxiv.org/pdf/2412.18380v2), §4.2.5.2·4.2.5.4, Tables6·8·Fig15, PDF17–19; §4.2.6 PDF20 | LiDAR 삭제 시 유리 구조/texture·수관 세부 저하·과신장, 잡음 증가 시 악화: **입력 교란 관찰** | 전체 pipeline을 유지한 stress 조건. LiDAR 기준 RMSE는 독립 최종 mesh 정확도와 다름. 자체 depth generator의 저텍스처 결함은 중간 결과 | 결손/잡음을 전혀 다루지 않았다는 주장 제외. ACMMP 대체의 품질/비용 차이도 이미 제시 |
| [CL-Splats arXiv v2](https://arxiv.org/html/2506.21117v2), §3.1·4.2·9.2, Table4·Fig12 | 극히 얇은 변경 대상의 영역 과소추정→갱신 실패: **full 사례** | 색상 GS+신규 RGB. 필요한 수정/생성 범위 제한은 저자 설명. 독립 metric mesh 손실은 미평가 | **원형에 mask dilation이 이미 있음.** no-dilation은 제거 실험. 전역 조명 범위는 별도이며 GaussianUpdate 기능과 비교 |
| [GaussianUpdate arXiv v1](https://arxiv.org/html/2508.08867v1), §4.2·4.3·5, Table4·Fig3 | 강한 반사/거울의 기하·외관 갱신 오류: **진술**. 과거 렌더의 작은 하락: **표 관찰** | Table4 T1 PSNR26.92→26.84, T2 26.05→25.92. 표면 손상·catastrophic forgetting으로 확대하지 않음. 반사 원인 통제 미확인 | appearance/layout 처리가 이미 존재. 제거 모듈/mask 없이 사라진 물체가 남는 Fig3는 full이 개선한 ablation |

### GeoGS 원본과 구현 계보

이번에는 출판 DOI 웹 열기가 오류여서 확보된 원본을 CPU Docker의 pypdf 6.0.0으로 직접 다시 읽었다. PDF는 18쪽이며 인쇄 페이지=PDF페이지+183이다.

- 원본: `/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf`
- SHA256: `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`
- [고정 공식 구현](https://github.com/zqlin0521/GeoGS/tree/db40c95c657ec03ff21c83cb99cf39f4e90247a6). 구현에 대한 이전 정적 감사는 [근거 카드](../literature_research_question_v1/cards/geogs.md)에 있다. 이번 잔여 분류는 실제 출판 결과를 기준으로 했으며 코드를 실행해 재현하지 않았다.
- GS4Buildings는 [고정 공식 구현](https://github.com/zqlin0521/GS4Buildings/tree/f0be3e257ee6f58e42d1aa3258810c7b78866a7d)과 출판 설정의 차이가 이전 [카드](../literature_research_question_v1/cards/gs4buildings.md)에 기록되어 있다. 공개 코드가 없다는 옛 설명이나 default CLI=논문 full이라는 가정을 사용하지 않는다.

## 2. 표현·감독·추출의 구성요소 문헌

| 문헌·버전·원문 위치 | 실제 잔여와 수준 | 기여 근거로 사용할 때의 경계 |
|---|---|---|
| [3DGS v1](https://arxiv.org/html/2308.04079v1), §7.4·Figs11–12 | 약관측 부분의 elongated/splotchy 요소·낮은 시각 세부와 popping: **렌더 사례/보고** | mesh 복원 오류 실험 아님. [StopThePop](https://doi.org/10.1145/3658187)의 sorting/consistency 개선 등 직접 후속 해결을 인정 |
| [2DGS v1](https://arxiv.org/html/2403.17888v1), AppendixC·Fig12; §7 | 유리/반투명 표면 복원 어려움·고광량 부분 구멍: **full 사례**. texture 위주 densification의 미세 형상 부정확·과평활: **진술** | Table5 추출 대안의 악화를 채택 full 실패처럼 사용하지 않음. 기존 기하 결합 후에도 동일 오류가 남는지는 별도 |
| [AGS-Mesh v2](https://arxiv.org/html/2411.19271v2), Table3·AppendixD.1/Table5·AppendixE | 추출 선택이 모든 기하 지표를 높이지 않음: **대안 비교/저자 진술** | 특정 구멍·허위면 원인으로 확정 불가. normal 동의가 잘못된 평행면을 통과시킨다는 말은 우리 추론 |
| [VCR-GauS v2](https://arxiv.org/html/2406.05774v2), AppendixB·Fig13 | Caterpillar의 반투명 창 표면 실패: **full 사례** | 거의 모든 view의 normal 오류/관측밖 복원 불가는 별도 한계 진술. D-Normal/confidence 제거 artifact는 full이 완화한 오류 |
| [HelixSurf v2](https://arxiv.org/html/2302.14340v2), SupplementH·Fig12, PDF14 | 무텍스처 고곡률 표면 artifact: **full object/scene 사례** | smooth-normal 가정은 저자 해석. MVS↔SDF feedback 자체는 기존 해결이며 단방향 실패로 분류 불가 |
| [DN-Splatter v3](https://arxiv.org/html/2403.17822v3), Tables4–8·AppendixC/Table12 | depth 종류·손실·추출의 성과 차이: **대안 비교**. 특정 위치의 full 잔여 형상 사례는 이번 검토에서 **미확인** | mono 대안의 열세를 sensor-depth full 실패로 대체하지 않음. 후속 AGS-Mesh를 함께 대조 |
| [DebSDF v3](https://arxiv.org/html/2308.15536v3), §III-B·V, Fig9·TableIV | 다수 prior가 틀릴 때 uncertainty 오판 가능성: **가능한 한계 진술**. 384×384·고해상도 prior 문제: **저자 경험 보고** | incomplete ablation의 얇은 구조 손실은 full SDF-density 보정이 개선. 이를 잔여로 넣지 않음. TableII는 비교군의 수동 mask를 양쪽에서 제거한 조건 |
| [NeuRIS v2](https://arxiv.org/html/2206.13597v2), §4.3·Figs6–7·Table3 | 대표 chair leg/얇은 구조 사례는 **full 성공·ablation 개선**. 별도 특정 full 잔여는 이번 검토에서 미확인 | 잘못된 초기 기하의 영구 prior 기각은 우리 추론. §4.1/5의 장면당 약10시간은 비용·적용성 한계로 분리 |
| [LGSM2022 저자 PDF](https://skyearth.org/publication/papers/2022_lgsmscc.pdf#page=7), §3.1·5, Tables2–4 | 수치상 잔여 시차 오차가 있으나 오류 prior에 의한 특정 실패·원인은 **미평가** | 정확한 guidance 가정을 관측된 낡은 기하 실패로 바꾸지 않음 |
| [PSMNet-FusionX3 CVPRW2023 출판 PDF](https://openaccess.thecvf.com/content/CVPR2023W/PCV/papers/Wu_PSMNet-FusionX3_LiDAR-Guided_Deep_Learning_Stereo_Dense_Matching_on_Aerial_Images_CVPRW_2023_paper.pdf#page=7), Fig11·§5 | Toulouse→Dublin/guidance0.5%의 비교 열세: **관찰**. 작은 구조 보간 문제: **진술** | 낮은 평균 성능을 특정 세부 소실의 증거로 치환하지 않음. 같은 잔여의 후속 해결 여부 미확인 |

## 3. 강건 외관·선택·불확실성

| 문헌·버전·원문 위치 | 실제 잔여와 수준 | 성공·설정·출력 구분 |
|---|---|---|
| [SpotLessSplats v2](https://arxiv.org/html/2406.20055v2), AppendixA·Fig12 | 가까운 정적/일시적 orange의 정적 부분 과마스킹: **full SLS-MLP 중간 사례** | 멀리 떨어지면 구분하는 성공도 제시. feature의 의미·외관·위치 관계는 저자 가설. metric 표면 삭제량 미평가 |
| 같은 원문 AppendixD·Fig13 | Train의 부드러운 사람 그림자를 부분적으로만 검출: **full 검출 한계의 사례 설명** | 최종 렌더 잔류량은 이번에 직접 검증하지 않음. hard shadow/transparent windshield/유사색 background에는 성공도 보임. 정적 외관 목표와 현재시점 외관 목표 차이 주의 |
| 같은 원문 §6·Fig8 | 공격적 UBP의 드물게 관측된 영역 제거: **설정 실패** | clean MipNeRF360 압축 조건. 기본 SLS full의 일반적 유효 구조 손상 증거로 확대 불가. Fig11에서 UBP 없이 transient 누출도 제시 |
| 같은 원문 §6·Fig9 | balloon string 등의 low-resolution feature 누락: **특징/mask 단계 한계** | 모든 최종 얇은 표면의 소실로 등치하지 않음 |
| [BayesRays v1](https://arxiv.org/html/2309.03185v1), §6·Fig7 | 기존 NeRF의 일부 view-inconsistency 오류에 uncertainty가 낮음: **full 진단 누락** | epistemic만 다루는 범위라는 저자 설명. 새 기하 생성 실패 아님. aleatoric 결합은 이미 저자 제안 |

추가 NeRF-on-the-go 원문 HTML 열기는 오류가 발생하여 그 방법 자체의 잔여를 새로 확인했다고 포함하지 않았다. 문헌별 오류를 최신 분야 전체의 미해결로 승격할 전수 검색이나 동일 조건 비교를 완료했다는 주장은 하지 않는다.
