# Wu–Vallet 원문 기반 P3 점군 갱신 실행 결과

2026-09-07 · `PHD-WU-VALLET-P3-UPDATE-v2` · **PAPER_BASED_POINT_UPDATE_COMPLETE** · `scientific_verdict: null`.

**현재 사용하는 TUM2TWIN ALS에는 GPS time이 있다. 실제 P3의 스캔 순서를 복원하고 다중반사점에서 센서 위치를 추정하여, GS 없이 Wu–Vallet의 분류·점군 갱신까지 실행했다.** 현재 영상은 기존 COLMAP depth를 사용하고 센서 위치는 추정값이므로 원 저자 코드/PSMNet/실측 궤적과 동일한 실행이라는 뜻은 아니다. 이전 v1의 별도 GS 개발 결과와 구분한다.

[Wu 점군 비교 화면](http://127.0.0.1:8898/) · [실행 프로토콜](PROTOCOL_ko_v2.md) · [원문·입력 대응](../wu_vallet_p3_v1/WU_VALLET_REPRODUCTION_ko_v1.md).

## 1. GPS time과 센서 위치가 미치는 영향

| 정보 | 원방법에서 쓰는 곳 | 없을 때의 영향 | 이번 실제 상태 |
|---|---|---|---|
| GPS time | 측정 스캔/beam 순서 복원, 센서 궤적과 반사점 연결 | 다른 scan/order 정보도 없으면 native sensor mesh와 측정 광선 연결이 어려움. 단순XYZ메시는 다른 전처리 | P3 52,762점 전량 유한, 고유pulse시각39,628개 |
| 측정시점별 센서 위치 | ALS에서 현재 표면을 향한 광선 검사 | 편도 현재영상 검사는 가능하나 신축 앞면 뒤 과거 표면 등의 판정이 달라질 수 있음 | 실측 궤적 미확보. 다중반사점의 실제 광선으로 추정 |
| 현재 카메라/영상 기하 | 현재 시점의 sensor mesh와 현재 광선 | 현재 관측이 빈공간/표면을 지지하는지 검사 불가 | 고정133번 master의 현재 camera-Z depth와 camera center 사용 |

시간이 없으면 모든 갱신 계산이 불가능한 것이 아니다. 어디서 측정했는지 모르는 광선 방향을 생략하거나, 다른 입력을 쓰는 제한된 구현은 가능하다. 그때 바뀌는 판단을 분리해야 한다. 이번 데이터는 시간·반사 정보가 있어 그 제한을 상당 부분 해소했다. 원방법 §3.1도 GPS time에서 스캔 순서를 복원하므로, 이전에 scan ID가 미리 없다는 이유를 필수 입력 결손처럼 쓴 설명은 정정한다.

## 2. 실제 ALS 획득 기하 복원

원 raw4타일에서 P3 52,762점의 원행·파일번호·XYZ·시간·각도·return 필드를 모두 대조했다. strip31=30,425점, strip32=22,337점이다. P3에 스캔131/109개가 있으며 모든 P3점이 양쪽 경계가 관측된 스캔 내부에 있다.

P3 측정시간 주변 ±0.25초에서 1,692,140행·1,231,925pulse를 추출했다. scan angle의 약−26→+26 반복 리셋 경계는234/212개, 스캔 주기는 약4.761ms였다. 리셋 문턱2/5/10/20°에서 같은 경계를 얻었고 비리셋 구간 각도 역행은0이었다. beam 좌표는 GPS offset을 사용하여 누락 pulse 간격을 압축하지 않았다. scan_direction/edge_of_flight_line flag는 P3 전량0이므로 사용하지 않았다.

완전 다중반사pulse229,244개를 확보했다. context에도 일부return이 없는 P3 2,920행은 삭제하지 않았다. P3 밖1pulse에서 return간1°각도 불일치를 발견하여 궤적 추정 입력에서만 제외했다. 원LAS 좌표 scale은1mm이며 센서 정확도가1mm라는 뜻은 아니다.

## 3. 실측 궤적 없이 광선 원점을 추정한 근거

동일 pulse의 여러 반사점은 센서가 놓인 광선의 방향을 제공한다. 여러 광선을 동시에 맞추는 시간국소 선형 궤적을 추정했다. 이는 [Karney–Kim 2022 §2](https://arxiv.org/abs/2208.12116), [PDAL trajectory filter](https://pdal.io/en/2.7.2/stages/filters.trajectory.html)의 관련 접근을 확인하여 구현한 것이다. PDAL의 spline/scan-angle 전체 구현과 동일하지 않다.

| 내부 검증 | strip31 | strip32 |
|---|---:|---:|
| 시간·광선 조건수 |약5.86|약5.86|
| fit에 사용하지 않은 pulse 수 |175|158|
| 미사용 pulse 광선에서 추정 원점까지 거리 p90 |0.03868m|0.03935m|
| 미사용 반사점에서 예측광선까지 거리 p90 |0.000450m|0.000466m|
| 시간블록 bootstrap 원점 변동 p95 최대 |0.01157m|0.02301m|

최소반사간격·시간창·목적함수5설정×2strip의 내부검증을 통과했고, P3 52,762점 모두 추정 원점을 지원한다. 설정간 P3 원점 차이 최대6.10mm, 광선방향 차이 최대0.000334°였다. 이는 같은 원자료 안에서의 안정성이며 실제 센서 궤적과의 절대 오차 인증이 아니다. 센서 높이/진행방향을 고정하거나 MVS/UAS/GT로 궤적을 맞추지 않았다.

## 4. 실제 메시·갱신 실행

ALS는 `(GPS-derived beam coordinate, scan ID)`에서 strip·return번호별 Delaunay를 만들었다. 명시한 scan gap1/beam gap32/edge2m 조건을 썼다. 새 가정인 return층 분리와 문턱을 저자 기본값으로 주장하지 않는다.

- ALS 문맥:183,521점·266,171면. P3 중47,638점이 메시 면에 속한다. 미메시5,124점은 **unassessed로 보존**하며 일치/현재성 판정 성공으로 세지 않는다.
- 문맥의 추정 원점 미지원336점은 전부 고립점이다. 실제 ALS 면266,171개는 모두 지원 원점만 참조한다. 원점 미지원 광선은 생략하되 표면거리/상대편 교차를 위한 기하는 유지하도록 구현했다.
- 현재 영상133:전체 depth sensor mesh657,682점·1,244,027면. P3 안145,577점을 갱신 입력으로 쓴다. 원 fused MVS865,108점 전체를 갱신한 결과는 아니다.
- 가시성에는 주변 문맥/전체 현재영상 mesh를 사용하고, 최종 원점 회계는 고정 P3 prism으로 제한한다. 문맥 밖 가림은 남은 제한이다.
- 양방향/현재영상 편도 × 거리0.1/0.3/0.6m × 작은영역0/1m²의12조건을116.02초에 실행했다. 원문 미기재 선택을 명시한 유한 vertex+centroid ray 구현이며 tetrahedron 전체 교차와 동일하지 않다.

대표 표시는 결과를 보기 전에 정한 거리0.3m/면적정제0이다. 모든 최종점은 그대로 유지된 원ALS 또는 추가된 현재영상 pixel의 XYZ다. 위치 이동·GS 학습·표면 역투영을 수행하지 않았다.

| 대표0.3m/영역정제0 | 현재영상 광선만 | 추정 ALS 광선도 사용 |
|---|---:|---:|
| 기존 ALS 유지 |46,225|41,204|
| 기존 ALS 삭제 |6,537|11,558|
| 현재영상 점 추가 |35,149|35,149|
| 최종 점군 |81,374|76,353|

추정 과거 광선을 추가하면 기존점5,021개의 유지/삭제가 달라졌다. 현재점의 changed/single 분류도6,960개 달라졌다. 추가점 수가 같은 이유는 이 재구현의 원문 갱신 규칙에서 **new changed와new single을 모두 추가**하기 때문이다. 일치 여부는 거리 단계에서 결정하므로 센서 광선 변경이 새 점의 추가 개수를 바꾸지 않는 경우가 있다.

거리0.1→0.6m에서 양방향 삭제 수는17,570→7,477개다. 0.3m에서1m² 작은영역 정제를 켜면 삭제가11,558→7,078개로 달라진다. 작은 changed component를 single로 되돌리는 동작도 미기재 구현 선택이며 raw face class와 무정제 실행을 보존한다.

추정 궤적5설정과 가용 범위 대조1개도 같은mesh/0.3m/정제0에서 실행했다(47.28초). main의 점·면 label과keep는 원실행과 정확히 같았다. 대안4개의 ALS 유지/삭제 변화는9/12/18/11점으로 최대18/52,762점이다. 현재점 추가여부 변화는0이나 이는 consistency 기반 채택 규칙의 성질도 포함한다. 짧은 시간창에서 주변 원점 지원이 줄어든 효과만 별도 적용한 대조의 변화는0이었다. 관찰한 차이는 원점 위치 차이에 따른 조건부 민감도이며 원 센서 위치 정확도 인증이 아니다.

## 5. 기존 방법에서 개선 필요성을 찾기 위한 관찰

같은 고정 단면에서 ALS의 연속적인 지붕 구조가 현재 image mesh의 결손을 보완하는 부분이 보인다. 따라서 구조 보존/보완 자체가 기존 방법에 없다고 주장할 수 없다. 동시에 현재 image mesh의 불일치점이 갱신 결과에 들어가고, 지붕의 일부 원ALS가 삭제되며 빈 부분이 남는 사례가 있다. 우선 조사할 대상은 **영상 기하의 오차와 실제 변화를 구분하지 못한 채 교체·추가했는가**이다.

후보/설정을 모두 끝낸 뒤 별도 평가에서 기존 고정 UAS 원행 crop3,087,747점을 읽었다. UAS 헤더EPSG:32632와 작업표기EPSG:25832의 datum/epoch 연결은 미보정이며 raw-shift 수치 편차다. 절대 정확도나 change GT가 아니다.

| 입력/갱신 결과 | 산출→UAS p90(m) | UAS→산출 p90(m) | 참조 점유8,633셀 중 결손 |
|---|---:|---:|---:|
| 원ALS |0.176|0.645|11|
| 현재 image sensor 점 |0.400|4.667|2,361|
| 편도 갱신0.3m/정제0 |1.887|0.640|197|
| 추정 양방향 갱신0.3m/정제0 |2.351|0.665|211|
| 추정 양방향 갱신0.3m/정제1m² |2.000|0.620|132|

대표 양방향에서 제거된 ALS점의 참조 편차 p90은0.369m, 남긴 ALS는0.138m다. 새로 추가한 영상점은 p90=4.410m, 일치하여 제외된 영상점은0.127m다. **이 실행에서는 불일치/단독 영역에서 채택한 영상점에 큰 수치 편차가 집중된다.** 큰 거리 문턱에서 최종 p90이 커지는 것은 추가점 집합·출력 분모의 구성 변화도 포함하며, 동일점을 더 멀리 이동시킨 결과가 아니다.

독립적인 원행/좌표 회계 검산14항목을 통과했다. 원pixel depth와K/R/t로 XYZ를 다시 계산한 차이는0이다. 현재 영상점 중 참조와2m 넘게 차이 나는7,971점은 모두 추가됐고 이 중7,866점은changed였다. 이 큰 편차점 중6,763점은 XY crop 경계에서5m 이상 내부에 있어 crop 경계만의 현상은 아니다. 2m는 결과 설명을 위한 사후 진단선이며 처리/선택 문턱으로 사용하지 않았다.

이 결과는 원 저자 방법 전체의 실패 판정이 아니다. 원PSMNet 대신 COLMAP을 쓴 영향, 유한 광선/센서 mesh/미기재 집계 선택, 좌표·센서오차, 실제 변화를 분리해야 한다. 궤적·문턱·현재 기하를 바꾸는 대조에서 현상이 유지되는지 확인한 뒤 수정 필요성과 기대 효과를 주장한다. 현재 자료에서 관찰된 **기존 방법의 구조 보완과 부정확한 신규 기하 유입의 공존**을 다음 수정의 출발점으로 삼는다.

## 6. 보존과 실행 위치

v2 시작 전 기존 수정·미추적310파일을 외부 `preservation_start_v2/`에 보관했다. 새로운 v2 code/config/output만 생성하며 기존 v1/P2 실험·viewer8893–8897은 유지했다. viewer8898만 별도 추가했다. commit/push와 기존 서비스 종료는 하지 않았다.

아래 공통 외부 prefix는 `../JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v2/`다. 모든 프로젝트 계산은 pinned Docker image `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`에서 실행했다. update/evaluation/viewer는 source snapshot·입력/출력해시·Git head·도구버전을 결속했다. 기존 artifact는 read-only다.

| 산출물 | prefix 아래 경로 |
|---|---|
| 원행 GPS·스캔 복원 |`PHD-WU-VALLET-P3-ACQUISITION-v2/` 안 `acquisition.npz`, `receipt.json`, `additional_validation.json`|
| 추정센서위치·검증 |`PHD-WU-VALLET-P3-TRAJECTORY-v2/` 안 `estimated_origins.npz`, `fits.json`, `fit_pulse_membership.npz`, `receipt.json`|
| 궤적설정→실제판정 민감도 |`PHD-WU-VALLET-P3-ORIGIN-SENSITIVITY-v2/receipt.json` 및각설정 `labels.npz`|
| Wu 점군 갱신12조건 |`PHD-WU-VALLET-P3-UPDATE-v2/run/` 안 `receipt.json`, `common.npz`, `meshes.npz`, 각조건의 `updated_points.ply/npz`, `face_decisions.npz`, `result.json`|
| 별도 참조 평가·단면 |`PHD-WU-VALLET-P3-EVALUATION-v2/run/` 안 `evaluation.json`, `cross_sections.png`, `height_comparison.png`|
| 점군3D/분류/단면 viewer |`PHD-WU-VALLET-P3-VIEWER-v2-r2/run/index.html`|

실행 진입점은 [run_docker.sh](../../../../scripts/phd/wu_vallet_p3_v2/run_docker.sh), 단위검증은 [validate.sh](../../../../scripts/phd/wu_vallet_p3_v2/validate.sh)다. 같은 실행ID의 출력 재사용은 거부한다. 과학적 판단·일반화·공식 PASS_usable은 설정하지 않는다.

검증은 Docker35개 단위검증 PASS, 실제 원행/광선/출력 회계 검증과 같은조건 재실행 exact equality로 남겼다. 브라우저 첫 실행은 headless WebGL context lost로 실패했고, 새 전용프로필에서 명시적 SwiftShader로 재실행하여 실제3D를 확인했다. 브라우저는 프로젝트 이미지에 Chrome/Node가 없어 호스트 전용프로필을 사용한 UI 검증이며, 과학 계산은 Docker에서만 했다. 원 실패receipt도 보존했다.

최종 viewer-r2는 **571개 브라우저 검사 PASS**, 12조건×5표시×2단면,199개파일 hash/bytes,7개스크린샷으로 확인했다. `PHD-WU-VALLET-P3-BROWSER-QA-v2-r3/browser_qa.json`에 기록되어 있다. 전체 실행과 보존 검증의 연결은 [v2 패키지 manifest](../../../../artifacts/manifests/phd/wu_vallet_p3_v2/technical_result_manifest_v2.json)에 결속했다.
