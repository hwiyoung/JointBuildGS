# 기존 기하와 영상의 상보성 — GS 계열 원문 대조

`reviewed_at: 2026-09-09` · `scientific_verdict: null`

문헌 정리이며 새 학습·렌더·방법 실험은 수행하지 않았다. 이전 [근거 카드 색인](../literature_research_question_v1/README.md)은 검색 시작점으로 사용하고, 아래 원문·공식 소스를 다시 대조했다. 목적의 유사성, 구현된 정보 사용, 실험이 입증한 효과를 구분한다.

## 1. 이 세 논문이 사용자의 의미와 같은 상보성을 다루는가

**그렇다. 특히 GeoGS는 구조적으로 안정되지만 세부가 없는 도시 모델과, 세부를 제공하지만 희소·가림 조건에서 불안정한 영상 기반 깊이의 상보성을 명시적으로 다룬다.** 다만 이를 실제로 모든 위치에서 성립하는 성질이나, 두 단독 입력을 모두 능가하는 검증 결과로 확대하면 안 된다.

| 논문 | 외부 기하가 영상 기반 복원을 보완하는 정보 | 영상이 기하 입력만으로 부족한 결과를 보완하는 정보 | 사용자 의미와의 관계 |
|---|---|---|---|
| GS4Buildings | LoD2의 면·방향·구조적 피복이 가림·희소시점의 표면 결손을 줄임 | RGB로 Gaussian 외관·기하를 최적화; LoD2 밖 관측 내용도 building-enhanced mode에서 복원 | 같은 큰 목적. 구조 지지의 추가 효과가 중심이며 세부 보완은 제한도 보고 |
| GeoGS | LoD2의 지리좌표·구조적 연결·면이 image-derived geometry의 모호성·drift를 억제 | RGB와 DA3 파생 깊이가 LoD2가 생략한 국소 표면변동·건물 밖 영역·외관을 제공 | 가장 직접적으로 같은 상보성을 명시. 두 정보의 역할을 anchoring/refinement로 구현 |
| ARSGaussian | LiDAR의 metric 측정이 항공영상의 깊이 모호성·floater·과성장을 제약하고 정합을 지원 | 영상 feature와 matching이 희소 LiDAR의 dense depth 생성에 참여; RGB가 외관과 GS 최적화에 참여 | 센서 기하와 영상의 상보성에 해당. 오래된 단순화 자산의 유효성을 판정하는 문제는 아님 |

여기서 “영상이 prior를 보완한다”는 **산출물의 의미**이다. 원 LoD2/LAZ 파일을 덮어쓰거나 두 방향의 반복 갱신을 해야만 상보적인 것은 아니다. 세 논문 모두 입력 기하를 유지하면서 결과 Gaussian에 외관·기하 정보를 결합할 수 있다. 이 해석은 본 정리의 정의이며 저자의 별도 신규 기여 주장이 아니다.

## 2. GS4Buildings

