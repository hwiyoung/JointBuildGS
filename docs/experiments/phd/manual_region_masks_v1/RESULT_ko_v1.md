# P1 전체 학습 시점의 수동 영역 표시

- 작성: 2026-09-15
- task_id: `PHD-P1-MANUAL-REGIONS-v1`
- 상태: `PASS_ALL_TRAIN_VIEW_ANNOTATION_DRAFT`
- 범위: 입력 기반 수동 분할과 현재 MVS를 통한 다중 시점 표시 초안
- scientific_verdict: null
- 원본 입력 변경, 학습 연결, GPU 최적화 실행: 없음

## 목적

A·B·C·D 사각형을 관찰용 표본으로 유지하면서, 실제 가중치 실험을 검토할 수 있도록
P1 학습 영상 전체에 region ID와 예시 depth 배율을 정의한다. 동일한 물리적 지면의
표시를 각 시점에 연결하며, 현재 관측되는 표면으로 가시성을 검사한다.

대상은 봉인된 **train 98장**이다. 별도 evaluation 15장은 사용하지 않는다.
현재 수동 annotation 원영상은 train index 0과 83의 두 장이며, 나머지 시점은
현재 MVS로 대응이 확인된 관측에 표면 구분을 전파한 **검토용 초안**이다.
모든 시점의 raster를 생성하는 것과 모든 픽셀의 의미를 사람이 검수하는 것은 다르다.

## 전체 분할과 예시 배율

| ID | 영역 | 표시용 MVS 배율 |
|---|---|---:|
| 1 | 보정 시험 지면 | α, 현재 그림의 예시는 4 |
| 2 | 현재 건물 표면 | 1 |
| 3 | 기타 정적 지면 | 1 |
| 4 | 대표 영상에서 수동으로 표시한 관측 제외 대상 | 0 |
| 5 | 미분류·대응 미확인·경계·충돌 등 판단 유보 | 0 |
| 6 | 현재 MVS XYZ가 기존 학습 문맥 범위 밖에 있는 유효 관측 | 0 |

MVS validity는 별도 boolean raster다. 결측은 ID 5와 validity=false로 저장하고
배율을 0으로 둔다. 결측에서 실제 3D 위치를 알 수 없으므로 임의로 ID 6을 부여하지 않는다.
회색의 원인은 결측, 유보, 범위 밖으로 구분하며 각 상태를 수치 0 하나로 합치지 않는다.

배율은 confidence 확률이 아니다. 예시 α=4는 학습에서 효과가 확인된 값이 아니다.
이 마스크는 MVS depth 감독을 위한 초안이며 RGB loss, prior 계수/보호, Gaussian
삭제·이동·추가를 제어하지 않는다.

## 수동 영역의 입력 근거

- index 0 현재 RGB에서 지면·건물·수목·장비·차량·조형물 등을 다각형으로 구분했다.
- A를 포함하는 보정 시험 영역은 같은 시점의 RGB/MVS/prior 입력 비교에서 관찰된
  과거 상부면과 현재 지면의 불일치 범위를 따라 수동으로 지정했다.
- 보정 영역은 현재 지면 label, 유효 MVS, 학습 문맥 범위로 다시 제한한다.
  입력 차이는 철거 정답이나 MVS의 절대 정확도를 뜻하지 않는다.
- index 83에서는 다른 시각에 보이는 차량·사람과 가림을 따로 표시했다.
- LoD2/UAS reference, GS 결과, 평가 점수로 영역이나 파라미터를 결정하지 않았다.
- 봉인 P1 입력에 의미 분할 파일은 없었다. 기존 `building_flag`는 의미적 건물
  분류로 사용하지 않았다.

수동 다각형과 메모는
`configs/phd/manual_region_masks_v1/p1_v1.json`에 전체 RGB 좌표로 기록되어 있다.
선택 당시 원영상과 prior 좌표 격자는 외부 inspection receipt에 보존한다.

## 시점 사이의 대응

1. 각 target 영상의 **native MVS 픽셀 ray**와 camera-Z depth로 XYZ를 역투영한다.
2. 해당 XYZ를 수동 source 영상에 투영한다.
3. source MVS depth와 camera-Z 차이 ≤0.5m, source native sample을 target으로
   되돌린 위치의 차이 ≤2 native pixels인 경우에만 전파 후보로 인정한다.
4. 무관측 source는 기권한다. 건물/지면 label이 충돌하면 유보한다. 실제 제외
   객체에 대응한 관측은 다른 시점에서 제외 객체로 복제하지 않고 유보한다.
5. 수동으로 직접 지정한 source 시점은 자신의 annotation을 우선 사용한다.
6. 원래 보정 다각형과 source-0 depth에 대응하고, 최종 표면 구분도 지면인
   픽셀만 ID 1로 둔다. 다른 시점에서 사각형/다각형 좌표를 그대로 복사하지 않는다.
7. 분할 경계와 depth 불연속 주변을 유보한다. Native→RGB 변환은 현재 MVS
   loader와 같은 K 기반 nearest 인덱스를 사용한다.

0.5m/2px, 경계 띠와 depth 불연속 기준은 초안의 재현 파라미터이며 측정오차나
confidence를 보정한 결과가 아니다. 같은 MVS에 의존한 대응은 독립 기하 검증이 아니다.
두 대표 영상에서 발견하지 못한 다른 시점의 작은 일시적 객체는 남아 있을 수 있다.

