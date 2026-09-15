# R1 기본 MVS–GeoGS 대조군 백그라운드 실행

- Task: `PHD-R1-MVS-CONTROL-RUN-v1`
- 승인: 2026-09-16 사용자 “기본 대조군 실험은 백그라운드에서 진행하는거지? 결과는 뷰어로 보여주고”.
- 상태: **학습·최종30k/Anchor8k RGB 표면 추출 PASS / recovery COMPLETE** (2026-09-17 확인). 최초 추출은 RAM 32GiB 한도 초과로 중단됐고, 동일 결과에서 RAM 56GiB로 추출만 재실행했다. 최신 상태는 resolver의 `active_mesh_recovery`와 해당 `status.txt`/receipt를 확인한다. 최초 실패 기록은 보존한다. 하늘 방향의 유한 렌더 depth가 메쉬 추출로 유입되는 현상은 [별도 진단](SKY_DIAGNOSTIC_ko_v1.md)에 기록했으며 기하 정확성 PASS를 뜻하지 않는다.
- `scientific_verdict: null`
- 뷰어: <http://127.0.0.1:8912/>

## 1. 실행 조건

2026-09-17 실제 trace 재확인: 8,001–30,000회 구간의 기록 221개에서 prior 계수는 전부 **0.005**, MVS 계수는 전부 **0.05**다. 구역별 수동 loss 가중치는 없다. 기존 native protection은 유지된다. 초기 1–8,000회는 prior 0.08이므로 8k 결과까지 prior 0.005였다고 해석하면 안 된다.

이전 준비 작업의 봉인된 R1 입력과 `runtime/execution_plan.json`을 실행한다. R1 새 초기화이며 기존 P1/P3 checkpoint를 재사용하지 않는다. ALS-adapted GeoGS 개발 대조군이고 정규 gsplat E1–E6 조건을 변경하지 않는다.

