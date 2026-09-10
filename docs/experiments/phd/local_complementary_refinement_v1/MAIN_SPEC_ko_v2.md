# 국소 상보 depth refinement 본 실험 명세 v2

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- 실행 revision: `main_v2`; scientific_verdict: null
- 근거: 2026-09-10 사용자의 본 실험 18개 구현·검증·실행·평가 지시. 종료 시각 제한 없음.
- 기계 명세: [experiment_v2.json](../../../../configs/phd/local_complementary_refinement_v1/experiment_v2.json)
- 이전 계획·기여 검토·자원 검토·분위수 config·P2 probe는 수정하지 않고 준비 계보로 보존한다.

## 의미와 결정 순서

같은 카메라 픽셀의 기존 prior와 영상 파생 DA3 depth가 조금 다르면 prior 감독을 유지하고, 크게 다르면 영상 depth 감독의 상대적 비중을 높인다. 이는 source 정오를 식별하는 추정기가 아니라 시험할 고정 배분 정책이다. 두 target의 오류·정합·가시 표면 차이는 이 신호만으로 분리할 수 없다. 기존 RGB와 controller·구조 보호를 유지한 전체 변경 효과를 비교한다.

1. 기존 봉인 입력과 complete Anchor8000을 해시 확인하여 재사용한다. 새 정합·DA3·Anchor 학습은 없다.
2. train 입력만으로 단위·ray·resize·결손과 배율 분포를 검사했다. 이 근거로 하나의 공통 문턱을 선택한다.
3. loss·실행·평가·자원 명세를 별도 revision으로 고정한다. 실제 worker가 config/binding/source/helper/probe hash를 검증한 뒤 실행한다.
4. 새 18개 전체의 기술 결과와 기존 18개를 대응 평가한다. 결과에서 유리한 지역별 문턱이나 조건을 다시 선택하지 않는다.

## 문턱의 새 결정

이번 본 실험은 `tau0=0.5m`, `tau1=2.0m`를 채택한다. `a=clip((abs(DP-DV)-0.5)/1.5,0,1)`이다. 이 선택은 **미터 규모 불일치에 직접 반응하는 비교 후보**를 시험하기 위한 탐색 결정이며, prior/영상의 정확성·노이즈·정합 허용오차를 보정한 값이 아니다. 0.5m 평가지표와 숫자가 같아도 학습 문턱을 GT에서 정한 것이 아니다.

입력 감사 `preflight/input_audit_v2/input_audit_v2.json`은 camera-Z 미터와 기존 bilinear resize를 확인했다. prior의 Open3D는 u+.5/v+.5이고 DA3 unprojection은 정수u/v라서 **엄밀히 동일한 subpixel ray를 입증하지 못했다**. 이번 대조는 기존 calibration에서 같은 pixel index를 대응시키는 정의이며 이 반픽셀 이산화 차이를 상속한다. 이는 부드러운 면의 수십m 차이를 설명하지는 못하지만 경계에서 영향을 줄 수 있다. 입력을 바꾸지 않고 기존 대조와 이 한계를 공유한다. 같은 grid가 동일 가시 표면을 보장하지 않으며 큰 차이를 DA3 척도 오류라고 판정할 근거도 없다.

전체 공통 유효 train 픽셀의 a=1 비율은 P1 69.38%, P2 62.38%, P3 47.26%, 평균 a는 .7582/.7053/.5626이다. 기존 균등 view 표본의 pooled a=1은 78.339%다. 따라서 이번 설정은 상당 부분 포화되며, 학습에서 실제 source별 유효 수·배율 평균을 별도로 기록해야 한다. prior 결손이 많은 전체 영상 유효 영역에서는 영상 배율 평균이 .9775/.9554/.9013으로 더 높다. view 표본과 전체 pixel 집계를 혼용하지 않는다.

