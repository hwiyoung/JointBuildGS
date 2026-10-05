# Prior–MVS 단계별 관측 진단

`PHD-MVS-EVIDENCE-v1` · 2026-09-14 · `scientific_verdict: null`

사용자가 승인한 P1/P2/P3 불일치 후보·가시성·다중 시점 지지·대응 모호성의
시각적 검토를 위한 별도 CPU 진단이다. 기존 MVS/PGSR 입력 결박을 재사용하고
원 학습·source·입력·평가·서비스를 보존한다. GS 학습 또는 Gaussian 선택은 하지 않는다.

## 입력과 표본

현재 `geogs_mvs_pgsr_v1/inputs_v2` receipt 및 P1/P2/P3 bindings가 MVS·RGB·K/R/t·train
membership·최대 8개 이웃 후보를 결박한다. 부모 GeoGS regional input manifest가 prior를
결박한다. 읽은 원 입력의 SHA256과 config/source/runtime을 신규 receipt에 기록한다.
지역별 train 카메라를 prior 관측 면적과 카메라 위치 다양성으로 3개 선정한다.
GT, 변화 정답, 성능 결과로 카메라를 고르지 않는다. 전체 train 목록과 선택 근거도 저장한다.
이는 세 지역의 여러 시점 진단이며 모든 카메라·전체 3D 표면의 완전한 판정이 아니다.

## 단계별 출력

1. 원사진·두 camera-Z depth·source 결손·signed/absolute discrepancy. Prior는 반 픽셀
   ray 차이를 보정해 조회하며 결손을 채우지 않는다. 0.5/1/2m는 탐색용 기준이다.
2. Prior→Prior와 MVS→MVS의 source 내부 depth-compatible/가림 의심/앞쪽 충돌/관측
   결손을 각각 기록한다. Prior→MVS는 현재 MVS에 조건부인 별도 호환성 검사다.
   이 세 검사는 가시성 정답도 독립적인 source 정확도도 아니다.
3. 같은 원사진 패치·같은 유효 픽셀·같은 이웃에서 두 raw-depth 가설의 ZNCC를
   비교한다. 이 단계의 support를 Prior→MVS 검사로 잘라 MVS를 유리하게 하지 않는다.
   비용, 지원 이웃 수, 텍스처, 시점간 우열 불일치, 시차각을 함께 보인다.
4. 48픽셀 격자에서 source별 local normal을 유지하고 가설 깊이를 바꾼 비용곡선을
   기록한다. 모든 깊이/두 normal branch에서 동일한 complete patch와 이웃만 비교한다.
   낮은 비용의 깊이 범위·여러 분리 구간·최소점의 탐색 끝 도달·지원 부재를 보인다.
   이 폭은 지정한 탐색 구간과 비용 허용폭에 조건부이며 확률적 신뢰구간이 아니다.

16픽셀 관측 격자와 48픽셀 비용곡선 격자는 관측한 중심점만 표시한다. 빈 공간을
보간해 연속 변화 확률처럼 표시하지 않는다. 전체 raster 불일치와 sampled evidence는
구분한다. 단일 낮은 비용, NCC 우열, MVS 자기 일치로 source authority를 결정하지 않는다.
역사 COLMAP 실제 생성 이웃은 복구되지 않았고 MVS와 평가영상은 독립이 아니다.

## 검증과 완료 기준

독립 합성 투영·왕복 오차·깊이 앞뒤·결손·반픽셀·동일 patch support 검사를 Docker에서
통과한 뒤 원 자료를 계산한다. 지역별 지도, 확대 원패치, 이웃별 비용, 깊이별 곡선,
원 수치 NPZ/JSON, 브라우저 검사 도구와 실행 receipt를 제공한다. 표시와 원 수치의
일치 및 실제 브라우저 동작을 확인한다. 관측 모형의 한계·예외는 이슈에 남긴다.

현재 출력에서 판별력을 먼저 검토한 뒤 3D/Gaussian 연결은 별도 단계로 진행한다.
