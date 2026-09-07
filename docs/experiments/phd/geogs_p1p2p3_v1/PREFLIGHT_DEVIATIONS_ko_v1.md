# 실행 전 확인된 입력·구현 편차

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

아래 변경은 세 지역의 GeoGS 결과를 보기 전에 입력 계약·실행 가능성을 점검하면서 결정한 것이다. 원 확보 코드와 기존 연구 자료는 보존한다. 이 문서는 원 설정 제어와 ALS 적용을 동일시하지 않기 위한 기록이다.

| 항목 | 실제 확인 | 적용과 해석 |
|---|---|---|
| CUDA 환경 | Python3.10.20 / Torch2.1.2+cu121 및 native CUDA submodule 컴파일·gradient 검사 PASS. compiler12.1.105, 저자 기록12.4 | 별도 image `jointbuildgs:geogs-official-db40c95-v1`. 버전 편차를 공개하고 모델·renderer는 고정 공식 코드 사용 |
| 동적 library | renderer import는 성공했으나 extraction import에서 system libstdc++가 ICU78 요구 `CXXABI_1.3.15`를 제공하지 못함 | 기존 학습을 중단하지 않고 새 extraction 프로세스의 library 경로를 별도 검증. 실제 성공한 환경을 명령 receipt에 기록 |
| 완전 상태 | 실제 native Gaussian과 Adam의 비영 momentum, 보호 hook, CPU/CUDA/NumPy/Python RNG, 카메라 순서·stack, DA controller fixture 저장·복원 PASS | 장면 단위 원본 연속/기록본 연속/재개 검증은 별도 필요. fixture 통과를 장면 성능 결과로 해석하지 않음 |
| 카메라 주점 | 지역 전뷰 1400×1013, fx922.0550838163813/fy922.470063461439/cx702.6193018201524/cy499.79701601553825. 공식 FoV-only 로더가 cx/cy를 버림 | 원 RGB/카메라를 warp하거나 중앙 주점으로 덮어쓰지 않고, 명시적 scene calibration metadata에만 반응하는 projection adapter 사용. compiled native renderer는 동일 |
| 투영 검증 | native CUDA의 세 점 렌더 위치 오차 최대6.2032px → adapter0.00560px. 공식 TSDF camera K복원 오차 최대3.17e-5 | `runtime/camera_projection_v1/receipt.json`. 합성 카메라 검증이며 장면 기하 정확도 개선 수치가 아님 |
| pixel convention | native rasterizer/TSDF K의 (W−1)/2와 point_utils의 W/2 사이0.5px 차이, Open3D ray의 half-pixel convention | 원경로 잔여 convention을 기록. 주점 보완만으로 전체 수치 경로가 완전히 일치한다고 주장하지 않음. 합성5m fixture의 역투영 잔차는 실제 항공 장면 오차의 상한이 아니며, 같은 각도 차이의 위치 오차는 거리에 따라 커진다. 실제 지역의 표면 오차에 기여한 크기는 이 fixture로 분리 측정하지 않았음 |
| ALS 표면 손실 | 삼각망에 표현되지 않은 core ALS점: P1 1,241/20,189, P2 5,952/45,986, P3 5,124/52,762 | 원점 삭제가 아니라 입력 mesh 표현 손실. 원 ALS와 실제 공급 mesh를 각각 평가한다 |
| DA3 분할 | train-only batch 상한8, P1/P2/P3는13/8/18 batch. 마지막1뷰 batch는 바로 앞 batch에서1뷰 이동해2뷰로 구성 | 모든 batch가 disjoint이고 각 train뷰는 정확히 한 batch에 포함. 이 singleton 처리는 입력 수·pose conditioning에 따른 사전 규칙이며 점수로 선택하지 않음 |
| DA3 자원 | 공식 예제 학습은 GPU1, DA3 전처리 preflight는 GPU0에 torch memory fraction0.8로19.2GiB 상한 | 지역 학습 동시성1 유지, desktop/service headroom 확보. 기존 서비스를 중단·재시작하지 않음 |
| prior 가시성 | 현재 Trimesh.Scene에 ray 속성이 없어 공식 sampling 경로가 예외 뒤 visible=True fallback에 들어갈 수 있음을 확인 | 가시성 filtering이 검증됐다고 표시하지 않는다. 실제 입력 wrapper와 occluder 검사 후 수정/보존 여부를 기록해야 함 |
| 공식 예제 | 제공 예제 역시 비중앙 주점. 제공 DA3의 원 입력 membership 미확인 | 원 예제는 원코드 그대로 재현하고 투영/DA3 계보 한계 표시. 세 지역의 보완된 카메라 조건과 구별 |
| LPIPS | native 학습 보고는 AlexNet, metrics.py 최종은 VGG. bundled LPIPS 입력 범위는[0,1] | backbone·weight hash·범위를 명시. 표준[-1,1] LPIPS를 추가하면 별도 column. metrics.py의 예외 삼킴 때문에 종료코드만으로 성공 판정하지 않음 |

계획의 비교 조건·학습량·평가 범위·임계값은 그대로 유지한다. 입력 adapter는 바닐라와 모든 변경 조건에 똑같이 적용한다. 원본 연속 실행과 같은 상태 재개를 먼저 검증하고, 실행한 script/config/source hash 및 실제 입력 패키지를 학습 전에 봉인한다.

## 원 제어 규칙을 유지한 대비의 해석

UAS와 지역 품질값을 열기 전에 실행 source의 `train.py:907–987`을 다시 대조했다. DA3 dual-gate는 실제 DA3 깊이와 RGB loss 이력을 사용해 수렴·감쇠·유지·잠금 상태를 갱신한다. 같은 anchor의 controller 상태와 초기 가중치·규칙을 사용해도, prior 깊이 계수 또는 보호를 변경한 뒤 실현된 DA3 가중치 궤적까지 조건 간 동일하다는 뜻은 아니다. 조건 대비는 이 원 제어 규칙을 유지한 실행 전체의 차이로 해석하며, DA3 궤적을 외부에서 동일하게 강제한 순수 직접 효과라고 부르지 않는다. 원 규칙이나 현재 실행 설정은 바꾸지 않았다.

보호 해제는 위치·회전·크기 gradient 감쇠와 보호 대상의 분할·복제·삭제 제한을 함께 해제한다. 여섯 조건으로 이 두 구성요소 각각의 단독 효과를 분리할 수 없다. 같은 조건의 CUDA 수치 반복 차이도 별도 표와 함께 검토한다. 이 해석의 실행 source SHA-256은 `08cfab996b144488b1a583bf722b991c627d90136a9031f85f7d33b1cae0c44b`이며, 새 알고리즘 또는 학습 변경을 뜻하지 않는다.

함수 이름에 `lr`가 들어가지만 `train.py:603–643`의 실제 보호 동작은 gradient hook의0.01 배율이다. optimizer는 `scene/gaussian_model.py:165`의 Adam이며 과거 momentum도 복원한다. 이를 좌표·회전·크기 변화량이 정확히100분의1이 된다는 의미로 읽지 않는다. 보호 개수나 전체 Gaussian 수는 학습 context의 상태 기록이며, 평가 ROI에서 보이는 표면의 유지·결손·품질을 직접 측정한 값이 아니다.
