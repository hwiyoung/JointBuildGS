# 2D depth supervision의 영역·가중치 기준 — 원문 확인 메모

2026-09-17. 설계 제안이며 구현·실험 조건 변경 없음. `scientific_verdict: null`.

## 1. 실제 관련 연구

| 연구 | 픽셀별 판단의 실제 기준 | 남는 한계 |
|---|---|---|
| [NeuRIS, ECCV 2022](https://arxiv.org/pdf/2206.13597), §3.2, 식 4–6 | 렌더 depth·normal로 픽셀 주변 국소 평면을 만들고, 인접 영상으로 patch를 homography warp한다. 여러 영상의 NCC를 검사해 해당 픽셀의 normal prior supervision을 0/1로 결정한다. | indoor normal prior 문제다. 과거 ALS와 현재 MVS의 어느 쪽이 맞는지 직접 비교하지 않는다. 현재 재구성으로 검사하므로 자기확증·무텍스처·가림에 대한 별도 검토가 필요하다. |
| [AGS-Mesh, 3DV 2025](https://arxiv.org/html/2411.19271v2), §4.1–4.2 | DNC는 sensor depth 유래 normal과 pretrained normal의 각도 차이로 depth 픽셀을 필터링한다. ANR은 rendered/pretrained normal 차이로 normal supervision을 필터링한다. Appendix A.1의 임계각은 10°다. | normal이 같은 두 평행면의 높이 차이는 잡지 못한다. 동일 현시점 sensor/normal의 불일치 해법을 cross-temporal source selector로 그대로 볼 수 없다. 임계값도 보편적 정답은 아니다. |
| [D3VO, CVPR 2020](https://arxiv.org/pdf/2003.01060), §3.1, 식 6–7 | 픽셀별 photometric uncertainty를 예측하고 Laplace likelihood의 `abs(residual)/scale + log(scale)` 형태로 학습한다. 관측별 가중치를 데이터 의존적으로 만든다. | photometric uncertainty이며 ALS/MVS metric-depth uncertainty가 아니다. 직접 전용할 수 없고 source별 오차 모델·보정·검증이 필요하다. |

각 논문의 공식 저자·학회 원문을 이번에 확인했다. AGS-Mesh의 [저자 코드](https://github.com/XuqianRen/AGS_Mesh)도 depth-normal consistency mask의 사전 생성 경로를 명시한다. 논문들이 영역 분할·가중치라는 단어를 같은 의미로 쓰는 것은 아니므로 입력, 실제 gate, 적용 loss를 구분해야 한다.

## 2. 이 문제에 대한 제안: 먼저 픽셀의 관측을 판정

큰 3D 구역의 완전한 분할은 depth weighting의 선행 조건이 아니다. 각 영상에서 다음 지도를 만든 뒤 같은 판단이 이어지는 픽셀을 설명용 영역으로 묶을 수 있다.

1. 대상·유효성: 하늘, 영상 밖, depth 부재, 표면 경계 혼합, 가림을 구분한다. depth 부재와 하늘은 같은 사유가 아니다.
2. MVS 후보: 그 픽셀의 MVS depth가 정의하는 표면을 다른 현재 영상·depth로 검사한다. 재투영 depth 잔차, RGB patch 일관성, 시선 기하, 가림을 별도로 기록한다.
3. prior 후보: 같은 현재 영상들에서 prior depth가 정의하는 후보 표면을 별도로 검사한다. native prior의 빈 공간·관측 부재를 유효 표면으로 채워 넣지 않는다.
4. 판정: 양쪽 후보의 현재 관측 지지가 구별되면 선택·감쇠하고, 둘 다 타당하면 유지하며, 구분할 수 없으면 유보한다. prior–MVS depth 차이는 충돌 후보일 뿐 source authority가 아니다.
5. 공간 묶음: 필요하면 동일 판단의 연결 성분 또는 경계 보존 smoothing을 사용한다. 지붕–벽·전경–배경의 depth/normal 불연속을 가로질러 confidence를 전파하지 않는다. 14개 구역은 결과 집계 단위로 유지한다.

이는 NeuRIS의 관측 검사 생각을 **각 source 후보에 따로 적용하자는 설계 추론**이며, NeuRIS가 이미 이 방법을 검증했다는 주장이 아니다. 현재 R1 판단 지도에는 수동 C1 및 context polygon이 포함되므로 자동 source 판정의 정답으로 취급하지 않는다.

## 3. 1·2·4의 적정값 문제

수동 배수 sweep은 민감도를 측정할 수 있지만 적정값을 증명하지 않는다. 두 요소를 구분해야 한다.

- **그 관측이 현재 표면에 유효한가:** 대상/가림/현재성/대응 표면의 판정.
- **유효한 관측이 얼마나 정밀한가:** source별 오차 크기의 추정과 보정.

metric L1에 Laplace 관측모형을 채택하면 `L = abs(rendered_depth-observed_depth)/b + log(b)`이고 `b>0`는 metre 단위 오차 scale다. 여기서 상대 가중치는 `1/b`가 되지만, 이는 채택한 확률모형에서 나온 관계다. 현재 GeoGS loss가 이미 calibrated likelihood라는 뜻은 아니다. L2/Gaussian 가정에서는 inverse variance를 쓰므로 L1에 `1/sigma^2`를 기계적으로 붙이지 않는다.

동일 손실에서 각 픽셀의 scale을 자유롭게 키우게 두면 어려운 관측을 무시하는 방향으로 학습할 수 있다. `log(b)` 항, 하한·상한 또는 적절한 prior, 공유된 예측 모델/별도 관측 검증이 필요하며, 이 장치만으로 calibration이나 source correctness가 보증되지는 않는다. 과거 표면의 구조적 변화도 단순한 zero-mean depth noise로 흡수하지 않아야 한다.

현재 run의 MVS 생산에 evaluation 영상이 포함되므로 같은 영상의 재투영 일관성은 개발용 근거다. 독립 검증이라고 부르지 않는다. UAS/LoD2 평가 기하를 threshold나 weight 선택에 사용하지 않는다. RGB loss 대비 전체 depth 영향 계수와 loss reduction/유효 픽셀 분모도 별도의 통제 조건으로 기록해야 한다.

따라서 다음 설계 산출물은 새 수동 구역·임의 배수보다 **source별 픽셀 근거 지도 + gate 이유 + 오차 scale의 검증 방법**이 적절하다. 이 메모는 자동화가 이미 해결됐다는 주장도, 새 실행 승인도 아니다.
