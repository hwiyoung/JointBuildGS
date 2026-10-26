# 새 중단 기준의 기록

추가 PSNR은 기존과 같은 다섯 영상이다. 중단 비교는 7,000·15,000·30,000회만 한다. 사전 출신과 참값 칸별 통계는 기록만 한다. 초기 출신 둘과 밀도 제어 생성은 서로 겹치지 않으며, 계보별 표는 생성된 자손도 포함한다.
요청의 MVS 출신은 기존 origin=0 영상 계보로 표시했다. 실제 초기점은 기존 fork_inputs_v6.py가 MVS 폴더의 sparse/points3D.bin에서 읽은 SfM 희소점이다. 초기 입력은 바꾸지 않았다.

| 단위·판 | 반복·시점 | 구분 | N | 불투명도 중앙값 | nojudge N | nojudge 중앙값 |
|---|---|---|---:|---:|---:|---:|
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 전체 | 133470 | 0.297297 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 사전 | 116117 | 0.280952 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 12770 | 0.455201 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 4583 | 0.477912 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 117600 | 0.282076 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 15870 | 0.454683 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 53449 | 0.229964 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 29348 | 0.322877 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 34803 | 0.363112 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 전체 | 157966 | 0.487776 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 사전 | 103181 | 0.388842 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 12002 | 0.539555 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 42783 | 0.912578 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 130681 | 0.474534 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 27285 | 0.546644 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48872 | 0.282910 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27208 | 0.450511 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 54601 | 0.558497 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 전체 | 243055 | 0.664926 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 사전 | 96407 | 0.463418 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11478 | 0.606878 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 135170 | 0.998816 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 193249 | 0.625629 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 49806 | 0.825441 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48018 | 0.325657 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 26831 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 118400 | 0.987204 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 전체 | 257302 | 0.735162 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 초기 사전 | 95872 | 0.467481 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 11435 | 0.608738 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 149995 | 0.999429 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보 전체 | 202942 | 0.687415 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 영상 계보 전체 | 54360 | 0.884851 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 48242 | 0.334417 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 26877 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 127823 | 0.994926 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 전체 | 257302 | 0.205560 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 사전 | 95872 | 0.278314 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11435 | 0.215937 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 149995 | 0.173842 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 202942 | 0.211538 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 54360 | 0.187336 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48242 | 0.159821 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 26877 | 0.320527 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 127823 | 0.214904 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 전체 | 214505 | 0.481497 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 사전 | 70495 | 0.528671 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 8217 | 0.607128 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 135793 | 0.404323 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 167427 | 0.490280 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 47078 | 0.453164 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 33406 | 0.430373 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20987 | 0.529950 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 113034 | 0.487084 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 전체 | 264841 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 사전 | 68828 | 0.563579 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 8056 | 0.678845 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 187957 | 0.424412 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 200792 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 64049 | 0.484931 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 34265 | 0.474463 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 21338 | 0.563013 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 145189 | 0.495442 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 전체 | 387416 | 0.504010 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 사전 | 66791 | 0.624215 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 7835 | 0.746961 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 312790 | 0.459323 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 280290 | 0.500272 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 107126 | 0.529001 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37002 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 22604 | 0.597881 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 220684 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 전체 | 525743 | 0.524857 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 사전 | 65390 | 0.678414 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 7668 | 0.794056 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 452685 | 0.487735 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 366109 | 0.511632 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 159634 | 0.566446 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 40731 | 0.514529 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 24295 | 0.634172 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 301083 | 0.500871 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 전체 | 540094 | 0.562106 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 초기 사전 | 65275 | 0.679855 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 7652 | 0.794531 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 467167 | 0.531127 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보 전체 | 375882 | 0.544025 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 영상 계보 전체 | 164212 | 0.609881 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 41064 | 0.527299 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 24535 | 0.644367 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 310283 | 0.536887 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 전체 | 540094 | 0.165664 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 사전 | 65275 | 0.417322 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 7652 | 0.295491 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 467167 | 0.148073 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 375882 | 0.171139 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 164212 | 0.152756 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 41064 | 0.204562 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 24535 | 0.291483 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 310283 | 0.162371 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 전체 | 425163 | 0.394334 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 사전 | 51394 | 0.698045 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5707 | 0.689278 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 368062 | 0.350418 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 295991 | 0.401827 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 129172 | 0.378996 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 31150 | 0.504449 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 19180 | 0.618459 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 245661 | 0.372080 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 전체 | 501464 | 0.406834 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 사전 | 50879 | 0.749013 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5655 | 0.741291 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 444930 | 0.362778 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 343523 | 0.411586 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 157941 | 0.397296 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 33403 | 0.524443 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20236 | 0.647896 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 289884 | 0.381074 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 전체 | 638746 | 0.481746 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 사전 | 50081 | 0.825851 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5427 | 0.816774 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 583238 | 0.438446 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 432232 | 0.487638 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 206514 | 0.469838 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 38058 | 0.578438 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 22625 | 0.701011 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 371549 | 0.459023 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 전체 | 786342 | 0.507096 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 사전 | 49497 | 0.865680 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5275 | 0.847313 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 731570 | 0.475992 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 527345 | 0.508660 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 258997 | 0.503524 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 43021 | 0.595319 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 25018 | 0.721354 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 459306 | 0.495682 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 전체 | 801377 | 0.535241 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 초기 사전 | 49431 | 0.866115 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 5262 | 0.848193 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 746684 | 0.505005 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보 전체 | 538317 | 0.536943 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 영상 계보 전체 | 263060 | 0.531801 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 43519 | 0.614507 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 25232 | 0.733250 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 469566 | 0.518309 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 전체 | 801377 | 0.172414 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 사전 | 49431 | 0.546643 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5262 | 0.417462 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 746684 | 0.157705 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 538317 | 0.172009 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 263060 | 0.173144 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 43519 | 0.276202 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 25232 | 0.410008 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 469566 | 0.157316 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 전체 | 612949 | 0.409649 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 사전 | 43880 | 0.779586 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4557 | 0.665476 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 564512 | 0.381162 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 407172 | 0.425531 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 205777 | 0.380662 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 35568 | 0.539555 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 21703 | 0.647206 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 349901 | 0.401290 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 전체 | 688468 | 0.439448 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 사전 | 43638 | 0.827040 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4493 | 0.711161 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 640337 | 0.408507 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 457096 | 0.457239 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 231372 | 0.406504 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37817 | 0.567609 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 22840 | 0.677552 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 396439 | 0.432209 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 전체 | 841556 | 0.458735 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 사전 | 43279 | 0.870675 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4378 | 0.774474 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 793899 | 0.429786 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 558830 | 0.474388 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 282726 | 0.429432 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 43250 | 0.578835 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 25315 | 0.698419 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 490265 | 0.451731 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 전체 | 980901 | 0.478886 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 사전 | 42925 | 0.898964 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4282 | 0.803295 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 933694 | 0.451335 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 651260 | 0.494834 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 329641 | 0.449611 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 47887 | 0.584857 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27585 | 0.708799 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 575788 | 0.473840 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 전체 | 995690 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 초기 사전 | 42899 | 0.899183 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 4269 | 0.805402 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 948522 | 0.475414 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보 전체 | 661334 | 0.511182 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 영상 계보 전체 | 334356 | 0.472236 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 48119 | 0.597808 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 27690 | 0.716915 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 585525 | 0.498882 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 전체 | 995690 | 0.140544 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 사전 | 42899 | 0.579881 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4269 | 0.413682 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 948522 | 0.128889 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 661334 | 0.152174 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 334356 | 0.116672 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48119 | 0.276379 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27690 | 0.360324 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 585525 | 0.138859 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 전체 | 694295 | 0.422877 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 사전 | 38693 | 0.784362 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3761 | 0.614105 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 651841 | 0.401340 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 473592 | 0.436765 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 220703 | 0.394433 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 38246 | 0.514468 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 22929 | 0.602758 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 412417 | 0.420302 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 전체 | 777586 | 0.447616 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38580 | 0.827448 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3741 | 0.663427 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 735265 | 0.424394 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 528368 | 0.463618 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 249218 | 0.415058 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 40672 | 0.534762 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 24017 | 0.631415 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 463679 | 0.447352 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 전체 | 922974 | 0.464642 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38368 | 0.872193 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3682 | 0.709485 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 880924 | 0.441933 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 625083 | 0.478872 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 297891 | 0.436835 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 45068 | 0.540557 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 26025 | 0.669972 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 553990 | 0.462541 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.480038 | 2532261 | 0.430331 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.902678 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.737790 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.457211 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.496296 | 2302664 | 0.434936 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.448173 | 229597 | 0.389880 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.558125 | 74792 | 0.382829 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.701500 | 29436 | 0.534946 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.480133 | 2198436 | 0.435365 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.482414 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.922997 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.759236 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.456636 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.441432 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.583886 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.744640 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.483422 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.502528 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.939045 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.782336 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.478737 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.524887 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.455198 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.623873 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.780547 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.504369 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.523754 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.951528 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.800990 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.499429 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.549770 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.470935 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.661476 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.815440 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.526884 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.550996 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.962312 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.816894 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.523655 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.580068 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.492337 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.696004 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.850619 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.554540 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.579348 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.970231 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.838955 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.551578 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.609708 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.517049 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.725163 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.883437 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.582796 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.607611 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.976723 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.855600 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.578409 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.641057 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.537808 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.755807 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.905955 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.612877 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.638649 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.981819 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.875035 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.610076 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.673412 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.565601 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.782044 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.924668 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.645061 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.665334 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.986049 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.883815 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.636540 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.701478 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.589157 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.800770 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.939380 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.673714 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.693456 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.989330 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.892509 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.665126 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.729614 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.616729 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.820599 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.952777 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.702543 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.722819 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.992041 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.900129 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.694562 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.760346 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.641376 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.844019 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.963396 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.733472 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.749313 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.994008 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.910111 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.721864 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.786624 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.666638 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.862541 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.970937 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.761617 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.773548 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.995409 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.912809 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.747411 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.809533 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.691146 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.877157 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.976294 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.786757 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.796720 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.996521 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.922834 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.771755 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.832852 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.713741 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.891151 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.981213 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.811228 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.816701 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.997491 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.935396 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.792384 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.850342 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.733461 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.903457 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.985747 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.830647 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 전체 | 1052577 | 0.835316 | 2532261 | 0.403009 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38116 | 0.998119 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3628 | 0.937896 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1010833 | 0.811925 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 712322 | 0.868470 | 2302664 | 0.378638 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 340255 | 0.753497 | 229597 | 0.663152 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 48701 | 0.916575 | 74792 | 0.760661 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 27609 | 0.988838 | 29436 | 0.968984 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 636012 | 0.849712 | 2198436 | 0.348617 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 전체 | 216215 | 0.239571 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 사전 | 134665 | 0.264370 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11492 | 0.221959 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 70058 | 0.174692 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 193404 | 0.241301 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 22811 | 0.224145 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 98197 | 0.225913 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 44851 | 0.247094 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 50356 | 0.296693 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 전체 | 311117 | 0.300571 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 사전 | 131221 | 0.268745 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11153 | 0.222158 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 168743 | 0.386825 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 264754 | 0.297304 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 46363 | 0.323730 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 110505 | 0.233934 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 51012 | 0.279664 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 103237 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 전체 | 497697 | 0.500005 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 사전 | 127377 | 0.278309 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 10761 | 0.225521 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 359559 | 0.812083 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 402240 | 0.493581 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 95457 | 0.754126 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 123959 | 0.253043 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 57940 | 0.323513 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 220341 | 0.910519 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 전체 | 531561 | 0.527534 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 초기 사전 | 126787 | 0.279870 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 10709 | 0.226501 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 394065 | 0.877058 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보 전체 | 425978 | 0.501017 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 영상 계보 전체 | 105583 | 0.861449 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 126237 | 0.262575 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 58909 | 0.337957 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 240832 | 0.952434 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 전체 | 531561 | 0.073743 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 사전 | 126787 | 0.087384 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 10709 | 0.063423 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 394065 | 0.069477 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 425978 | 0.082006 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 105583 | 0.037950 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 126237 | 0.086199 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 58909 | 0.067777 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 240832 | 0.083316 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 전체 | 372389 | 0.167999 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 사전 | 76205 | 0.160544 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5475 | 0.128238 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 290709 | 0.171466 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 306900 | 0.165781 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 65489 | 0.179882 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 93778 | 0.126210 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 39350 | 0.158159 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 173772 | 0.203763 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 전체 | 443338 | 0.199051 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 사전 | 73949 | 0.170099 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5238 | 0.130615 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 364151 | 0.207950 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 356672 | 0.194351 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 86666 | 0.222136 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 98264 | 0.133054 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 42713 | 0.177393 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 215695 | 0.244239 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 전체 | 618279 | 0.268577 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 사전 | 69320 | 0.200808 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4723 | 0.145258 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 544236 | 0.283467 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 480137 | 0.258378 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 138142 | 0.309958 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 108858 | 0.165747 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 50546 | 0.226053 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 320733 | 0.317432 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 전체 | 827032 | 0.336831 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 사전 | 66193 | 0.230901 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4417 | 0.157332 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 756422 | 0.353736 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 624960 | 0.320186 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 202072 | 0.395883 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 123354 | 0.212844 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 59828 | 0.268473 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 441778 | 0.374945 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 전체 | 852301 | 0.373115 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 초기 사전 | 66033 | 0.231835 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 4400 | 0.157738 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 781868 | 0.394155 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보 전체 | 644843 | 0.354019 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 영상 계보 전체 | 207458 | 0.441671 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 125028 | 0.226008 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 60529 | 0.290332 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 459286 | 0.414789 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 전체 | 852301 | 0.075984 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 사전 | 66033 | 0.079871 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4400 | 0.041429 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 781868 | 0.075885 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 644843 | 0.081821 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 207458 | 0.048448 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 125028 | 0.049565 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 60529 | 0.042323 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 459286 | 0.097891 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 전체 | 561718 | 0.205265 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 사전 | 39233 | 0.202768 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1911 | 0.151955 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 520574 | 0.205735 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 433854 | 0.193647 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 127864 | 0.252722 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 67934 | 0.138963 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 33115 | 0.178692 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 332805 | 0.210745 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 전체 | 661554 | 0.231374 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 사전 | 38145 | 0.229570 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1840 | 0.165846 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 621569 | 0.231778 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 500569 | 0.219920 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 160985 | 0.271720 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 73576 | 0.161166 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 37118 | 0.197144 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 389875 | 0.237292 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 전체 | 864859 | 0.295512 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 사전 | 37038 | 0.288638 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1754 | 0.180400 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 826067 | 0.296245 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 642704 | 0.284406 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 222155 | 0.328846 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 90012 | 0.216168 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 45879 | 0.246313 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 506813 | 0.303000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 전체 | 1113588 | 0.350356 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 사전 | 36269 | 0.335082 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1673 | 0.199727 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1075646 | 0.351308 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 819339 | 0.340115 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 294249 | 0.380016 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 110085 | 0.286513 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 54865 | 0.290422 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 654389 | 0.353435 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 전체 | 1139651 | 0.380475 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 초기 사전 | 36184 | 0.337158 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 1663 | 0.201576 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 1101804 | 0.382277 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보 전체 | 839914 | 0.368143 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 영상 계보 전체 | 299737 | 0.416631 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 111850 | 0.308240 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 55341 | 0.321778 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 672723 | 0.381267 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 전체 | 1139651 | 0.089987 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 사전 | 36184 | 0.113113 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1663 | 0.102620 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1101804 | 0.088849 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 839914 | 0.088443 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 299737 | 0.095935 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 111850 | 0.070323 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 55341 | 0.068555 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 672723 | 0.097910 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 전체 | 775869 | 0.217866 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 사전 | 29820 | 0.174013 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1335 | 0.132979 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 744714 | 0.219589 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 572615 | 0.207174 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 203254 | 0.250599 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 76454 | 0.113830 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 36041 | 0.145436 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 460120 | 0.237104 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 전체 | 872545 | 0.247034 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 사전 | 29461 | 0.199517 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1315 | 0.137261 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 841769 | 0.248635 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 642540 | 0.238610 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 230005 | 0.271038 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 82070 | 0.126929 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 40211 | 0.161415 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 520259 | 0.269943 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 전체 | 1098436 | 0.290600 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 사전 | 28626 | 0.255141 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1268 | 0.147406 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1068542 | 0.291587 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 806694 | 0.283483 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 291742 | 0.309914 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 94684 | 0.158450 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 49063 | 0.199310 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 662947 | 0.313192 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 전체 | 1357430 | 0.338682 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27918 | 0.317306 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1229 | 0.160075 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1328283 | 0.339226 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1001266 | 0.333639 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 356164 | 0.351751 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 107686 | 0.198800 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 58661 | 0.242155 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 834919 | 0.360881 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 전체 | 1386993 | 0.366761 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 초기 사전 | 27872 | 0.319348 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 1226 | 0.160517 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 1357895 | 0.367800 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보 전체 | 1025235 | 0.362466 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 영상 계보 전체 | 361758 | 0.378105 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 108723 | 0.210987 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 58717 | 0.268245 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 857795 | 0.391534 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 전체 | 1386993 | 0.065095 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 사전 | 27872 | 0.143285 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1226 | 0.115255 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1357895 | 0.062601 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1025235 | 0.068285 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 361758 | 0.052950 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 108723 | 0.089121 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 58717 | 0.114123 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 857795 | 0.060564 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 전체 | 822020 | 0.209039 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 사전 | 24706 | 0.184908 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1027 | 0.133053 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 796287 | 0.209886 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 618395 | 0.197238 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 203625 | 0.250853 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 77546 | 0.124482 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 49328 | 0.154370 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 491521 | 0.225625 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 전체 | 926609 | 0.242104 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 사전 | 24458 | 0.202985 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1007 | 0.137432 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 901144 | 0.243213 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 692703 | 0.231549 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 233906 | 0.275744 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 81069 | 0.131691 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 51645 | 0.165174 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 559989 | 0.266982 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 전체 | 1228320 | 0.305480 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 사전 | 24108 | 0.246189 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 976 | 0.144660 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1203236 | 0.306563 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 929470 | 0.305425 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 298850 | 0.305642 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 91750 | 0.149096 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 58618 | 0.179049 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 779102 | 0.351124 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.424308 | 2532261 | 0.430331 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.307564 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.152099 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.425933 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.456609 | 2302664 | 0.434936 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.342549 | 229597 | 0.389880 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.177666 | 74792 | 0.382829 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.208995 | 29436 | 0.534946 |
| B0_b10 lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.515278 | 2198436 | 0.435365 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.367896 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.344927 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.160311 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.368421 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.391216 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.309413 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.171898 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.194952 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.447945 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.352297 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.385488 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.160562 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.352112 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.368898 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.309501 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.174008 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.191038 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.421560 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.344186 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.447287 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.163539 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.343174 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.358493 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.307332 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.177844 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.197476 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.405642 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.340794 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.175718 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.339059 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.351280 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.312311 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.183802 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.202766 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.394136 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.341277 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.500000 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.187789 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.338681 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.348857 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.321411 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.189905 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.205103 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.388655 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.342438 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.500488 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.187531 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.338936 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.346886 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.330222 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.200294 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.214353 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.382612 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.346554 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.509373 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.215851 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.341928 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.347215 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.344703 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.211446 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.224200 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.379032 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.351402 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.521678 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.234300 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.346079 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.349439 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.356881 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.222450 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.233396 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.379090 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.356525 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.538425 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.279585 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.350299 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.351865 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.369941 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.239828 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.240290 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.377815 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.359779 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.561440 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.300491 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.352572 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.352392 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.380586 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.260170 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.248358 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.373399 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.363177 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.607954 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.328777 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.355035 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.354499 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.387984 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.273403 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.248880 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.374694 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.373312 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.636350 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.364402 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.364051 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.362370 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.404131 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.295667 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.259921 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.379293 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.380385 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.665349 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.376462 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.370390 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.366130 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.422445 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.318260 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.264610 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.379578 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.386502 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.721411 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.410528 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.375247 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.368282 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.438572 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.339087 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.275345 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.378426 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 전체 | 1677211 | 0.391705 | 2532261 | 0.403009 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 사전 | 23720 | 0.757768 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 947 | 0.447936 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1652544 | 0.379706 | 기록 없음 | 기록 없음 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 1303693 | 0.369799 | 2302664 | 0.378638 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 373518 | 0.453519 | 229597 | 0.663152 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 102996 | 0.361130 | 74792 | 0.760661 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 65424 | 0.285010 | 29436 | 0.968984 |
| B0_b10 lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 1135273 | 0.377151 | 2198436 | 0.348617 |
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
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.487568 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.961767 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.761347 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.471237 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.532418 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.467523 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.433097 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.486166 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.657346 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.501348 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.968092 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.763647 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.490659 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.551350 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.486557 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.456835 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.675656 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.522024 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.973680 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.784755 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.508364 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.569925 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.508849 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.473771 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.697479 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.545022 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.977404 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.793746 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.530346 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.588740 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.532938 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.493804 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.500254 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.720495 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.569761 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.981132 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.805708 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.555062 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.611899 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.558603 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.513250 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.517949 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.743548 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.596173 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.984985 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.807098 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.581324 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.631496 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.587046 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.531212 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.523877 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.765151 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.622001 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.987389 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.815064 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.607256 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.650656 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.614461 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.551493 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.545478 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.784310 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.651694 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.989933 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.824641 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.637224 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.672479 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.646298 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.572378 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.569639 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.806262 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.677608 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.991670 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.834470 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.663063 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.693202 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.673473 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.591080 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.579325 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.827424 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.703892 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.993273 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.846266 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.689842 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.712994 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.701593 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.605781 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.606267 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.845474 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.728752 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.994501 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.859953 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.715042 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.732908 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.727752 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.628677 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.633297 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.862465 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.755357 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.995717 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.860659 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.742380 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.757951 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.754724 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.651586 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.671596 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.880695 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.777208 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.996575 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.857778 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.764713 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.772587 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.778300 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.662750 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.683134 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.893617 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 전체 | 1379799 | 0.797742 | 2796061 | 0.354446 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27165 | 0.997225 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1750 | 0.863555 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1350884 | 0.785959 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223118 | 0.789749 | 395633 | 0.655533 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1156681 | 0.799741 | 2400428 | 0.287534 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105483 | 0.680908 | 163396 | 0.655912 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14643 | 0.720209 | 8029 | 0.635453 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 102992 | 0.908241 | 224208 | 0.656257 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 전체 | 94206 | 0.360973 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 사전 | 75750 | 0.342509 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11103 | 0.499133 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 7353 | 0.416121 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 77589 | 0.343875 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 16617 | 0.473716 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 27198 | 0.412817 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4929 | 0.143062 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 45462 | 0.312992 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 전체 | 129627 | 0.500003 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 사전 | 69737 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 10301 | 0.564613 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 49589 | 0.681696 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 82681 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 46946 | 0.681376 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 29986 | 0.463171 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4271 | 0.306710 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 48424 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 전체 | 240900 | 0.782346 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 사전 | 66852 | 0.502441 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9750 | 0.606468 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 164298 | 0.990753 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 100842 | 0.515575 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 140058 | 0.997465 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 36726 | 0.506179 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8314 | 0.843124 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 55802 | 0.510886 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 전체 | 251541 | 0.831312 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 사전 | 66699 | 0.502679 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 9705 | 0.609959 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 175137 | 0.995537 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보 전체 | 102423 | 0.525330 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 영상 계보 전체 | 149118 | 0.999078 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 37115 | 0.522143 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 8900 | 0.926899 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 56408 | 0.514960 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 전체 | 251541 | 0.174434 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 사전 | 66699 | 0.388625 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9705 | 0.118608 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 175137 | 0.139504 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 102423 | 0.248358 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 149118 | 0.146152 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37115 | 0.212511 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8900 | 0.037649 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 56408 | 0.432292 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 전체 | 206945 | 0.502293 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 사전 | 48573 | 0.662677 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5465 | 0.628278 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 152907 | 0.430932 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 76534 | 0.585270 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 130411 | 0.438961 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 28941 | 0.543586 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 3849 | 0.283604 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 43744 | 0.636577 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 전체 | 268915 | 0.521363 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 사전 | 47905 | 0.692161 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5311 | 0.678095 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 215699 | 0.465804 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 86334 | 0.590501 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 182581 | 0.477164 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 33297 | 0.536780 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4484 | 0.325160 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 48553 | 0.648739 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 전체 | 411337 | 0.544147 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 사전 | 47063 | 0.728463 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5111 | 0.722456 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 359163 | 0.503312 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 108828 | 0.586683 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 302509 | 0.520881 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 43424 | 0.524418 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5926 | 0.375549 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 59478 | 0.654400 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 전체 | 572974 | 0.557975 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 사전 | 46364 | 0.763452 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4967 | 0.746901 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 521643 | 0.526868 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 134719 | 0.583715 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 438255 | 0.546310 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 55695 | 0.509761 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7592 | 0.448934 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 71432 | 0.659212 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 전체 | 590914 | 0.595991 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 사전 | 46308 | 0.763930 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 4959 | 0.747363 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 539647 | 0.570599 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보 전체 | 137855 | 0.608480 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 영상 계보 전체 | 453059 | 0.590643 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 57313 | 0.542283 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 7792 | 0.493502 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 72750 | 0.677611 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 전체 | 590914 | 0.160114 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 사전 | 46308 | 0.517285 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 4959 | 0.201319 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 539647 | 0.147999 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 137855 | 0.203924 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 453059 | 0.153715 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 57313 | 0.090561 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7792 | 0.069956 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 72750 | 0.407712 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 전체 | 445528 | 0.410606 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 사전 | 35304 | 0.837699 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3151 | 0.681468 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 407073 | 0.373858 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 97889 | 0.601980 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 347639 | 0.363929 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 36244 | 0.488017 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4604 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 57041 | 0.699240 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 전체 | 543195 | 0.419013 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 사전 | 35077 | 0.862302 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3101 | 0.726017 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 505017 | 0.384009 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 115045 | 0.574468 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 428150 | 0.375368 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 45033 | 0.477801 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5684 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 64328 | 0.670725 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 전체 | 732435 | 0.511170 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 사전 | 34615 | 0.915733 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2885 | 0.790483 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 694935 | 0.489743 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 142418 | 0.625441 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 590017 | 0.481168 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 59305 | 0.503607 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7480 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 75633 | 0.740635 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 전체 | 939977 | 0.562425 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 사전 | 34232 | 0.929919 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2759 | 0.807632 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 902986 | 0.541310 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 172885 | 0.606674 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 767092 | 0.550755 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 75548 | 0.492801 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 9374 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 87963 | 0.727951 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 전체 | 956004 | 0.587853 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 사전 | 34202 | 0.930172 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2743 | 0.812738 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 919059 | 0.568766 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보 전체 | 174725 | 0.628320 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 영상 계보 전체 | 781279 | 0.577815 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 76457 | 0.517248 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 9483 | 0.500348 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 88785 | 0.742874 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 전체 | 956004 | 0.135187 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 사전 | 34202 | 0.775869 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2743 | 0.439795 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 919059 | 0.126803 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 174725 | 0.285697 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 781279 | 0.117867 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 76457 | 0.187722 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 9483 | 0.162241 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 88785 | 0.470397 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 전체 | 684354 | 0.417903 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 사전 | 31585 | 0.893432 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2312 | 0.636829 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 650457 | 0.395505 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 141492 | 0.535148 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 542862 | 0.387658 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 58573 | 0.402619 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 6954 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 75965 | 0.669981 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 전체 | 783616 | 0.448337 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31405 | 0.912945 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2271 | 0.697686 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 749940 | 0.425363 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 157085 | 0.540004 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 626531 | 0.418729 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 67433 | 0.416675 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7927 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 81725 | 0.670029 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 전체 | 999930 | 0.483245 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31110 | 0.934240 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2180 | 0.741147 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 966640 | 0.462470 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 190517 | 0.530675 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 809413 | 0.460243 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 86665 | 0.419477 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 10005 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 93847 | 0.652133 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 전체 | 1214821 | 0.507977 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 사전 | 30849 | 0.946911 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2114 | 0.766428 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1181858 | 0.499580 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 219727 | 0.523487 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 995094 | 0.502837 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 103775 | 0.416361 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11662 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 104290 | 0.641796 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 전체 | 1234850 | 0.531312 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 사전 | 30824 | 0.946990 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2104 | 0.767519 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 1201922 | 0.518006 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보 전체 | 222277 | 0.542100 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 영상 계보 전체 | 1012573 | 0.528403 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 105387 | 0.444893 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 11783 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 105107 | 0.655705 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 전체 | 1234850 | 0.123551 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 사전 | 30824 | 0.774499 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2104 | 0.386737 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1201922 | 0.116626 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 222277 | 0.233519 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1012573 | 0.108138 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105387 | 0.129466 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11783 | 0.128162 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 105107 | 0.407193 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 전체 | 833283 | 0.408976 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 사전 | 27606 | 0.909200 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1724 | 0.655984 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 803953 | 0.392842 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 163969 | 0.517996 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 669314 | 0.383567 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 69685 | 0.409940 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7817 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 86467 | 0.615894 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 전체 | 933861 | 0.443211 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27499 | 0.930402 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1701 | 0.700894 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 904661 | 0.426296 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 178498 | 0.529856 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 755363 | 0.418446 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 78435 | 0.424390 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8754 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 91309 | 0.627905 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 전체 | 1161452 | 0.467375 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27327 | 0.946113 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1660 | 0.710308 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1132465 | 0.451898 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 210193 | 0.513470 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 951259 | 0.450152 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 97394 | 0.411982 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 10827 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 101972 | 0.611688 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.498147 | 2796061 | 0.360820 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.957045 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.739177 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.483743 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.506603 | 395633 | 0.410882 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.488359 | 2400428 | 0.352843 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.406461 | 163396 | 0.369895 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.500000 | 8029 | 0.423804 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.604762 | 224208 | 0.449313 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.498360 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.962456 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.752684 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.482810 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.516609 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.485162 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.419482 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.619102 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.508592 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.967049 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.751657 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.499767 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.527422 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.502759 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.435468 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.631959 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.529086 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.972338 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.753983 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.515614 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.547920 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.523449 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.457249 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.500228 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.655020 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.550976 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.977084 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.773812 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.537304 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.566510 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.546326 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.478727 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.514480 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.678166 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.575078 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.980640 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.779582 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.561068 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.589781 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.570848 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.500022 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.519698 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.698922 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.599498 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.984260 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.768910 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.585117 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.611106 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.596168 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.524654 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.534377 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.719593 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.625309 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.987090 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.784493 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.610866 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.630398 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.623871 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.542441 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.541702 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.741855 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.650617 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.990074 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.777971 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.636281 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.652560 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.650001 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.562439 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.562242 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.763479 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.678183 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.992015 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.794350 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.664055 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.676343 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.678693 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.586883 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.586851 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.788265 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.702318 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.993416 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.801383 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.688370 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.695576 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.703980 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.606206 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.597064 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.807663 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.724753 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.994509 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.809519 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.711219 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.713123 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.727864 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.621688 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.622323 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.828364 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.746749 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.995520 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.821262 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.733727 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.731654 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.751063 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.641452 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.634427 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.846297 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.770421 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.996575 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.824328 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.757938 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.757364 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.774113 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.666003 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.649597 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.866073 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.788694 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.997053 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.830279 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.776818 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.771084 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.793791 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.678147 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.686526 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.880435 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 전체 | 1397086 | 0.806837 | 2796061 | 0.354446 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 사전 | 27187 | 0.997652 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1617 | 0.842427 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1368282 | 0.794995 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236868 | 0.786676 | 395633 | 0.655533 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1160218 | 0.812139 | 2400428 | 0.287534 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 113355 | 0.692955 | 163396 | 0.655912 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12491 | 0.708999 | 8029 | 0.635453 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111022 | 0.893174 | 224208 | 0.656257 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 전체 | 94935 | 0.349072 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 사전 | 75834 | 0.330329 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11043 | 0.487531 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 8058 | 0.382323 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 77888 | 0.332078 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 17047 | 0.447232 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 27335 | 0.416159 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4937 | 0.138059 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 45616 | 0.292283 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 전체 | 126239 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 사전 | 69340 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 10230 | 0.555365 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 46669 | 0.611764 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 82561 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 43678 | 0.612288 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 30520 | 0.469210 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4333 | 0.307599 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 47708 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 전체 | 235540 | 0.780668 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 사전 | 66528 | 0.501709 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9652 | 0.592015 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 159360 | 0.991290 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 102674 | 0.524486 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 132866 | 0.997143 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37383 | 0.506446 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11001 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 54290 | 0.508511 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 전체 | 247779 | 0.834695 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 사전 | 66361 | 0.501922 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 9623 | 0.594057 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 171795 | 0.996613 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보 전체 | 104318 | 0.536517 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 영상 계보 전체 | 143461 | 0.999296 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 37845 | 0.521695 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 11640 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 54833 | 0.512478 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 전체 | 247779 | 0.174764 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 사전 | 66361 | 0.349786 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9623 | 0.140503 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 171795 | 0.141030 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 104318 | 0.228807 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 143461 | 0.150858 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37845 | 0.195876 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11640 | 0.042408 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 54833 | 0.375733 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 전체 | 205413 | 0.497077 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 사전 | 47877 | 0.655421 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5600 | 0.623467 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 151936 | 0.401747 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 76613 | 0.578046 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 128800 | 0.402576 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 28401 | 0.553416 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5201 | 0.424797 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 43011 | 0.610458 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 전체 | 267889 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 사전 | 47187 | 0.683091 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5441 | 0.689676 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 215261 | 0.429872 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 86305 | 0.585136 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 181584 | 0.430316 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 32533 | 0.549707 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 6053 | 0.491756 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 47719 | 0.619499 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 전체 | 421661 | 0.508319 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 사전 | 46300 | 0.730563 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5234 | 0.728359 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 370127 | 0.469495 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 111716 | 0.614812 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 309945 | 0.457064 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 42180 | 0.540797 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12073 | 0.865953 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 57463 | 0.639601 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 전체 | 608441 | 0.535940 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 사전 | 45720 | 0.769063 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5102 | 0.743687 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 557619 | 0.505804 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 145755 | 0.672911 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 462686 | 0.485344 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 53480 | 0.520672 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 24396 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 67879 | 0.652538 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 전체 | 629930 | 0.574418 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 사전 | 45651 | 0.770059 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 5090 | 0.745122 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 579189 | 0.549488 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보 전체 | 149742 | 0.702796 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 영상 계보 전체 | 480188 | 0.528825 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 54926 | 0.552390 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 25850 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 68966 | 0.669287 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 전체 | 629930 | 0.140637 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 사전 | 45651 | 0.529589 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5090 | 0.213406 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 579189 | 0.128145 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 149742 | 0.176736 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 480188 | 0.135300 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 54926 | 0.104304 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 25850 | 0.030963 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 68966 | 0.462388 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 전체 | 461448 | 0.382492 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 사전 | 35128 | 0.838954 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3262 | 0.650167 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 423058 | 0.347192 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 100048 | 0.611436 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 361400 | 0.332497 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 35384 | 0.486606 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 9956 | 0.549198 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 54708 | 0.711834 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 전체 | 571415 | 0.390279 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 사전 | 34851 | 0.863650 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3190 | 0.709424 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 533374 | 0.358988 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 116266 | 0.589034 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 455149 | 0.345674 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 43538 | 0.476614 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11264 | 0.524569 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 61464 | 0.685612 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 전체 | 778501 | 0.476019 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 사전 | 34344 | 0.912149 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2961 | 0.774815 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 741196 | 0.446975 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 145871 | 0.655014 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 632630 | 0.426253 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 57412 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 16687 | 0.896868 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 71772 | 0.743358 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 전체 | 1005789 | 0.507638 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 사전 | 33983 | 0.926618 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2803 | 0.805829 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 969003 | 0.494036 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 179012 | 0.653747 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 826777 | 0.473530 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 73368 | 0.484502 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 22925 | 0.976439 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 82719 | 0.732819 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 전체 | 1025997 | 0.534093 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 사전 | 33944 | 0.926895 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2786 | 0.810688 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 989267 | 0.516371 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보 전체 | 182035 | 0.678815 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 영상 계보 전체 | 843962 | 0.502320 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 74372 | 0.508133 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 24133 | 0.990114 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 83530 | 0.745853 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 전체 | 1025997 | 0.123487 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 사전 | 33944 | 0.730407 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2786 | 0.428003 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 989267 | 0.114583 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 182035 | 0.291795 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 843962 | 0.105621 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 74372 | 0.208531 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 24133 | 0.103159 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 83530 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 전체 | 716806 | 0.400665 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 사전 | 31250 | 0.871078 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2361 | 0.652756 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 683195 | 0.379938 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 143478 | 0.553969 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 573328 | 0.363752 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 58880 | 0.405138 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 13932 | 0.725647 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 70666 | 0.678623 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 전체 | 835021 | 0.427992 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31064 | 0.896425 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2312 | 0.704250 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 801645 | 0.407843 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 158245 | 0.560387 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 676776 | 0.392564 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 67325 | 0.416782 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 15253 | 0.728058 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 75667 | 0.679006 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 전체 | 1093951 | 0.454267 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 사전 | 30731 | 0.920914 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2227 | 0.734160 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1060993 | 0.436578 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 190964 | 0.542647 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 902987 | 0.425621 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 85821 | 0.412424 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 18206 | 0.710711 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 86937 | 0.654739 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 전체 | 1398801 | 0.493683 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 사전 | 30452 | 0.935399 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2146 | 0.752711 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1366203 | 0.478860 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 220989 | 0.539904 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1177812 | 0.473173 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 101584 | 0.411630 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 23061 | 0.766166 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 96344 | 0.646583 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 전체 | 1436468 | 0.514574 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 사전 | 30409 | 0.935776 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2137 | 0.754050 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 1403922 | 0.504102 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보 전체 | 223881 | 0.561079 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 영상 계보 전체 | 1212587 | 0.504179 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 103096 | 0.439737 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 23608 | 0.789389 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 97177 | 0.662203 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 전체 | 1436468 | 0.092896 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 사전 | 30409 | 0.722572 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2137 | 0.381872 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1403922 | 0.087458 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 223881 | 0.249750 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1212587 | 0.076621 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 103096 | 0.147993 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 23608 | 0.199202 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 97177 | 0.431706 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 전체 | 910428 | 0.384607 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 사전 | 26954 | 0.890894 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1753 | 0.641411 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 881721 | 0.370907 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 165595 | 0.537415 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 744833 | 0.355132 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 70120 | 0.404473 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 16213 | 0.722489 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 79262 | 0.638352 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 전체 | 1063306 | 0.414144 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26824 | 0.918629 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1730 | 0.701984 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1034752 | 0.400038 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 179690 | 0.552607 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 883616 | 0.384980 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 77941 | 0.426606 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 18238 | 0.733954 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 83511 | 0.653089 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 전체 | 1562425 | 0.480488 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26632 | 0.939260 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1689 | 0.731481 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1534104 | 0.468691 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 216615 | 0.547659 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1345810 | 0.461161 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 94242 | 0.413692 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 29878 | 0.794471 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 92495 | 0.635968 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 전체 | 95444 | 0.358057 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 사전 | 76012 | 0.342598 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 11014 | 0.490764 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 8418 | 0.352658 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 78297 | 0.344010 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 17147 | 0.435690 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 27435 | 0.425187 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5041 | 0.136160 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 45821 | 0.311809 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 전체 | 128232 | 0.500823 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 사전 | 70439 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 10248 | 0.554805 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 47545 | 0.659682 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 83369 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 44863 | 0.653544 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 30184 | 0.504320 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4183 | 0.366026 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 49002 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 전체 | 238947 | 0.805040 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 사전 | 67552 | 0.503053 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9686 | 0.589194 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 161709 | 0.997050 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 102244 | 0.523754 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 136703 | 0.999784 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37238 | 0.526879 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 7498 | 0.710261 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 57508 | 0.516750 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 전체 | 250740 | 0.855117 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 사전 | 67398 | 0.503375 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 9641 | 0.591839 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 173701 | 0.999121 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보 전체 | 103916 | 0.536140 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 영상 계보 전체 | 146824 | 0.999974 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 37685 | 0.542572 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 8023 | 0.796706 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 58208 | 0.522530 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 전체 | 250740 | 0.171255 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 사전 | 67398 | 0.339811 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 9641 | 0.157363 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 173701 | 0.130638 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 103916 | 0.248054 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 146824 | 0.133319 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 37685 | 0.220634 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 8023 | 0.064205 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 58208 | 0.332211 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 전체 | 206069 | 0.498312 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 사전 | 50044 | 0.621060 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5800 | 0.606617 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 150225 | 0.412935 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 79996 | 0.550756 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 126073 | 0.418668 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 30054 | 0.512261 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 4576 | 0.407227 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 45366 | 0.594114 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 전체 | 267343 | 0.500051 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 사전 | 49270 | 0.654295 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5651 | 0.666454 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 212422 | 0.443018 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 90658 | 0.565605 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 176685 | 0.450119 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 34540 | 0.517568 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 5625 | 0.443126 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 50493 | 0.611553 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 전체 | 414150 | 0.518554 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 사전 | 48205 | 0.700734 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5424 | 0.718416 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 360521 | 0.484059 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 117784 | 0.590061 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 296366 | 0.480923 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 44781 | 0.518453 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 10668 | 0.708438 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 62335 | 0.626978 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 전체 | 590482 | 0.548627 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 사전 | 47451 | 0.741769 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5264 | 0.742396 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 537767 | 0.520747 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 156812 | 0.658659 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 433670 | 0.503932 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 56458 | 0.508131 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 25179 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 75175 | 0.638777 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 전체 | 609146 | 0.586905 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 사전 | 47393 | 0.742394 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 5248 | 0.743308 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 556505 | 0.564448 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보 전체 | 161372 | 0.689703 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 영상 계보 전체 | 447774 | 0.545520 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 57909 | 0.540104 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 26924 | 1.000000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 76539 | 0.659908 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 전체 | 609146 | 0.152274 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 사전 | 47393 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 5248 | 0.202381 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 556505 | 0.139976 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 161372 | 0.145902 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 447774 | 0.153582 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 57909 | 0.099104 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 26924 | 0.034818 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 76539 | 0.326871 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 전체 | 451958 | 0.401508 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 사전 | 35872 | 0.817395 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3317 | 0.653288 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 412769 | 0.366096 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 105937 | 0.571729 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 346021 | 0.357392 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 36913 | 0.486776 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 10692 | 0.477991 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 58332 | 0.654843 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 전체 | 552104 | 0.406644 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 사전 | 35588 | 0.843410 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3251 | 0.693231 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 513265 | 0.373613 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 123558 | 0.556495 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 428546 | 0.364949 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 45438 | 0.481870 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 11755 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 66365 | 0.635042 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 전체 | 731362 | 0.489261 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 사전 | 34985 | 0.893984 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 3040 | 0.753512 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 693337 | 0.458597 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 150593 | 0.606702 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 580769 | 0.446077 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 59462 | 0.500174 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12886 | 0.547692 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 78245 | 0.699221 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 전체 | 920167 | 0.514577 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 사전 | 34541 | 0.909713 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2877 | 0.765809 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 882749 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 182398 | 0.597571 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 737769 | 0.490870 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 75911 | 0.496069 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 15467 | 0.553261 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 91020 | 0.695732 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 전체 | 936099 | 0.540201 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 사전 | 34505 | 0.910023 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2863 | 0.768903 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 898731 | 0.521262 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보 전체 | 184425 | 0.618028 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 영상 계보 전체 | 751674 | 0.519529 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 76903 | 0.518042 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 15602 | 0.574893 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 91920 | 0.709262 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 전체 | 936099 | 0.135131 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 사전 | 34505 | 0.687619 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2863 | 0.413743 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 898731 | 0.127205 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 184425 | 0.280448 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 751674 | 0.115737 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 76903 | 0.199169 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 15602 | 0.240405 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 91920 | 0.414264 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 전체 | 679531 | 0.410244 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 사전 | 31729 | 0.861366 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2379 | 0.633372 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 645423 | 0.388919 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 150768 | 0.522850 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 528763 | 0.378766 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 59929 | 0.403409 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 12034 | 0.533844 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 78805 | 0.629975 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 전체 | 780356 | 0.439385 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31501 | 0.889617 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2323 | 0.694278 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 746532 | 0.417839 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 167132 | 0.532539 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 613224 | 0.408475 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 68902 | 0.416519 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 13589 | 0.529651 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 84641 | 0.640452 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 전체 | 992578 | 0.464063 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 사전 | 31103 | 0.916955 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2229 | 0.729888 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 959246 | 0.445058 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 202874 | 0.524015 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 789704 | 0.438821 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 88119 | 0.412129 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 16533 | 0.516374 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 98222 | 0.627511 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 전체 | 1197434 | 0.491627 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 사전 | 30811 | 0.932194 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2161 | 0.759475 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1164462 | 0.474432 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 234029 | 0.518414 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 963405 | 0.472728 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 105043 | 0.406104 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 19016 | 0.510315 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 109970 | 0.623565 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 전체 | 1214801 | 0.506740 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 사전 | 30774 | 0.932528 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 초기 영상(MVS 계열) | 2157 | 0.759795 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 밀도 제어 생성 | 1181870 | 0.499240 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보 전체 | 236774 | 0.537297 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 영상 계보 전체 | 978027 | 0.497056 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 맞음 | 106450 | 0.434852 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 틀림 | 19215 | 0.528483 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 사전 계보·참값 없음 | 111109 | 0.638939 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 전체 | 1214801 | 0.125986 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 사전 | 30774 | 0.697550 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 2157 | 0.374555 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1181870 | 0.119486 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 236774 | 0.219521 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 978027 | 0.111708 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 106450 | 0.133140 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 19215 | 0.164889 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 111109 | 0.359847 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 전체 | 825391 | 0.407125 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 사전 | 26991 | 0.888035 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1690 | 0.668939 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 796710 | 0.392168 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 170973 | 0.521596 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 654418 | 0.379557 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 70535 | 0.406526 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 13366 | 0.548271 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 87072 | 0.617087 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 전체 | 928361 | 0.437064 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26893 | 0.917616 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1669 | 0.717658 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 899799 | 0.421449 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 187116 | 0.534202 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 741245 | 0.410382 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 79187 | 0.421728 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 14864 | 0.562028 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 93065 | 0.628771 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 전체 | 1151299 | 0.457097 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26735 | 0.937291 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1635 | 0.741714 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1122929 | 0.442803 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 220872 | 0.518154 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 930427 | 0.436585 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 97151 | 0.403646 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 17874 | 0.543598 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 105847 | 0.616551 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.488872 | 2796061 | 0.360820 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.951128 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.779053 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.475580 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.510808 | 395633 | 0.410882 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.476536 | 2400428 | 0.352843 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.398675 | 163396 | 0.369895 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.550031 | 8029 | 0.423804 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.610246 | 224208 | 0.449313 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.487547 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.958790 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.783869 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.472944 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.519296 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.472198 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.408302 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.557358 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.618032 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.500000 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.963568 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.795761 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.488936 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.530369 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.488014 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.424530 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.580438 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.631379 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.517595 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.969195 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.789360 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.504800 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.549904 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.507803 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.444570 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.600389 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.652680 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.539609 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.974177 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.824880 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.526232 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.569322 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.530565 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.464696 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.624931 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.672789 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.563177 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.978825 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.813105 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.549424 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.588187 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.555795 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.484737 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.654698 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.692509 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.589226 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.983065 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.827021 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.575323 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.614581 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.581695 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.513932 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.691757 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.717351 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.613171 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.986207 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.839364 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.599172 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.634619 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.607278 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.530766 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.719728 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.735904 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.639775 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.988667 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.845782 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.626113 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.654900 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.635613 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.551579 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.749852 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.761034 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.667596 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.990812 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.842315 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.653776 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.680772 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.663945 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.576296 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.774989 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.785577 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.692116 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.992518 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.845428 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.678615 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.702213 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.689306 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.594868 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.805054 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.805746 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.715825 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.993791 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.867352 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.702560 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.719781 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.714682 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.611673 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.830025 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.823261 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.738911 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.994914 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.860107 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.726226 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.740677 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.738455 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.632838 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.857279 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.840511 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.762974 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.995888 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.864896 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.750656 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.763951 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.762612 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.659573 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.878694 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.857623 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.782538 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.996643 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.858889 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.771056 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.777984 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.783757 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.670715 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.896539 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.872714 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 전체 | 1386593 | 0.801311 | 2796061 | 0.354446 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 사전 | 26566 | 0.997198 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 초기 영상(MVS 계열) | 1599 | 0.874938 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 밀도 제어 생성 | 1358428 | 0.790087 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보 전체 | 249470 | 0.795238 | 395633 | 0.655533 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 영상 계보 전체 | 1137123 | 0.802931 | 2400428 | 0.287534 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 맞음 | 112166 | 0.687467 | 163396 | 0.655912 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 틀림 | 20425 | 0.911530 | 8029 | 0.635453 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 사전 계보·참값 없음 | 116879 | 0.888339 | 224208 | 0.656257 |