| 항목 | 실제 실행 |
|---|---|
| GPU | 1, RTX 3090 24GB; 시작 직전 여유 24,034MiB, 사용률 0% 확인 |
| 영상 | 588 train / 84 evaluation |
| 초기 단계 | 1–8,000회, RGB + prior 0.08 및 원래 정규화. MVS 계수 0 |
| 재개 점검 | 새 Anchor8k에서 8,001–8,100회, 별도 출력 |
| 본 대조군 | 같은 Anchor8k에서 새로 8,001–30,000회, MVS + prior 0.005 |
| MVS 계수 | 초기 0.05, 기존 동적 제어 유지; trace에 실제 값 기록 |
| 보호 | 기존 native protection |
| 가중치·추가 기능 | 수동 구역 가중치 없음, PGSR 없음, 추가 Gaussian completion 없음 |
| 런타임 | Docker image `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, CPU 8, RAM 32GiB, shm 4GiB |
| 추출 | 원래 `render.py`, bounded TSDF mesh_res 512, num_cluster 50; raw와 post 모두 보존 |

준비 설정의 `PREPARED_NOT_EXECUTED`는 이전 준비 시점의 역사 기록으로 유지했다. 이번 실행 권한과 시도는 별도 task/attempt의 `authorization.txt`, 명령, 입력 검증 기록에 남겼다.

## 2. 백그라운드 실행과 검증

실행은 Codex 도구 호출 수명과 독립적인 systemd 사용자 서비스다.

```text
jbgs-r1-attempt_20260916T141804Z_0zDUJ0xj.service
```

단계 순서는 `verify → anchor → preflight → refinement → extract_final → extract_anchor`다. 어느 단계든 실패하면 다음 단계로 진행하지 않고 `status.txt`에 실패 단계를 남긴다. 성공 종료 시에는 `COMPLETE`를 기록한다. 실패한 실행을 덮어쓰거나 자동으로 학습을 반복하지 않는다.

- 봉인된 입력 2,473개 및 anchor/refinement 구현 hash를 재검증했다.
- 학습 소스는 준비한 그대로 유지하고, 외부 관측 wrapper로 선택 카메라와 유한 loss, 100회 간격의 실제 optimizer gradient 유한성을 기록한다. wrapper는 gradient/weight/model/RNG를 수정하지 않는다. 실행 시간은 계측의 영향을 받는다.
- Anchor8k와 최종 완전 상태의 checkpoint/PLY hash를 검사한다.
- 재개 시 모델·optimizer·RNG·카메라 순서/스택·native protection의 즉시 복원 동등성을 요구한다.
- refinement의 첫 8,001회 MVS 출처, prior 0.005, 유한 loss/gradient와 최종 30,000회 trace를 검사한다.
- 표면 추출 후 비어 있지 않은 유한 삼각형 기하를 확인한다. 저장된 84개 evaluation GT RGB를 원본 영상과 비교해 렌더링 순서를 검증한다.

`camera_sampling.jsonl`의 `valid_mvs_loss_pixels`는 실제 선택 영상에서 해당 loss 식의 유효 픽셀 수다. **전체 영상 집계이며 R1 각 구역의 gradient 기여 수가 아니다.** 초기 단계는 MVS 계수가 0이므로 유효 픽셀이 있어도 MVS supervision 기여는 0이다. C1/S1/U1 및 전체 14구역에 대한 실제 국소 gradient 기여 분석은 별도로 남아 있으며, 이번 기록만으로 그 수를 확정하지 않는다.

## 3. 뷰어

4개 카메라를 동기화해 `ALS prior → 현재 MVS → Anchor8k → MVS–GeoGS30k`를 비교한다. MVS 패널에서 원본 RGB와 전체 영역 판단 초안을 선택할 수 있다. 구역 버튼은 해당 위치로 확대하며 주변 기하도 함께 표시한다. R1 전체 지도와 구역별 원영상 검토 카드도 포함했다.

학습 완료 receipt가 PASS인 경우에만 Gaussian 중심점을 추가한다. 표면 추출 receipt가 PASS이면 RGB 삼각형 표면을 추가하고, 사용자가 후보를 직접 고르지 않은 패널은 새 표면을 기본으로 선택한다. Gaussian 중심과 추출 표면은 별도 후보로 남긴다. 뷰어는 60초마다 갱신하며 publisher는 30초마다 새 검증 결과를 확인한다.

표시 프레임은 객체축 `(u, -v, local z)`다. 원본 좌표/모델을 바꾸지 않고 표시용 버퍼만 회전한다. prior는 중립 회색, MVS는 fused-MVS 표본의 저장 RGB, Gaussian 중심은 SH 기본색, 추출 표면은 정점 RGB다. 색과 표면의 출처를 혼동하지 않는다. 실제 loss의 입력은 원래 native COLMAP MVS depth이며, 뷰어 MVS 점군은 융합 표본이다.

활성 서비스 (2026-09-17):

- `jbgs-r1-control-publisher-8912-v3`
- `jbgs-r1-control-viewer-8912-v2`

viewer source v1은 보존했다. v2는 네 화면 배치, 표시 프레임 문구, 구역 순서, 새 표면의 기본 선택, 갱신 실패 표시를 다듬었다. 학습 컨테이너는 이 변경과 독립적으로 계속 실행했다.

실제 Chromium CPU 브라우저로 초기 뷰어의 4개 창, 실제 binary buffers, Z08 확대, 판단 색상 선택, 모바일 화면 폭, HTTP/JavaScript 오류 유무를 확인했다. 첫 QA와 활성 v2 QA 모두 각각 9개 검사 PASS이며 별도 receipt를 보존했다. 학습 완료 후 결과 자체의 정확성을 이 UI 검증이 보증하지 않는다.

2026-09-17 최종 30k 추출은 865.984초에 PASS했다. raw/post 표면의 유한 기하와 84개 evaluation RGB 순서를 확인했다. 뷰어의 `refinement_mesh`는 raw 추출 표면을 R1으로 잘라 표시한 정점 RGB 삼각형 메쉬다(2,196,299개 정점, 3,758,781개 삼각형). `qa_mesh_20260917T025011Z_tXDsAlOH`의 Chromium 검사 9개도 PASS했으며, 최종 패널이 실제 mesh를 선택·로드·표시한 증거를 보존했다. Gaussian RGB 렌더는 추출 디렉터리의 `model/train/ours_30000/renders` 및 `model/test/ours_30000/renders`에 별도로 생성되어 있다. 이 기술적 PASS는 기하 정확성 판정이 아니다.

Anchor8k 추출 완료 후 `qa_complete_20260917_9MJo27dY`의 Chromium 검사 9개가 PASS했다. `anchor_mesh` 6,108,064개 삼각형과 `refinement_mesh` 3,758,781개 삼각형을 각각 실제 로드·표시한 상태를 확인했다. 앞선 QA launch 오류는 별도 실패 receipt와 이슈 로그에 보존했다.

## 4. 경로와 재현

Resolver: `artifacts/manifests/phd/r1_mvs_control_run_v1/manifest_v1.yaml`.

```text
../JointBuildGS-artifacts/phase-payloads/phd/r1_mvs_control_run_v1/
  PHD-R1-MVS-CONTROL-RUN-v1/attempt_20260916T141804Z_0zDUJ0xj/
    status.txt                     # 실행 단계 또는 실패
    systemd_unit.txt
    authorization.txt
    commit.txt / image_inspect.json / driver_hashes.sha256
    snapshot/                      # 실행 당시 driver
    verify/receipt.json
    anchor/                        # 실제 초기 학습 및 완전 상태
    preflight/                     # 같은 Anchor8k에서 짧은 재개 확인
    refinement/                    # 본 대조군
    extract_final/ / extract_anchor/
    viewer/source/ / source_v2/     # 보존된 뷰어 구현
    viewer/data/status.json / manifest.json
    viewer/qa_v1/ / qa_v2/          # 실제 브라우저 검사·스크린샷
```

새 실행은 `bash scripts/phd/r1_mvs_control_run_v1/launch.sh`, 새 뷰어는 `bash scripts/phd/r1_mvs_control_run_v1/start_viewer.sh <attempt>`로 구성한다. GPU 점유 또는 8912 포트 점유 시 신규 실행은 중단하므로 기존 실행을 반복 호출하지 않는다. 정확한 재현은 활성 attempt의 snapshot과 명령을 기준으로 한다.

## 5. 해석 제한

8k 초기 학습·재개 점검·30k 본 학습과 최종/Anchor 표면 추출은 모두 PASS다. Anchor 표면 추출은 850.919초에 완료됐다. R1 원경/경계는 유한한 25m 초기 기하 문맥과 전체 RGB 프레임의 차이가 있다. 기존 MVS 생산에 evaluation 영상이 들어갔으므로 독립 정확도·일반화 평가가 아니다. UAS/LoD2 평가 기하는 학습과 추출 컨테이너에 제공하지 않았다. 수동 가중치 비교는 기본 대조군 결과를 검토한 뒤 별도 단계로 진행한다. 픽셀별 영역·가중치의 연구 근거는 [원문 확인 메모](PIXEL_WEIGHT_LITERATURE_ko_v1.md)에 별도로 정리했다.
