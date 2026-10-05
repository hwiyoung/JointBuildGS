# 감사 범위·예외·보존

2026-09-10 · PHD-GEOGS-EXPECTATION-AUDIT-v1 · scientific_verdict: null

## 검증된 작업 범위

- Docker에서 기존 입력 manifest·초기화 좌표·원 ID·저장 거리만 검사·재집계했다. 실행 자체는 1회 성공했다.
- 새 학습·장면 렌더·메쉬 추출·정합·거리 질의·방법 실험을 시작하지 않았다.
- 기존 payload와 repo는 컨테이너에 read-only로 마운트했다. 네트워크·GPU 없이 새 감사 출력 경로만 쓰기 허용했다.
- P1/P2/P3 기존 단면·사진·저장 montage와 공식 PDF·코드를 열람했다. 후속 방법론·scientific verdict를 확정하지 않았다.

## 열람 중 예외와 해결

- 논문 그림을 읽기 위해 PDF 페이지만 Docker에서 raster화했다. 장면을 새로 렌더한 것이 아니다. PyMuPDF 1.26.4는 일회용 컨테이너의 임시 /tmp에만 설치했다.
- 첫 PDF 변환은 tmpfs noexec의 공유 라이브러리 mmap 제한으로 실패했다. 임시 /tmp를 rw,exec로 바꾼 후 성공했다. 원 PDF·호스트 의존성·프로젝트·서비스는 변경하지 않았다.
- 일부 추정 검색 경로(freeze_sources.py, prepare_inputs.py)는 없었다. rg로 실제 evaluation/freeze_baselines.py와 input/prepare.py를 찾아 읽었다.
- JSON 조회 도구 jq가 없어 읽기 명령으로 대체했다. 정적 감사 Python은 기존 Docker 의존성을 사용했다.

## 남은 분석 한계

- 초기점 50개 전달은 해당 창의 정보 일부가 들어갔다는 확인이다. 골별 충분한 표본·다중시점 가시성·깊이 감독의 정확성·연속 표면 보존을 증명하지 않는다.
- 공식 LoD2 방법과 ALS 표면화 적응 결과를 분리한다. 후자의 잔여가 전자의 보편적 한계인지는 미확인이다.
- raw/post는 동일 참조 좌표·원 ID를 대응했다. 해당 제거 성분의 의미·현재 유효성까지 검증하지 않았다. 두 조건에서 precision 개선도 함께 있다.
- 기존 all-view MVS는 이 GeoGS의 직접 dense 입력이 아니다. 평가 UAS와 평가 사진은 학습 정보 존재의 증거로 사용하지 않는다.
- 512 단면과 1024 재집계를 분리한다. 미세 단면 형상은 정성 관찰이며 독립 반복·새 기하 점수로 제시하지 않는다.
- 기존 P1/P2/P3는 개발 자료다. 관측 실패·미평가·미확인과 과학적 신규성 판정을 구분한다.

## 원문 내부 주의점

- Table6D의 기본 F1@.2=.459는 같은 표 A/B/C의 .469와 다르다. 핵심 ablation 인용은 B를 사용했다.
- Fig10의 M3C2 숫자는 Table4 점군 수치와 일치한다. 메쉬 수치로 인용하지 않았다.
- Fig11의 창문 확대는 Rendered Image다. metric 3D 세부 생성의 직접 근거로 인용하지 않았다.
- Gaussian 점군과 TSDF 메쉬의 점수 차이는 입력/표본/표면 정의가 다르므로 곧바로 추출 손실량으로 바꾸지 않았다.

## 보존 확인

검사 전 기존 PhD Markdown 251개의 SHA 목록과 tracked binary diff를 임시 경로에 저장했다. 완료 시 248개 문서의 SHA가 같았고, 아래 진행 중 작업의 문서 3개는 달라졌다. 이 감사와 하위 검토 작업은 세 파일을 수정하지 않았으며 변경 주체를 추정해 확정하지 않는다. 원상 복구·덮어쓰기 없이 현재 바이트를 유지했다. 기존 dirty thesis 문서 4개를 포함한 tracked binary diff는 검사 전후 동일하며 git diff --check도 통과했다. 이번 신규 경로는 다음 세 곳뿐이다.

- docs/experiments/phd/geogs_expectation_audit_v1/
- configs/phd/geogs_expectation_audit_v1/
- scripts/phd/geogs_expectation_audit_v1/

동시 변경을 관측한 경로는 기존 geogs_p1p2p3_v1 아래 SFM_NO_ANCHOR_HANDOFF_ko_v1.md, SFM_NO_ANCHOR_EXECUTION_ko_v1.md, ISSUES_ko_v1.md다. 최신 인계는 별도 SfM 초기화·anchor 생략 작업의 진행 기록이다. 이번 감사는 해당 학습·서비스를 시작·중단·수정하거나 미완료 품질 결과를 사용하지 않았다. 따라서 “모든 기존 문서의 바이트가 그대로”라는 검증 결과를 내지 않는다.

보존 검사 최종 관측과 전후 SHA는 analysis/preservation.txt에 기록했다. 입력 23개는 감사 실행 내부에서 전후 SHA 동일성을 확인했다. 신규 Markdown 3개 내 로컬 링크 39개와 감사 결과 null/행 수/초기점 수는 별도 read-only Docker 검사에서 통과했다. 서비스 변경·Git stage/commit은 하지 않았다.
