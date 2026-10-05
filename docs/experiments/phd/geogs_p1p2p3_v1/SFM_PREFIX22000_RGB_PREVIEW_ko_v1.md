# P2 고정22k 공식 RGB 조기 확인

2026-09-10 · 추가 표시 절차 · `scientific_verdict: null`

**최종 상태: 필수22k 상태 부재로 미실행.** 아래 계획은 보존 기록이며 종료 사유는 마지막 절에 있다.

P2 마지막 재시도가21,300회까지 진행된 시점에 이 절차를 추가했다. 사전 지정한22k 상태가 저장된 뒤에도30k까지 약3시간의 학습이 남아 있어, 평가 사진9장의 실제 렌더를 먼저 확인하려는 목적이다.22k 품질을 보고 checkpoint나 학습 조건을 고른 절차가 아니다. 원22k/30k 학습·공식 TSDF·정량 평가와 고정 historical8k는 그대로 유지한다.

정책은 `configs/phd/geogs_p1p2p3_v1/sfm_prefix22000_rgb_preview_v1.json`과 task의 `contracts/`에 동일 bytes로 보존했다. SHA256은 `b104c30133fc22a26b35428a1865f78c6a8e3d86d2186d3552897c130c19dcfc`다. 선택은 P2 `no_anchor_sfm_gradient_memory_v3_P2`의22,000회 한 상태,9개 고정 평가 영상 전체다. 최소22,100회 trace까지 기다려 저장과 대용량 읽기가 바로 겹치지 않게 한다.

완료 capture receipt와 PLY SHA·수·필드·유한값, 원 invocation/config/amendment/source, 초기화·첫 refinement step,22k까지의 완결 trace를 검증한다. 모델 PLY와 `cfg_args`는 별도 출력으로 복사하고 공식 `render.py --iteration 22000 --skip_train --skip_mesh`를 실행한다. checkpoint 전체 tensor·optimizer를 독립 검증하지 않는 RGB preview이며, checkpoint SHA는 capture가 선언한 값과 실제 재검증 범위를 구분한다. 부모 학습의 상태는 관측 시각과 함께 그대로 기록하고 닫힌 PASS receipt를 만들지 않는다.

학습 GPU0와 기존 desktop/service는 보존한다. preview는 빈 GPU1과 기존 GPU lane lock·heavy CPU lock을 사용하며 Docker CPU2/RAM16GiB/network none으로 제한한다. task 전체나 UAS를 producer에 마운트하지 않는다. 시작 전 host available memory32GiB 이상을 확인하고 native 렌더는1회만 시도한다. 실패하면 그 출력·로그를 보존한다. GPU가 달라도 CPU·RAM·스토리지·PCIe 전송은 공유하므로 겹친 구간의 학습 시간은 순수한 단독 실행 속도가 아니다.

출력9장의 index·해상도·디코딩과 원사진 대응을 검사한다. 원사진 대응에는 이미 검증된 historical8k 공식 GT PNG의9개 bytes를 사용하며, 그 export receipt SHA도 정책에 고정했다. 실제 비교 화면은 같은 사진·고정 투영 사각범위를 사용하고, 기존 원설정30k/깊이 완화30k와 신규22k의 학습량 차이를 표시한다. 첫 화면은 고정 index0이고 전체9장을 확인할 수 있게 한다.

출력은 task `preview22000_v1/P2/`에 추가한다. 기존 main/8k 코드·정책·산출물을 바꾸지 않고 preview 품질로 학습을 중단하거나 설정을 조절하지 않는다. 이 preview는 PSNR/SSIM/LPIPS·TSDF·기하 정량을 새로 계산하지 않으며, 최종 수렴이나 Anchor 필요성의 결론을 제공하지 않는다. main worker가22k 렌더를 나중에 다시 수행하는 추가 비용도 남긴다. 이 문서 작성 시 실제22k preview는 아직 생성되지 않았다.
## 종료 기록: 필수22k 상태 부재로 미실행

2026-09-09 21:51 UTC에 P2 마지막 학습이22,000번째 optimizer 반환 뒤 정기 평가 renderer CUDA OOM으로 닫혔다.22k complete checkpoint·PLY와22100 trace가 없으므로 아래 정책의 실행 gate를 충족하지 않는다. `run.sh`, 갤러리 생성, 실제22k browser QA는 실행하지 않았고 결과 디렉터리도 만들지 않았다. CPU static preflight·문법 검증은 개발 검증일 뿐 실제 RGB/갤러리 검증이 아니다. 일부 남은 셔플된 카메라의 정기 평가 이미지를 완성된9장 preview로 사용하지 않는다. `scientific_verdict: null`.

원 계획과 미실행 code/config는 보존한다. 앞부분의 계획은 실패 전에 고정한 기록이다.
갤러리 QA의 읽기 검토에서 패널 간 폭이 같은지만 확인하던 확대 검사를 실제2배 확대·0보다 큰 동기 스크롤 확인으로 보완했다. 실제22k 입력이 없어 이 browser QA를 실행하거나 PASS를 주장하지 않았다.
