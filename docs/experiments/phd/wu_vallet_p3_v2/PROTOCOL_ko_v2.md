# Wu–Vallet P3 점군 갱신 — GPS·센서 기하 복원

2026-09-07 · `PHD-WU-VALLET-P3-UPDATE-v2` · 비확증 개발 · `scientific_verdict: null`.

사용자는 Wu–Vallet 자체의 결과에서 개선 필요성을 찾기 위해, 현재 TUM2TWIN ALS의 GPS time을 확인하고 가능한 범위까지 구현하도록 요청했다. 이번 대상은 원소스 분류와 GS 없는 갱신 점군이다. v1의 별도 GS 개발 결과는 이 결과를 대신하지 않는다. 기존 파일·산출물은 보존하고 새 v2 경로에서 실행한다.

## GPS time의 역할과 실제 확인

Wu–Vallet §3.1은 GPS time에서 스캔 순서를 복원하고, 별도 센서 궤적을 시간 보간하여 각 반사점의 optical center를 얻는다. 시간값은 센서 좌표가 아니다. 시간/스캔 순서가 없으면 측정 인접성과 궤적 연결이 어려워지고, 센서 위치가 없으면 과거 ALS에서 현재 표면을 향하는 가시성 검사를 그대로 수행할 수 없다. 거리 비교·현재 카메라 방향의 교차 검사·점군 유지/제거/추가 전체가 계산 불가능해지는 것은 아니다. [원문](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/)

현재 P3 원 ALS 52,762점에는 GPS time이 모두 유한하며 고유 pulse 시각은39,628개다. strip31/32, scan angle, return 정보도 있다. 이 수치는 이전100,000점 표본이 아닌 P3 원행 전량 검사다. 스캔 방향/끝 flag가0이어도 시간·각도 반복에서 순서를 복원할 수 있는지 확인한다. 실제 산출물의 exact raw membership/해시/복원 민감도를 기술 반환에서 연결한다.

## 부족한 궤적을 다루는 실행 순서

1. GPS·strip·scan angle에서 측정 스캔 순서와 beam 좌표를 복원한다. 원 행과 다중반사 pulse를 보존하며 공간XY Delaunay로 바꾸지 않는다.
2. 같은 pulse의 여러 반사점이 정의하는 광선들을 이용해 센서 궤적을 추정한다. 이는 기존 연구와 PDAL에도 있는 접근이다. 사용한 시간선형 근사·forward residual·held-out pulse·퇴화/조건수·bootstrap 검증을 명시한다. 원 센서 궤적과 동일하다고 주장하지 않는다. [Karney–Kim 2022](https://arxiv.org/abs/2208.12116), [PDAL](https://pdal.io/en/2.7.2/stages/filters.trajectory.html)
3. 검증 가능한 추정 궤적이 있으면 Wu 원문의 양방향 분류·점군 갱신까지 연결한다. 추정 불가 범위에는 임의 센서 높이를 넣지 않고 미판정/보존 범위를 표시한다.
4. 현재 카메라 방향만 사용한 결과도 같은 입력에서 따로 실행하여, 과거 센서 광선을 사용할 때 분류·출력이 얼마나 달라지는지 직접 기록한다. 편도 결과를 원방법 전체라고 명명하지 않는다.

## 비교와 해석

현재영상 mesh는 v1에서 깊이 피복만으로 고정한133번 master의 native pixel topology를 사용한다. 기존 COLMAP depth가 원논문의 PSMNet matching을 대신한다. 스캔 복원·추정 optical center·영상 기하 대체·유한 ray sampling·삼각형/원점 집계는 재구현 가정으로 공개한다. 이 가정에서 생긴 실패와 Wu 방법 자체의 실패를 구분한다.

거리 문턱0.1/0.3/0.6m, 작은 영역 정제0/1m²를 사전 개발 민감도로 고정한다. 원 저자 기본값·인증된 오차 범위가 아니다. 최종 참조 결과를 보고 가장 유리한 값을 채택하지 않는다. 원 ALS·현재 sensor mesh·최종 갱신 점군과 유지/삭제/추가/미판정 출처 지도·고정 단면을 먼저 만든 뒤, 별도 평가에서 기존 고정 UAS 참조를 읽는다.

판정은 P3 주변의 기하 문맥을 포함하고 결과는 원 P3 prism으로 자른다. 문맥 밖 가림은 여전히 불확실할 수 있다. source/return 층별 mesh에 들어가지 못한 기존 점도 최종 accounting에서 삭제하지 않고 미판정 보존으로 표시한다. 단독 피복/미판정 보존을 현재성 확인이라고 부르지 않는다.

기존 UAS 헤더 EPSG:32632와 작업표기 EPSG:25832의 datum/epoch 연결은 미보정이다. 같은 raw-shift 수치에서의 참조 편차로 보고하며 새로운 정합·reference 기반 parameter 선택·절대 정확도 판정을 하지 않는다. 기존 E1–E6/C 계보와 과학적 verdict를 변경하지 않는다.