Q50/Q90의 약30.83/138.23m는 수m 차이의 영상 depth 감독을 0으로 만드는 다른 정책이므로 준비 이력으로 남긴다. .5/5m와 입력 Q10/Q25(.532/2.750m)는 감사에서 비교한 대안이며 추가 실험·최적 문턱 주장이 아니다. 이 18개에서는 문턱을 재조정하지 않는다.

## 실제 loss와 고정 제어

각 source의 finite positive target, finite prediction에 native mask를 적용한다. 유한 음수 prediction은 오차로 벌점을 준다. 둘 다 유효하면 `(bP,bV)=(1-a,a)`, 하나만 유효하면 해당 배율1, 둘 다 없으면0이다. 결손을 차이값으로 치환하지 않는다.

`LD=lambdaP*sum(bP*abs(pred-DP))/nP + lambdaV(t)*sum(bV*abs(pred-DV))/nV`.

source별 **원래 valid pixel 수**가 분모이며 배율 합으로 재정규화하지 않는다. 빈 source 항은0이다. confidence와 scale-invariant 옵션은 비활성이다. target과 a는 detach하고 prediction gradient는 유지한다. RGB·기존 기하 regularizer·depth 정의·renderer·해상도·iteration·densification 설정은 대응 기존 run과 같다. 원 raw depth loss를 controller에 전달한다. 실제 lambdaV(t)는 결과 궤적에 반응하므로 G/LC 사이에 다를 수 있다.

3지역 × lambdaP(.005/.0005/0) × native/release = 새18개, 각1회. 각8001–30000의22000step, 합396000step이다. lambdaP=0에도 a·Anchor·보호 이력에 prior가 남으므로 image-only라 부르지 않는다. native/release는 기존 보호 유지·묶음 해제를 각각 그대로 사용한다. 학습 flags는 기존 invocation과 비교하여 complete 복원·저장 instrumentation 외 차이를 거부한다.

## 재사용과 실제 결박

정확한 Anchor 경로는 [재사용 근거](RESOURCE_AND_REUSE_REVIEW_ko_v1.md)의 §2를 따른다. 기존18개는 `parent/runs_allocator_v2/{P1,P2,P3}/{D...}`의 complete30000을 재사용한다. 입력 manifest 전 파일과 Anchor checkpoint, 기존 최종 checkpoint/PLY를 다시 해시 검사하고 receipt·runtime/source·명령 일치를 기록한다. P1 Anchor만 원 `runs/` 경로인 예외를 유지한다.

새 payload는 기존 local task 아래 `contracts/main_v2/`, `source_v2/`, `main_v2/preflight/`, `main_v2/runs/`, `main_v2/evaluation/`, `main_v2/queue/`에만 쓴다. input binding은 원 준비 binding을 참조하되 덮어쓰지 않는다. Gate는 P2 native/release의 같은 v2 문턱 GPU1step probe와 CPU 검증 후 고정한다. 실행마다 gate/config/binding/source/실행 helper의 hash를 확인하고 trace에도 config/binding hash를 남긴다.

## 평가 고정값과 해석

기존 512 TSDF raw가 주 비교이고 동일 post512는 보조다. 이미 동일 설정으로 추출·평가된 Anchor/G를 재사용한다. 고정 parent Anchor raw512 ROI, 원 reference ID·순서·0.1m voxel·원점0·0.1m surface sampling·seed0·0.5m XY cell을 유지한다. CRS는 EPSG:25832 working과 기존 UAS EPSG:32632 header·world shift·z bridge·datum 미검증 상태를 함께 보존한다. 새 참조 정합은 없다.

거리 문턱 `.1/.2/.25/.5/1/2m` 전체와 주 paired `.5m`를 보고한다. accuracy는 예측 sample→관측 reference point, completeness는 고정 reference→triangle 거리다. 둘을 별도로 제시하고 피복 밖 오차를 확정하지 않는다. 결손 prediction은 참조가 있는 위치에서 실패로 계산한다. 1e-6m는 수치 동률 표시일 뿐 의미 있는 개선의 경계가 아니다.