## 범위와 결과 읽기

분할의 공통 공간은 기존 P1 **80×80m 학습 문맥**이다:
X=[−48,32], Y=[−46,34], local Z=[−90,80]. 기존 **30×30m P1 평가 영역**과
같은 범위가 아니다. 이번 작업은 기존 평가 범위나 학습 설정을 변경하지 않는다.
원 좌표계 계보는 EPSG:25832이며 기존 working frame과 그 높이 datum 한계를 유지한다.

다른 방향에서 광장이 가려지면 ID 1이 없을 수 있다. 다른 표면만 관측되거나
source와 대응되지 않으면 그 부분은 ID 5다. 이 상태를 '현재 건물/지면이 없음'이나
'MVS가 부정확함'으로 단정하지 않는다.

향후 α 비교에서는 동일한 전체 분할·유효성·제외 정책을 모든 조건에 고정하고
ID 1의 배율만 바꿔야 한다. 이 제외 정책을 쓰는 기준선과 기존 native 전체
depth 기준선은 구분해야 한다. 이번 출력만으로 학습 준비 완료나 효과를 주장하지 않는다.

## 산출물 및 검증

최종 export 검증은 `PASS_EXPORTED_ARRAYS_AND_HASHES`다. **98/98 시점, native/RGB
배열 196개, 출력 해시 900개**를 확인했고 PDF는 98페이지다. Contact sheet 9장
전체를 열어 표시 누락·깨진 그림·큰 영역 번짐을 확인했으며, 대표/보조 시점
0·1·2·83은 전체 프레임을 추가로 확인했다.

전체 유효 문맥 RGB 표본 중 ID 1–4가 배정된 비율은 **26.29%**이고 나머지는
유보다. RGB 표본은 native nearest 중복과 다중 시점의 반복 관측을 포함하므로
이 비율은 고유 3D 면적의 coverage나 분할 정확도가 아니다. 유효 문맥 depth가
없는 시점은 14개다. ID 1 표본이 있는 시점은 19개지만 2·4·10픽셀 등의 극소
조각을 포함하므로 충분한 다중 시점 지원이 19개라고 해석하지 않는다.

기존 표본과의 대응 확인: A 9,600픽셀 중 보정 지면 8,778 / 기타 지면 389 /
유보 433, B 2,800픽셀은 모두 기타 지면, C 7,700픽셀 중 건물 7,365 / 유보 335,
D 5,200픽셀 중 제외 4,946 / 유보 254다. 사각형 자체가 label 정의가 아니므로
표본 내부 경계·결측까지 같은 class로 강제하지 않는다.

정확한 외부 경로와 최종 완료 상태는
`artifacts/manifests/phd/manual_region_masks_v1/p1_20260915.yaml`이 연결한다.

- `P1_two_views.png`: 두 대표 시점의 RGB/depth 영역 표시
- `P1_all_98_views.pdf`: 전체 시점의 원 RGB, RGB 표시, 원 depth, depth 표시
- `contact_sheets/`: 전체 시점의 depth 표시를 순서대로 모은 그림
- `views/<index>_<camera>/full_frame.png`: 해당 시점의 전체 프레임 비교
- `native_masks.npz`, `rgb_masks.npz`: region ID, validity, 예시 배율, 투표·충돌·경계 진단
- `region_id.png`: 색상 없는 정수 ID PNG. `regions_color.png`는 표시용 색상 PNG
- `weight_alpha4.png`: 배율 0/1/4의 표시용 그림. 학습용 수치는 NPZ에 보존
- `manual_sources/`: 직접 지정한 원영상 좌표 다각형과 분할
- `coverage.csv`, `receipt.json`: 시점별 분할 수, 유효 문맥 내 분류 비율, 정확한 입력/출력 해시

고정 Docker CPU, 좁은 입력 읽기 전용 mount, network none, GPU 미노출로 생성한다.
분할의 완전성, 무효 depth의 배율 0, 기존 loader와 native/RGB sampling 동일성,
입력 해시 재확인을 수행한다. 투영·가림·결측·좌표계 불변성·충돌 처리 등의 합성
기하 및 boolean 자료형 테스트 15개가 같은 고정 Docker image에서 통과했다. 이 테스트는 실제 장면의
semantic 정확도나 가중치 효과를 검증하지 않는다.

재현: `bash scripts/phd/manual_region_masks_v1/run_p1.sh`.
매번 신규 immutable attempt에 실행 source/config/command/commit을 보존한다.

초기 `attempt.uCJGq4`에서 RGB로 옮긴 boolean 진단 배열이 정수로 저장된 문제를
발견했다. 원본 attempt를 보존하고 `repair_p1_boolean_exports.sh`로 새 attempt의
boolean 자료형을 바로잡았다. 모든 영역 값과 그림의 동일성을 검사하며, 이후의
새 생성에서는 수정된 nearest resampling 함수가 boolean 자료형을 유지한다.
최종 수정본은 `attempt.boolfix.QrP8Ir`이며, 결과 receipt SHA256은
`809c14181dc5afb21a5fd056c48c2d09ee9e815c943167e1d44830644dcec66a`다.
