# CL-Splats — 국소 장면 갱신과 유효 영역 보존

- 상태: 문헌 감사, 2026-09-09. `scientific_verdict: null`.
- 식별: Ackermann et al., *CL-Splats: Continual Learning of Gaussian Splatting with Local Optimization*, ICCV 2025. 확인 버전: arXiv **2506.21117v2, 2025-10-15**, 본문·보충자료 합본 19쪽. 아래 페이지는 PDF의 1부터 센 페이지다.
- 원문: [PDF](https://arxiv.org/pdf/2506.21117v2), [검색 가능한 전문](https://arxiv.org/html/2506.21117v2), [저자 프로젝트](https://cl-splats.github.io/).
- 공식 코드: [jan-ackermann/cl-splats](https://github.com/jan-ackermann/cl-splats/tree/587fffc207f9c7cbb348f35e6d1d223d007eab69), 확인 commit `587fffc207f9c7cbb348f35e6d1d223d007eab69` (2026-06-12). **공개 재구현과 원논문 구현을 구분한다.** README의 Disclaimer는 원논문과 차이가 있을 수 있다고 밝힌다. 이번에는 소스만 읽었고 재현 실행은 하지 않았다.
- 확인 PDF SHA-256: `1cc33307ea559fdc310db34edfce80d51bcdc94ff92e49fa6ab2c8664e6fb000`. 원문 파일은 임시 열람용이며 저장소에 재배포하지 않았다.
- 비교 지위: 기존 **색 있는 3DGS**와 신규 영상이라는 조건에서 직접 갱신 비교 후보. 무색 ALS/LoD 자산을 직접 받는 방법으로 분류하지 않는다.

## 1. 문제와 입출력

기존 장면의 국소 변경을 적은 신규 영상으로 반영하며 미관측·미변화 영역과 시기별 이력을 보존한다. 실제 관측은 신규 RGB, 파생 입력은 카메라 및 기존 3DGS, 사전학습 정보는 DINOv2 특징이다. 출력은 갱신 GS·새 시점 영상·변경 영역·복원 가능한 이력이다. 기존 GS는 이전 영상의 압축된 추정이며 외부 독립 측정이 아니다. [원문 §3, pp.2–4; §5, p.8](https://arxiv.org/pdf/2506.21117v2)

적용 가정은 국소 변경과 변경부 관측이다. 신규 자세는 기존 좌표계에 있어야 한다. 실험의 실영상 COLMAP은 **모든 시기 영상을 함께** 이용했다. 과거 원영상 없는 GS 갱신 설정과, 실험 카메라 복구에 과거 영상이 관여한 사실은 별개다. 합성에는 Blender 자세를 사용한다. 전역 조명 변화는 저자가 범위의 한계로 명시한다. [원문 §7 Camera Pose Estimation, pp.12–13; §6 Limitations, p.8](https://arxiv.org/pdf/2506.21117v2)

## 2. 기여의 위치

`새`는 논문이 제안한 요소라는 뜻이며 세계 최초 판정이 아니다.

| 요소 | 분류 | 확인 내용 |
|---|---|---|
| 입력·전처리 | 새+사용 | 렌더–실영상 DINOv2 차이·팽창 마스크 조합; DINOv2는 기존 모델 |
| 좌표·카메라·정합 | 사용 | COLMAP/Blender 자세; GS loss에서 자세를 되돌려 고치는 경로는 확인되지 않음 |
| 표현 | 사용+새 | 표준 3DGS; 변경 Gaussian과 인덱스에 의한 이력 기록 |
| 관측모형·렌더링 | 사용+새 | 3DGS 합성; 원논문은 국소 Gaussian의 전체 렌더와 같은 gradient를 주는 커널 |
| 증거 사용·감독·제약 | 새+사용 | 다중뷰 majority vote, 배경 고정, 구 합집합 제약; 사진 손실은 기존 방식 |
| 초기화·최적화·모델 변경 | 새+사용 | 새 물체 sampling, 국소 최적화·영역 밖 prune; GS densification 사용 |
| 추출·후처리 | 새/미확인 | 변경 병합·과거 상태 복구; 측량용 surface/mesh 추출은 미확인 |

근거: [원문 §3, Fig.2–3, Algorithm 1; §5·§7·§11](https://arxiv.org/html/2506.21117v2). 현재 공개 코드는 [trainer.py](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/clsplats/trainer.py#L299)에서 **Depth-Anything V2 lifting, gsplat rasterization, inactive gradient/optimizer-state 고정**을 사용한다. [lifter 구현](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/clsplats/lifter/depth_anything_lifter.py#L22)은 렌더 깊이로 단안 상대깊이를 정렬한다. 이 추가 사전학습 깊이를 원논문 입력으로 소급하지 않는다.

## 3. 무엇을 고정하고 무엇을 수정하는가

| 상태 | 변수·중간 결과 | 고정 이유와 풀 때의 예상 영향 |
|---|---|---|
| 추정·수정 | 변경 Gaussian의 위치·크기·회전·opacity·색, 개수 | 변경을 표현; 완전한 외부기하 오차 보정 모델과는 다름 |
| 고정 | 비변경 Gaussian, 카메라, DINO backbone, 초기 변경 근거 | 희소 관측에서 기존 영역 손실 방지; 풀면 재관측 없는 영역 drift 위험 |
| 강한 제약 | 허용 구 영역 밖 Gaussian prune | 국소성 확보; 영역 과소검출이면 필요한 복원이 막힐 수 있음 |
| 반복 갱신 | 투영 위치·계산 tile, 활성 Gaussian과 분할/삭제 상태 | 모델이 바뀌므로 계산 마스크도 바뀜 |

증거 흐름: `기존 GS → 현재 자세의 렌더 + 신규 RGB → DINO 변화마스크 → 3D 투표·sampling → 제한영역 최적화 ↔ 재투영 계산마스크 → 갱신 GS`. 초기 특징·판정·경계를 매 반복 다시 추정하는 것으로 확인되지는 않는다. 그러나 후단 Gaussian이 재투영 마스크를 바꾸므로 **완전한 단방향 방법도 아니다**. 배경을 렌더에 포함한 채 그 변수만 고정한다. [원문 §3.3·§7, Fig.3](https://arxiv.org/html/2506.21117v2)

우리 해석: 상태 보존은 우수한 손상통제 비교군이지만, 고정된 영역이 현재도 옳다는 새로운 증명은 아니다. 반복 시 재사용되는 초기 변경 근거와 새로 계산되는 가시성·gradient를 분리해야 한다.

## 4. 실제 검증 범위

| 항목 | 확인 범위 |
|---|---|
| 데이터·분할 | 자체 합성 3단계 복잡도, 실내외 실사 5장면, CL-NeRF 자료. 합성 초기 200장 및 변경 train/test 25장 기술; 실사 초기 100–200장·변경 10–30장. 개별 실사 평가 membership은 원문만으로 미확인 |
| 비교·ablation | 3DGS, 2D mask loss, GaussianEditor, CLNeRF/CL-NeRF; 배경 고정·투표·경계 primitive·커널 분리 |
| 성공 | Table 5: 배경 고정 제거 20.773 dB, full 40.833 dB; 커널 제거 40.812 dB/8분, full 40.833 dB/5분. 배경 보호와 계산 절약을 분리해 읽을 수 있음 |
| 범위 | PSNR/SSIM/LPIPS/FPS, 마스크 recall/precision, 이력 저장. 표면 거리·완전성·국소 기하 악화·항공영상의 현재성 검정은 미평가 |

근거: [원문 §4, Tables 2–5; §8, pp.13–15](https://arxiv.org/html/2506.21117v2). Table 5의 8→5분과 본문의 평균 60% 절약은 서로 다른 집계이므로 같은 수치로 환산하지 않는다. 현재 공개 README는 COLMAP 매8번째 holdout과 Blender `transforms_test.json`을 명시하지만 이것을 원논문 membership으로 동일시하지 않는다. [고정 코드 README](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/README.md)

## 5. 남은 오류와 전달 경로

| 구분 | 조건·잔여 오류 | 전달 경로·대안 원인 |
|---|---|---|
| 원문 사실·관측된 실패 | 매우 얇은 구조에서 변경영역 과소추정, Fig.12 갱신 잔여물 | 특징 검출→허용영역→수정 불가. 저자 해석은 낮은 recall; 관측수·초기 GS 품질 기여는 별도 분리되지 않음 |
| 저자 해석·범위 밖 | 전역 조명 변화 | 국소변화 가정 불성립; 전역 외관모델 결합이 가까운 해결책 |
| 우리 추론·미평가 | 기존 GS 자체의 체계적 기하오차가 비변화로 고정될 가능성 | 렌더 특징은 유사해도 metric geometry는 틀릴 수 있음; 이 논문의 관측된 실패로 주장하지 않음 |
| 미확인 | 실제 ALS→GS 변환 뒤 손상·복원 성능 | 입력 계보가 다르므로 이 결과로 판정 불가 |

근거: [원문 §9.2, p.14; Fig.12, p.17](https://arxiv.org/pdf/2506.21117v2). Fig.12를 실제 PDF 이미지로도 확인했다. 정합오차 스트레스 부재는 검증 부족이지 정합오차에 반드시 실패한다는 사실이 아니다.

## 6. 연구 공백 후보

이미 해결된 부분은 **국소 변화 반영·미관측부 보존·후단 모델에 따른 계산 마스크 갱신·이력 복구**다. 이를 신규 기능으로 다시 주장할 수 없다.

후보는 외관 변화, 초기기하 오류, 관측부족이 공존할 때 어떤 수정 자유도가 metric geometry를 개선하고 유효 구조를 해치는지의 식별이다. 현재 증거는 **적용 조건 차이와 검증 부족**에 강하고, 새로운 판정/공동법이 필요하다는 방법론 결론에는 약하다.

가까운 해결책은 GaussianUpdate의 전역 외관 처리, 기존 강건 정합, CL의 배경 고정 및 NeuRIS식 사진검정의 조합이다. 최소 비교는 동일 영상·초기자산에서 무갱신, 정합만, CL 원설정, 외관보정+CL, 강한 순차법이며, 재판정은 그 뒤 후보로 둔다. 새 학습 실행은 이번 범위 밖이다.

기각 조건: 조합이 같은 관측량·계산예산에서 국소 기하 개선/악화 양쪽과 현재성 오류를 충분히 통제하면 추가 판단모듈 필요성을 접는다. Oracle도 최선 고정 선택을 이기지 못하면 국소 선택 연구를 축소한다. 렌더만 개선되고 독립 표면/세부 점수가 개선되지 않으면 기하복원 주장을 기각한다.
