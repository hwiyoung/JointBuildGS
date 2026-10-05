# Wu–Vallet 원문 재구현·P3 개발 기술 반환

2026-09-07 · `PHD-WU-VALLET-P3-v1` · **PARTIAL** · `scientific_verdict: null`.

문헌·원문 기반 구성요소 구현, 통제 점군 갱신, P3 입력 동결·영상 sensor mesh, 실제 GS 개발4조건과 별도 참조평가는 완료했다. **실제 P3의 Wu–Vallet 전체 원방법 재현과 실제 A 판단을 받은 B/전체 비교는 미완료**다. ALS 촬영 궤적·scan topology 및 원논문 미공개 설정·matching 계보가 남아 있다.

[실제 P3 비교 화면](http://127.0.0.1:8897/) · [프로토콜/필요성 재검토](PROTOCOL_ko_v1.md) · [Wu 원문 대응](WU_VALLET_REPRODUCTION_ko_v1.md) · [관련 연구](RELATED_METHODS_ko_v1.md) · [실패·미결 기록](ISSUES.md).

## 1. 이번에 확인한 결과

1. **원문 핵심 계산은 구현할 수 있다.** optical origin·native sensor topology를 필수로 받는 양방향 sampled-ray 분류와 원점군 유지/제거/추가를 구현했다. 단위검증9개와5개 통제 장면의 출처 표시 갱신 점군이 PASS다. 원문의 미기재 sampling/거리/집계 선택을 명시했으며 저자 코드와의 동일성은 확인하지 못했다.
2. **P3 실제 자료로 개발까지 진행했다.** 원 MVS865,108점·ALS52,762점과157뷰를 원본 해시·행까지 동결했다. A40뷰의 native depth 피복을 감사하고 현재영상 sensor mesh를 생성했다. 별도의 공급원 가정 B에서4조건×384step을 실행하고8뷰 실제 RGB·기하 깊이·역투영 점군과 UAS 수치 비교를 만들었다.
3. **ALS 원점군의 상대적인 장점이 GS 출력에 그대로 전달되지 않았다.** ALS 원점군의 작은 참조 편차와 고정기하 GS의 큰 역투영 점군 편차를 구분했다. 이는 학습 전 초기 표현/readout에서도 이미 있는 문제다. renderer의 기하 깊이는 여러 평면 교차 깊이의 가중평균이며 물리적 첫 표면을 선택한 결과가 아니다.
4. **제한된 기하 이동의 효과는 혼재했다.** 동일 ALS에서 제한된 법선 이동을 추가하면 외관 지표의 작은 차이와 일부 피복 증가가 있었지만 기존 공통 영상 지지1,488픽셀이 사라졌고 일부 반대 방향 거리 지표는 악화했다. 개선·구조 보존·세부 복원을 입증한 결과로 해석하지 않는다.

## 2. 원방법 재현 수준

| 항목 | 실행 결과 | 해석 |
|---|---|---|
| Wu–Vallet 공식 코드 | 지정 repo/API HTTP404, 저자 checkpoint/설정 미확보 | 공식 코드 재현 미실행 |
| 광선 분류·갱신 모듈 |9개 Docker 단위검증 PASS | finite sampled-ray component; 2023 tetrahedron predicate와 동일하지 않음 |
| GS 없는 통제 점군 갱신 | unchanged/demolition/construction/single/mixed5장면 PASS; 결과점4/4/4/8/20개 | synthetic local metre 좌표. 실제 P3나 논문 원실험 수치 재현 아님 |
| image/ALS sensor mesh API |11개 Docker 단위검증 PASS | 영상 pixel topology 및 명시적 scan/beam/GPS/trajectory 입력의 보간·Delaunay 구현 |
| P3 실제 영상 sensor mesh | A40뷰 중29뷰가 최소64face 충족,11뷰는0face. hash순 첫 적격133번에서145,532정점·264,611삼각형 | 기존 COLMAP camera-Z depth를 사용. 원논문 PSMNet matching 단계 대체를 명시 |
| P3 첫 시도668번 | prism 내부 depth3픽셀, 인접 삼각형0 → 실패 기록 보존 | 전체 prism을 보는 카메라 목록과 native depth 피복은 다른 조건 |
| P3 실제 ALS sensor mesh | 유효 GPS time/strip ID는 존재. 조사한 경로에서 trajectory 미확보 | 센서 optical center/scan topology를 가정으로 생성하지 않음 |
| P3 전체 원방법·실제 A→B | 미실행 | 이 누락을 새 GS 개발 결과로 대체하지 않음 |

원문은 과거 기하 보존·현재 관측 갱신을 이미 다룬다. 이번 구현 가능성 확인은 기존 방법의 실패나 본 연구의 신규성을 입증하지 않는다. 주 대조군은 전체 연구에서 유지한다. Zhou2020·ARSGaussian·GeoGS를 우선 검토했고 GS4Buildings·CL-Splats 입력/원산출물/공식 구현도 구분했다. ARSGaussian은 공식 실행 코드 미공개, GeoGS/GS4Buildings는 공식2DGS 구현, CL-Splats 공개본은 논문 당시 구현과 차이가 있을 수 있는 저자 재구현이다. 이 추가 방법들은 이번에 실행하지 않았다.

## 3. 공통 자료·참조 조건

- P3: tile `x003_y004`, scene-local `x[-60,-20), y[-42,12), z[-49.223,-16.993)`, world shift `[690953,5336071,604]m`.
- MVS는 원 scene-local, ALS는 기존 raw Z+45.7m 후 shift 차감 계보를 정확 재검증했다. 새 정합·수직 보정 없음. 기존 terrain-MVS gravity 추정값과 출처를 재사용한다.
- 157뷰를 hash순 A40/B학습24/외관평가8/reserve85로 고정했다. 모든 뷰는 이전 개발 사용·exact937 MVS/pose와의 의존성이 있어 확증/독립 일반화 분할이 아니다.
- UAS는 B 완료 뒤에만 읽었다. 고정 prism에3,087,747점,0.5m XY grid8,640개 중8,633개 점유. 후보 생성·학습·정합·문턱 선택에서 참조를 사용하지 않았다.
- **UAS 헤더는 EPSG:32632이고 연구 작업 표기는 EPSG:25832다. 이번 평가는 재투영 없이 raw XYZ에서 shift만 차감했다.** datum/epoch·수직 연결·센서 정밀도가 새로 보정되지 않았으므로 아래는 **수치 공통 좌표의 편차**이며 보정된 절대 정확도가 아니다.

## 4. A와 독립된 B 개발 실행

이번 B는 실제 source authority 판단을 전달받은 실행이 아니다. MVS·ALS·합집합 각각을 사용할 기하로 가정하고 초기화한 공급원 진단이다. 동일 ALS의 두 arm만 초기 기하/외관·학습 mask·view 순서까지 동일하다. 다른 소스는 native point 수와 관측 지지가 달라 완전한 matched reconstruction 비교가 아니다.

| 조건 | Gaussian 수 | 바꾼 변수 | 고정 union 분모 PSNR 초기→최종 | 고정 intersection 분모 PSNR 최종 |
|---|---:|---|---:|---:|
| MVS 색 적합 |190,659|SH 외관|11.950→12.842dB|13.562dB|
| ALS 색 적합 |43,286|SH 외관|10.960→11.557dB|13.009dB|
| 단순 합집합 색 적합 |233,945|SH 외관|12.259→13.149dB|13.426dB|
| ALS 법선 이동 허용 |43,286|같은 SH 외관+최대0.15m 법선 방향 중심 이동|10.960→11.580dB|13.016dB|

모든 arm은24뷰 동일 순서384step, 동일 최대영상축768px를 사용했다. 총168.63초에는 초기화·CUDA 준비·그림·저장이 포함된다. 소스별 연산량 동일화나 수렴 검증은 하지 않았다. 고정 union346,985픽셀/intersection281,489픽셀을 모든 arm에 동일 적용했고 없는 출력도 분모에 유지했다. union mask에는 합집합 arm의 초기 지지가 포함되므로 그 arm의 결손0이 전체 건물 완전성 보장은 아니다. 일부 개별 평가뷰는 자신의 초기 상태보다 악화하여 ‘모든 시점 개선’이라고 쓰지 않는다.

고정기하3조건은 center·quaternion·scale·opacity와8뷰 기하 depth/mass가 초기/최종에서 **정확 동일**했다. 법선 이동 조건은 ALS 고정 조건 대비 union PSNR+0.02248dB/intersection+0.00701dB 차이에 그쳤다. intersection의 기하 결손은0→1,488픽셀, union 결손은55,232→54,648픽셀로 양방향 변화가 섞였다. 반복 seed/통계·독립 관측 없이 유의한 효과나 세부 회복을 주장하지 않는다.

## 5. 원점군과 GS readout을 분리한 수치 비교

아래 GS 행은 **기하 기대 깊이를 역투영한 점군**이다. native ALS/MVS 원행 자체와 다르다. 각 arm은 같은8뷰의 실제 renderer 출력에서 stride2로 읽고 고정 prism 밖 제외 수를 별도로 기록했다. 거리 큰 점을 잘라내는 필터는 사용하지 않았다.

| 입력/산출물 | 산출→UAS p90(m) | UAS→산출 p90(m) | UAS 점유 셀 중 결손 |
|---|---:|---:|---:|
| Native MVS |0.482|0.703|231/8,633|
| Native ALS |0.176|0.645|11/8,633|
| MVS 고정기하 GS readout |1.326|0.995|895/8,633|
| ALS 고정기하 GS readout |2.608|0.698|374/8,633|
| 단순 합집합 고정기하 GS readout |1.326|1.045|899/8,633|
| ALS 법선 이동 GS readout |2.595|0.700|352/8,633|

Native ALS가 일부 지표에서 작아도 전면 우위는 아니다. 반대 방향 평균은 ALS0.309m/MVS0.289m, 최대는 ALS9.043m/MVS5.584m로 다른 양상이다. 밀도·부재·다층·위치별 차이를 지도/단면과 함께 읽는다. 이 수치만으로 ALS의 현재 적합성을 확정하거나 기존 방법의 source 선택을 평가할 수 없다.

### source→표현→readout 차이에서 확정된 것과 가설

**코드로 확인:** C8은 각 Gaussian 평면의 ray 교차 깊이 `z_hit`를 `alpha×transmittance`로 가중한 뒤 전체 mass로 정규화한다. 첫 교차점/지배 표면/median 선택이 아니다. C8 기하는 평면의3D Gaussian 지지를 쓰며 C4의2D low-pass 지지가 직접 혼입된 것이 아니다. 정렬은 Gaussian 중심 깊이 순서이며 픽셀별 실제 교차 깊이 재정렬이 아니다. 추출은 mass≥0.5와finite·positive 조건을 쓰고 깊이층 분리·분산·법선 일치 검사를 하지 않는다.

**실측으로 확인:** ALS 고정기하 arm은 학습 전후 기하와 깊이가 같으므로 native→readout 편차 증가를 학습 중 기하 이동 탓으로 돌릴 수 없다. 법선 이동 cap0.15m도 최종 readout 변형 한계는 아니다. 유지된 ray 깊이 변화의 뷰별p90은0.258–0.724m였다. 같은 XY 셀의 평균/중앙 높이 변화에는 층 선택·표본 변화도 섞일 수 있다.

**원인 가설:** 여러 깊이층의 부분 투과 기여가 섞인 기대 깊이는 어느 원표면에도 없는 중간 점을 만들 수 있다. 경계 지지·비스듬한 교차·중심 깊이 정렬도 영향을 줄 수 있다. 단면/구현과 부합하지만 각각의 기여량을 분해해 확정하지 않았다. 별도 ray별 기여/층 분석 없이 새로운 readout을 유리한 참조 결과에 맞춰 선택하지 않는다.

## 6. 보존·검증·실행 위치

프로젝트 처리는 image `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`, torch2.4.1+cu121/gsplat1.4.0/CUDA12.1, Git head `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`의 별도 source snapshot에서 실행했다. 실제 dirty code/config bytes는 각 snapshot manifest에 결속했다. GPU1,6CPU/24GiB 제한, 기존 artifact와 소스는 read-only이며 CUDA cache/adapter도 별도 복사했다. commit/push와 기존 서비스 중단은 하지 않았다.

사전281개 기존 수정·미추적 파일을 보관했고 재검사에서 **280개 hash 동일, 삭제0개**, 인계문1개만 이번 방향 addendum이 추가됐다. 기존 인계 본문은 유지했다. 기존 P2 뷰어8893–8896과 관련 기존 서버를 유지했다. 이번 작업이 새로 만든8897 viewer만 자기 소유r1→r2로 교체했다.

검증: ray9+sensor mesh11+평가7=**27개 Docker 단위검증 PASS**, 합성5장면PASS, P3 입력 hash/원행 exact replay,4조건 finite gradient/고정 기하 및 렌더 불변 검사PASS. 별도 새 Chrome 프로필에서 실제 브라우저 **359항목 PASS**, 189개 표시 파일·8뷰·초기/최종·공통 crop/전체 화면·모바일을 확인하고9개 화면을 저장했다. Chrome/Node가 없는 프로젝트 이미지 대신 호스트 브라우저를 사용한 UI 검증이며 프로젝트 계산은 Docker에서 수행했다. 첫 모바일 overflow와 실행 오류는 원로그와 새 시도 경로를 모두 보존했다.

모든 아래 경로의 공통 외부 prefix는 `../JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v1/`이다. 컨테이너에서는 `/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_p3_v1/`이다.

| 산출물 | 경로 |
|---|---|
| 기존 작업 snapshot |`preservation_20260907T0547/`|
| 논문 원문/접근 응답/해시 |`literature_20260907/`|
| 공통 P3 입력·원행·뷰 역할·ALS metadata |`PHD-WU-VALLET-P3-v1-r2/` 안 `manifest.json`, `common/native.npz`, `common/views.json`|
| 원문 component 통제 갱신 점군·출처/단면 |`PHD-WU-VALLET-RAY-FIXTURE-v1-r2/run/receipt.json` 및 각scene NPZ/PLY|
| 실제 현재영상 native sensor mesh |`PHD-WU-VALLET-P3-IMAGE-SENSOR-MESH-v2/run/` 안 `receipt.json`, `image_sensor_mesh.npz`, `coverage_audit.json`|
| P3 B 초기/최종 실제 렌더·기하 깊이·역투영 점군 |`PHD-WU-VALLET-P3-B-DEVELOPMENT-v1/run/result.json` 및4조건 폴더|
| UAS 독립 처리·지도·단면·수치 |`PHD-WU-VALLET-P3-EVALUATION-v1-r2/evaluation/evaluation.json`|
| 오프라인 비교판 |`PHD-WU-VALLET-P3-VIEWER-v1-r2/viewer/index.html`|
| 실제 브라우저 QA |`PHD-WU-VALLET-P3-BROWSER-QA-v1-r2/`|

실행 드라이버는 [run_docker.sh](../../../../scripts/phd/wu_vallet_p3_v1/run_docker.sh)이며 같은 run ID 재사용은 거부한다. `preflight/ray/image-v2/b/evaluation/viewer`와 별도 새 ID로 새 실행을 분리한다. [validate.sh](../../../../scripts/phd/wu_vallet_p3_v1/validate.sh)는27개 단위검증과 shell 구문 검사를 실행한다. 최종 파일/실행 연결은 [패키지 manifest](../../../../artifacts/manifests/phd/wu_vallet_p3_v1/technical_result_manifest_v1.json)에 기록한다. 아래 연구 작업을 재개할 때 이번 결과/실패/분모를 초기 상태로 사용한다.

## 7. 아직 필요한 후속 작업

1. ALS의 optical-center trajectory와 scan/beam topology를 결속하고, 공개되지 않은 Wu 설정의 명시적 선택·민감도를 정해 실제 P3 갱신 점군까지 연결한다. 원matching을 대체한 component 비교와 end-to-end 재현을 구분한다.
2. A는 같은 후보와 허용 관측에서 source 검정/원분류·갱신을 비교한다. B와 병행하여 설계하되 현재 P3 결과를 실제 A 판단의 타당성 증거로 사용하지 않는다.
3. B는 기하를 고정한 ray별 기여·깊이층 분석으로 source→기대 깊이 산출 차이를 먼저 분해하고, 같은 실제 인계를 받은 텍스처링/기존 prior 재구성/수정 방법의 비교로 확장한다. 이번 제한 이동의 작은 RGB 차이를 신규성·세부 복원으로 승격하지 않는다.
4. 좌표·수직·epoch 연결 및 참조 정확도를 원자료 근거로 보정한 뒤 실제 오류를 평가한다. 참조를 보고 후보를 정합하는 누출은 피한다.
5. P3에서 절차를 고정한 뒤 P2를 낡은 ALS 배제의 후속 대조로 사용한다. 현재 미실행 항목·E1–E6·역사적 C 계보·`scientific_verdict: null`을 유지한다.
