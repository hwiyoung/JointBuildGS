# P1/P2/P3 단계별 뷰어 — 기술 검증 결과

- 상태: 실행 및 실제 브라우저 검증 완료. `scientific_verdict: null`.
- [큰 원본 사진부터 열기](http://127.0.0.1:8903/?region=P2&stage=2&cell=5) · [첫 단계부터 열기](http://127.0.0.1:8903/).
- 영역별 후보 입력·관측 평가·소스 판단, 전체 셀 탐색, 원본 사진 확대/이동/큰 보기,
  영상쌍·패치 변경, 실제 점군 3D 회전/이동/확대·소스 토글을 제공한다.
- 브라우저 검사 **107개 통과**, 화면 캡처 **26개**를 보존했다.
- P1/P2/P3 × 3단계와 대표·오판·관측 부재 사례를 확인했다.
  1600/1024/768 px 화면과 빠른 영역 전환도 점검했다.
- 고정 method 파일 해시를 재검사했으며 원 연구 결과는 바뀌지 않았다.
- 서버는 기존 뷰어와 별도로 127.0.0.1:8903에서 실행한다.
  검증 범위는 이 컴퓨터의 브라우저와 Docker Chromium이다.

원본 사진은 보존된 1400×1013 JPG이고, 검사 패치의 확대는 원영상 복원 또는
새로운 영상 세부의 생성이 아니다. 소스 선택·기하 정확도·GS 성능은 재평가하지 않았다.

- [사용·재현 안내](README_ko_v1.md)
- [실행 및 검증 이슈](ISSUES_ko_v1.md)
- [검증 receipt](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_viewer_v1/PHD-SOURCE-CANDIDATE-VIEWER-v2/browser_qa/qa-v2/browser_qa.json)
- [artifact manifest](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/artifacts/manifests/phd/source_candidate_viewer_v1/technical_result_manifest_v1.json)
