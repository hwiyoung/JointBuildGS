# 실제 입력 봉인

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

세 지역의 GeoGS 학습을 시작하기 전에 카메라·RGB·학습/평가 명단·prior 깊이·DA3 깊이·초기화/보호점과 각 생성 영수증을 동일 패키지로 봉인했다. 최종 설정은 외부 task의 `contracts/execution_v1.json`이다. 각 단계에서 사용한 이전 설정 snapshot도 남아 있다. 설정이나 입력 해시가 달라지면 실행기는 실패한다.

| 지역 | 학습 / 평가 RGB | prior / DA3 지도 | 초기화·보호점 | 봉인 파일 수 | input_manifest SHA256 |
|---|---:|---:|---:|---:|---|
| P1 | 98 / 15 | 98 / 98 | 93,583 | 1,011 | `3257b3604f630a64948606605c3ae46f2e22d4d5829b5ad49a7d46b342a42112` |
| P2 | 57 / 9 | 57 / 57 | 93,497 | 617 | `6493c602332144510526a54f31700c28cb31eb648250e690d6528fcffe5162a2` |
| P3 | 137 / 20 | 137 / 137 | 94,644 | 1,388 | `5f22de0224d255765adc126d3ba587388e56f3234b93a3657c821921c4d8911a` |

경로는 각각 외부 task의 `inputs/P*/input_manifest.json`이다. 본 단계는 참조를 마운트하거나 읽지 않았다. 평가 RGB는 GeoGS의 평가 split에만 존재하며 prior/DA3 생성 명단은 학습뷰와 정확히 일치한다. DA3의 공식 cubic 보간 음수와 prior의 ray-miss infinity/NaN은 원값을 보존하고 공식 finite-positive loss mask의 제외 대상으로 기록했다. [DA3 전수 감사](DA3_DEPTH_VALIDITY_AUDIT_ko_v1.md)에 전체 수치와 원자료 경로가 있다.

추후 기하 평가용 원 ALS·기존 OpenMVS 바이트도 새 task의 `evaluation_inputs/P*/native.npz`로 그대로 복사하여 `contracts/evaluation_sources_v1.json`에 사전 결박했다. 이는 Wu–Vallet 최적화 결과를 GeoGS 결과로 사용하는 것이 아니다. 포함 배열은 원 ALS/MVS 좌표·원 행 대응·MVS RGB이며 UAS/reference 배열은 없다. 기존 원본 파일은 유지했다.

| 지역 | 원 ALS/MVS native.npz SHA256 |
|---|---|
| P1 | `ef4dba8cf7946ebc7e0337c234298ae9af27e6c46add561cbecdca298e7db794` |
| P2 | `4d64f75d2acdb9ccf3db1f1bdff6c37b954c0519cf349c4ae7330c4302981d6a` |
| P3 | `b2a30325d0742ee1c426ea24cdac8519fd39d148189e98566b82214bb2db7acf` |

이 문서는 입력 준비 완료 기록이다. GeoGS 학습·렌더·표면 품질의 성공 판정이나 과학적 결과를 뜻하지 않는다.
