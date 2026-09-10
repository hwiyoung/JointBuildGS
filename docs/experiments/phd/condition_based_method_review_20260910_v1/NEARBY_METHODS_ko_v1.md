# 가까운 기존 방법의 성공·남은 질문과 최소 비교

- 작성일: 2026-09-10
- 상태: `EXPLORATORY_DESIGN_ONLY`; `scientific_verdict: null`
- 이번 사용자 지시가 새 탐색 설계의 기준이다. AGENTS.md, 헌장, DEC-P1-025는 운영·보존 지침과 기존 연구의 맥락으로 읽었다. E1–E6, ALS, source-decision, GS 또는 단계 구성을 이 설계의 필수 방법으로 승격하지 않는다.
- 이 문서는 GeoGS·AGS-Mesh·NeuRIS의 근접 비교를 맡는다. 세 문헌은 탐색의 경계가 아니다. 다른 방법군과 최신 직접 경쟁 후보는 같은 경로의 종합 문서와 함께 읽는다.

## 1. 이 세 방법을 비교할 조건

도시·시간차·GS라는 키워드보다 **독립 기존 기하의 유용성, 영상의 실제 관측력, 영상 파생 감독의 정확도가 위치마다 어떻게 달라지는가**를 먼저 묻는다. 기존 기하에 정밀 세부가 있고 영상 기하가 더 거칠 수 있다.

| 현실 조건 | 기대할 수 있는 도움 | 남는 질문과 연구상 중요성 |
|---|---|---|
| 유효한 기존 기하, 약한 영상 기하 증거 | 모호한 위치·면 방향을 제한 | 유효 구조가 유지되는가. 실제 관측이 없는 세부의 복원 성공을 주장하지 않는다 |
| 틀린 위치·형상, 충분한 다중 시점 관측 | 현재 영상으로 실제 보정 가능 | 정보가 있는데 초기화·보호·감독 편향 때문에 수정하지 못하는가 |
| 정확한 면과 틀린 부분·결손·세부가 같은 주변에 존재 | 두 입력의 국소 상보성 | 필요한 수정과 인접 유효 구조 손상을 함께 줄이는가. 건물 전체 단일 품질값으로 가리지 않는다 |
| 깊이·법선이 국소적으로 편향되지만 영상에는 단서가 존재 | 사진 일관성·독립 기하가 편향을 제어 | 낮은 잔차·일치도가 정확성의 대리로 충분한가 |
| 가림·반복 무늬·불충분 baseline·반사·실제 결손 | 추가 가정이 일부 모호성을 제한 | 정보 부족과 활용 실패를 구분. 잘못된 현재성/세부를 만들어내지 않는가 |
| 정합 오차·표현 차이·mesh 추출 손실 | 정합·변수 전달·추출 수정으로 해결 가능 | 감독 선택 문제로 오진하지 않는가 |

앞의 네 조건은 보존·보정·세부·외관을 함께 묻는 비교의 중심이다. 마지막 두 조건은 어려운 사례인 동시에 **제안 제어가 불필요할 수 있는 경쟁 설명**이다. 현재 참조는 평가에만 쓴다.

## 2. 입출력·가정·실제 피드백

| 방법·역할 | 입력 → 출력 | 고정되는 것 / 수정되는 것 | 확인한 피드백과 범위 |
|---|---|---|---|
| **GeoGS: 직접 경쟁 골격** | 정합 LoD2·보정 RGB/pose·DA3 깊이 → planar GS·렌더·TSDF mesh | LoD2·pose·사전 생성 depth는 고정 / Gaussian 기하·외관·개수와 시각 깊이 공통 계수 변화 | 현재 RGB/depth 손실 추세가 DA3 가중에 되먹임. refinement에도 LoD 깊이와 구조 보호가 남는다. prior의 참·거짓을 국소적으로 다시 추정하는 제어와는 구분 |
| **AGS-Mesh: 구성요소 경쟁** | 동기화 실내 RGB·센서 깊이·단안 법선 → GS·mesh·렌더 | 센서/단안 예측·pose와 DNC 깊이 필터는 고정 / GS와 현재 기하 기반 ANR 선택 변화 | DNC는 입력끼리의 방향 일치, ANR는 현재 렌더 깊이 유래 법선과 예측 법선의 일치. sampled view마다 ANR 재계산; 누적 영구 기각 조건이 없어 재포함 가능 |
| **NeuRIS: 구성요소 경쟁** | calibrated 실내 RGB·영상 예측 법선 → SDF 표면·외관 | 입력 법선·pose 고정 / SDF·색·감독 사용상태 변화 | 현재 깊이·법선 → patch warp/NCC → 법선 감독 → 다음 기하의 되먹임. 기존 기각을 누적하여 다시 쓰지 않음 |

