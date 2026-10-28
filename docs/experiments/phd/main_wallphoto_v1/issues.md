# 문제 기록

- 2026-10-28 19:54 KST: 전체 벽 입력 목록과 점 묶기가 정상 저장된 뒤 실행 셸이 종료 코드 2를 냈다. 실행 중 `run.sh`에 메모리 제한 프로필을 덧붙여 셸의 읽기 위치가 달라진 것이 원인이다. 계산 프로세스는 끝났으며 `inventory.json`과 21개 벽 타일의 저장 기록이 있다. 현재 셸은 `bash -n`으로 다시 검사했다. 실행 중인 파일은 이후 고치지 않고, 필요한 경우 새 실행 파일을 사용한다.
- 2026-10-28 19:54 KST: MemAvailable 약 46 GiB. MESHPATCH 입장 여유 56 GiB와 이 작업 최대 12 GiB를 합한 68 GiB에 못 미쳐 사진 계산은 대기한다. 대기 시간은 외부 작업 폴더의 `logs/resource_wait.log`와 `logs/admission_wait_seconds.txt`에 기록한다.

scientific_verdict: null
- 2026-10-28 20:07 KST: 호스트 nohup 대기 셸이 도구 세션 종료 후 남아 있지 않음을 확인했다. 사진 계산은 시작하지 않았다. Docker 분리 실행으로 입장 대기와 정시 묶음을 유지하도록 바꾸었고, 두 컨테이너의 실행 상태와 상태 파일 갱신을 확인했다.
- 2026-10-28 20:11 KST: 패치 표 양쪽 계산 완료 상태를 읽는 입장 규칙을 추가했다. 앞 대기 컨테이너는 계산 미시작을 확인한 뒤 중지하고 admission-v1 이름으로 보존했다. 현재 worker가 계속 대기한다. 대기 기록은 삭제하지 않았다.

2026-10-28T23:28:15.560386+09:00
```
Traceback (most recent call last):
  File "/repo/scripts/phd/main_wallphoto_v1/wall_pipeline.py", line 33, in <module>
    try:main()
        ^^^^^^
  File "/repo/scripts/phd/main_wallphoto_v1/wall_pipeline.py", line 17, in main
    replay()
  File "/repo/scripts/phd/main_wallphoto_v1/wall_replay.py", line 13, in main
    assert finite_diff==0 and (not len(diff) or diff.max()<.01)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError

```

2026-10-28T23:36:11.499967+09:00
```
Traceback (most recent call last):
  File "/repo/scripts/phd/main_wallphoto_v1/wall_pipeline.py", line 33, in <module>
    try:main()
        ^^^^^^
  File "/repo/scripts/phd/main_wallphoto_v1/wall_pipeline.py", line 17, in main
    replay()
  File "/repo/scripts/phd/main_wallphoto_v1/wall_replay.py", line 13, in main
    assert finite_diff==0 and (not len(diff) or diff.max()<.01)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError

```

2026-10-28T23:43:34.548588+09:00
독립 점수 재현 검증이 같은 assertion에서 반복 실패하여 이 작업의 worker만 중지했다. 기존 117,989점의 계산값과 설정은 보존했다. 투영 숫자 점검은 PASS이나 전체 계산은 미시작이다. 원인을 별도 diagnostic에 기록한다. 점수식·문턱은 변경하지 않는다.

2026-10-28T23:51:10.817687+09:00
독립 재계산 원인 확인: 고정한 표본 4점 중 6908_53360의 point:2224, h=-3.8 m 한 곳에서 원본 float32 보간/평균/분산 반올림으로 균일한 사진(673)의 표준편차가 1e-6을 넘었다. float64 직접 보간의 유효 여부 실패는 FAIL_FINITE_STATUS로 그대로 기록했다. 같은 정밀도의 독립 NumPy 투영·명시적 사진 쌍 점수는 4점 모두 통과했고, 원본 CPU 재실행 float16 저장값도 4점 모두 정확히 일치했다. 원본 Cameras/select_photos/compute/derive 및 설정 SHA는 변경하지 않았다. 전체 발생 빈도나 과학적 결론은 내지 않는다.
추가 수정: 표본 재시도는 기존 결과 SHA를 확인하고 반복 보고만 생략; 그림 메타데이터의 source 중복 인자를 방지; 시험 7동 파일을 전체 시작 전에 동결해 09시 ZIP에 보존; 진행문에 실제 검증 상태 표기. 메시 패치 표가 둘 다 끝난 뒤 소규모 검사도 여유 16 GiB를 적용한다. 기존 구현 잠금은 validation/pre_replay_diagnosis_20261028에 보존하고 새 잠금을 기록했다.

2026-10-28T23:52:28.388835+09:00
기존 4906968 벽 대조: 24,041점의 좌표·법선·접선 및 선택 사진이 일치했다. 15개 조합의 360,615개 판단 중 360,614개가 같고 1개가 달랐다. 원본은 CUDA, 이번 발주는 CPU이며, 곡선 최대 차이는 타일별 0.0004883/0.0284424/0.0161438이다. 수치 정밀도 차이와의 인과를 단정하지 않으며 불일치를 그대로 공개한다(tables/independent_replay.json).
