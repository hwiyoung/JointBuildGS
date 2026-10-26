# 새 중단 기준의 기록

추가 PSNR은 기존과 같은 다섯 영상이다. 중단 비교는 7,000·15,000·30,000회만 한다. 사전 출신과 참값 칸별 통계는 기록만 한다. 초기 출신 둘과 밀도 제어 생성은 서로 겹치지 않으며, 계보별 표는 생성된 자손도 포함한다.
요청의 MVS 출신은 기존 origin=0 영상 계보로 표시했다. 실제 초기점은 기존 fork_inputs_v6.py가 MVS 폴더의 sparse/points3D.bin에서 읽은 SfM 희소점이다. 초기 입력은 바꾸지 않았다.

| 단위·판 | 반복·시점 | 구분 | N | 불투명도 중앙값 | nojudge N | nojudge 중앙값 |
|---|---|---|---:|---:|---:|---:|
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 전체 | 95252 | 0.359904 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 사전 | 75954 | 0.343449 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11071 | 0.491351 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 8227 | 0.362435 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 78181 | 0.345268 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 17071 | 0.443045 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 27531 | 0.433667 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4922 | 0.144942 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 45728 | 0.304826 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 전체 | 128034 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 사전 | 70009 | 0.478478 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 10196 | 0.553268 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 47829 | 0.648276 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 83563 | 0.487273 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 44471 | 0.656877 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 30926 | 0.473880 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 3993 | 0.287012 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 48644 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 전체 | 245173 | 0.837723 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 사전 | 67235 | 0.500066 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9699 | 0.590773 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 168239 | 0.999761 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 98663 | 0.504976 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 146510 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 38012 | 0.516461 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5070 | 0.446481 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 55581 | 0.504521 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 전체 | 259572 | 0.893102 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 사전 | 67085 | 0.500102 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 9675 | 0.592222 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 182812 | 0.999989 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보 전체 | 99731 | 0.511249 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 영상 계보 전체 | 159841 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 38520 | 0.534159 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 5139 | 0.481920 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 56072 | 0.507446 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 전체 | 259572 | 0.158449 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 사전 | 67085 | 0.360596 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9675 | 0.154974 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 182812 | 0.118391 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 99731 | 0.262342 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 159841 | 0.117294 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 38520 | 0.202090 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5139 | 0.077439 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 56072 | 0.371112 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 전체 | 203381 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 사전 | 49599 | 0.633252 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5821 | 0.608048 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 147961 | 0.412851 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 77267 | 0.562004 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 126114 | 0.418625 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 29482 | 0.541619 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 3458 | 0.350475 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 44327 | 0.590929 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 전체 | 261801 | 0.500319 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 사전 | 48917 | 0.666995 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5672 | 0.658923 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 207212 | 0.437545 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 86978 | 0.572816 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 174823 | 0.445551 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 33737 | 0.538133 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4350 | 0.350748 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 48891 | 0.613366 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 전체 | 399794 | 0.512588 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 사전 | 47982 | 0.703111 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5466 | 0.705842 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 346346 | 0.473677 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 109219 | 0.574246 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 290575 | 0.478632 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 43781 | 0.532295 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 6146 | 0.372945 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 59292 | 0.620794 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 전체 | 556827 | 0.527889 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 사전 | 47307 | 0.743940 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5279 | 0.737844 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 504241 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 134158 | 0.572880 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 422669 | 0.507056 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 55347 | 0.521578 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8291 | 0.429948 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 70520 | 0.631491 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 전체 | 574067 | 0.564056 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 사전 | 47236 | 0.744899 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 5256 | 0.739746 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 521575 | 0.537896 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보 전체 | 136918 | 0.596100 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 영상 계보 전체 | 437149 | 0.550192 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 56782 | 0.554082 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 8481 | 0.475519 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 71655 | 0.650254 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 전체 | 574067 | 0.160220 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 사전 | 47236 | 0.526899 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5256 | 0.222321 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 521575 | 0.145846 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 136918 | 0.210958 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 437149 | 0.152306 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 56782 | 0.099811 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8481 | 0.064158 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 71655 | 0.419777 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 전체 | 433396 | 0.398839 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 사전 | 36285 | 0.825406 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3434 | 0.644883 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 393677 | 0.360607 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 96966 | 0.590926 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 336430 | 0.351263 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 35763 | 0.491380 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5082 | 0.437269 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 56121 | 0.686152 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 전체 | 530268 | 0.405283 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 사전 | 36029 | 0.852318 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3384 | 0.693008 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 490855 | 0.370413 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 113709 | 0.570251 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 416559 | 0.362313 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 44064 | 0.480617 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 6474 | 0.420739 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 63171 | 0.660766 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 전체 | 705362 | 0.495184 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 사전 | 35490 | 0.905289 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3114 | 0.758134 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 666758 | 0.461424 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 140019 | 0.605553 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 565343 | 0.452377 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 57587 | 0.500024 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8541 | 0.461932 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 73891 | 0.718695 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 전체 | 891127 | 0.518253 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 사전 | 35095 | 0.922762 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2966 | 0.777208 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 853066 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 168223 | 0.593845 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 722904 | 0.497885 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 72963 | 0.495666 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 10563 | 0.468898 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 84697 | 0.712274 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 전체 | 906844 | 0.544088 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 사전 | 35053 | 0.923133 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2955 | 0.778294 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 868836 | 0.523356 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보 전체 | 170071 | 0.614844 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 영상 계보 전체 | 736773 | 0.525884 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 73825 | 0.514486 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 10722 | 0.498166 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 85524 | 0.725761 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 전체 | 906844 | 0.140987 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 사전 | 35053 | 0.741177 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2955 | 0.425157 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 868836 | 0.133425 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 170071 | 0.299977 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 736773 | 0.127283 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 73825 | 0.221610 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 10722 | 0.130594 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 85524 | 0.489817 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 전체 | 665553 | 0.419929 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 사전 | 32244 | 0.878351 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2535 | 0.632298 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 630774 | 0.396872 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 139425 | 0.537539 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 526128 | 0.388563 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 58712 | 0.415881 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7792 | 0.417457 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 72921 | 0.680527 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 전체 | 766926 | 0.447117 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 사전 | 32015 | 0.901994 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2489 | 0.696765 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 732422 | 0.424217 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 154225 | 0.543092 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 612701 | 0.415798 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 66990 | 0.431235 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8967 | 0.442074 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 78268 | 0.682938 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 전체 | 977994 | 0.472456 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31675 | 0.923681 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2393 | 0.746634 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 943926 | 0.451936 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 186011 | 0.531173 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 791983 | 0.447148 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 84948 | 0.419083 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11323 | 0.458170 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 89740 | 0.663093 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 전체 | 1180813 | 0.494280 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31356 | 0.937715 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2309 | 0.768068 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1147148 | 0.476071 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 213674 | 0.521255 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 967139 | 0.475205 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 100315 | 0.414268 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 13612 | 0.470755 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 99747 | 0.651970 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 전체 | 1198413 | 0.507873 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 사전 | 31321 | 0.937965 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2300 | 0.769205 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 1164792 | 0.499996 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보 전체 | 216174 | 0.540377 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 영상 계보 전체 | 982239 | 0.498467 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 101788 | 0.442545 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 13818 | 0.497485 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 100568 | 0.667143 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 전체 | 1198413 | 0.133907 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 사전 | 31321 | 0.729230 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2300 | 0.385997 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1164792 | 0.126962 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 216174 | 0.231904 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 982239 | 0.120904 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 101788 | 0.138713 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 13818 | 0.097811 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 100568 | 0.419299 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 전체 | 832547 | 0.401713 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 사전 | 27593 | 0.890506 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1855 | 0.646616 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 803099 | 0.386039 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 156749 | 0.525018 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 675798 | 0.375614 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 67455 | 0.408374 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8773 | 0.416974 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 80521 | 0.653637 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 전체 | 936831 | 0.431692 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27485 | 0.919449 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1831 | 0.699022 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 907515 | 0.415511 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 170513 | 0.534956 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 766318 | 0.406277 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 75419 | 0.424625 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 9928 | 0.447278 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 85166 | 0.659030 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 전체 | 1157974 | 0.449950 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27316 | 0.938623 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1788 | 0.741620 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1128870 | 0.435298 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 198714 | 0.524289 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 959260 | 0.428801 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 91481 | 0.421538 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12418 | 0.458746 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 94815 | 0.643409 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.469266 | 2796061 | 0.360820 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.948574 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.762578 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.455857 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.515664 | 395633 | 0.410882 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.453036 | 2400428 | 0.352843 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.412787 | 163396 | 0.369895 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.474041 | 8029 | 0.423804 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.634025 | 224208 | 0.449313 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.469442 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.956666 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.765099 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.454635 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.523682 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.450544 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.422485 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.473142 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.641672 | 기록 없음 | 기록 없음 |