GeoGS는 현재 목적의 가까운 전체 비교 방법이지만, ALS/DSM으로 바꾼 실행은 별도의 입력 적응이다. AGS-Mesh와 NeuRIS를 동일 도시 자산 문제에 그대로 넣을 수 있다고 간주하지 않는다. 전체 원방법 비교와, 같은 복원 기반에 감독 제어만 넣는 비교를 구분해야 입력·표현 차이를 신규 제어 효과로 오인하지 않는다. [GeoGS 공식 구현](https://github.com/zqlin0521/GeoGS/tree/db40c95c657ec03ff21c83cb99cf39f4e90247a6), [AGS-Mesh §4](https://arxiv.org/html/2411.19271v2#S4), [NeuRIS §3](https://arxiv.org/html/2206.13597v2#S3).

## 3. 성공, 해결된 ablation, 실제 부족, 미평가를 분리

| 방법 | 성공·해결 범위 | 실제 보고된 한계·미해결 | 이 목표에서 아직 묻지 않은 것 |
|---|---|---|---|
| GeoGS | 희소 aerial/street views에서 geometry·외관 개선. §5.5/Table 7의 높이편향·수평이동·부분결손 LoD에서도 큰 구조 지표가 비교적 안정적. §5.4/Table 6의 prior-depth 제거와 보호 제거는 각각 악화 | Table 7에서 perturbation에 따른 외관 악화가 나타남. §6은 큰 pose 오차/강한 오정합과 비건물 영역의 한계를 명시 | 큰 구조 지표의 안정성이 오류 부분의 충분한 수정과 유효 부분의 비악화를 각각 입증하지는 않음. 다양한 표현·정확도의 자산, 혼합 국소 품질에서 가장 좋은 전역 조정의 충분성은 별도 질문 |
| AGS-Mesh | §5.3/Table 3: 2DGS F1 .6345 → 센서 depth .8861 → depth+normal .8880 → DNC .9061 → ANR .9092. 센서 감독 자체의 큰 도움과 추가 필터의 이득을 구분 | Appendix E: IsoOctree의 전체 기하 개선이 일관되지는 않음. Table 4의 단안 depth 대체는 센서 depth보다 낮음; 이것은 완성 방법의 공통 실패를 뜻하지 않음 | 오래된 독립 기하의 위치 편향, 법선은 맞고 높이가 틀린 면, 인접 유효 면 손상과 필요한 수정의 대응 평가 |
| NeuRIS | §4.3/Table 3: normal prior로 F-score .284→.724, geo-check로 .736. Fig.6–7의 chair leg/얇은 구조와 배경 면 동시 복원은 이미 해결한 사례 | §5: 장면별 수시간 최적화로 큰 규모에 제한. 이 감사에서 완성 NeuRIS가 정확한 prior를 기각해 실패한 실증 사례는 확인하지 못함 | 초기 오차·가림에 의해 유효 감독을 영구 기각하는 일이 실제로 중요한가. 독립 측정기하의 위치를 보정하며 유효 구조를 보존하는 문제는 원 입력 범위 밖 |

숫자는 원문 보고치이며 서로 다른 데이터·평가 문턱의 **방법 간 순위표가 아니다**. AGS Table 3의 감독 필터 비교는 같은 TSDF 조건이며 마지막 IsoOctree 행은 추출 변화이므로 따로 해석한다. NeuRIS의 얇은 구조 ablation 실패를 완성 NeuRIS의 잔여 실패로 재사용하지 않는다. [AGS-Mesh §5.3 및 Appendix E](https://arxiv.org/html/2411.19271v2#S5.SS3), [NeuRIS §4.3–5](https://arxiv.org/html/2206.13597v2#S4.SS3). GeoGS 전문 위치와 바이트는 §7에 기록했다.

## 4. GeoGS의 논문·코드·실제 개발 실행 구분

1. **논문 §3.4.2 식15:** visual-depth loss의 mask는 valid prediction을 나타내는 binary mask다. 식16–19의 시간 가변 공통 계수를 연속 DA3 픽셀 confidence와 혼동하지 않는다.
2. **공식 코드:** `--use_confidence` 기본값은 false이고 `--da_conf_path`가 따로 있다. 활성화하면 미리 읽은 DA3 confidence를 평균으로 정규화하여 DA3 L1에 적용한다. prior 유효성의 학습 중 재추정으로 부르지 않는다. [train.py 옵션](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L1259), [적용부](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L788).
3. **현재 P1/P2/P3 개발 실행:** D005/D0005 native 여섯 `train.log:22` 모두 confidence weighting disabled or maps missing을 기록한다. 기존 command/receipt 감사도 옵션·경로 부재를 확인한다. 이번에는 여섯 로그와 P2 대표 receipt를 다시 읽었다. 논문 저자 실험에서의 옵션 사용 여부는 여기서 확정하지 않는다. [기존 실행 감사](../geogs_causal_followup_v1/REFINEMENT_FRAMING_CLARIFICATION_ko_v1.md).
4. **깊이 prior와 보호:** 전자는 target에 대한 손실이며, 후자는 Gaussian 위치·회전·크기 gradient와 clone/split/prune 가능성을 제어한다. gradient 0.01배는 Adam의 실제 변위 0.01배 보장이 아니다. refinement depth weight=0도 초기/anchor와 보호 영향을 제거하지 않는다.

**P2는 기존 해법의 성공도 담는다.** `.005→.0005`에서 높은 부가 윤곽·내부 파편 감소, 일부 현재 상단 면의 위치·형상 개선이 관찰됐다. 같은 512 raw 평가에서 prediction→UAS 평균 거리는 .6511→.5834m, precision@.5m은 .5490→.5809로 개선했다. 반대로 recall은 .5209→.3804, F1은 .5346→.4598로 감소했다. 건물·지면·주변을 포함한 prism의 변화이며, F1 감소로 정성적 형상 개선을 부정하지 않는다. [P2 재분석 §1–6](../p2_geometry_reassessment_v1/REASSESSMENT_ko_v1.md).

P1/P2/P3 결과는 존재하는 개발 관찰이다. P3에서 저가중이 악화될 것이라는 일반 예측은 미검증 가설로 유지한다. 일부 제어 대비의 관측과 새로운 P3 기대를 혼동하지 않는다. 실제 P3는 조건별 DA3 가중 궤적도 다르므로 prior 변경만의 단독 인과로 해석하지 않는다. [제어 궤적](../geogs_p1p2p3_v1/CONTROL_TRAJECTORIES_ko_v1.md).

## 5. 우선 부족과 경쟁 원인 가설

아래는 새로운 실패 판정이 아니라 설계 우선순위다. 원인을 모두 확정한 뒤 설계해야 한다는 조건을 두지 않는다.

| 우선 질문 | 중요한 영향 | 경쟁 가설·상태 | 구별할 관찰 |
|---|---|---|---|
| **Q1 필요한 보정과 유효 구조 손상이 전역 제어로 동시에 해결되는가** | 보존·수정·세부의 직접 요구 | H1 국소 품질 차이를 공통 계수가 충분히 다루지 못함; H2 잘 선택한 전역 값/기존 gate로 충분함. 모두 비교할 가설 | 같은 위치·이웃의 보정량과 손상량을 paired 평가. 기존 조정의 성공 영역도 포함 |
| **Q2 틀린 감독을 줄이는 것으로 충분한가** | 현재 기하·세부 위치 | H3 DA3/단안 감독의 bias; H4 정확한 감독도 보호·변수 전달·opacity 혼합 때문에 작동하지 못함 | 입력 target, 현재 학습 깊이, 명시 표면을 동일 가시 광선에서 대응; 선택 오류와 전달 오류 분리 |
| **Q3 재판정이 필요한가** | 기각 뒤 회복 가능성 | H5 현재 잘못된 기하를 기준으로 맞는 감독을 기각; H6 지속 기각이 유해 감독 재유입을 막음. NeuRIS의 기각 지속은 코드 사실, 우리 조건의 실패 여부는 미평가 | 동일 초기·photo check에서 지속 기각과 재포함만 비교; 좋은 prior의 재포함과 나쁜 prior의 재유입을 모두 집계 |
| **Q4 문제의 시작점이 제어 이전/이후인가** | 방법 기여의 잘못된 귀속 방지 | H7 정합/visibility/초기 표면화; H8 depth rendering/표현/TSDF extraction; H9 실제 정보 부족 | 정합·ray convention·visibility를 먼저 기록. 최종 mesh만 비교하지 않고 target→학습 depth→surface의 손실 위치 확인 |

P2 골의 얕아짐은 저장된 final expected depth에서도 나타났으므로 **그 관측량에 한해서** TSDF에서 처음 발생한 변화는 아니다. 그러나 prior ray와 GS ray의 반 픽셀 차이, anchor 다중면, 가림, DA3 batch 상관, expected-depth 혼합이 남아 있다. DA3의 단독 원인이나 정확한 초기 골의 파괴로 확정하지 않는다. [기존 DA3 감사 §2–6](../geogs_causal_followup_v1/DA3_INPUT_AUDIT_ko_v1.md).

## 6. 질문별 최소 비교와 기각·축소 조건

동일 입력·초기 상태·감독 정보·정합·renderer·추출·계산 예산을 맞춘 **구성요소 비교**가 인과 질문의 우선이다. 서로 다른 전체 pipeline의 실행 비교는 외적 충분성 검토이며 효과 분해와 구분한다. 추가 normal/confidence 생성 비용도 예산에 포함하고 모든 후보가 같은 정보를 받을 수 있게 한다.

| 질문 | 필요한 최소 대비 | 제안 원리 후보 | 기각·축소 조건 |
|---|---|---|---|
| Q1 전역 설정으로 충분한가 | 동일 초기에서 충분히 조정한 prior-depth weight × 보호강도. 그다음 고정 입력 confidence 또는 기존 DNC/ANR·photo gate 중 조건에 맞는 최선 제어 추가 | 관측이 지지하는 수정 방향·범위에만 기존 기하 제약 완화 | 적정 전역 설정이나 기존 제어가 같은 손상에서 같은 보정을 달성하면 새 제어 필요성 축소 |
| Q2 편향인가 전달인가 | 기존 신뢰도 제어 vs 동일 제어+감독 target bias 보정 vs 동일 제어+기하 변수 전달/제약 변경. 첫 비교는 원인에 맞는 한 가지 변경만 | confidence가 높아도 지속되는 깊이 위치 bias를 분리하고, 근거가 있는 기하 자유도에 수정 전달 | 정합·depth convention 또는 기존 bias/gradient 해법만으로 회복하면 해당 기존 요소 채택. 새 신뢰도 추정 주장은 철회 |
| Q3 누적 기각이 부족한가 | 같은 NCC 기준·예산에서 NeuRIS식 지속 기각 vs 재포함 허용 | 현재 기하의 변화로 다시 검정할 때의 회복과 오염을 통제하는 규칙 | 단순 재포함으로 충분하면 복잡한 반복법 불필요. 재유입 손상이 이득보다 크면 지속기각 또는 제한된 재검정 채택 |
| Q4 표현/추출/관측 한계인가 | 동일 학습 결과의 현재 depth와 surface 차이 감사; 승인 후에만 하나의 추출 또는 표현 변경 비교 | 필요할 때만 표면 위치와 세부를 잃지 않는 감독 전달·표현 원리 | 입력에 단서가 없으면 자동 세부 복원 주장을 축소. 추출 변경만의 효과라면 학습 제어 기여로 주장하지 않음 |

여러 비교를 한 번에 모두 실행하자는 계획이 아니다. Q1 성공/부족을 먼저 보고 Q2–Q4 중 해당 현상을 가장 잘 구별하는 비교를 선택한다. GT로 gate·bias·parameter를 만들지 않는다. 평가 단위는 동일 물리 영역에서 accuracy/completeness, 유효 구조 손상, 필요한 수정, 관측 가능한 세부, 현재성, 외관, 시간/메모리를 분리한다. 개선·악화·참조 미피복을 모두 남긴다.

**방법 기여의 현재 판정:** 보존과 보정을 동시에 요구하거나 감독을 국소 조절하는 것 자체는 선행이 이미 다룬다. 감독과 수정 범위를 연결한다는 일반 아이디어도 새로운 경쟁 문헌까지 대조해야 한다. 그러나 혼합 품질에서 어떤 기존 규칙의 충분성이 깨지는지 설명하고, 이를 겨냥한 하나의 보정/제약 규칙이 적정 기존 해법보다 유리한 보정–손상 관계를 보이면 방법 기여 후보가 된다. 지금은 구체 후보와 기각 계획이며 우월성·박사학위 충분성의 확정 판정이 아니다. 문제 설정·원인 설명·방법·검증의 기여를 나누되 평가 항목 분리 자체를 알고리즘 신규성으로 세지 않는다.

## 7. 출처와 검토 범위

- **GeoGS:** Zhang, Wysocki, Jutzi, *ISPRS JPRS* 240 (2026), 184–201. [출판사 원문](https://www.sciencedirect.com/science/article/pii/S0924271626003588). §3.4.2/PDF6–7, §5.4/Table6/PDF15, §5.5/Table7/PDF16, §6/PDF16–17. 기존 [첨부 PDF](/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf) SHA256=`21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`를 이번에 재확인하고 기존 추출 텍스트 `/tmp/jbgs-geogs-attached-fulltext-20260907.txt`의 해당 절을 직접 읽었다. 코드 pin=`db40c95c657ec03ff21c83cb99cf39f4e90247a6`; 로컬 원본 `train.py` SHA256=`4c09f6a117d7f4a13e3bd3c5d9eb49b1830e428950a53c0f86be4001637c7a10` 재확인. 공식 웹 source도 열람했다. 논문은 median depth를 서술하지만 해당 개발 실행의 저장 깊이는 별도 감사에서 expected depth로 확인됐으므로 혼용하지 않는다.
- **AGS-Mesh:** [원문 v2](https://arxiv.org/html/2411.19271v2), §4.1–4.4, §5.1–5.3/Tables1–4, Appendix E. 공식 pin=`93fda851a20cf0bd5fce642c46da0c83c637165e`. [train.py](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py#L118) L118–169의 깊이 mask/ANR와 L213–242의 densification/optimizer 확인. 이번 세부 코드는 공개 2DGS trainer 범위이며 Splatfacto 구현 전체 동등성이나 논문 수치 재현을 주장하지 않는다.
- **NeuRIS:** [원문 v2](https://arxiv.org/html/2206.13597v2), §3.2/식6, §4.3/Table3/Figs6–7, §5. 공식 pin=`fab2cc4ca45847fbee7490e978d3c60c582123b1`. [exp_runner.py](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L320) L320–350에서 현재 NCC·이전 confidence·30도 normal 차이의 결합 및 기각 지속을 재확인. 변수명 `normals_gt`는 여기서 단안 prior 입력이며 평가 GT를 새 설계의 감독으로 허용한다는 뜻이 아니다.
- **로컬 실행:** P1/P2/P3 주18개 결과/제어 trace와 후속 재분석은 기존 개발 자료다. 이번에는 문서·공식 source·제시한 기존 log/receipt만 읽었으며 payload 전수 hash 검증이나 정량 재계산을 수행하지 않았다.
- **읽기 이슈:** 기존 GeoGS 추출 텍스트를 찾기 위한 `/tmp` 파일 목록 조회에서 일부 다른 서비스의 private directory/socket 접근 오류가 출력됐다. 해당 경로는 조사하지 않았고 발견된 작업 관련 기존 텍스트만 읽었다. 새 추출·프로젝트 도구·학습·추론·렌더·재구성·서비스 변경·Git commit은 없었다.

`scientific_verdict: null`
