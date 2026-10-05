# 30k 체크포인트의 화면 크기별 RGB 기여·제외 진단

2026-09-15 · `PHD-GEOGS-RGB-RADIUS-PROBE-v1` · `scientific_verdict: null`

## 확인 결과

기존 30k 모델의 7개 case/condition 조합에 대해 새 학습 없이 103.738초에 기여 지도와 제외 렌더를 생성했다. 기술 상태는 `PASS_RENDER_ONLY_DIAGNOSTIC`이다. P1의 바닥 흐림과 P2/P3의 회색 가림에는 서로 다른 양상이 있다. 기존 방법의 성능 재현, 원인 수정, 개선된 최종 산출물은 아니다.

- **P1_train_1 MVS/.0005:** 큰 투영 범위를 가진 Gaussian 집단이 바닥의 흐린 표현을 대부분 담당한다. 투영 반경 >100px 집단의 기여는 원래 alpha>=.95인 ROI에서 평균68.22%로, 같은 사진의 prior .005에서34.92%보다 높다. 이 집단을 제외하면 선명한 바닥 줄눈이 나타나지 않고 빈 영역이 크게 늘어난다. 단순히 선명한 결과 앞의 가림만 제거하면 해결되는 상태라는 설명은 이 사례에서 지지되지 않는다. 작은 투영 반경 집단만으로 현재 바닥 표현을 유지할 수 없다는 관찰이다.
- **P2_evaluation_2 MVS/.005:** >100px 집단을 제외하면 오른쪽의 회색 가림이 줄고 뒤의 반복 지붕 무늬가 드러난다. 이 국소 가림에 해당 집단이 기여한다는 직접 개입 근거다. 다만 다른 부분이 손상되어 전체 ROI SSIM과 alpha coverage는 낮아진다. 전역 크기 제거를 품질 개선책으로 채택할 근거는 아니다.
- **P3_evaluation_2 MVS/.005:** >100px 집단이 원래 alpha>=.95인 ROI에서 평균99.19%의 합성 기여를 차지한다. 제외 후 청회색 가림이 사라지고 건물 일부가 나타나지만, 바닥에 큰 빈 영역이 남는다. 가림과 불충분한 잔여 표현이 함께 관찰된다.
- **대조:** P1_train_2의 비교적 선명한 같은 모델에도 >100px 기여39.04%가 존재한다. P2_train_1 DA3/.005에도43.54%가 존재하고 크기 제외 시 악화한다. 큰 투영 반경 자체를 결함 판정으로 사용하지 않는다.

## 고정 ROI 측정

아래 기여율은 **각 원래 렌더의 alpha>=.95인 픽셀**에서 `selected contribution / alpha`를 평균한 값이다. 두 조건 사이의 픽셀 집합이 정확히 같다는 주장은 하지 않는다. PSNR·SSIM·평균 alpha는 제외 전후 동일 전체 bbox에서 계산했다.

| case / 조건 | >100px 기여율 | PSNR 원래→제외 | SSIM 원래→제외 | 평균 alpha 원래→제외 |
|---|---:|---:|---:|---:|
| P1_train_1 MVS/.0005 |68.22%|22.374→8.853|.502→.237|.958→.399|
| P1_train_2 MVS/.0005 |39.04%|22.516→17.741|.720→.641|.989→.944|
| P1_train_1 MVS/.005 |34.92%|24.279→13.819|.675→.529|.963→.740|
| P2_evaluation_2 MVS/.005 |44.70%|17.920→19.051|.674→.613|.996→.936|
| P2_evaluation_2 MVS/.0005 |39.41%|25.308→17.751|.751→.599|.982→.859|
| P2_train_1 DA3/.005 |43.54%|26.466→17.595|.798→.637|.978→.897|
| P3_evaluation_2 MVS/.005 |99.19%|10.171→14.582|.307→.458|.999→.732|

20/50px 개입, 원래 기여량의 전체 ROI 평균, alpha>=.95 피복률, Gaussian 수, 각 이미지·모델 식별자는 개별 `result.json`과 합본 receipt에 있다. 새 RGB의 uint8 반올림과 원 exporter의 양자화 차이 때문에 종전 저장 PNG 지표와 소폭 다르다. 파일 비교에서 최대 차이는 모든 사례에서1이었다. 이 미세한 차이를 학습 효과로 해석하지 않는다.

## 방법과 검증

1. 앞선 RGB 진단의 manifest SHA를 검증하고, 이미 관찰된 사례와 짝 조건을 고정했다. 실패 중심 개발 진단으로 일반화 평가가 아니다.
2. 저장된 30k PLY, SH degree3, 같은 사진·카메라·K·해상도·배경을 사용했다. 원래 렌더를 다시 생성해 저장 PNG와 전체 화소 비교했다.
3. native rasterizer가 반환한 투영 AABB 반경에 대해 >20/>50/>100px 지시자를 `override_color`의 RGB 채널에 넣었다. 검은 배경, 기존 opacity·가림 순서를 유지하므로 각 채널은 해당 집단의 실제 `sum(T*alpha)` 기여다.
4. `m100<=m50<=m20<=alpha`와 alpha 불변을 검사했다. 각 조건에서 최대 alpha 차이0이었다.
5. 각 집단의 opacity를 메모리에서만0으로 만들어 재렌더링하고 즉시 복원했다. 제외는 가림 순서를 통한 합성 효과를 바꾸므로 기여 지도와 구분한다. 복원 후 렌더 최대 차이는 모두0이었다.
6. 원사진에 대한 전체 고정 ROI PSNR·native SSIM과 alpha를 함께 측정했다. 원 입력·소스·모델은 read-only mount이고 optimizer·훈련·추출은 실행하지 않았다.

투영 반경은 Gaussian 표준편차나 모든 픽셀에서의 실제 support 크기가 아니다. 길고 얇은 정상 primitive도 큰 값일 수 있다. 이 결과는 화면 크기 제거 코드 문제의 학습 중 인과 효과, 잘못된 카메라, depth 감독 충돌 중 어느 것이 원천 원인인지 확정하지 않는다.

## 재현 및 산출물

- Script: [rgb_radius_probe.py](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_mvs_pgsr_v1/rgb_radius_probe.py)
- Config: [rgb_radius_probe_v1.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/geogs_mvs_pgsr_v1/rgb_radius_probe_v1.json)
- Launcher: [rgb_radius_probe.sh](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_mvs_pgsr_v1/rgb_radius_probe.sh)
- 외부 payload: `phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_radius_probe_v1/attempt.r4dC0sQH`
- [receipt.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_radius_probe_v1/attempt.r4dC0sQH/receipt.json), SHA256 `1178276264b1084a14f97a28bc5d19c033bc54633876e2d0170800d5ca4710cf`
- [P1 흐린 바닥 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_radius_probe_v1/attempt.r4dC0sQH/P1_train_1__mvs_0.0005/montage.png)
- [P2 회색 가림 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_radius_probe_v1/attempt.r4dC0sQH/P2_evaluation_2__mvs_0.005/montage.png)
- [P3 청회색 가림 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_radius_probe_v1/attempt.r4dC0sQH/P3_evaluation_2__mvs_0.005/montage.png)

실제 Docker image ID·버전·GPU·소스 및 PLY SHA·명령·script/config snapshot·시작/종료 GPU 상태를 attempt에 보존했다. 스크립트 정적 검토와 실제 렌더의 일치·기여·복원 검사를 통과했다. `MGP-018`로 원인 미확정 범위를 기록한다.
