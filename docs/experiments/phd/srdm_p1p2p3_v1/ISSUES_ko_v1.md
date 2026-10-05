# SRDM P1/P2/P3 이슈와 편차

`PHD-SRDM-P1P2P3-v1` · `scientific_verdict: null`

1. 공식 실행 코드 미확보: 논문 기반 두 단계 재구현으로 진행. 원형과 미명시 설정의 차이는 IMPLEMENTATION_AUDIT_ko_v1.md에 기록한다.
2. 입력 기하 합성검사의 초기 2개 실패: OpenCV alpha=0 정류 후 초점거리를 원 카메라 값으로 가정한 테스트 기대값 문제였다. 실제 rectified P1을 기준으로 검사하도록 고쳤으며 담당 검토의 최종 7개 기하 검사를 통과했다. 실제 영상/ALS 또는 카메라 값은 이 수정으로 변경하지 않았다.
3. P1/P2/P3의 기존 UAS 좌표 기준·표면 피복 한계는 유지한다. 참조의 최근접 거리만으로 소스 정답·시기 변화를 확정하지 않는다.
4. 기존 GeoGS가 GPU를 사용 중이므로 SRDM은 CPU4/동시1개 작업으로 제한한다. RAM은 P1/P2 12GiB, P3 16GiB이며 시작 시 host available 최소24/32GiB를 요구한다. 기존 컨테이너·볼륨·실행 파일을 수정하거나 중단하지 않는다.
5. P1 첫 실행의 임시 배열 I/O 병목: 원해상도·141 disparity의 비용 배열 한 개는0.745GiB이고 동시 전체 배열은 약4.5GiB다. 메모리 여유가 있어도 모든 배열을 공유 디스크 memmap에 쓰고 flush하여, 관측한 순간 CPU3.40%·메모리4.9/12GiB·누적block write13.9GB였다. 약한 단계까지184.5초가 걸렸다. SRDM 전용 container `914078403e60`만 정지했으며 stop 유예 종료 후 exit137을 기록했다. 이는 관측된 OOM이 아니라 에이전트가 요청한 종료다. 원 P1 입력/설정 snapshot과 attempt/console/receipt, 부분 run 및 scratch는 `preserved_attempts/P1_memmap_io_v1`·`P1_memmap_io_scratch_v1`로 보존했다. 참조는 접근하지 않았다. 영상·판단 규칙을 유지한 RAM/하이브리드 임시 저장 복구를 별도 기록한다.
6. 저장 복구: P1/P2는 비용 배열 6개를 RAM에, P3는 사진 비용 2개만 읽기용 파일에 두고 반복 DP 배열 4개를 RAM에 둔다. 동일 float32 계산식과 C++ backend를 사용한다. Docker 합성검사에서 memmap/ram/hybrid의 판단 및 모든 최종 배열이 바이트 단위로 동일했다(13개 core 검사 PASS). 실제 장면에서의 전수 저장방식 동등성 실험을 뜻하지 않는다. P3 자원 상한만 위와 같이 조정하고 해상도·판단·복원 파라미터는 유지했다.
7. P3 hybrid 캐시 회수: 비용6개 논리합16.67GiB가16GiB 한도를 넘어, 실제 `memory.events max=5998, oom=0, oom_kill=0`과 디스크 재읽기를 관측했다. 첫 자원 변경 검사는 순간 host available40GiB 미만에서 중단되어 아무 변경도 하지 않았다. 이후 host available46,220,517,376bytes를 확인한 05:33:35UTC에 해당 SRDM container만20GiB로 확장했다. `attempts/run-P3-20260908T052708.130111Z/RESOURCE_AMENDMENT_REQUEST.json`과 `RESOURCE_AMENDMENT_RESULT.json`에 명령·전후 상한·이벤트·성공을 기록했다. 실행 snapshot/launch의16GiB는 당시 조건으로 보존하며 실제 실행은16→20GiB다. 향후 launcher config는20GiB/시작 여유40GiB로 수정했다. 계산·입력·판단·출력 조건은 바꾸지 않았다.
8. 첫 보고서의 단면 표시: 행 사이 제목/축 라벨이 겹쳤고 RGB 예측점이 검정 UAS·흰 배경과 구별되기 어려웠다. 첫 보고서는 `preserved_attempts/report_layout_v1`로 보존했다. 단면 간격을 자동 조정하고 같은 원 예측점을 청색으로 표시하는 최종 보고서를 다시 생성했다. 점군 RGB·기하·판단·평가·단면 위치/폭/축 범위는 변경하지 않는다.