## 다섯 영상 PSNR

| 판 | 반복·시점 | 이번 dB | nojudge dB | 중단 |
|---|---|---:|---:|---|
| lt_dyngt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 14.008034 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 16.233286 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 16.975668 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 16.688434 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 16.619904 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 17.238244 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 17.891659 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 18.841576 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 19.118803 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 18.472776 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 18.452983 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 19.361774 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 19.628570 | 20.085838 | 없음 |
| lt_dyngt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 19.733163 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 20.474686 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 19.605127 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 19.524338 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 20.206119 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 20.274450 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 20.781182 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 21.229025 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 21.058199 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 20.349971 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 20.818714 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 21.281010 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 21.388590 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 21.725782 | 22.202314 | 없음 |
| lt_dyngt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 21.846834 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 21.999127 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 22.436541 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 22.854362 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 22.618808 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 22.768865 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 22.860306 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 22.737418 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 23.007222 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 23.006193 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 23.427239 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 23.221344 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 23.147561 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 23.367738 | 기록 없음 | 없음 |
| lt_dyngt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 23.419484 | 24.250185 | 없음 |
| lt_fixgt_LoD2_s0 | 1000 after optimizer and opacity floors, before density/reset | 11.967990 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 2000 after optimizer and opacity floors, before density/reset | 15.927810 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 3000 after optimizer and opacity floors, before density/reset | 16.292999 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 3000 immediately before actual periodic reset, after density | 15.992009 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 3100 after optimizer and opacity floors, before density/reset | 12.636479 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 3500 after optimizer and opacity floors, before density/reset | 15.971259 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 4000 after optimizer and opacity floors, before density/reset | 16.996986 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 5000 after optimizer and opacity floors, before density/reset | 17.972542 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 6000 after optimizer and opacity floors, before density/reset | 18.282019 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 6000 immediately before actual periodic reset, after density | 18.005090 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 6100 after optimizer and opacity floors, before density/reset | 13.746413 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 6500 after optimizer and opacity floors, before density/reset | 17.415215 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 7000 after optimizer and opacity floors, before density/reset | 18.084643 | 20.085838 | 없음 |
| lt_fixgt_LoD2_s0 | 8000 after optimizer and opacity floors, before density/reset | 18.440018 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 9000 after optimizer and opacity floors, before density/reset | 19.036474 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 9000 immediately before actual periodic reset, after density | 18.796688 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 9100 after optimizer and opacity floors, before density/reset | 17.050611 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 9500 after optimizer and opacity floors, before density/reset | 18.618332 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 10000 after optimizer and opacity floors, before density/reset | 18.703762 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 11000 after optimizer and opacity floors, before density/reset | 19.454931 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 12000 after optimizer and opacity floors, before density/reset | 19.793195 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 12000 immediately before actual periodic reset, after density | 19.538208 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 12100 after optimizer and opacity floors, before density/reset | 15.883193 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 12500 after optimizer and opacity floors, before density/reset | 18.500117 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 13000 after optimizer and opacity floors, before density/reset | 19.076369 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 14000 after optimizer and opacity floors, before density/reset | 19.407525 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 15000 after optimizer and opacity floors, before density/reset | 19.581764 | 22.202314 | 없음 |
| lt_fixgt_LoD2_s0 | 16000 after optimizer and opacity floors, before density/reset | 19.888531 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 17000 after optimizer and opacity floors, before density/reset | 19.991945 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 18000 after optimizer and opacity floors, before density/reset | 20.213842 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 19000 after optimizer and opacity floors, before density/reset | 20.485811 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 20000 after optimizer and opacity floors, before density/reset | 20.317385 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 21000 after optimizer and opacity floors, before density/reset | 20.524164 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 22000 after optimizer and opacity floors, before density/reset | 20.595979 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 23000 after optimizer and opacity floors, before density/reset | 20.541722 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 24000 after optimizer and opacity floors, before density/reset | 20.666080 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 25000 after optimizer and opacity floors, before density/reset | 20.670718 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 26000 after optimizer and opacity floors, before density/reset | 20.780070 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 27000 after optimizer and opacity floors, before density/reset | 20.676369 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 28000 after optimizer and opacity floors, before density/reset | 20.593849 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 29000 after optimizer and opacity floors, before density/reset | 20.732672 | 기록 없음 | 없음 |
| lt_fixgt_LoD2_s0 | 30000 after optimizer and opacity floors, before density/reset | 20.677782 | 24.250185 | training PSNR more than 3 dB below same-iteration nojudge |
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
| lt_dyngt_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 24.197215 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 24.582121 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 24.579694 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 24.827096 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 24.831234 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 25.247602 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 24.506787 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 24.895785 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 25.078199 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 24.977407 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 25.337838 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 25.223413 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 25.613044 | 기록 없음 | 없음 |
| lt_dyngt_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 25.706836 | 25.919701 | 없음 |
| lt_dynnow_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 14.054082 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 16.128063 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 17.149842 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 3000 immediately before actual periodic reset, after density | 16.869701 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 17.236114 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 17.908500 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 18.389050 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 19.406474 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 20.373093 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 6000 immediately before actual periodic reset, after density | 20.130320 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 19.253602 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 20.258908 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 20.883726 | 20.828419 | 없음 |
| lt_dynnow_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 20.794247 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 21.243475 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 9000 immediately before actual periodic reset, after density | 21.053181 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 20.807156 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 21.628273 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 21.805894 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 22.160584 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 22.504102 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 12000 immediately before actual periodic reset, after density | 21.721380 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 21.489637 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 22.600941 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 22.478102 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 23.070284 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 23.288784 | 23.523298 | 없음 |
| lt_dynnow_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 23.520229 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 23.947995 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 24.294012 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 24.284383 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 24.565747 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 24.558683 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 24.955399 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 24.215343 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 24.628646 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 24.795469 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 24.728280 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 25.060365 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 24.928605 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 25.293628 | 기록 없음 | 없음 |
| lt_dynnow_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 25.334840 | 25.919701 | 없음 |
| lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 14.218595 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 16.196446 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 17.928976 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 17.687618 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 18.163221 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 18.614739 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 19.080431 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 19.866906 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 20.689761 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 20.409689 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 19.526749 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 20.355098 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 20.973975 | 20.828419 | 없음 |
| lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 20.877921 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 21.148594 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 20.857759 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 21.073689 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 21.599866 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 21.778647 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 21.966420 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 22.628034 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 22.371912 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 21.426081 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 22.522758 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 22.458329 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 22.900887 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 1000 after optimizer and opacity floors, before density/reset | 13.397761 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 2000 after optimizer and opacity floors, before density/reset | 16.107687 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3000 after optimizer and opacity floors, before density/reset | 17.685275 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3000 immediately before actual periodic reset, after density | 17.511549 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3100 after optimizer and opacity floors, before density/reset | 18.185402 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 3500 after optimizer and opacity floors, before density/reset | 18.603661 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 4000 after optimizer and opacity floors, before density/reset | 19.010346 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 5000 after optimizer and opacity floors, before density/reset | 19.878494 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6000 after optimizer and opacity floors, before density/reset | 20.721371 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6000 immediately before actual periodic reset, after density | 20.436815 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6100 after optimizer and opacity floors, before density/reset | 19.798025 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 6500 after optimizer and opacity floors, before density/reset | 20.387822 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 7000 after optimizer and opacity floors, before density/reset | 21.055323 | 20.828419 | 없음 |
| lt_dynsoft_ALS_s0 | 8000 after optimizer and opacity floors, before density/reset | 20.962589 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9000 after optimizer and opacity floors, before density/reset | 21.375312 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9000 immediately before actual periodic reset, after density | 20.425921 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9100 after optimizer and opacity floors, before density/reset | 21.244323 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 9500 after optimizer and opacity floors, before density/reset | 21.837784 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 10000 after optimizer and opacity floors, before density/reset | 21.936917 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 11000 after optimizer and opacity floors, before density/reset | 22.332774 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12000 after optimizer and opacity floors, before density/reset | 22.376818 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12000 immediately before actual periodic reset, after density | 22.108302 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12100 after optimizer and opacity floors, before density/reset | 21.449904 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 12500 after optimizer and opacity floors, before density/reset | 21.728147 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 13000 after optimizer and opacity floors, before density/reset | 22.606121 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 14000 after optimizer and opacity floors, before density/reset | 23.085225 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 15000 after optimizer and opacity floors, before density/reset | 23.245563 | 23.523298 | 없음 |
| lt_dynsoft_ALS_s0 | 16000 after optimizer and opacity floors, before density/reset | 23.642429 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 17000 after optimizer and opacity floors, before density/reset | 24.035510 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 18000 after optimizer and opacity floors, before density/reset | 24.417048 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 19000 after optimizer and opacity floors, before density/reset | 24.410498 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 20000 after optimizer and opacity floors, before density/reset | 24.692033 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 21000 after optimizer and opacity floors, before density/reset | 24.716038 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 22000 after optimizer and opacity floors, before density/reset | 25.099752 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 23000 after optimizer and opacity floors, before density/reset | 24.357058 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 24000 after optimizer and opacity floors, before density/reset | 24.732644 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 25000 after optimizer and opacity floors, before density/reset | 24.900177 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 26000 after optimizer and opacity floors, before density/reset | 24.788623 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 27000 after optimizer and opacity floors, before density/reset | 25.263182 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 28000 after optimizer and opacity floors, before density/reset | 25.036489 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 29000 after optimizer and opacity floors, before density/reset | 25.402756 | 기록 없음 | 없음 |
| lt_dynsoft_ALS_s0 | 30000 after optimizer and opacity floors, before density/reset | 25.494345 | 25.919701 | 없음 |

