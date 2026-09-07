# P3 재구현·개발 이슈

2026-09-07 · 모든 항목은 비확증 개발 기록이며 `scientific_verdict: null`.

| ID | 문제 → 확인된 원인 | 조치 | 상태·남은 제한 |
|---|---|---|---|
| WV-P3-I01 | 공식 `whuwuteng/ChangeUpdateJN` 공개 URL/API가 HTTP404. commit·저자 설정·checkpoint를 확보하지 못함 | 공식 논문을 읽고 원문 기반 모듈과 구현 선택 대응표 작성. 저자 코드 재현 표기 금지 | OPEN. 원문 핵심 구현 가능, 저자 구현과 동등성 미확인 |
| WV-P3-I02 | P3 ALS visibility 센서 입력 미결속. 원 LAZ에 유효 GPS time·strip ID는 존재하나 bounded 파일명 검색에서 trajectory 후보0 | exact raw membership과 LAS sample·검색범위 기록. optical origins/topology 없는 원방법 실행은 거부 | OPEN. raw13/work5838 파일 검색 완료; data30000 제한 도달. 조사 밖 부재를 단정하지 않음 |
| WV-P3-I03 | 첫 preflight 실행에서 JSONDecodeError 발생. 신규 설정 regex의 `\\.pos` JSON escaping이 잘못됨 | JSON escape 수정, Docker 구문 검증 후 별도 `PHD-WU-VALLET-P3-v1-r2`에서 재실행 | RESOLVED. 첫 console log/source snapshot 유지. r2 입력 동결47.93초 완료 |
| WV-P3-I04 | 기존 P2 sample builder는 tile(4,4)·66뷰·P2 unit ID에 결합 | P3용 새 builder 작성. tile(3,4),157뷰, 원점군 원행 전체 검증 | RESOLVED. 기존 P2 코드는 변경하지 않음 |
| WV-P3-I05 | 실행 전 리뷰에서 B의 축소 camera K/width/height가 provenance에 반영되지 않고, source mask 기록은 마지막 source로 덮임을 발견 | 실제 렌더 K/크기와 원본 값 분리; source별 mask count/hash 저장 | RESOLVED_BEFORE_RUN. source별 학습 분모 차이는 비교 한계에 유지 |
| WV-P3-I06 | B 렌더러의 수정 CUDA를 시작 전 expected hash와 대조하는 guard 누락 | audited adapter manifest·CUDA bytes 전용 snapshot, 실행 시작 hash 검증 추가 | RESOLVED_BEFORE_RUN. 현재 기존 파일과 감사 해시가 일치함도 확인 |
| WV-P3-I07 | 평가 `laspy.parse_crs()`가 동일 이미지의 미설치 optional pyproj에 의존하는 과거 실패 위험 | GeoKey VLR 직접 판독으로 교체, 결손·큰오차·경계·CRS 테스트7개 Docker PASS | RESOLVED_BEFORE_RUN. datum/epoch bridge 정확도는 미보정 |
| WV-P3-I08 | 원문 거리 문턱·ray 집계·small-region filter·PSMNet checkpoint 누락 | 미기재 선택을 config/반환 provenance에 공개하고 finite sampled ray component로 한정 | OPEN_FOR_FULL_REPRODUCTION. 통제 테스트9개 통과는 P3 원재현·성능 입증 아님 |
| WV-P3-I09 | 첫 ray fixture 실행이 source snapshot에 `.git`이 없어 `git rev-parse` 실패 | wrapper가 제공하는 고정 `JBGS_SOURCE_GIT_HEAD`를 우선 사용하고 image/snapshot 정보도 기록 | RESOLVED. 첫 로그/snapshot 보존. `PHD-WU-VALLET-RAY-FIXTURE-v1-r2`에서 5개 통제 장면의 source-labelled 갱신 점군 생성 PASS |
| WV-P3-I10 | 첫 참조평가의 종료 hash 재검사에서 `str`에 `.open()`을 호출해 AttributeError 발생 | hash 함수 입력을 Path로 정규화, 별도 `PHD-WU-VALLET-P3-EVALUATION-v1-r2` 경로에서 재실행 | 첫 계산/그림/failure.json/log/snapshot 보존. 성공 상태는 r2 receipt로 확인하며 첫 실행을 완료로 보고하지 않음 |
| WV-P3-I11 | 첫 영상 sensor mesh 대상668에서 P3 안 native depth3픽셀, 인접 삼각형0개. 깊이/edge 문턱 이전의 입력 피복 부재 | v1 실패 보존. v2는 동결 A40뷰 전부의 기하 피복을 기록하고 hash순 첫64face 이상 뷰 선택으로 규칙 개정 | 깊이 관측 부재/앞쪽 표면은 확인했으나 가림의 정확성은 별도. PSMNet 원재현이나 ALS 센서 입력 확보를 뜻하지 않음 |
| WV-P3-I12 | 첫 브라우저 QA에서 모바일 viewport390px에 page410px overflow. 갤러리 자체 가로 스크롤은 정상 | receipt의 강제 한줄 CSS를 줄바꿈으로 수정, 새 viewer r2 및 새 QA 실행 | RESOLVED. r2에서359항목 PASS·189파일·9스크린샷. 기존 viewer/QA 실패 기록 보존. QA 조건은 완화하지 않음 |
| WV-P3-I13 | UAS header EPSG:32632와 작업 표기 EPSG:25832의 datum/epoch 연결이 미보정 | 원 raw-shift 수치 비교로 한정하고 화면·반환에 CRS 차이 명시 | OPEN_FOR_CALIBRATED_ACCURACY. 평가 참조를 이용한 정합/문턱 조정 없음 |
| WV-P3-I14 | Native ALS의 작은 참조 편차가 GS 역투영 점군에 유지되지 않음. fixed geometry arm에서도 존재 | renderer가 ray-plane hit의 정규화 가중평균을 깊이로 산출함을 코드로 확인; source/native·초기 표현·학습·readout 분리 | OPEN. 다층 혼합/정렬/지지 문제는 가능한 원인이며 각 기여량 미확정. 0.15m 중심 이동 cap을 최종 표면 변형 한계로 해석하지 않음 |
| WV-P3-I15 | 최종 metadata seal의 첫 실행에서 닫는 괄호 누락으로 SyntaxError | 괄호 수정 후 Docker에서 다시 실행 | 원 실험/참조/뷰어 산출물 접근·수정 전 실패. 수치 결과에는 영향 없음 |

일반 경로 확인 중 존재하지 않는 이전 P2 config/driver 이름을 조회한 실패는 읽기 전용 탐색이었다. `rg --files`로 실제 파일명을 확인했으며 기존 상태는 변경하지 않았다. 문헌 PDF는 web의 크기 제한 후 공식 호스트에서 직접 열람해 확인했다.
