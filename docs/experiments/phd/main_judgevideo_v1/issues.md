# PHD-MAIN-JUDGEVIDEO-v1 issues

1. 패치 표에 B173 region 없음(`region` = none/R1/B0/R2/…; B173은 다른 이름 체계). 발주문의 'region/building이 B173 주변 장면에 드는 패치'를 TRAINLOG-v1 scope(`buffered_footprint`, z 범위)로 패치 중심을 고르는 것으로 바꿈.
2. 발주문의 열 'A_n'은 쓰지 않음: 최종 구조(판 다·혼합 경계, mf19 `panel_lo`)는 '지금 점군'(`none_*`) 판정 위에 서므로 `none_n`·`none_significant`·`none_judgment`를 씀.
3. 단계 ① 결측 = `none_n` < 4 이면서 제거가 아닌 패치(`none_judgment` 4 또는 9, 넓이 3.56 m²), 제거 = `none_judgment` 3(4.40 m²). 판정 9(미판정)인 n<4 패치 5개(0.33 m²)를 결측 색에 넣음.
4. 유의 아님인데 `none_judgment` 1·2·9 인 패치 937개(70.6 m²)는 모두 JUDGECHECK 기하 코드 9(면 맞춤 불가, L 없음 → 변화 탐지 안 함). 발주문 네 단계 어디에도 들지 않아 '아직 안 정함'으로 두고, 판단 결과 장면에서 '그 밖(L 없음)' 회색으로 칠함. 나눔: 미판정 555개 40.3 m², 사전정보 사용 257개 21.8 m², 영상 깊이 사용 125개 8.5 m² (`judge_steps_check.json` other_breakdown).
5. 단면의 목표 높이 선: 일치·작은 차이 = 정밀도 가중 평균(prior_height/σ_P² + mvs_mean/u_M²; jc2 region-0 규칙을 그리기용으로 다시 셈, 판정은 다시 셈하지 않음), 영상 따름 = mvs_mean, 되돌림·결측 = prior_height.
6. 영상 이미지 jointbuildgs:geogs-da3-3d835ec-v1(TRAINLOG의 ffmpeg)가 이 호스트에 없음 → jointbuildgs:dev 컨테이너에서 `pip install --target` 으로 imageio-ffmpeg 0.5.1(정적 ffmpeg 4.2.2, libx264)을 결과 폴더 tmp/pylib 에 받아 씀. 인코딩 규칙(libx264 veryfast, crf 18, yuv420p, 25 fps)은 r6 과 같음.
7. 이은 동영상의 '입력'·'0'~'30,000' 프레임은 r6 PNG 그대로라 그 프레임들의 진행 막대에는 판단 점 넷이 없음(판단 구간 프레임에만 있음).