## 저장 모델의 통계

15,000·30,000회 모델을 읽었다. 과거 생성 표식이 없어 초기 사전·초기 영상·밀도 제어 생성의 분리는 ‘기록 없음’이다. 계보별·참값 칸별 통계는 정확한 저장값으로 센다.

| 단위·판 | 반복 | 구분 | N | 중앙값 | nojudge N | nojudge 중앙값 |
|---|---:|---|---:|---:|---:|---:|
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 전체 | 1052577 | 0.480038 | 2532261 | 0.430331 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 초기 사전 | 38116 | 0.902678 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 초기 영상(MVS 계열) | 3628 | 0.737790 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 밀도 제어 생성 | 1010833 | 0.457211 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 사전 계보 전체 | 712322 | 0.496296 | 2302664 | 0.434936 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 영상 계보 전체 | 340255 | 0.448173 | 229597 | 0.389880 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 사전 계보·참값 맞음 | 48701 | 0.558125 | 74792 | 0.382829 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 사전 계보·참값 틀림 | 27609 | 0.701500 | 29436 | 0.534946 |
| B0_b10 lt_dyngt_LoD2_s0 | 15000 | 사전 계보·참값 없음 | 636012 | 0.480133 | 2198436 | 0.435365 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 전체 | 1052577 | 0.835316 | 2532261 | 0.403009 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 초기 사전 | 38116 | 0.998119 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 초기 영상(MVS 계열) | 3628 | 0.937896 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 밀도 제어 생성 | 1010833 | 0.811925 | 기록 없음 | 기록 없음 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 사전 계보 전체 | 712322 | 0.868470 | 2302664 | 0.378638 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 영상 계보 전체 | 340255 | 0.753497 | 229597 | 0.663152 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 사전 계보·참값 맞음 | 48701 | 0.916575 | 74792 | 0.760661 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 사전 계보·참값 틀림 | 27609 | 0.988838 | 29436 | 0.968984 |
| B0_b10 lt_dyngt_LoD2_s0 | 30000 | 사전 계보·참값 없음 | 636012 | 0.849712 | 2198436 | 0.348617 |
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
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 전체 | 1379799 | 0.469266 | 2796061 | 0.360820 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 초기 사전 | 27165 | 0.948574 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 1750 | 0.762578 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 밀도 제어 생성 | 1350884 | 0.455857 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 사전 계보 전체 | 223118 | 0.515664 | 395633 | 0.410882 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 영상 계보 전체 | 1156681 | 0.453036 | 2400428 | 0.352843 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 105483 | 0.412787 | 163396 | 0.369895 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 14643 | 0.474041 | 8029 | 0.423804 |
| B173nb_b10 lt_dyngt_ALS_s0 | 15000 | 사전 계보·참값 없음 | 102992 | 0.634025 | 224208 | 0.449313 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 전체 | 1379799 | 0.797742 | 2796061 | 0.354446 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 초기 사전 | 27165 | 0.997225 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 1750 | 0.863555 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 밀도 제어 생성 | 1350884 | 0.785959 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 사전 계보 전체 | 223118 | 0.789749 | 395633 | 0.655533 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 영상 계보 전체 | 1156681 | 0.799741 | 2400428 | 0.287534 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 105483 | 0.680908 | 163396 | 0.655912 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 14643 | 0.720209 | 8029 | 0.635453 |
| B173nb_b10 lt_dyngt_ALS_s0 | 30000 | 사전 계보·참값 없음 | 102992 | 0.908241 | 224208 | 0.656257 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 전체 | 1397086 | 0.498147 | 2796061 | 0.360820 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 초기 사전 | 27187 | 0.957045 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 1617 | 0.739177 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 밀도 제어 생성 | 1368282 | 0.483743 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 사전 계보 전체 | 236868 | 0.506603 | 395633 | 0.410882 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 영상 계보 전체 | 1160218 | 0.488359 | 2400428 | 0.352843 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 113355 | 0.406461 | 163396 | 0.369895 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 12491 | 0.500000 | 8029 | 0.423804 |
| B173nb_b10 lt_dynnow_ALS_s0 | 15000 | 사전 계보·참값 없음 | 111022 | 0.604762 | 224208 | 0.449313 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 전체 | 1397086 | 0.806837 | 2796061 | 0.354446 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 초기 사전 | 27187 | 0.997652 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 1617 | 0.842427 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 밀도 제어 생성 | 1368282 | 0.794995 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 사전 계보 전체 | 236868 | 0.786676 | 395633 | 0.655533 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 영상 계보 전체 | 1160218 | 0.812139 | 2400428 | 0.287534 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 113355 | 0.692955 | 163396 | 0.655912 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 12491 | 0.708999 | 8029 | 0.635453 |
| B173nb_b10 lt_dynnow_ALS_s0 | 30000 | 사전 계보·참값 없음 | 111022 | 0.893174 | 224208 | 0.656257 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 전체 | 1386593 | 0.488872 | 2796061 | 0.360820 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 초기 사전 | 26566 | 0.951128 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 초기 영상(MVS 계열) | 1599 | 0.779053 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 밀도 제어 생성 | 1358428 | 0.475580 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 사전 계보 전체 | 249470 | 0.510808 | 395633 | 0.410882 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 영상 계보 전체 | 1137123 | 0.476536 | 2400428 | 0.352843 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 사전 계보·참값 맞음 | 112166 | 0.398675 | 163396 | 0.369895 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 사전 계보·참값 틀림 | 20425 | 0.550031 | 8029 | 0.423804 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 15000 | 사전 계보·참값 없음 | 116879 | 0.610246 | 224208 | 0.449313 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 전체 | 1386593 | 0.801311 | 2796061 | 0.354446 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 초기 사전 | 26566 | 0.997198 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 초기 영상(MVS 계열) | 1599 | 0.874938 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 밀도 제어 생성 | 1358428 | 0.790087 | 기록 없음 | 기록 없음 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 사전 계보 전체 | 249470 | 0.795238 | 395633 | 0.655533 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 영상 계보 전체 | 1137123 | 0.802931 | 2400428 | 0.287534 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 사전 계보·참값 맞음 | 112166 | 0.687467 | 163396 | 0.655912 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 사전 계보·참값 틀림 | 20425 | 0.911530 | 8029 | 0.635453 |
| B173nb_b10 lt_dynsoft_ALS_s0 | 30000 | 사전 계보·참값 없음 | 116879 | 0.888339 | 224208 | 0.656257 |
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
