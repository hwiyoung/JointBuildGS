# 원문 접근·논증 검토·보존 확인

2026-09-09 · `PHD-INFORMATION-CONTRIBUTION-v1` · `scientific_verdict: null`

## 원문/구현 접근과 근거 경계

| 항목 | 실제 발생과 조치 | 남은 경계 |
|---|---|---|
| Schenk2002 웹 PDF timeout | 기존에 저장된 원문 추출본을 재열람. 2007은 웹 PDF 전문 재확인 | 2007은 실자료 없는 개념 논문. 성능 증거로 쓰지 않음 |
| Zhou/Wu2026 web PDF 오류 | 기존 원문 PDF를 CPU Docker에서 재열람 | 원문 전체 파이프라인 실행·독립 재현 아님 |
| LGSM HTML404·FusionX3 HTML timeout | 공식 저자/학회 PDF 다운로드 후 CPU Docker pypdf 추출 | LGSM 실행 코드 미확인. 타 논문 코드를 대신 연결하지 않음 |
| FusionX3 첫 API422 | 기본 branch가 main이라는 추정 오류. metadata의 master 확인 후 고정 commit 읽음 | 현재 공개 코드와 저자 모든 실험 설정의 동등성 미검증 |
| DN-Splatter 공식 PDF web 오류 | arXiv v3 전문으로 대체 | 현재 repository의 AGS 통합을 원논문 실행으로 소급하지 않음 |
| 임시 source 경로 추정 오류/권한 오류 | 알려진 경로·고정 공식 raw source로 읽기 범위 수정 | 서비스 디렉터리 권한 변경 없음 |
| HelixSurf 스크립트 경로 오류 | scripts가 아닌 run_scripts/next_mvs.sh 확인 | 실제 upstream 재매칭과 camera 고정을 구별 |
| GitHub 출력 head의 curl23 | 파이프 종료로 broken pipe; 이후 고정 SHA source 정상 읽기 | source 손실이나 method 실행 실패가 아님 |
| GeoGS의 옛 전문/실험 상태 | 현재 출판 PDF, 코드 및 P2/요인 대비 보고 재확인 | ALS 적용과 native LoD2 실험을 분리. 이번 payload 재측정 없음 |
| GaussianUpdate/Wu 등 code 가용성 | 이번 읽기에 실제 확인한 것만 source note에 명시 | 이전404/미공개를 이번 실시간 재검증으로 바꾸지 않음 |

정확한 원문 버전·페이지·표·그림·소스 commit 및 PDF SHA는 [고전](CLASSICAL_CHAIN_ko_v1.md), [기하](GEOMETRY_CHAIN_ko_v1.md), [외관/현재성](APPEARANCE_VALIDITY_CHAIN_ko_v1.md)에 기록했다. 검색 결과와 기존 요약은 색인이며 핵심 문헌 주장 자체는 원문/공식 소스로 확인했다. 모든 관련 분야를 전수 검색했다는 주장은 하지 않는다.

## 교차 논증 검토와 반영

통합 담당 외 문헌 담당들이 입력/원인/필요성 문서를 교차 검토했다. 다음 교정을 반영했다.

- '현재 영상 파생 기하가 정확하지 않다'를 '정확성이 자동 보장되지 않는다'로 교정했다.
- 반복·표현 변경이라는 연구 주제가 해결됐다는 표현을, 그 방식을 쓰는 선행 해결책이 있다는 의미로 제한했다.
- SpotLessSplats의 삭제 대상을 원관측이 아닌 장면 표현의 유효 지지로 명확히 했다.
- BayesRays의 고정 모델 민감도 진단을 현재 RGB 차이 기반 갱신과 분리했다.
- GS 표현의 native depth/normal/opacity/support와 추출된 표면을 구분했다.
- GS4B의 저자 원인 해석과 GeoGS 지역 악화의 원인 미분리를 분리했다.
- 일반적인 '우리만의 방법이 필요하다' 대신 기존 설명/해결 뒤 남는 원인에 추가 분석·변경이 기여할 조건을 적었다.
- 서로 다른 논문에서 확인된 연결을 동일 입력의 한 인과 실험으로 합치지 않는다는 경계를 추가했다.
- Wu2026의 오염된 학습 label 정제 사례를 구체적 연결로 넣었다. 이미 해결된 연결과 그 뒤 미분리 원인을 구별했다.
- 사례 선택에 추적 가능성뿐 아니라 원래 복원 목적에서의 중요성·반복성을 포함했다.
- 참조 기반 oracle을 모든 연속 재추정의 일반 상한으로 사용하지 않도록 교정했다.

이는 문헌 해석과 논증의 QA이며 방법 성능의 과학적 verdict가 아니다.

## 보존 범위와 문서 검사 방법

작업 전에 기존 `docs/experiments/phd` 아래 Markdown의 SHA-256 목록과 tracked binary diff를 `/tmp/jbgs-info-chain-preexisting-20260909.sha256` 및 `/tmp/jbgs-info-chain-preexisting-20260909.diff`로 기록했다. 새 소유 경로는 `docs/experiments/phd/information_to_contribution_v1/`뿐이다. 기존 thesis dirty 수정, 문헌 카드, 상보성 문서, 진행 중 구현/결과는 수정하지 않았다.

문서 검사는 기존 Docker image `jointbuildgs:geogs-official-db40c95-compat-v1`, ID `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`의 일회 CPU 컨테이너에서 수행한다. `/repo`를 읽기 전용으로 마운트하고 `--network none --cpus 1 --memory 512m`를 사용한다. Python 표준 라이브러리로 새 Markdown의 로컬 링크, 제목·null 지위, 빈 파일/미완료 표시, 원치 않는 일본어 문자, 단순 whitespace를 검사한다. 로컬 링크 검사는 파일 존재 검사이며 외부 URL 가용성·모든 원문 해석 또는 Mermaid의 실제 화면 렌더를 인증하지 않는다.

기존 문서 hash와 tracked diff 비교도 수행한다. 이는 해당 문서와 tracked 변경 보존의 검사이며 모든 외부 payload·서비스 상태를 새로 감사한 것은 아니다. 새 학습·렌더·방법 실험, stage·commit·push, 서비스 lifecycle 변경은 없다.

첫 문서 검사에서는 이 문서의 검사 설명에 들어 있던 미완료 표시 예시를 실제 미완료 상태로 감지해 실패했다. 실제 빈 문서·누락 링크는 없었다. 설명 문구를 일반화하고 같은 검사를 다시 수행했다. 첫 실패를 문헌 내용의 오류나 방법 실행 실패로 해석하지 않는다.

## 완료 확인

2026-09-09 16:34:30 KST(07:34:30 UTC) 재검사 결과:

- **PASS:** 새 Markdown 9개, 로컬 링크 50개, 제목/null 지위·미완료/문자·whitespace 검사 오류 0개.
- **PASS:** 작업 전 기록한 기존 Markdown 222개의 SHA-256 일치.
- **PASS:** 기존 tracked `git diff --binary`가 작업 전 스냅샷과 동일.
- **PASS:** `git diff --check` 오류 없음. 이 명령은 tracked diff 검사이며 새 파일 검사는 위 Docker 검사와 구분한다.
- 논증 교차 검토 완료. 새 방법 성능·원인 전체·신규성의 실증 verdict는 하지 않았다. `scientific_verdict: null`.

임시 보존 검사 파일은 장기 백업을 의미하지 않는다. Docker는 CPU 문서/PDF 처리에만 사용했고 새 연구 방법 실행·GPU 사용·서비스 변경은 없었다.