**원문과 위치:** Zhang et al., ISPRS Annals X-4/W6-2025, 249–256. [출판 PDF](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/249/2025/isprs-annals-X-4-W6-2025-249-2025.pdf), [arXiv v1 HTML](https://arxiv.org/html/2508.07355v1). 아래 PDF 페이지는 1부터 센다.

- **명시된 목적:** §1–2, pp249–251/PDF1–3은 영상의 가림·약한 texture·희소시점 문제와 LoD2의 신뢰 가능한 구조를 대응시킨다. `complementarity`라는 단어 자체보다 내용상 역할 분담으로 확인했다.
- **실현 경로:** §3, pp250–252/PDF2–4, Fig2: LoD2→초기점·depth·normal; RGB와 함께 2DGS 최적화→TSDF mesh. prior 입력은 고정이고 Gaussian은 움직인다. 원 prior의 현시점 타당성을 별도로 검정하지 않는다.
- **확인된 결과:** §4, Tables1–3/PDF5–7에서 MVS·2DGS와 기하 및 NVS 비교. Table4/PDF7은 init/depth/normal 구성요소 제거. 영상 기반 비교군은 있지만 **LoD2만 사용한 결과와 동일 참조·범위에서 비교하는 완전한 양단독 시험은 확인되지 않는다**. LoD2와 구조적으로 일관된 LoD3가 completeness 참조이므로 currentness 증거와 구분한다.
- **성공의 경계:** §4.4/PDF6–8, Fig6은 충분한 영상에서 얇은 구조와 처마·창·문 세부를 더 놓치는 사례를 보고한다. 이는 상보성을 목표로 했다는 사실과 모든 조건에서 실현했다는 주장을 구별하게 한다.

**공식 구현:** [고정 소스 f0be3e2](https://github.com/zqlin0521/GS4Buildings/tree/f0be3e257ee6f58e42d1aa3258810c7b78866a7d). 공개 `train.py`의 RGB/prior 손실 결합과 schedule을 정적으로 확인했다. 논문의 Phase2 prior-weight 점감 서술과 현재 depth-weight 유지 경로가 다르므로 코드 기본값을 논문 full arm과 동일시하지 않는다. 상세는 [기존 카드](../literature_research_question_v1/cards/gs4buildings.md).

## 3. GeoGS

**원문과 위치:** Zhang et al., ISPRS JPRS 240 (2026), 184–201. [DOI](https://doi.org/10.1016/j.isprsjprs.2026.07.011). 확보된 18쪽 출판 PDF를 재확인했다. PDF page+183=인쇄 페이지. 로컬 원본 및 SHA256은 아래 재확인 기록에 둔다.

- **명시된 목적:** §1/PDF2의 짧은 표현은 “two prior sources offer complementary strengths”. §3.3/PDF5와 §6/PDF17도 LoD2의 metric 구조와 visual depth의 세부를 연결한다. 우리 연구만의 새로운 문제의식으로 사용할 수 없다.
- **입력의 정확한 의미:** LoD2와 **현재 RGB+pose→DA3 깊이**를 결합한다. DA3는 영상에서 파생되면서 사전학습 정보도 사용한다. 독립 LiDAR 관측이나 RGB와 독립된 두 번째 센서가 아니다.
- **실현 경로:** Fig2/PDF4, §3.4/PDF6–7: LoD2 초기화·depth anchor·근접 구조 보호 이후 visual-depth와 RGB가 Gaussian을 갱신. 입력 LoD2·pose·DA3 depth는 고정; visual loss 가중치는 바뀐다.
- **실제 분리:** Table6/PDF15의 full F1@.5=.788, w/o DA3=.772, w/o LoD depth=.780. 그러나 w/o DA3에도 RGB가 남고, w/o LoD depth에도 LoD 초기화가 남는다. **이를 prior-only/image-only 양단독 시험으로 부르면 안 된다.** 2DGS 비교와 구성요소 효과는 있다.
- **경계:** Table3의 지역별 악화와 Table7/PDF16의 prior/pose 교란 평가가 모두 있다. 잘못된 prior를 전혀 시험하지 않았다는 주장은 제외한다. 자연 시간차의 유효성·세부별 복원·전 구역 비악화까지 입증하지는 않는다.

**공식 구현:** [고정 소스 db40c95](https://github.com/zqlin0521/GeoGS/tree/db40c95c657ec03ff21c83cb99cf39f4e90247a6). 구조 보호와 dual-gate는 서로 다른 기능이다. 후자는 DA3 loss 가중을 제어하며 입력 LoD2의 정답 여부·현재성을 직접 판정하지 않는다. 실제 로컬 P1/P2/P3 결과가 존재한다는 현재 상태는 [기존 카드](../literature_research_question_v1/cards/geogs.md)와 해당 실행 보고를 따른다. 여기서는 재계산하지 않았다.

## 4. ARSGaussian

**원문과 위치:** Yao et al., [arXiv:2412.18380v2](https://arxiv.org/pdf/2412.18380v2), 2026-03-10, 24쪽 accepted manuscript. [출판 DOI](https://doi.org/10.1016/j.isprsjprs.2025.10.022). 페이지는 v2 PDF 기준.

- **명시된 목적:** §1/PDF1–4에서 LiDAR의 기하와 영상의 NVS를 결합한다. §2.2/PDF5의 `complementary characteristics`는 인용한 **LVI-GS**를 설명하는 문장이다. 이를 ARS 자신의 직접 인용으로 옮기지 않는다. ARS의 목적·경로는 같은 센서 역할 분담으로 해석할 수 있다.
- **실현 경로:** §3.2–3.3/PDF7–9: LiDAR+영상 feature로 pose 정합, LiDAR/SfM plane 초기화·Delaunay·ACMH로 dense depth/normal, RGB+기하 감독으로 GS 최적화. 영상이 희소 지지를 보완하는 경로도 존재한다.
- **실제 분리:** Table1/PDF13의 image-based 방법 비교, Table3/PDF14의 densification/alignment/geoloss 제거가 있다. `w/o LiDARconst`는 densification 모듈 제거이며 **모든 LiDAR 정보를 제거한 image-only가 아니다**. LiDAR-only의 동등 출력 비교는 확인되지 않는다.
- **경계:** Table5–9는 밀도·잡음·결손·depth completion 효과를 이미 평가한다. 기하 RMSE의 주 참조가 감독 LiDAR라는 한계가 있다(§4.2.5.2/PDF17). 원 LiDAR의 오류를 현재 영상으로 독립적으로 수정했다는 검증이나 자연 시간차 건물 갱신 검증으로 확대하지 않는다.

**공식 구현:** [공식 저장소](https://github.com/WenjuanZhang-aircas/ARSGaussian)는 이번 열기에서도 README·img.jpg·video.gif 및 `Coming soon!` 상태다. 알고리즘 실행 코드를 확인했다고 쓰지 않는다. 기존 고정 HEAD는 `b4007e55ef1fca516ce03b179a5843ad56a7024b`. 상세는 [기존 카드](../literature_research_question_v1/cards/arsgaussian.md).

## 5. 정의와 후속 질문에 대한 함의 — 우리 해석

이 자료들이 지지하는 구분은 다음과 같다.

1. **상보성을 의도함:** 한 입력이 약한 정보를 다른 입력에서 얻겠다는 목적.
2. **상보성을 구현함:** 두 입력의 정보가 결과를 바꿀 실제 경로가 존재함.
3. **상보성의 효과를 검증함:** 특정 비교와 조건에서 이득이 측정됨.
4. **각각의 단독 사용보다 충분한 결과를 얻음:** 동일 목표·허용 입력·참조·범위에서 두 단독 결과와 결합 결과를 비교해야 할 더 강한 주장.

세 논문에서 1–3의 근거를 확인했다. 4의 완전한 검증이 없다는 점만으로 방법론적 공백을 선언하지 않는다. 또한 단순 상보성에 **모든 지표의 동시 우위, 양 입력 원본 수정, 반복, source replacement**를 정의상 요구하지 않는다.

Raw ALS, LoD2, 영상 파생 깊이는 같은 `3D prior`로 묶되 정보의 내용은 따로 적어야 한다. Raw ALS는 측정점의 범위·피복·잡음이 있고, LoD2는 일반화·모델링된 면과 구조를 제공하며, DA3는 영상과 사전학습에서 추론한 깊이다. 어느 정보가 영상의 어느 약점을 보완하는지는 prior 종류와 관측 조건에 따라 달라진다. 따라서 “prior=항상 정확·완전, 영상=항상 현재·세밀”을 고정 정의로 쓰지 않는다.

## 6. 재확인 기록과 한계

- GS4Buildings arXiv HTML, 출판 PDF의 기존 전문 추출, 고정 공식 `train.py`를 읽었다.
- GeoGS 출판 PDF 원본: `/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf`. 이번 SHA256 재확인: `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`. 기존 Docker 추출 전문에서 §1/3.3/3.4/6과 Table6을 재독했다. 출판사 웹 열기는 Internal Error였으므로 웹 열기 성공으로 기록하지 않는다.
- ARS v2 PDF는 웹에서 직접 재확인했다. arXiv HTML 열기는 Internal Error였고 PDF로 해소했다.
- 임시 원문 탐색에서 `/tmp`의 무관 서비스 디렉터리에 permission/socket 오류가 발생했다. 이후 이미 알려진 문헌 임시 경로와 원문 URL로 한정했다. 서비스나 파일 권한을 변경하지 않았다.
- 원문 주장과 코드 정적 확인을 기록했으며 독립 재현·원인별 실험·전체 문헌 포괄성 판정은 수행하지 않았다.
