# 출처 감사와 현재 프로젝트 맥락

2026-09-09 · `PHD-LITERATURE-RQ-v1` · `scientific_verdict: null`

## 확인한 맥락과 적용 범위

이번 사용자 연구 목적을 분석 범위로 적용했다. [AGENTS](../../../../AGENTS.md), [연구 헌장](../../../research/00_RESEARCH_CHARTER.md), [결정 로그 DEC-P1-025](../../../research/06_DECISION_LOG.md#dec-p1-025--불확실성-인지형-cross-temporal-prior-guided-reconstruction-상위-문제정의)는 연구 계보·참조 분리·비확증 상태를 확인하는 준거다. 기존 LoD2 프로그램, 특정 GS 구현, 명시적 source decision은 학위 전체의 유일한 형식으로 강제하지 않았다. GS·반복·교체의 필요성은 이번 범위에서 다시 열린 질문이다.

다음 자료는 문헌 탐색 색인 및 현재 개발 맥락으로 읽었다. 그 문서가 인용한 논문 주장은 원문/공식 구현에서 다시 확인했다.

| 기존 문서 | 이번 사용과 현재 상태 |
|---|---|
| [01_NECESSITY](../thesis_topic_v1/01_NECESSITY_ko_v1.md), [02_GAP](../thesis_topic_v1/02_GAP_ko_v1.md) | R1–R4·source authority·출력 품질·관측 한계를 읽음. 기존 dirty working draft를 수정하지 않음 |
| [CONTRIBUTION_AUDIT](../geogs_contribution_v1/CONTRIBUTION_AUDIT_ko_v1.md) | 공식 GeoGS 제어·초기 source 목록. 전문 미확보/장면 결과 없음은 당시 상태 |
| [PAPER_AUDIT](../geogs_p1p2p3_v1/PAPER_AUDIT_ko_v1.md) | 이후 확보한 GeoGS 출판 PDF·Table7 오류 실험·논문/코드 구분. 이번에 원 PDF와 공식 commit 직접 재확인 |
| [P2_REVIEW](../geogs_p1p2p3_v1/P2_REVIEW_ko_v1.md) | 실제 P2 기하·렌더 완료와 품질 상충·원인 귀속 한계 확인 |
| [FACTOR_CONTRASTS](../geogs_p1p2p3_v1/FACTOR_CONTRASTS_ko_v1.md) | 실제 18개 주 실행 및 대비표 존재, 보조 반복 실패/미시작과 비확증 상태 확인 |
| [Wu v7 종합](../wu_vallet_synthesis_v7/RESULTS_AND_CONTRIBUTION_ko_v7.md) | 원문 기반 재구현의 개선/손상·정제 민감도. 저자 native 방법과 같지 않음을 유지 |

## GeoGS/Wu의 현재 상태를 어떻게 읽었는가

**GeoGS 전문은 확보되어 있다.** 출판 PDF SHA256 `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`를 이번에 직접 재확인하고 본문을 읽었다. 출판 원문 Table7은 prior 높이/수평 오차·부분 결손 및 camera 교란 실험을 이미 포함한다. 공식 코드 live HEAD도 `db40c95c657ec03ff21c83cb99cf39f4e90247a6`다. [원문·코드 카드](cards/geogs.md)

**프로젝트의 GeoGS 실제 결과도 있다.** 현재 FACTOR_CONTRASTS는 `PRIMARY18_SUPPLEMENTAL_INCOMPLETE`의 결과를 기록한다. 세 지역×여섯 주 제어 조건은 완료됐고, native 반복의 P1/P2 CUDA OOM·P3 미시작으로 반복 품질 변동은 미측정이다. 원 LoD2가 아닌 ALS 파생 surface/depth/초기화이며, 변경 arm은 같은 지역 anchor8000에서 분기한다. depth=0도 image-only가 아니다. 이번 문헌 분석에서는 이 결과를 재학습·재렌더·재집계하거나 payload 전체를 재감사하지 않았다.

기존 P2 문서의 관측은 다음과 같이 제한해서 사용한다. `.005→.0005, native protection`에서 final1024 raw F1@.5m은 `.6141→.5238`로 낮아지고 ROI 평균 PSNR은 `+5.462163dB`다. 렌더 평균 개선과 기하 완전성/정확도 변화는 같은 의미가 아니다. 원 adaptive DA3의 실제 궤적, 보호의 gradient/density 묶음, 추출·후처리, reference sampling, CRS/datum 제약이 남는다. 이 수치는 **기존 보고의 인용**이며 이번 재측정도 native GeoGS의 과학적 실패 판정도 아니다. [P2 §3·6·8](../geogs_p1p2p3_v1/P2_REVIEW_ko_v1.md)

Wu v7 역시 실제 실행 결과가 있는 **원문 기반 로컬 재구현**이다. 같은 점군 입력에서 P1/P2 개선과 P3의 ALS 대비 손상을 보고하고, 작은 영역 정제 강화는 일부 점수를 회복하지만 피복/거리의 모든 축을 회복하지는 못했다. 저자 PSMNet·실측 trajectory·정확한 ray predicate와 동일하지 않아 원논문 고유 한계로 일반화하지 않는다. 새로운 연구의 유효성은 이 개발 사례들과 독립된 설계가 필요하다. [Wu v7 §1–5](../wu_vallet_synthesis_v7/RESULTS_AND_CONTRIBUTION_ko_v7.md)

## 원문과 구현의 버전 확인

카드마다 primary URL·서지·절·표/그림·확인 페이지·source hash/commit을 기록했다. 아래는 문헌 상태가 바뀌기 쉬운 구현 확인 요약이다. `HEAD`는 **2026-09-09 조회시점**이며 출판 실험의 실행 commit이라는 뜻이 아니다.

| 방법 | 확인 버전 | 실제 확인 수준 |
|---|---|---|
| 3DGS | `54c035f7834b564019656c3e3fcc3646292f727d` | 공식 train.py; 현재 depth/exposure 기능은 2023 원문과 구별 |
| 2DGS | `f3e3b9fa67bbd1c75e05167ff37391d8dab2a678` | 공식 train.py의 loss/density·optimizer |
| GS4Buildings | `f0be3e257ee6f58e42d1aa3258810c7b78866a7d` | 현재 소스 공개 확인. 검색 캐시 Coming soon을 교정; paper schedule/full arm과 default 불일치 기록 |
| GeoGS | `db40c95c657ec03ff21c83cb99cf39f4e90247a6` | 출판 PDF+공식 train/gaussian model·현재 source SHA |
| ARSGaussian | `b4007e55ef1fca516ce03b179a5843ad56a7024b` | raw README Coming soon, tree는 소개 asset. 실행 코드 미공개 확인 |
| AGS-Mesh | `93fda851a20cf0bd5fce642c46da0c83c637165e` | 전처리 DNC와 train ANR·loss. 별도 DN-Splatter 통합판과 구분 |
| SpotLessSplats | `0caae3cc45bb1fddf86bd47e4a521888f5c49889` | gsplat 기반 trainer의 mask·classifier·histogram·pruning |
| CL-Splats | `587fffc207f9c7cbb348f35e6d1d223d007eab69` | 공식 저자 공개 재구현. 논문과 다를 수 있다는 README 경계 포함 |
| VCR-GauS | `aa715d19bfacfa9d491f477c572eab1839dcee3e` | confidence detach·normal/depth loss·density 경로 |
| HelixSurf | `3b46727bf76b4f089afbc79a37a6fb37dc9c66c2` | SDF export→MVS 재호출 확인; gmvs gitlink 별도 카드 |
| SceneEdited | `36a1df1d0ebf87c135659c4eba0a7861190d550c` | 편집·평가·source split code. predictor end-to-end driver는 미확인 |
| NeuRIS / BayesRays | 카드의 고정 commit 참조 | 각각 persistent rejection / uncertainty 계산 소스 확인 |
| GaussianUpdate | 공식 project·supplement·원문 확인 | 학습 실행 코드 미확인. 코드 부재는 방법 실패 근거 아님 |
| Wu 2026 | 출판 페이지가 연결한 ChangeUpdateJN | 현재 공개 URL/API 404; 원문과 source 분리 |
| SRDM / Zhou / Wu 2023 / Qin | 카드에 고정한 원문 판본 | 공식 실행 코드 미확인. 로컬 재구현은 공식 구현을 대신하지 않음 |

## 검색 범위와 추가 문헌의 선정

시작 논문은 제목/저자/DOI로 식별하고, 공식 author/project·arXiv·CVF/학회·출판사와 저자 GitHub를 교차 확인했다. 검색 결과/기존 repo 문서는 **찾는 경로**이며 그것만으로 방법 주장에 근거를 부여하지 않았다. 최신판을 무조건 원논문과 합치지 않고 실제 읽은 판을 카드에 적었다.

| 탐색 출발 | 직접 경쟁성 | 추가 결과 |
|---|---|---|
| 기존 LoD2를 무색 영상으로 검정 | source 판단을 새 기능으로 주장하는지 확인 | Qin 원문 카드 |
| prior filtering/normal uncertainty 인용망 | 현재 geometry로 supervisor 갱신 | NeuRIS·VCR-GauS 카드 |
| spatial uncertainty와 model cleanup | uncertainty 의미/잔여 오류/보정 구분 | BayesRays 카드 |
| MVS↔surface iterative refinement | 단방향 vs 반복의 잘못된 이분법 검토 | HelixSurf 원문+공식 구현 카드 |
| old point cloud + image-guided map updating | 갱신 문제/benchmark 및 explicit module 필요성의 직접 경쟁 | SceneEdited 출판본+toolkit 카드 |

추가 검색 결과에 DN-Splatter, DeSplat, DebSDF, GVGS/GSSR, PSMNet-FusionX3 등이 있었고, 본문 인용망에는 GNC/M3C2·SLAM/정합 계열도 있다. 이번에는 이들 전체를 같은 깊이로 감사하지 않았다. **개별 새 카드가 없는 이 방법들의 부재·실패·상대 우위를 공백 근거로 사용하지 않는다.** 특정 공백을 우선 채택하면 해당 구성요소의 가까운 경쟁법을 더 확인해야 한다. 이 작업은 19편의 표적 검토이며 체계적 전수검색·메타분석 또는 모든 최신법의 SOTA 판정이 아니다.

## 기록과 보존

시작 Git HEAD는 `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`. 기존 수정 4개 thesis 문서 및 다수 untracked 작업을 발견했다. 새 Git 대상 문서는 이 디렉터리에만 작성했다. 원문 다운로드/코드 열람 임시는 `/tmp`에 두고 원자료·실험 payload를 복제/삭제하지 않았다. 문헌 PDF 해석은 일회성 CPU Docker에서 수행했고 GPU 학습·렌더·방법 실험·service lifecycle 명령은 실행하지 않았다. 새 문서 연결과 기존 dirty diff의 보존 검사는 [이슈/검증 기록](ISSUES_ko_v1.md)에 적는다.