같은 reference point와 XY cell에서 Anchor→G, Anchor→LC, G→LC 수정·손상을 함께 기록하고, 기존 수정의 LC 유지/파괴·기존 손상의 LC 회복을 3자 전이표로 분리한다. 고정 카메라 원사진·Anchor/G/LC와 동일0.5m폭 단면을 제공한다. mesh 주 비교와 renderer 결과를 구분한다.

prior triangle proximity<.5m와 기존 strict DA3 world-Z residual<=.5m 조합은 **평가 proxy 층**이다. strict 미지원, ±1m target error, 3view 이상이면서1m초과 spread를 따로 보고한다. 이를 원사진 관측 가능 O/X나 시간적 정오로 대체하지 않는다. 원사진에서 관측 가능하지만 DA3가 틀린 사례는 직접 사진·camera evidence를 검토하여 별도로 설명한다. 참조·평가 label은 학습 컨테이너에 연결하지 않는다.

외관은 같은 frozen test cameras의 native PSNR/SSIM/LPIPS와 고정 prism bbox PSNR을 비교한다. ROI SSIM/LPIPS가 계산되지 않으면 미측정으로 표기한다. native LPIPS의 VGG/[0,1] 관례를 명시한다. G/LC raw/weighted loss·phase·lambdaV(t)·source 평균배율·Gaussian 수·보호 수·wall/RAM/VRAM·추출/평가 비용을 구분한다.

## 자원·실패·검증

고정 Docker image ID `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, native allocator `backend:native,max_split_size_mb:128`, CPU8/RAM32GiB/GPU1 per job, 최대2학습. swap은 없고 `--memory-swap 32g`로 추가 swap을 요청하지 않는다. 새 학습1개는 host available38GiB, 두 동시 시작은70GiB를 요구하여6GiB headroom을 둔다. 부족하면 같은 paired scope를 순차 실행한다. GPU idle used<1800MiB/util<10%, 외부 disk100GiB 이상을 확인한다. 최초512GiB를 저장 계획으로 잡고 서비스·브라우저·기존 작업을 종료하지 않는다.

순서는 .005 여섯개→.0005 여섯개→0 여섯개, 각 P2→P1→P3 native/release 쌍이다. 각 쌍 완료 후 추출·외관 지표를 실행하며 추출과 학습을 겹치지 않는다. 과거17–20시간 학습 준비 추정은 보장값이 아니며 직렬화·실측으로 갱신한다. 본 실험 중간 결과를 제시하되 결과에 따라 조건을 빼지 않는다.

검증은 source native loss/disabled/gradient/결손/분모/controller raw 값, complete model/optimizer/RNG/camera/protection 복원, source/config 변조 거부, command 동일성, 합성 geometry/빈 표면/전이계수·GT 경계와 실제 캐시 재사용을 포함한다. 실패는 원 경로와 receipt를 남기고 issue 문서에 기록한다. 재시도·구현 변경은 별도 명시된 revision/attempt로만 하며 학습량·해상도·정책을 숨겨 줄이지 않는다.

## 네 기여와 허용 결론

- 문제 차별성: 같은 부위의 재사용 가능한 구조 보존과 필요한 최신 수정이 충돌하는 조건의 실증. ALS 사용 자체를 독자성으로 삼지 않는다.
- 원인 설명: 전역 제어의 배분 한계·보호·target 오류·가시성·controller·추출이 경쟁 설명이다. 성공만으로 하나를 확정하지 않는다.
- 방법 신규성: 간단한 불일치 상보 규칙의 신규성은 미확정이다. 기존법의 충분성과 새 방법 악화도 인정한다.
- 검증 기여: 같은 입력/Anchor/ROI에서 성공·악화·수정·손상·피복·계산량을 재현 가능한 개발 비교로 남긴다.

첫18개에 평균배율 전역 대조·controller replay·반복은 없다. 공간 배분 고유 효과, 작은 차이의 재현성, 모집단 일반화, 공식 PASS나 학위 충분성은 확정하지 않는다. 모든 기술 결과의 `scientific_verdict`는 null이다.
