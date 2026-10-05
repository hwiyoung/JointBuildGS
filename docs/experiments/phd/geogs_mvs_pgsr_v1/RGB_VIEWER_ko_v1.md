# P1/P2/P3 RGB 비교 뷰어

`PHD-GEOGS-MVS-PGSR-RGB-VIEWER-v1` · `scientific_verdict: null`

주소: [RGB 비교 뷰어](http://127.0.0.1:8910/)

추가 진단: [학습뷰·평가뷰 RGB 비교](http://127.0.0.1:8910/app/rgb_diagnostic.html).
P1/P2/P3의 저장 full-SH RGB를 원사진과 같은 camera/crop으로 대조한다.
12개 사진·여섯 조건, 100%/200% 확대와 동기 스크롤을 제공한다.
[진단 결과와 해석 범위](RGB_TRAIN_EVAL_DIAGNOSTIC_ko_v1.md)를 함께 참고한다.

사용자가 승인한 순서대로 7개 화면을 같은 좌표·시점으로 비교한다.
기존 서비스와 학습 큐를 유지하면서 별도 CPU 표시 자료와 서비스를 추가했다.

| 패널 | 표시 내용 | RGB 출처 |
|---|---|---|
| Prior | 기존 GeoGS에 실제 입력한 ALS 변환 prior 형상 | 현재 train 사진 투영색. 같은 prior depth로 가림을 검사하고 미관측은 회색 |
| MVS | 기본: 실제 감독 COLMAP depth 역투영점. 선택: 기존 OpenMVS 융합점군 | 해당 원사진의 RGB / OpenMVS의 원본 RGB |
| Anchor-only | 원래 8,000 iteration Anchor의 raw TSDF512 | native 표면 정점 RGB |
| Vanilla GeoGS | DA3, prior 0.005, native 보호, 30,000 iteration | native raw TSDF512 정점 RGB |
| GeoGS 변형 | 기존 6조건: prior 0.005/0.0005/0 × 보호 유지/해제 | 조건별 native raw TSDF512 정점 RGB |
| MVS GeoGS | MVS-only / MVS+PGSR × prior 0.005/0.0005, 보호 유지. 표면 전용 | native raw TSDF512 정점 RGB. 추출 전에는 명시적 대기 |
| Drone LiDAR (GT) | 같은 frozen UAS 참조점의 원본 행 | 원본 LAZ의 16-bit RGB 속성을 `/256`으로 변환 |

Prior 사진색은 형상을 움직이지 않는다. 현재 사진을 입힌 과거 형상이 현재 기하로
바뀌는 것은 아니다. 색상 지원률과 회색 미관측 부분을 표시하며, GT 색상은 prior나
GS에 전달하지 않는다. UAS XYZ는 원본 LAZ 행에서 기존 world shift를 뺀 값과 직접
대조한다. 원본 LAZ 전체 SHA도 builder 시작 때 확인한다.

## 조작과 자동 갱신

- P1/P2/P3 전환, MVS·GeoGS·MVS GeoGS 조건 선택.
- 드래그 회전, Shift 또는 오른쪽 드래그 이동, 휠 확대를 7개 화면에 동기화.
- 위/비스듬히/옆 시점과 전체 맞춤, 패널 확대 보기.
- 기본 `자동`은 실제 RGB 표면이 있으면 표면, 점만 있으면 해당 RGB 점을 표시한다.
  `RGB 표면`을 명시적으로 선택했는데 실제 표면이 없으면 대기로 표시한다.
- MVS GeoGS 패널은 전역 `RGB 점` 선택에도 실제 삼각형 표면을 유지한다.
  표면이 아직 없으면 학습 대기와 30,000 step 완료·표면 추출 대기를 구분한다.
- CPU builder와 브라우저가 각각 60초마다 상태를 확인한다. 학습 완료 receipt를
  확인한 조건에서 native 추출까지 완료되어야 RGB 표면을 표시한다.
  학습 완료 수와 표면 준비 수는 별개이며, 미완료 조건을 다른 결과로 채우지 않는다.
- 전체 후처리 보고서가 완료되면 보고서 링크도 나타난다.

## 표시 자료와 원결과의 관계

기존 고정색 viewer 배열을 원본 RGB로 재사용하지 않았다. native PLY의 실제 RGB를
읽고, 경계에서 잘린 삼각형에는 RGB를 보간한다. 표면 연결을 단순화하거나 새로운
막음 면을 만들지 않는다. 점 모드는 면적에 따른 seed 0 표본 또는 원래 점의
순서를 유지한 제한 표본이다. 표시 점 수는 최대 200,000개이며 scoring 입력이 아니다.
XYZ는 기존 local frame을 유지하며 WebGL용 float32로 내보낸다.

초기 뷰어는 추출 전 최종 Gaussian 중심점에 SH-DC 색을 표시했다. 이는 추출 표면이나
미분 가능 렌더링 결과와 다르며 opacity를 반영하지 않았다. 당시 SH-DC 색은
`clip(0.5 + 0.28209479177387814 * f_dc, 0, 1)`로 표시했다. opacity 필터나 임의의
표면 연결을 추가하지 않았다. 2026-09-15 surface-only 갱신 이후 MVS GeoGS는 이
중심점 대체 표시를 사용하지 않는다. 기존 중심점 cache와 초기 검증 기록은 보존한다.

표면은 최종 Gaussian을 native renderer로 렌더링해 TSDF로 추출한 raw RGB mesh다.
점에 새로 면을 잇거나 보기 좋게 평활화한 결과가 아니다. 원래 finalization 추출을
우선하고, 아직 없으면 동일 최종 PLY·입력·설정·소스·이미지·실제 추출 파라미터가
일치하는 완료된 matched comparison의 표면을 사용한다. P1/P2 prior 0.005의
MVS-only/MVS+PGSR 네 표면은 이 경로로 연결된다. canonical 추출은 개별 PASS receipt가
완료되면 등록되며, 전체 정량 평가 완료를 뜻하지 않는다.

학습 opacity는 native depth 합성에 반영되지만, 이 raw TSDF 경로가 낮은 누적
alpha 영역을 별도로 제거하는 것은 아니다. 따라서 표면 표현으로 바꾸는 것만으로
잔여층·추출 잡음까지 사라진다고 보장하지 않는다. 원래 추출 파라미터를 유지한다.

현재 COLMAP depth의 effective 생성 이웃 명단은 미복구다. 개발 입력·정성 비교라는
기존 범위를 유지하며, 뷰어 검증을 기하 개선·현재성·일반화 성능으로 해석하지 않는다.

## 실행과 계보

- 앱: `src/apps/geogs_rgb_comparison_v1/`
- 설정: `configs/phd/geogs_mvs_pgsr_v1/viewer_rgb_v1.json`
- 실행: `bash scripts/phd/geogs_mvs_pgsr_v1/viewer/start.sh`
- 실행 중 builder의 표면 전용 갱신: `bash scripts/phd/geogs_mvs_pgsr_v1/viewer/refresh_surface_builder.sh`
  별도 staging에서 export와 다른 여섯 패널의 RGB/기하 buffer 불변성을 먼저 확인한다.
  기존 builder는 삭제하지 않고 중지된 rollback container로 보존한다.
- 서비스: `jbgs-geogs-rgb-viewer-8910`, `jbgs-geogs-rgb-builder-v1`
- 외부 payload: 기존 MVS+PGSR task 아래 `viewer_rgb_v1/`
- `sources/`는 실행 시점 builder/config snapshot, `cache/`는 RGB·기하별 불변 표시
  파일, `snapshots/`는 시간별 manifest, `manifest.json`은 현재 표시 목록이다.
- `builder_status.json`은 실제 export 실패를 포함한다. 브라우저 QA와 스크린샷은
  `browser_qa/`의 새 attempt에 보존한다.

모든 프로젝트 실행은 Docker CPU에서 수행한다. builder의 원입력·GT·학습 결과는
read-only이며, 신규 학습·GPU 추출·정량 재평가를 추가 실행하지 않는다. 원래 실험의
큐·driver 해시도 별도로 유지한다.

## 초기 표시 버전 검증 기록 — 2026-09-15 01:12 UTC

**뷰어 기술 검증 PASS. 학습 전체 완료와는 별개다.** 이 시점에 신규 학습 8개가
등록돼 있고 P3의 4개는 대기다. P1/P2는 각 15개 표시 후보, P3는 11개 표시 후보와
4개 대기 후보로 제공한다. builder의 export 오류는 0개다.

CPU export 검사 12개와 실제 브라우저 검사 218개가 통과했다. P1/P2/P3에서 MVS
2종·GeoGS 6조건·MVS GeoGS 4조건, 총 36개 드롭다운 선택을 확인했다. 실제 렌더러에
올라간 RGB/XYZ/triangle buffer의 SHA와 색상 변환, 화면 픽셀, 카메라 동기화,
390px 모바일 화면을 검증했고 브라우저·네트워크 오류는 0개다.

최종 browser evidence는 외부 payload의
`browser_qa/attempt.20260915T011018Z.HcvqY51O/receipt.json`과 같은 폴더의 4개 PNG다.
앞선 출력 UID 및 favicon 실패 attempt도 삭제하지 않았다. P1/P2 화면을 직접
확인했으며 실제 RGB와 기하가 표시된다.

Prior 정점의 사진색 지원률은 P1 96.83%, P2 92.63%, P3 95.54%다. 지원하지 않는
정점은 회색을 유지한다. 이 비율은 색상 투영 지원률이며 형상 정확도가 아니다.

## MVS GeoGS 표면 전용 갱신 검증 — 2026-09-15 04:37 UTC

**표시 갱신 PASS.** P1/P2 × MVS-only/MVS+PGSR × prior 0.005 네 조건이 native
raw RGB TSDF512 표면으로 표시된다. 나머지 여덟 조건은 아직 표면 대기다.
학습 완료는 11/12이고 P3 MVS+PGSR prior 0.0005 학습은 계속 실행 중이다.
이는 해당 시점의 상태이며, 추출 receipt가 완료되면 builder가 자동 반영한다.

- source snapshot: `sources/attempt.96SnSkp0`.
- 갱신 receipt: `surface_only_updates/attempt.9IPoPwgA/publication_receipt.json`.
- 다른 여섯 패널에 속하는 33개 후보의 mesh/point XYZ·RGB·indices 등 buffer SHA가
  초기 표시와 모두 같다. staged 실제 buffer 167개 해시 검증 PASS, export 오류 0개.
- Docker CPU export/helper 검사 20개와 실제 Publisher의 실패 후 완료·표면 대기
  회귀 검사 1개 PASS. 브라우저에서는 422개 검사, 기본 조건 선택 36개,
  추가 surface-only 조건 선택 12개, RGB/삼각형 buffer와 390px 화면을 검증했다.
  전역 RGB 점에서도 MVS GeoGS만 mesh/pending을 유지한다. 브라우저·네트워크 오류 0개.
- browser receipt: `browser_qa/attempt.20260915T043509Z.LtRnBEbg/receipt.json`,
  SHA256 `58619787259d0bf8a3f37b8fee4c689cde180ceb4cbd7a10b65bf84bb29cb97f`.
  P1/P2/P3 및 모바일 PNG 4개를 보존하며, P1/P2 실제 RGB 표면과 P3 추출 대기를
  직접 확인했다.
- 기존 builder는 `jbgs-geogs-rgb-builder-v1-rollback-attempt.9ipopwga`로 중지 보존한다.
  viewer 서버와 학습 컨테이너는 유지했다. 새 학습·GPU 추출·정량 재평가는 없다.

정성적 잔여 문제의 코드·trace 근거는 [별도 진단](REFINE_QUALITATIVE_GAP_ko_v1.md)에
기록했다. 표면 표현과 표시 QA는 기하 개선 판정이 아니다.