## 다섯 영상 PSNR

| 판 | 반복·시점 | 이번 dB | nojudge dB | 중단 |
|---|---|---:|---:|---|
| lt_dyngt_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 13.063932 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 16.137393 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 17.440088 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 3000 immediately before actual periodic reset, after density | 17.197877 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 17.732817 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 18.229107 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 18.435213 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 19.362821 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 20.267356 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 6000 immediately before actual periodic reset, after density | 20.020330 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 19.239510 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 20.194857 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 20.898870 | 20.828419 | 없음 |
| lt_dyngt_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 20.640262 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 21.316523 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 9000 immediately before actual periodic reset, after density | 20.415269 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 21.124530 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 21.724197 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 21.905544 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 22.151984 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 22.666906 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 12000 immediately before actual periodic reset, after density | 22.388900 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 21.438728 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 22.654856 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 22.630606 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 23.118202 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 23.411518 | 23.523298 | 없음 |
| lt_dyngt_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 23.792749 | 기록 없음 | 없음 |

## 저장 모델의 통계

15,000·30,000회 모델을 읽었다. 과거 생성 표식이 없어 초기 사전·초기 영상·밀도 제어 생성의 분리는 ‘기록 없음’이다. 계보별·참값 칸별 통계는 정확한 저장값으로 센다.

