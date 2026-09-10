# Normal 관측 비용 진단 v3.7 이슈

scientific_verdict: null

- 비용 순위와 참조 오차 순위 불일치: P2_high의 9×9는 raw/plane 모두 Prior를 지지하지만 동일 UAS 참조에서는 DA3의 오차가 더 작다. 수치 구현 오류의 증거가 아니라 현재 사진 비용의 source 판별 한계로 기록한다. normal 추가로 해결되지 않았다. 17×17/33×33 결과도 같이 보존했다.
- 평가 지원 부족: 8개 중 7개는 65×65 문맥에도 지역 UAS 참조가 없다. 정답/오답 또는 판별 성공률로 보간·집계하지 않는다.
- 평면 및 비용 해석: 원본 target에서 얻은 normal은 독립 관측이 아니며 평면 적합 잔차를 아직 quality gate로 사용하지 않았다. visibility는 unknown이고 높은 상대 지지율도 절대 적합성을 보증하지 않는다.
- 화면 분모 사전 검토: 비용이 정의된 사진 수(paired_views)와 개발 수치 요건을 충족한 사진 수(eligible_views)를 구분했다. 방향 counts와 median은 후자의 집합이며, .02 이내를 정확한 동률로 표시하지 않도록 게시 전에 수정했다.
- 해시와 기존 결과 보존: 계산·평가·게시를 각각 별도 출력에 기록하고 새 packet을 생성했다. 기존 packet 및 current.json을 변경하지 않았다.
- 첫 브라우저 검사 `browser_qa/attempt_20260911T112931Z_1q9JR3`에서 root evaluation.json 요청이 HTTP 404였다. 기존 정적 서버는 root 파일명 허용 목록을 사용하므로 파일이 있어도 해당 이름을 제공하지 않는다. 새 UI가 이미 허용된 `assets/evaluation/receipt.json`을 읽도록 수정하고 새 packet을 생성했다. 서버 및 첫 packet은 보존했다. 계산·참조 평가 수치 변경은 없다.
- 두 번째 packet의 `browser_qa/attempt_20260911T113108Z_NP7Pvv`는 수치/HTTP 11,646검사·195상태를 통과했지만 root 육안 검토에서 확대창이 9px 원 크기를 유지하고 모바일 점수표의 사진명 열이 좁아 행이 400px 이상으로 늘어나는 문제가 확인됐다. PNG 밖의 회색 letterbox도 결손처럼 보였다. 새 UI에 실제 확대 폭·표 최소 폭·정사각 패치 프레임과 밝은 배경을 적용하고 별도 packet에서 다시 검증한다. 이 기록은 이전 numeric PASS와 수동 사용성 판정을 구분하며 기존 screenshot/receipt를 덮어쓰지 않는다.
- 최종 packet `packet_normal_photometry_v3_7_20260911T113326_160982Z`는 `browser_qa/attempt_20260911T113404Z_ba7CYd`에서 12,037검사·195상태 PASS. 실제 확대 240px 이상, 사진명 열 최소 160px, 표 행 최대 160px, 정사각 패치 표시를 새 검사에 포함했다. root가 desktop_patch_zoom·mobile_score_table_left·desktop_P2_high33을 직접 확인하여 위 표시 문제가 해결됐음을 확인했다. 남는 한계는 가시성, reference 지원 및 source 판별 능력이며 구현·UI 통과로 해소됐다고 주장하지 않는다.
