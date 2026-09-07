# 기본 GeoGS의 실제 분할 기준과 저자 예제 비교

2026-09-15 · `PHD-GEOGS-NATIVE-EFFECTIVE-SCALE-AUDIT-v1` · `scientific_verdict: null`

검토 질문은 prior 가중치별 상대 차이가 아니라, **우리 기본 DA3/.005/native 30k의 RGB와 표면 색상이 왜 충분히 선명하지 않은가**이다. 이번 읽기 감사는 그 원인을 확정하지 않았지만 동일 설정값이 서로 다른 실제 분할 경계로 작동함을 확인했다.

## 확인된 차이

저자 제공 예제와 지역 실행의 Gaussian 코드 SHA는 동일하다. 같은 `percent_dense=.01`이어도 camera extent가 다르므로 clone/split 경계는 아래와 같다. extent는 학습 카메라 중심의 평균부터 최대 거리 ×1.1이고, 아래 크기는 Gaussian의 최대 scale(world 좌표 단위, 이 실행의 m)이다. 화면 반경이나 지붕 면적이 아니다.

| 항목 | 저자 제공 예제 | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| 학습 카메라 수 |13|98|57|137|
| camera extent |44.635|200.766|268.425|212.431|
| clone/split scale 경계 |0.446|2.008|2.684|2.124|
| 초기 XYZ optimizer 학습률 |.007142|.032123|.042948|.033989|
| 15k까지 평균 카메라 선택 횟수 |1153.8|153.1|263.2|109.5|

`scene/gaussian_model.py:396–436`에서 gradient 문턱을 넘고 보호 대상이 아닌 Gaussian은 최대 scale이 경계보다 크면 2개로 split하며 scale을1.6으로 나눈다. 경계 이하이면 동일 위치·크기를 복사하는 clone이다. 예를 들어 max scale=1인 Gaussian은 다른 자격 조건을 충족할 때 저자 예제에서는 split, 우리 세 지역에서는 clone 쪽이다. clone도 이후 최적화로 이동·축소될 수 있으므로 영구적으로 세부 형성이 불가능하다는 뜻은 아니다.

따라서 기본 숫자를 그대로 썼다는 사실은 같은 물리적 분할 동작을 보증하지 않는다. 우리 카메라 범위에서 큰 Gaussian이 더 오래 넓은 표현을 맡을 수 있다는 **구체적인 원인 후보**다. 하지만 실제 분할 사건·국소 기여의 시간 기록이나 해당 기준만 바꾼 개입 결과가 없으므로 이것을 기본 RGB 품질 저하의 확정 원인 또는 최대 기여 원인으로 승격하지 않는다.

XYZ 학습률도 같은 extent를 곱하므로 달라진다. 위 값은 초기 optimizer learning-rate 계수이며 실제 Adam 위치 이동량이 아니다. 15k 카메라 선택 횟수는 단일 카메라 순환 샘플링의 평균이고 특정 표면의 관측·갱신 횟수는 아니다. 같은15k densification 종료·30k 학습량이 동일 학습 기회를 뜻하지 않는다는 비교이며, 학습 부족의 확증은 아니다.

다른 확인된 입력 차이는 지역 ALS context를 잘라 초기화·prior로 사용하면서 RGB loss는 전체 사진을 사용한다는 점이다(`input/prepare.py:244`, 실제 `train.py:831,846–847`). 제한된 초기 공간 밖의 표면을 설명하려는 최적화가 ROI를 해쳤는지는 미측정이다. 저자 예제도 유한 공간을 사용하므로 단순한 crop 존재만으로 차이의 원인을 확정하지 않는다.

## 저자 예제와 초기화 귀속 정정

동일 pinned Docker에서 저자 예제는 원 학습→30k 렌더→mesh→metrics 실행을 완료했다. 저장된 `test/ours_30000/renders/00000.png`를 다시 열어 지붕 타일과 창문 세부가 복원되고 나무·거리 일부에는 artifact가 남는 것을 확인했다. 이것은 실행 환경 전체가 선명한 건물 표현을 만들지 못한다는 설명을 약화하지만, 논문 그림·지표·mesh 텍스처의 동일 재현을 증명하지 않는다. 실제 metrics는 PSNR16.901653, SSIM.527660, LPIPS.377536이고 지역 ROI 지표와 직접 순위화하지 않는다.

**과거 대화에서 저자 예제의55,413점을 SfM 초기화로 불렀다면 잘못된 귀속이다.** 실제 `output/model/input.ply`는 `scene/sparse_lod/0/points3D.ply`와 byte-identical이며 둘 다55,413점이다. 별도 `scene/sparse/0/points3D.ply`는37,675점이고 다른 SHA다. `--lod_init`가 선택한 경로를 확인한 것이며 저자 초기점의 모든 생성 과정을 역추적한 것은 아니다. 따라서 ‘저자 SfM 대 우리 ALS’라는 대비로 선명도 차이를 설명하지 않는다.

## 실행과 재현

- CPU Docker, 입력 read-only, 새 학습0회, `PASS_READONLY_EFFECTIVE_SCALE_AUDIT`, exit0.
- Script: [native_effective_scale_audit.py](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_p1p2p3_v1/analysis/native_effective_scale_audit.py)
- Config: [native_effective_scale_audit_v1.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/geogs_p1p2p3_v1/native_effective_scale_audit_v1.json)
- Receipt: [receipt.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/native_effective_scale_audit_v1/attempt.VwpI4ip5/receipt.json)
- Receipt SHA256: `b20bdf8ea18f4083b18b6d6148c8ec95721f28fa77ad6731e329a8618869ab5a`.
- 같은 attempt의 `command.sh`, script/config snapshot, 입력 SHA, `operator_head.txt`, `run.log`, `exit_code.txt`가 재현 정보를 보존한다. 기존 학습 소스·입력·모델은 변경하지 않았다.
- Camera 식: `scene/dataset_readers.py:271–291`; extent 결박: `scene/__init__.py:94,108`; 기본값: `arguments/__init__.py:119`; 위치 학습률: `scene/gaussian_model.py:157,166–167`.

본 감사의 비교 대상은 실제 저자 제공 예제다. 논문 모든 지역이 같은 extent나 카메라 수를 사용했다고 일반화하지 않는다. 왜 우리 기본 결과가 선명하지 않은지의 인과 검증은 미완료다.