| 단위·판 | 반복 | 구분 | N | 중앙값 | nojudge N | nojudge 중앙값 |
|---|---:|---|---:|---:|---:|---:|
| B0_b10 nojudge_ALS_s0 | 15000 | 전체 | 2303580 | 0.390750 | 2303580 | 0.390750 |
| B0_b10 nojudge_ALS_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_ALS_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_ALS_s0 | 15000 | 사전 계보 전체 | 312334 | 0.377412 | 312334 | 0.377412 |
| B0_b10 nojudge_ALS_s0 | 15000 | 영상 계보 전체 | 1991246 | 0.393127 | 1991246 | 0.393127 |
| B0_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 94957 | 0.326076 | 94957 | 0.326076 |
| B0_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 1306 | 0.500121 | 1306 | 0.500121 |
| B0_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 없음 | 216071 | 0.402348 | 216071 | 0.402348 |
| B0_b10 nojudge_ALS_s0 | 30000 | 전체 | 2303580 | 0.409704 | 2303580 | 0.409704 |
| B0_b10 nojudge_ALS_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_ALS_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_ALS_s0 | 30000 | 사전 계보 전체 | 312334 | 0.682967 | 312334 | 0.682967 |
| B0_b10 nojudge_ALS_s0 | 30000 | 영상 계보 전체 | 1991246 | 0.344051 | 1991246 | 0.344051 |
| B0_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 94957 | 0.590842 | 94957 | 0.590842 |
| B0_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 1306 | 0.930617 | 1306 | 0.930617 |
| B0_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 없음 | 216071 | 0.725159 | 216071 | 0.725159 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 전체 | 2532261 | 0.430331 | 2532261 | 0.430331 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 사전 계보 전체 | 2302664 | 0.434936 | 2302664 | 0.434936 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 영상 계보 전체 | 229597 | 0.389880 | 229597 | 0.389880 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 맞음 | 74792 | 0.382829 | 74792 | 0.382829 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 틀림 | 29436 | 0.534946 | 29436 | 0.534946 |
| B0_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 없음 | 2198436 | 0.435365 | 2198436 | 0.435365 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 전체 | 2532261 | 0.403009 | 2532261 | 0.403009 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 사전 계보 전체 | 2302664 | 0.378638 | 2302664 | 0.378638 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 영상 계보 전체 | 229597 | 0.663152 | 229597 | 0.663152 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 맞음 | 74792 | 0.760661 | 74792 | 0.760661 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 틀림 | 29436 | 0.968984 | 29436 | 0.968984 |
| B0_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 없음 | 2198436 | 0.348617 | 2198436 | 0.348617 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 전체 | 2066519 | 0.512773 | 2796061 | 0.360820 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 사전 계보 전체 | 375941 | 0.569643 | 395633 | 0.410882 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 영상 계보 전체 | 1690578 | 0.500554 | 2400428 | 0.352843 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 181992 | 0.372523 | 163396 | 0.369895 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 23674 | 0.296475 | 8029 | 0.423804 |
| B173nb_b10 lt_fixgt_ALS_s0 | 15000 | 사전 계보·참값 없음 | 170275 | 0.846029 | 224208 | 0.449313 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 전체 | 2066519 | 0.577945 | 2796061 | 0.354446 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 사전 계보 전체 | 375941 | 0.840809 | 395633 | 0.655533 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 영상 계보 전체 | 1690578 | 0.501364 | 2400428 | 0.287534 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 181992 | 0.517507 | 163396 | 0.655912 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 23674 | 0.449389 | 8029 | 0.635453 |
| B173nb_b10 lt_fixgt_ALS_s0 | 30000 | 사전 계보·참값 없음 | 170275 | 0.988240 | 224208 | 0.656257 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 전체 | 2796061 | 0.360820 | 2796061 | 0.360820 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 사전 계보 전체 | 395633 | 0.410882 | 395633 | 0.410882 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 영상 계보 전체 | 2400428 | 0.352843 | 2400428 | 0.352843 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 163396 | 0.369895 | 163396 | 0.369895 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 8029 | 0.423804 | 8029 | 0.423804 |
| B173nb_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 없음 | 224208 | 0.449313 | 224208 | 0.449313 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 전체 | 2796061 | 0.354446 | 2796061 | 0.354446 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 사전 계보 전체 | 395633 | 0.655533 | 395633 | 0.655533 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 영상 계보 전체 | 2400428 | 0.287534 | 2400428 | 0.287534 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 163396 | 0.655912 | 163396 | 0.655912 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 8029 | 0.635453 | 8029 | 0.635453 |
| B173nb_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 없음 | 224208 | 0.656257 | 224208 | 0.656257 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 전체 | 2983470 | 0.376252 | 2983470 | 0.376252 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 사전 계보 전체 | 2474388 | 0.388472 | 2474388 | 0.388472 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 영상 계보 전체 | 509082 | 0.323401 | 509082 | 0.323401 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 맞음 | 102579 | 0.418828 | 102579 | 0.418828 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 틀림 | 26788 | 0.500000 | 26788 | 0.500000 |
| B173nb_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 없음 | 2345021 | 0.385665 | 2345021 | 0.385665 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 전체 | 2983470 | 0.348067 | 2983470 | 0.348067 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 사전 계보 전체 | 2474388 | 0.373889 | 2474388 | 0.373889 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 영상 계보 전체 | 509082 | 0.247449 | 509082 | 0.247449 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 맞음 | 102579 | 0.741419 | 102579 | 0.741419 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 틀림 | 26788 | 0.822950 | 26788 | 0.822950 |
| B173nb_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 없음 | 2345021 | 0.342188 | 2345021 | 0.342188 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 전체 | 2593666 | 0.394554 | 2593666 | 0.394554 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 사전 계보 전체 | 157453 | 0.293428 | 157453 | 0.293428 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 영상 계보 전체 | 2436213 | 0.402315 | 2436213 | 0.402315 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 116431 | 0.246394 | 116431 | 0.246394 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 2736 | 0.392816 | 2736 | 0.392816 |
| R1rep_b10 nojudge_ALS_s0 | 15000 | 사전 계보·참값 없음 | 38286 | 0.508341 | 38286 | 0.508341 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 전체 | 2593666 | 0.351959 | 2593666 | 0.351959 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 사전 계보 전체 | 157453 | 0.358318 | 157453 | 0.358318 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 영상 계보 전체 | 2436213 | 0.351554 | 2436213 | 0.351554 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 116431 | 0.254417 | 116431 | 0.254417 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 2736 | 0.613980 | 2736 | 0.613980 |
| R1rep_b10 nojudge_ALS_s0 | 30000 | 사전 계보·참값 없음 | 38286 | 0.669675 | 38286 | 0.669675 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 전체 | 3607818 | 0.459637 | 3607818 | 0.459637 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 사전 계보 전체 | 1865165 | 0.507803 | 1865165 | 0.507803 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 영상 계보 전체 | 1742653 | 0.406187 | 1742653 | 0.406187 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 맞음 | 70458 | 0.294268 | 70458 | 0.294268 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 틀림 | 70222 | 0.579802 | 70222 | 0.579802 |
| R1rep_b10 nojudge_LoD2_s0 | 15000 | 사전 계보·참값 없음 | 1724485 | 0.515177 | 1724485 | 0.515177 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 전체 | 3607818 | 0.258028 | 3607818 | 0.258028 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 초기 사전 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 초기 영상(MVS 계열) | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 밀도 제어 생성 | 기록 없음 | 기록 없음 | 기록 없음 | 기록 없음 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 사전 계보 전체 | 1865165 | 0.190457 | 1865165 | 0.190457 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 영상 계보 전체 | 1742653 | 0.351279 | 1742653 | 0.351279 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 맞음 | 70458 | 0.294874 | 70458 | 0.294874 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 틀림 | 70222 | 0.873130 | 70222 | 0.873130 |
| R1rep_b10 nojudge_LoD2_s0 | 30000 | 사전 계보·참값 없음 | 1724485 | 0.168592 | 1724485 | 0.168592 |
