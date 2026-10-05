# B v4: 현재 MVS 초기화에서 외관 개선 확인

상태: 같은 P2에서 MVS 기하를 고정한 SH0/SH3 × 균일/잔차 강조 개발 진단. `scientific_verdict: null`.
v1–v3 소스·결과·manifest는 보존한다. 이번 실행은 A의 실제 영역 판정을 입력받은 통합 실행이 아니다.

## 1. 바꾼 것과 질문의 범위

앞선 v3은 ALS의 기하를 고정하고 색 표현·잔차 가중치만 비교한 진단이었다. 전역 ALS 초기화는 B 실험의 선택이었으며, A가 P2 전체에 PRIOR를 승인한 결과가 아니다.
이번에는 사용자가 지적한 변경 지역의 현재 관측을 반영하여 **현재 영상 MVS를 초기 기하로 선택**한다. 현재 MVS가 모든 위치에서 정확하거나 A의 적격성 검사를 통과했다는 뜻은 아니다.
질문은 “같은 현재 MVS 기하에서 현재 영상의 외관이 초기보다 개선되는가, SH 차수와 잔차 강조가 각각 어떤 영향을 주는가”이다.
과거 자산을 사용할 영역과 IMAGE/PRIOR/FUSION/ABSTAIN의 실제 공간별 연결은 후속 A→B 통합 범위이다.

## 2. 실제 입력과 고정 조건

- source run: `/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-B-CORRECTED-NATIVE-v1/`.
- seed: `mvs_source_seeds.npz`, 초기 state: `image_only/gaussians_initial.npz`.
- 원래 P2 MVS 330,679점에서 v2의 patch별 0.12m voxel 선택으로 보존된 266,361개 seed를 그대로 사용한다. 새 보간·분할·기하 이동을 하지 않는다.
- `seed_id`로 common native MVS에 역참조하여 XYZ·native tile row·patch ID·unit ID를 전수 exact 비교한다. 초기 state의 XYZ와 모든 원행 식별자도 같은 seed와 비교한다.
- 초기 SH0는 image_only G0에서 그대로 복사한다. SH3의 나머지 15×RGB 계수는 0이며 실제 11뷰의 초기 RGB가 SH0와 같은지 확인한다.
- 중심·quaternion·크기·opacity·개수와 원행 식별자를 전부 고정한다. 매 step 허용된 색 계수 외 gradient가 생기면 실패한다.
- 33 학습·11 외관 평가 뷰, v2 native crop의 최대 1536 크기와 768 학습 tile, 같은 카메라·수정 gsplat adapter를 사용한다. 이 뷰들은 이미 개발에 노출된 역사 자료이다.

v3 `PHD-P2-AB-V3-B-APPEARANCE-v1/uniform/training.jsonl`의 512개 image ID와 tile 좌표를 직접 재사용한다.
따라서 네 v4 arm과 이전 ALS 진단의 영상 crop 순서는 같다. 초기 source 지지·품질 분모·Gaussian 수가 달라서 ALS 대 MVS를 순수한 한 변수 효과로 해석하지 않는다.
학습 전에 모든 tile의 MVS 지원 픽셀 수·q 합계·이전 ALS 지원 수를 저장한다. 지원 0인 tile은 임의 대체하지 않고 실패 기록을 남긴다.

## 3. 네 조건의 계산

| arm | SH 차수 | 잔차 강조 β |
|---|---:|---:|
| sh0_uniform | 0 | 0 |
| sh0_residual_weighted | 0 | 1 |
| sh3_uniform | 3 | 0 |
| sh3_residual_weighted | 3 | 1 |

v3의 [색 전용 계산](../p2_ab_v3/B_CONCRETE_METHOD_ko_v3.md)과 hyperparameter를 그대로 사용한다.
고정 초기 기하 지지에서 조건부 전경 가림을 제외한 M에 대해 RGB 전 채널이 거의 0 또는 1이면 `q=0.25M`, 나머지는 `q=M`이다. 이는 작은 영상 포화 휴리스틱이며 추정된 잡음·현재성 확률이 아니다.
`r=mean_c|Î−I|`, `s=max(median_{q>0}(detach(r)),1/255)`, `a=detach(1+β min(r/s,2))`, `w=detach(qa/Σqa)`이다.
손실은 `0.8Σwr + 0.2(1−maskedSSIM(Î,I;M))`이며 잔차 강조는 L1에만 작용한다. `Σq=0`은 명시적 실패이다.
Adam 512회, SH0 LR 0.015에서 선형 감소, SH3 고차 LR은 그 1/20, gradient norm clip 10이다. 초기 SH0/DC 색은 [0,1] 범위로 제한한다.
고차 SH norm 정규화·노출 보정·분할/증감·세부 기하 최적화는 추가하지 않는다. L1은 gsplat RGB 직접, SSIM·평가·PNG는 [0,1]로 자른 RGB를 사용한다.
매 128회 평가 추세를 기록하지만 평가값으로 단계·파라미터를 고르지 않는다. 사전 고정된 512회 결과를 모두 보존하며 수렴을 주장하지 않는다.

## 4. 출력과 정량·정성 검증

