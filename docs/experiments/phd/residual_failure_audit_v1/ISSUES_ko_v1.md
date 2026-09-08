# 잔여 실패 감사 — 이슈와 확인 범위

2026-09-09 · `scientific_verdict: null`

## 1. 해석 정정

| 항목 | 확인한 문제 | 이번 조치 |
|---|---|---|
| RFA-01 | 이전 네 표현이 입력 조건·동작·출력·중간 오류를 혼합 | 실패명과 실제 평가 출력을 분리. 새 실패 개수를 고정하지 않음 |
| RFA-02 | Zhou의 변화 누락을 최종 형상 결손처럼 확대할 위험 | 변화 label/시차 근거와 최종 표면 손상 평가를 구별 |
| RFA-03 | CL의 dilation을 새로 넣을 기능처럼 읽힐 위험 | 원형 §3.1에 이미 적용, Table4 no-dilation은 제거 실험이라고 명시 |
| RFA-04 | Wu Fig15의 sensor mesh 변화 표시를 최종 fused mesh 손상처럼 읽을 위험 | Fig16 fused point cloud와 분리. 독립 갱신 품질 평가 미확인 명시 |
| RFA-05 | NeuRIS/VCR/DebSDF/GaussianUpdate 제거 실험 오류를 full 잔여로 사용할 위험 | 이미 개선한 문제로 제외. VCR 반투명 창 full 사례는 별도로 추가 |
| RFA-06 | GeoGS 지역 지표 열세를 유효 구조 손상·낡은 기하 잔류로 설명할 위험 | 비교 열세만 인정. 허용치·출력 종류별 순위 차이와 평균 성공을 동시 기록 |
| RFA-07 | SLS UBP 압축 조건의 손실을 모든 기본 full에 일반화할 위험 | 설정 실패와 full의 mask/그림자 사례를 구별 |
| RFA-08 | SLS의 그림자 부분 검출을 최종 렌더 잔류로 확대할 위험 | 원문 직접 진술인 부분 검출로 기록. 최종 렌더 잔류량을 확인한 것으로 쓰지 않음 |

## 2. 접근·도구 이슈

- GeoGS DOI 웹 열기 오류: 이미 확보된 출판 PDF 18쪽을 CPU Docker에서 재열람했다. 원본 SHA와 읽은 페이지는 원장에 기록했다.
- Docker image에 pypdf가 없어 첫 읽기가 `ModuleNotFoundError`로 종료됐다. 일회 컨테이너의 `/tmp`에 `pypdf==6.0.0`을 설치한 후 PDF12·13·16·17 읽기에 성공했다. host 환경과 기존 image/service는 변경하지 않았다.
- 사용 Docker image: `jointbuildgs:geogs-official-db40c95-compat-v1`, ID `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`. PDF 원본은 read-only mount, dependency는 일회 tmpfs를 사용했다.
- 추가 NeRF-on-the-go HTML 접근 오류: 새 검토 완료 문헌으로 세지 않았다.

## 3. 보존과 검증 범위

새 문서는 `docs/experiments/phd/residual_failure_audit_v1/`에만 작성했다. 기존 문헌 카드·학위 초안·결과 보고를 수정하지 않았다. 다음 읽기 전용 snapshot을 기준으로 보존을 검증한다.

- 기존 PhD Markdown: `/tmp/jbgs-residual-audit-preexisting-20260909.sha256`
- 기존 tracked 변경: `/tmp/jbgs-residual-audit-preexisting-20260909.diff`

문서 파일·링크와 기존 문서 SHA/변경내용을 검사하며 과학적 검증으로 해석하지 않는다. 새 학습·장면 렌더·방법 실험·기존 결과 재계산은 없다. stage/commit/push와 서비스 조작도 없다. 최종 문서 검증 결과는 아래에 기록한다.

2026-09-09 검증 결과: **PASS**. 신규 Markdown 4개, 로컬 파일 링크 10개, 각 문서의 null verdict와 공백 형식 확인. 기존 PhD Markdown 231개의 SHA256이 모두 동일하고, 기존 tracked binary diff도 snapshot과 동일하다. `git diff --check` 통과. 고전·기하·외관/진단 문헌의 교차 검토 정정을 반영했다. 이 결과는 문서·보존 검증이며 과학적 verdict가 아니다.
