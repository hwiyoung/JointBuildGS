# 최종 모델의 색상 적합과 손실 방향 진단

2026-09-15 · `PHD-GEOGS-RGB-COLOR-FIT-PROBE-v1` · `scientific_verdict: null`

## 결과와 해석

3개 사례의 최종 30k 모델에서 각각 SH 색상만100회 적합하고, 적합 전 RGB와 prior/visual/normal 손실의 기하 파라미터 gradient를 측정했다. 실제 실행105.820초, 색상 진단 optimizer update 총300회, 새 전체 학습0회다. 기술 검증은 `PASS_SHORT_DIAGNOSTIC`이며 논문 성능 재현이나 개선된 다중 시점 결과가 아니다.

| 고정 학습뷰 ROI | PSNR 적합 전→후 | SSIM 적합 전→후 | 관찰 |
|---|---:|---:|---|
| P1_train_1 MVS/prior .0005 |22.374→22.495|.5017→.5098|바닥 줄눈·작은 물체가 거의 복구되지 않고 넓은 번짐이 남는다.|
| P1_train_1 MVS/prior .005 |24.279→24.523|.6748→.6867|색상 적합만으로 얻는 개선이 작다.|
| P2_train_1 DA3/prior .005 |26.466→27.758|.7978→.8214|전체 사진 적합은 개선되지만 지붕의 작은 질감 대신 긴 번짐이 남는다.|

기존 [화면 반경 진단](RGB_RADIUS_PROBE_ko_v1.md)과 결합하면 P1은 넓은 투영 범위의 Gaussian이 흐린 표현을 맡으며, 이를 제외하거나 색상만 짧게 조정해도 선명한 바닥이 나타나지 않는다. 단순한 색상 학습 부족보다 Gaussian의 배치·크기·가림·세부 분할 형성 과정을 우선 조사할 근거다. 다만100회 단일 학습률 결과는 해당 표현의 최적 도달 품질이나 불가역적인 용량 한계를 증명하지 않는다.

## 실제 gradient가 수정하는 가설

최종 모델의 **전체 영상** RGB 손실과 각 기하 손실을 xyz/log-scale/quaternion/logit-opacity에 대해 미분했다. 보호 hook·Adam moment·preconditioning을 복원하지 않은 raw objective gradient다. 최종 trace의 실제 prior·visual 가중치를 적용했다.

- **P1 MVS/.0005:** MVS와 RGB의 scale/opacity cosine은 각각+.477/+.487이고 norm ratio는1.164/1.105다. 위치·회전은 거의 직교한다. normal은 네 군 모두 양의 cosine이다. prior gradient norm ratio는 최대.025다.
- **P1 MVS/.005:** MVS와 RGB의 scale/opacity cosine은+.503/+.530이다. prior gradient norm ratio는 모든 군에서.10 미만이다. 실제 마지막 visual 가중치는.0475다.
- **P2 DA3/.005:** prior는 네 군에서 RGB와 반대 방향이다(cosine−.299∼−.736). 그러나 DA3는 모두 정렬된다(+.575∼+.763). DA3/RGB norm ratio는 scale3.30, opacity6.17이다.
- 세 사례 모두 각 파라미터군에서 **가중 prior+visual+normal gradient 합과 RGB gradient의 내적은 양수**다. 각 성분의 기록된 dot을 더해 확인했다. 따라서 이 최종 전체 영상에서 ‘기하 손실 전체가 RGB 개선을 반대로 밀어 흐림이 유지된다’는 공통 설명은 지지되지 않는다.

이 결과는 과거 학습 중 충돌, 특정 ROI에서의 충돌 또는 실제 protected Adam step을 배제하지 않는다. SH 색상은 기하 손실에 직접 연결되지 않으므로, 색상 적합의 개선 자체를 기하 감독 제거 효과로 해석하지 않는다. 같은 파라미터군 안에서만 gradient 크기를 비교하며 서로 다른 단위의 xyz·scale·rotation·opacity norm을 직접 순위화하지 않는다.

## 절차와 검증

1. 앞선 RGB 진단 manifest와 사진·저장 렌더 SHA를 검증했다. 세 대상은 기존 학습뷰이며 신규 평가뷰 적합은 없다.
2. 원본 native depth loss 함수를 AST로 추출했다. prior/DA3는 학습 로더와 같은 `INTER_LINEAR`, MVS는 frozen binding의 원 depth와 K/R/t로 재표본화했다. scale-invariant·confidence 보정은 사용하지 않는다.
3. 실제 전체 영상 RGB·기하 손실 gradient를 측정한 뒤, 위치·회전·크기·opacity·카메라·개수를 고정했다.
4. 각 사진의 기존 고정 bbox에서 `.8 L1 + .2(1-SSIM)`을 Adam100회로 적합했다. 새 moment와 DC/고차 SH 동일 lr=.01을 사용한 공격적인 단일 시점 진단으로, 공식 native continuation이 아니다.
5. 단계0/25/50/75/100의 RGB·손실을 저장했다. geometry/opacity tensor 불변, alpha 최대 차이0, 원 SH 복원 후 RGB 완전 일치를 확인했다. 저장 native PNG와 최대 차이는1/255 이내였다.
6. 원 데이터·모델·소스는 read-only mount다. 학습 모델/PLY를 내보내거나 기존 결과를 대체하지 않았다.

## 산출물

- Script: [rgb_color_fit_probe.py](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_mvs_pgsr_v1/rgb_color_fit_probe.py), [gradient helper](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_mvs_pgsr_v1/rgb_final_gradient_probe.py)
- Config: [rgb_color_fit_probe_v1.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/geogs_mvs_pgsr_v1/rgb_color_fit_probe_v1.json)
- [receipt.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_color_fit_probe_v1/attempt.BY4TsDnU/receipt.json), SHA256 `ad51058539212e31da0818b6cd699c10da7e394a6d685a4d7cd6d0fa8dab0666`
- [P1 색상 적합 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_color_fit_probe_v1/attempt.BY4TsDnU/P1_train_1__mvs_0.0005/montage.png)
- [P2 vanilla 색상 적합 비교](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/rgb_color_fit_probe_v1/attempt.BY4TsDnU/P2_train_1__da3_0.005/montage.png)

스크립트·config snapshot, 명령, Docker image ID·버전·GPU, Git HEAD, 입력·모델·trace·소스 SHA, 단계별 이미지와 gradient.json을 attempt에 보존했다. 실행 전 MVS extraction 모델에는 학습 trace가 없는 경로 문제를 발견해 원 training receipt로 경로를 해석하고 staged/original PLY·cfg_args SHA 일치를 Docker에서 검증했다. 실행 실패는 없었다.
