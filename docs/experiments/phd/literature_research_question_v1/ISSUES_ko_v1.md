# 문헌 접근·검토 이슈와 검증

2026-09-09 · `PHD-LITERATURE-RQ-v1` · `scientific_verdict: null`

접근 실패를 문헌의 기능 부재로 해석하지 않는다. 다음은 이번 작업에서 실제 만난 실패·판본 차이와 조치다.

| ID | 문제 | 조치·해결 상태 | 남은 해석 경계 |
|---|---|---|---|
| LIT-01 | GeoGS 옛 기여문서의 전문 미확보/장면 결과 없음 | **해결:** 기존 첨부 출판 PDF SHA를 대조·직접 읽음. 현재 PAPER/P2/FACTOR 문서 확인 | 로컬 실험 payload 전체 재감사/성능 재계산은 이번 범위 아님 |
| LIT-02 | GS4Buildings 검색 HTML 캐시는 Coming soon | **해결:** git HEAD·raw README·실제 source tree로 code 공개 확인 | paper/default schedule·normal enable 차이 카드 기록 |
| LIT-03 | Zhou web PDF 오류; Wu2026 39MB web 크기 제한 | **해결:** 공개 PDF 직접 download, CPU Docker 추출/필요 페이지 시각 확인 | 원문 SHA/버전 카드 기록; author 전체 pipeline 코드 동일성 미확인 |
| LIT-04 | 기존 Docker image의 fitz/pypdf 없음으로 첫 PDF extraction 실패 | **해결:** 기존 service/host 환경 변경 없이 일회 Docker 임시 디렉터리의 pypdf 사용 | host dependency 설치 없음; 연구 도구 실행/학습 아님 |
| LIT-05 | HelixSurf CVF403·arXiv web 크기 제한; GS4 PDF 재열기 실패 | **해결:** author/기관 원문 download 후 Docker 해석 | Helix 검토판은 arXiv v2, 최종 CVF와 모든 문장 동일성 미확인 |
| LIT-06 | 3DGS/2DGS web PDF 경로 internal error | **부분 해결:** 버전 고정 arXiv HTML 전문+공식 코드로 확인 | 카드에 PDF page 미확인 명시, HTML section/table/figure로 인용 |
| LIT-07 | AGS PDF page8 web screenshot timeout, SpotLess PDF 후속 find 오류 | **부분 해결:** 이미 확인된 PDF text 및 HTML을 대조 | AGS screenshot 성공으로 기록하지 않음. SpotLess HTML/PDF 그림번호 차이 명시 |
| LIT-08 | Wu2026 출판 페이지의 ChangeUpdateJN 공개 주소/API404 | **미해결:** 원문 방법만 확인, 공개 코드 미확인으로 유지 | 코드 접근불가로 성능/기능 부재 판단 금지 |
| LIT-09 | ARSGaussian 공식 code Coming soon; GaussianUpdate training code 못 찾음 | **미해결:** ARS raw/tree로 현재 상태 확인, GaussianUpdate는 미확인 유지 | 논문/보충자료만으로 upstream 실행 경로 일부 확정 불가 |
| LIT-10 | GitHub tree 출력을 head로 자르면서 curl23 broken pipe | **해결:** 출력 파이프 종료 때문; 이후 전체 입력을 소비하는 제한 출력 사용 | 서버 접근실패나 source 손실로 분류하지 않음 |
| LIT-11 | 광범위 외부 source 검색에서 permission error | **해결:** manifest가 가리키는 source로 검색 범위 축소 | 기존 파일 permission 변경 없음 |
| LIT-12 | SceneEdited 본문/보충 outdated map 수, ARS 일부 표, GeoGS Table6 값 불일치 | **미확인 유지:** 서로 합쳐 임의 기준값을 만들지 않음 | 카드에 실제 판본/표와 모순 위치 기록; 저자 해명 없음 |
| LIT-13 | 모델·분할·source snapshot이 논문 당시와 다를 수 있음 | **부분 해결:** HEAD/원문판/읽은 파일·미확인 경로 기록 | code 공개/읽기와 전체 재현 성공을 구분 |

## 독립 내용 검토

문헌 담당과 별도 담당이 통합표 및 root 카드의 원문–해석 경계를 교차 검토했다. 확인된 오류를 다음처럼 교정했다.

- 2DGS에서 Deep Blending을 데이터셋으로 쓴 부분을 비교 방법으로 교정했다.
- Zhou의 D2→D1 비교→change/search 확장→재매칭 경로를 통합 흐름에 복원했다.
- SpotLessSplats의 appearance latent/MLP, Crab(1)/(2) 분할 예외, UBP 활용도 정의를 추가했다.
- VCR-GauS 기존 normal 감독에도 제한된 위치 gradient가 있음을 반영했다.
- SRDM 정합 등 기존 부품, CL의 국소 커널·이력복구, Helix occupancy sampling의 기여 위치를 교정했다.
- AGS ablation의 3장면 분모를 전체 6장면과 구분했다. 근거가 없는 구체 장면 이름은 사용하지 않았다.
- SceneEdited의 GT-mask oracle baseline과 predictor/정합/point membership 변수를 명확히 했다.

이 검토는 문헌 해석 QA다. 논문 알고리즘의 새 실행·성능 재현 시험은 아니다. 문헌의 미확인 사항과 공백 후보의 scientific verdict를 기술 QA로 채우지 않는다.

## 문서·보존 확인

2026-09-09 00:35 KST에 기존 `jointbuildgs:geogs-official-db40c95-compat-v1` 이미지의 일회 CPU Docker에서 Python 표준 라이브러리로 검사했다. 저장소를 읽기 전용으로 마운트하고 네트워크를 차단했으며 GPU는 사용하지 않았다.

- **PASS:** Markdown 27개, 논문 카드 19개의 공통 1–6절 및 `scientific_verdict: null` 확인.
- **PASS:** 로컬 링크 124개 확인, 누락 경로 0개. 외부 사이트의 영구 가용성이나 문헌의 모든 주장을 인증하는 검사는 아니다.
- **PASS:** 작업 전 기록한 기존 thesis 문서 12개의 SHA-256 일치. 기존 tracked 수정의 `git diff --binary`도 작업 전 스냅샷과 동일했다. 전체 외부 payload의 해시 감사나 서비스 상태 검사는 수행하지 않았다.
- **PASS:** `git diff --check` 오류 없음. 이 명령의 검사 범위는 tracked diff이며, 새 문서의 링크·구조 검사는 위 Docker 검사로 확인했다.
- 새 학습·렌더·방법 실험, stage·commit·push는 수행하지 않았다. 이번 산출물은 이 새 문서 디렉터리에만 작성했다. `scientific_verdict: null`을 유지한다.