run: `/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v4/PHD-P2-AB-V4-B-MVS-APPEARANCE-v1/`.
`initial/`에 11개의 target·RGB·support·q·depth·geometry_mass·alpha를 저장하고, 네 arm 폴더에는 모든 최종 RGB·depth·mass·alpha와 실제 전체 Gaussian NPZ·매 step 로그를 저장한다.
`rgb_ID.png`, `depth_ID.npy`, `geometry_mass_ID.npy`, `alpha_ID.npy`가 공통 파일명이다. Gaussian state의 `sh0/sh_rest/sh_degree`가 실제 색 계수이며 `rgb`는 DC 색 미리보기이다.
기하 파라미터 및 최종 depth/mass/alpha의 초기 대비 exact 비교와 렌더 finite/mass 범위 검사를 통과해야 기술 완료로 표시한다. 초기 MVS의 현재 기하 정확성 판정과는 다르다.
각 source의 고정 지지 전체 픽셀 MAE·고정 q MAE·뷰 평균 MAE/SSIM을 함께 기록한다. source별 자체 지원 마스크 수치는 ALS/MVS 간 직접 비교 분모가 아니다.
전체 11뷰의 target·MVS 초기·네 최종을 정성 비교에 넘긴다. ALS는 이전 진단의 맥락으로만 함께 표시하며 별도 공통 광선 분모 평가는 root가 수행한다.

## 5. 실행 결과

`COMPLETED_DIAGNOSTIC`, 전체 소요시간 82.94초(초기화·평가·저장 포함). 네 조건 모두 완료했으며 좋은 장면만 선택하거나 참조 UAS로 튜닝하지 않았다.

| 조건 | 고정 지지 픽셀 가중 MAE ↓ | 고정 q MAE ↓ | 뷰 평균 MAE ↓ | 뷰 평균 SSIM ↑ |
|---|---:|---:|---:|---:|
| MVS 초기 G0 | 0.139627 | 0.137733 | 0.184822 | 0.313119 |
| SH0 uniform | 0.146278 | 0.144418 | 0.174472 | 0.378862 |
| SH0 residual_weighted | 0.145236 | 0.143408 | 0.174299 | 0.378371 |
| SH3 uniform | 0.126669 | 0.124851 | 0.154442 | 0.428990 |
| SH3 residual_weighted | 0.125462 | 0.123681 | 0.153726 | 0.429140 |

확인된 결과는 **기하를 그대로 둔 SH3 조건의 현재 영상 외관 개선**이다. SH3에서 잔차 강조의 추가 차이는 전체 MAE 약 −0.001207, SSIM 약 +0.000150으로 표현 확장의 차이보다 작다.
SH0에서는 SSIM과 뷰 평균 MAE가 개선되어도 전체 픽셀 MAE는 악화됐다. 평균 방식·영상별 면적·L1+SSIM 목표가 다른 사실과 색 표현 용량 효과를 구분하며, 정확한 열화 원인을 노출/반사/오정합 중 하나로 확정하지 않는다.
SH3 residual_weighted의 128/256/384/512회 전체 MAE는 0.131946/0.128092/0.126156/0.125462였다. 마지막 단계가 사전 종료점이며 평가로 단계를 선택하지 않았다.
이 표는 각 MVS 조건에 동일한 초기 지원 4,558,325픽셀을 사용한다. 이전 ALS의 자체 지원 지표와 직접 순위를 만들지 않는다. 정성 비교와 root의 공통 지원 비교는 별도로 연결한다.

- MVS native→seed→G0의 9개 원행/좌표 검산 전수 PASS. 실제 11뷰에서 고차 계수 0의 SH3 RGB와 SH0 RGB exact PASS.
- 512개 사전 tile 중 지원 0은 없고 최소 1,541픽셀이다. 반복 tile 방문의 지원 합계는 MVS 98,832,741, 이전 ALS 99,116,302이다. 서로 다른 고유 픽셀 개수가 아니라 반복 방문 분모다.
- 네 arm 모두 중심·quaternion·scale·opacity·group·원행 식별자가 초기와 정확히 같다. 11뷰 각각의 depth·geometry mass·RGB alpha도 초기와 정확히 같다.
- 매 step 기하 gradient가 없고 모든 출력·색 gradient는 finite였다. SH3 고차 gradient 최소 norm은 uniform 0.003094, weighted 0.003449로 실제 비영 갱신을 확인했다.
- 세 MVS/파라미터 분리 단위검산 PASS. 실행에 결속된 새 소스와 v2 동결 46개 B 소스의 SHA가 유지됐다. 11 target PNG는 이전 ALS 진단과 byte-identical이다.

외관 개선은 현재 기하·새 세부 복원이나 A의 현재 사용 승인 성공을 뜻하지 않는다. 미관측 영역 생성·구조 갱신·densification·강한 기존 방법 재현은 이번 비교에 없다. `scientific_verdict: null`.

## 6. 재현성과 보존

- [실행 script](../../../../scripts/phd/p2_ab_v4/b_mvs_appearance_probe.py), [Docker driver](../../../../scripts/phd/p2_ab_v4/b_mvs_appearance_docker.sh), [config](../../../../configs/phd/p2_ab_v4/b_mvs_appearance_v1.json), [MVS 검산/표현 adapter](../../../../src/phd/p2_ab_v4/appearance_probe.py), [단위검산](../../../../tests/phd/test_p2_ab_v4_mvs_init.py).
- 실행: `bash scripts/phd/p2_ab_v4/b_mvs_appearance_docker.sh`. 새 출력·새 v4 CUDA cache만 쓰고 repo·기존 artifact·수정 CUDA adapter는 읽기 전용으로 mount한다.
- GPU 1, Docker `jointbuildgs:dev`의 실행 당시 exact image ID와 Git HEAD를 result에 기록한다. uncommitted 새 소스는 실행 전 source snapshot과 SHA로 식별한다.
- source run의 `independent_plane_hit_v1` adapter exact CUDA SHA 및 동결 v2 B 소스 46개를 검사한다. v3에서 읽어 쓰는 색 계산 소스도 이번 source snapshot/hash에 포함한다.
- 기존 run 디렉터리 재사용·기존 코드 수정·참조 UAS 사용·staging/commit은 하지 않는다. 실패하면 새 run의 `FAILED.json`과 console을 보존한다.
