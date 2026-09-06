# B v2 개발 이슈

`scientific_verdict: null`. 기존 v1과 실패한 v2 run을 덮어쓰지 않는다.

| ID | 문제 | 원인/조치 | 상태 |
|---|---|---|---|
| B2-001 | 부분 관측 그룹 평균 회전 제한이 초과할 수 있음 | 독립 코드검토로 발견. 전체 점 수 대신 관측점 수로 평균을 정의하고, 개별 회전 제한 뒤 최종 그룹 수축을 적용. 부분 관측 및 두 제한 교집합 Docker 검산 통과 | 실행 전 수정 |
| B2-002 | Docker driver repo 경로가 한 단계 위를 가리킴 | 실행 전 코드검토에서 `../../..`로 수정 | 실행 전 수정 |
| B2-003 | PREFLIGHT-v1 첫 multiview world 역투영에서 Float/Double 불일치 | NumPy 정수 좌표에서 만든 pixel tensor가 float64로 추론됨. 명시 float32로 수정. 초기 실제 G0/평가 프레임까지 생성된 실패 run은 보존 | PREFLIGHT-v2로 재검산 |
| B2-004 | 435번 평가 영상에서 P2 밖 전경 배관이 prior 지붕을 가림 | 원본 영상 육안검토로 확인. G0 self-visibility만으로 해결되지 않음. 동일 카메라의 fullscene COLMAP 깊이를 별도 K로 매핑하고 G0보다 1m 이상 앞선 부분 및 2px 경계 여유를 초기색·관측수·photo/coverage·양방향 multiview 관측에서 제외. depth 미상은 별도 분모로 유지. 이는 조건부 가림 마스크이며 prior 현재성 판정이 아님 | PREFLIGHT-v3에서 적용 검산 |
| B2-005 | 기존 깊이→법선 helper의 integer pixel과 CUDA ray center +0.5 불일치 | 기존 파일을 변경하지 않고 v2의 법선 계산만 실제 CUDA pixel center와 맞춤 | main 전 수정 |
| B2-006 | 435/400의 P2 source Z와 fullscene depth의 큰 차이 해석 | P2 전용 비교만으로 frame 오류를 의심했으나, 44M 전체 current MVS 감사에서 각각 99.46%/100%의 대응 픽셀이 P2 밖 전경으로 확인. 296은 같은 metric 깊이에 잘 맞음. 모든 depth 경계를 인증한 것은 아님. 본실행은 lowdepth 2×2가 모두 알려지고 가장 먼 값+1m도 G0 앞인 경우에만 제외하며 unknown으로의 dilation 제거 | 조건부 가림 처리로 진행 |
| B2-007 | NATIVE-v1의 geometry_fixed만 SH0 범위 제약 누락 | geometry-active arm은 domain projection에서 색을 [0,1]로 제한하지만 geometry_fixed는 그 함수를 호출하지 않아 실제 decoded RGB가 [-0.0452,2.3352], 11,536 channels 범위 밖. export RGB는 clip되므로 해당 arm의 실제 상태를 정확히 표시하지도 못함. 다른 7 arm에는 적용된 제약이다. geometry_fixed에도 같은 색 제한을 적용하고 새 NATIVE-FIXED-v2에서만 재실행. 원 arm/원 상태 보존 및 최종 공정 비교 제외. 새 export에는 raw SH0도 추가 | 수정 실행 예정 |
| B2-008 | screen-filter RGB 지지가 무한 평면 교점 깊이를 오염시키고 일부 직접 미분을 누락 | 361번 실제 ray에서 Gaussian 중심 camera-Z 180.134m, plane rho 약9.24e9인데 screen rho2.12의 opacity가 17,589m 평면 교점에 곱해져 기대 깊이4,261m 생성. 역투영 오류가 아니라 렌더러 합성 계약 오류. 기하 손실·초기 관측·추출 표면 모두 영향받으므로 최초 v2 성능 해석 무효. 기존 overlay/results 보존하고 별도 C4 RGB/C8 plane geometry 두 pass adapter로 수정. 31개 실제 CUDA 검산 후 같은 2,048-step 설정으로 새 세 run 재실행 | 새 12개 결과 및 CORRECTED-VERIFICATION-v1 PASS; 과학적 결론은 별도 |
