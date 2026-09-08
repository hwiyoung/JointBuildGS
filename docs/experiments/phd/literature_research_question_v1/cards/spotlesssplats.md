# SpotLessSplats — 관측 기각과 모델 갱신의 상호작용

검토일 2026-09-09 · `scientific_verdict: null` · 역할: transient 강건화·감독 갱신 구성요소. 최신 형상의 존치 판단과 목표가 다르다.

## 근거와 버전

- Sabour, Goli et al., *SpotLessSplats: Ignoring Distractors in 3D Gaussian Splatting*. [arXiv 2406.20055v2, 2024-07-29](https://arxiv.org/html/2406.20055v2), [PDF](https://arxiv.org/pdf/2406.20055v2), [저자 페이지](https://spotlesssplats.github.io/).
- §4.1–4.2: clustering·MLP·warm-up·UBP, §5: RobustNeRF/On-the-go 및 ablation, §6: 한계. HTML과 PDF 그림 번호가 다르게 표시되는 항목이 있어 아래 Fig.8–11은 **HTML locator**다. PDF 기준 §4는 pp.4–6이며 개별 결과 그림의 PDF 페이지 대응은 미확인이다.
- [공식 구현](https://github.com/lilygoli/SpotLessSplats/tree/0caae3cc45bb1fddf86bd47e4a521888f5c49889), HEAD `0caae3cc45bb1fddf86bd47e4a521888f5c49889`. [examples/spotless_trainer.py:600](https://github.com/lilygoli/SpotLessSplats/blob/0caae3cc45bb1fddf86bd47e4a521888f5c49889/examples/spotless_trainer.py#L600)–691 mask/손실·histogram, 757–770 pruning을 직접 읽었다. gsplat 기반 공개판이며 논문 당시 실행과 전체 동일성은 미확인이다.

## 1. 문제와 입출력

[원문 사실] 움직이는 방해물이 있는 여러 RGB에서 정적 배경 Gaussian 장면을 복원한다. RGB는 관측, pose/SfM은 파생, Stable Diffusion feature는 사전학습 정보를 사용하는 고정 특징이다. 기존 ALS/mesh는 없다. 지속되는 배경을 관측하고 transient를 식별할 수 있어야 하며, 장기 변화 건물을 최신 상태로 유지하는 과제가 아니다(§2–4).

## 2. 기여의 위치

| 요소 | 판정과 내용 |
|---|---|
| 입력·전처리 | 기존 feature 사용+새 clustering 구성 |
| 좌표·카메라·정합 | 기존 사용; 원문 기여로 pose 개선 미확인 |
| 표현 | 기존 사용: 3DGS, 새 보조 MLP classifier; appearance latent/MLP 결합 |
| 관측모형·렌더링 | 기존 GS 사용; UBP 계산을 위한 기여량 활용 |
| 증거 사용·감독·제약 | 새: semantic cluster/MLP mask, robust residual 결합 |
| 초기화·최적화·모델 변경 | 새: warm-up·sampling·global residual 통계·utilization pruning |
| 추출·후처리 | 미확인: 검증된 최종 mesh 복원 경로 |

## 3. 고정과 수정, 정보의 갱신

[원문 사실] 특징/공간 cluster는 전처리 고정이고 inlier label은 바뀐다. SLS-mlp는 classifier와 Gaussian을 번갈아 최적화한다. 렌더 잔차→분위수 label→mask/MLP→영상 손실→GS→새 잔차의 폐루프다. 잔차를 전혀 쓰지 않는 semantic-only 검정이 아니다. Bernoulli sampling과 warm-up은 초기 오기각을 줄이고 residual histogram은 여러 view의 분포를 누적한다(§4).

§4.2.4는 view별 64D appearance latent와 MLP도 학습하여 SH에 affine 보정을 적용한다. 이 학습 정보와 고정된 Stable Diffusion feature를 구분한다. UBP는 masked rendered color의 projected Gaussian position에 대한 미분 제곱을 여러 view에 누적한 활용도다(§4.2.3 식11). loss gradient나 보정된 확률 uncertainty와 동일하지 않다.

[코드 확인] mask는 RGB loss에서 detach하고 별도 classifier loss를 사용한다. 현재 code에는 optional pose optimizer도 있으나 존재만으로 논문 기본 실험의 pose 재추정을 주장하지 않는다. [우리 추론] 고정 feature를 풀면 semantic prior와 현재 잔차가 함께 변해 감독 퇴화 가능성이 달라진다. 모델 내 검증은 새 독립 관측의 취득이 아니다.

## 4. 실제 검증 범위

[원문 사실] RobustNeRF·NeRF On-the-go의 clutter training/clean test와 clean 3DGS 대조를 이용한다. PSNR·SSIM·LPIPS, Gaussian 수·시간, clustering/MLP·UBP·warm-up ablation을 보고한다(§5). 공개 코드의 `clutter`/`extra` prefix도 확인했다. 계산 압축은 clean 장면도 평가한다.

§5는 Crab(1)의 train/test가 같은 camera views인 문제와 수정된 Crab(2)를 구분한다. 본문 baseline 비교와 ablation/부록의 사용판이 다르므로 clean test 전체를 독립 미사용 시점으로 간주하지 않는다.

[미평가] 독립 표면 참조의 정확도·완전성, 건물 구조 비악화와 실제 영구 변화 현재성. clean test 영상과 clean training 상한은 역할이 다르다. distractor 억제 성과를 geospatial surface accuracy로 환산하지 않는다.

## 5. 남은 오류와 전달 경로

[원문 사실·관측된 실패/저자 해석] §6: 가까이 있는 같은 semantic class를 서로 구분하지 못하거나 저해상도 feature가 가는 구조를 놓칠 수 있다. 과도한 UBP threshold는 드물게 관측된 유효 장면 일부도 제거한다(HTML Fig.8–9). 즉 낮은 활용도→삭제가 항상 유효하지 않음을 이미 논의한다.

[우리 추론] feature 혼동→mask 과기각→gradient 결손→실제 구조 누락이 전달 경로 후보다. 가림·초기화 부족·밝기 변화도 같은 증상을 만들 수 있다. 새 건물을 transient로 버릴 가능성은 우리 적용 추론이며 논문의 영구 건물변화 실패 실험이 아니다.

## 6. 공백 후보와 기각 조건

[우리 추론] 감독과 재구성의 반복, 초기 자기확증 완화는 새로움으로 주장할 수 없다. 비교 질문은 드문 유효 관측과 실제 방해물을 어떤 증거에서 구분하는가이다. SLS의 원 warm-up/UBP, robust loss, CL-Splats/GaussianUpdate의 영구 갱신을 각자의 native 과제와 공통 확장 조건으로 나눠 비교한다. 기존 threshold·sampling·갱신 모델 조합이 구조 보존/현재 복원을 충족하면 새 명시적 판단 모듈의 필요성을 기각한다.
