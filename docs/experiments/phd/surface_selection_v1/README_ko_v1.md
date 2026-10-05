# 연결 표면·인접 그래프·다중뷰 선택 결과

[P3 표면 분할부터 열기](http://127.0.0.1:8904/?region=P3&stage=1)
· [P2 관측 평가부터 열기](http://127.0.0.1:8904/?region=P2&stage=3)
· [기존 2 m 셀 뷰어](http://127.0.0.1:8903/)

이 작업의 실제 처리 실행 ID는 `PHD-SURFACE-SELECTION-P1P2P3-v2`이며, 연구 task ID는
`PHD-SURFACE-SELECTION-P1P2P3-v1`이다. 첫 실행의 출력 디렉터리 권한 실패는
실제 자료 처리 전에 발생했고, 소스·테스트·실패 로그를 보존했다.

## 확인 순서

1. **표면 분할:** P1/P2/P3를 고르고 MVS·ALS 표면 목록에서 요소를 선택한다.
   3D를 회전/확대하며 전체 영역, 선택 표면, 비교 부분을 전환한다. 회색 미분할 점도 보존한다.
2. **인접 관계:** 소스별 그래프에서 표면 간 접촉, 단차, 법선 차이를 확인한다.
   그래프는 휠 확대·드래그 이동·두 번 클릭 초기화를 지원한다. 공통 경계 지도와
   전체 원본 JSON으로 작은 조각과 겹친 표면도 확인할 수 있다.
3. **관측 평가:** 원본 사진 두 장, 영상쌍·패치 선택, 독립 소스 검사와 공통 마스크
   비교를 확인한다. 독립 검사에서는 후보마다 마스크가 다르므로 비용을 직접 순위로 읽지 않는다.
   각 사진은 확대·이동·원본 배율·큰 보기를 지원한다.
4. **소스 선택:** 판단 이유, 직접 지지 범위, 미관측 범위와 사후 참조 평가를 확인한다.
   지도에서 색칠된 것은 직접 지지 범위이다. 전체 표면에 선택을 전파한 가정은
   별도 진단으로 표시하며 실제 결과에 포함하지 않는다.

## 해석

연결 표면은 기하 후보이고 지붕 의미 정답이 아니다. 높이와 법선만으로 분할 오차가
사라지는 것은 아니며, 이번 실행의 공통 경계 분할은 매우 작은 비교 부분을 많이 만든다.
표면 수·미분할 점·면적 분포와 선택 면적을 함께 본다. 기존 실험과의 비교는 동일
0.5 m 공간 분모를 사용하며, 선택 단위 개수의 비율을 정확도 개선으로 해석하지 않는다.
원영상·원점·카메라·기존 결과를 변경하지 않았다. GS 학습은 이 작업에서 실행하지 않았다.
`scientific_verdict: null`.

## 재현과 저장

설정: `configs/phd/surface_selection_v1/run_v1.json`.
과학 계산·테스트·뷰어는 Docker에서 실행한다. 호스트 런처는 표준 라이브러리로
새 소스 스냅샷, 읽기 전용 입력 마운트와 실행 receipt를 만든다.

```bash
/usr/bin/python3 scripts/phd/surface_selection_v1/launch.py method --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/surface_selection_v1/launch.py evaluation --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/surface_selection_v1/launch.py report --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/surface_selection_v1/launch.py viewer --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/surface_selection_v1/launch.py qa --run-id NEW_RUN_ID
```

완료된 단계는 덮어쓰지 않는다. 새 뷰어/QA에는 새로운 `--attempt-id`를 사용한다.
`--replace-own`은 동일 task label의 이 작업 뷰어만 교체하며 이전 컨테이너 정보와 로그를 보존한다.

외부 payload:
`../JointBuildGS-artifacts/phase-payloads/phd/surface_selection_v1/PHD-SURFACE-SELECTION-P1P2P3-v2/`.
`run/`에 모든 영역의 표면, 소속, 그래프, 관측, 판단과 사후 평가를 보존한다.
`report/`에 한국어 결과·JSON·CSV, 각 단계별 폴더에 실행 명령·소스 해시·검증 로그가 있다.
원 UAS는 방법 실행과 뷰어에 마운트하지 않고, 모든 판단을 동결한 이후 별도 평가에서만 읽는다.

- [실행 전 프로토콜](PROTOCOL_ko_v1.md)
- [정량·정성 결과](RESULT_ko_v1.md)
- [최신 뷰어 검증 기록](TECHNICAL_RETURN_ko_v2.md)
- [이슈 기록](ISSUES_ko_v1.md)
