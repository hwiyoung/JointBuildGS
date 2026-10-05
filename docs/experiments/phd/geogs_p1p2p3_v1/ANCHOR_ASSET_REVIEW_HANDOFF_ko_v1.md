# Anchor512 표시와 자산 보존·갱신 분석 인계

2026-09-09 · `PHD-GEOGS-ASSET-REVIEW-v1` · `scientific_verdict: null`

사용자는 Anchor 표시와 기존 결과에서 개선점 도출을 요청했고, 추가 질문에서 **기존512로 Anchor·최종을 맞춰 표시·분석**하는 범위를 선택했다. 새 학습·1024 복구를 수행한 것으로 기록하지 않는다.

- [바로 여는 Anchor512 뷰어](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/anchor_review_v1/manifest.json&color=height)
- [통합 개선점](ASSET_RETENTION_AND_UPDATE_ANALYSIS_ko_v1.md)
- [P2 상세 검토](ASSET_REVIEW_P2_ko_v1.md), [P1·P3 상세 검토](ASSET_REVIEW_P1_P3_ko_v1.md)

새 viewer profile은 기본조건 D0005_Pnative, 추출512다. ③ Anchor8000과 ④·⑤ final30000을 동일512로 표시한다. 단면36개는 prior→Anchor→바닐라→선택 결과의 기존 고정 PNG를 화소 변경 없이 연결했다. Raw/post는 단면 선택 항목에도 명시되어 있으므로 해당 그림의 label을 확인한다. 현재 앱은 3D 표면 선택과 모든 아래 그림의 raw/post 선택을 자동 동기화하지 않는다.

기존 세 지역 Anchor mesh/렌더와 결과를 재사용했다. 새 표면 추출0, 모델 학습0, 지표 재계산0이다. 원1024 viewer와 실패한 Anchor1024 영수증은 그대로다. 코드·원입력·서비스를 재시작하지 않았다.

외부 task: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`.

새 output은 `evaluation/anchor_review_v1/`. 생성 receipt/script/config/launcher snapshot,36PNG와 manifest가 있다. 최초 mesh404 browser 실패는 `browser_qa/`에 남겨 두었다. 같은 task의 `evaluation/viewer/P1,P2,P3`를 새 profile의 상대 경로로 연결해 해결했고 `mesh_link_repair_receipt.json` 및 당시 수정 소스를 보존했다. 재검사 `browser_qa_fixed_v1/receipt.json`은37검사/3스크린샷 PASS다. 새 생성기는 처음부터 이 세 alias를 만든다. 원 source manifest SHA는 `12ba0d9a54b7313a7ded96fb9ceb255d0489948e1e18f4d3dadfb1ebcfda61d6`로 유지됐다.

실행기는 `scripts/phd/geogs_p1p2p3_v1/viewer/run_anchor_review_v1.sh`; 기존 output이 있으면 재실행을 거부한다. Browser 실행기는 같은 디렉터리의 `check_anchor_review_v1.sh <fresh-QA-id>`다. 기존 QA를 덮어쓰지 않는다. 신규 실행이 필요하면 정확한 신규 output/config를 정하고 Docker에서 수행한다.

핵심 해석은 “D0005가 더 깨끗해지는 실제 이득 + 원래 근접했던 기하·세부를 잃는 비용”의 공존이다. P2 final1024 raw의 깊이 가중치 .005→.0005 대비에서는 평균 표면→UAS 거리는 감소하지만 중앙값은 증가하고 recall이 크게 감소한다. P3는 바닐라부터 곡면 유지·측벽 보완을 수행한다. 유효한 부분까지 바꿔야 한다거나, 모든 추가 띠가 낡은 자산이라는 결론을 내리지 않는다.

후속 진단 후보는 동일 참조점 hit→miss/miss→hit, raw→post 제거 성분의 영향 추적, 동일 시점의 렌더 깊이–추출 표면 대응이다. 아직 새로 계산하지 않았다. 이 진단 지도는 평가 전용이며 미래 학습·정합·제어 선택에 사용하지 않는다. 다음 방법 비교에서는 단순 전역 설정/스케줄과 한 번 정한 국소 제어를 먼저 비교하고, 반복 재판단의 추가 효과는 별도 질문으로 둔다.

원래 주18개 결과는 확보됐으나 동일 조건 반복 품질 변동은 미측정이다. DA3의 규칙은 같아도 실현 궤적은 다를 수 있다. Raw/post·512/1024·RGB·참조 피복을 구분한다. 새 기여의 우위와 scientific verdict는 확정하지 않는다.
