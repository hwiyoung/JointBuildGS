# 2DGS — 표면 표현과 내부 기하 제약

검토일 2026-09-09 · `scientific_verdict: null` · 역할: 영상 기반 표면 복원의 직접 기준선 후보 및 표현 참고.

## 근거와 버전

- Huang, Yu, Chen, Geiger, Gao, *2D Gaussian Splatting for Geometrically Accurate Radiance Fields*, SIGGRAPH 2024. [프로젝트](https://surfsplatting.github.io/), [전문 arXiv 2403.17888v1](https://arxiv.org/html/2403.17888v1).
- 근거 위치: §4·Fig.2–3 ray–splat 및 표현, §5 식13–14 감독, §6 Tables 1–5 실험·추출 ablation, §7 한계. 본 카드의 번호는 v1 HTML 기준이며 PDF 페이지 대응은 미확인이다.
- [공식 코드](https://github.com/hbb1/2d-gaussian-splatting/tree/f3e3b9fa67bbd1c75e05167ff37391d8dab2a678), HEAD `f3e3b9fa67bbd1c75e05167ff37391d8dab2a678`. [train.py:73](https://github.com/hbb1/2d-gaussian-splatting/blob/f3e3b9fa67bbd1c75e05167ff37391d8dab2a678/train.py#L73)–140의 손실·density control을 직접 확인. 논문 당시 실행 바이트와의 동일성은 미확인이다.

## 1. 문제와 입출력

[원문 사실] RGB 다중뷰에서 렌더 장면과 더 정확한 표면을 얻는다. 사진은 관측, SfM점·pose는 파생 입력이다. 외부 기하와 사전학습 normal은 필수가 아니다. oriented 2D Gaussian을 최적화하고 depth를 TSDF 통합하여 mesh를 만든다. 정합된 정적 영상·표면 가시성과 불투명 표면 모델을 가정한다.

## 2. 기여의 위치

| 요소 | 판정과 내용 |
|---|---|
| 입력·전처리 | 기존 사용: 보정 영상·SfM 초기점 |
| 좌표·카메라·정합 | 기존 사용: 카메라; 새 pose 추정 없음 |
| 표현 | 새: oriented planar Gaussian 구성 |
| 관측모형·렌더링 | 새: perspective-accurate ray–splat; tile·alpha blending은 기존 활용 |
| 증거 사용·감독·제약 | 새 적용: depth distortion·normal consistency; RGB loss 기존 사용 |
| 초기화·최적화·모델 변경 | 기존 사용/적용: gradient 최적화와 3DGS 계열 밀도 제어 |
| 추출·후처리 | 기존 사용 및 선택 검증: median depth→TSDF, Poisson 대조 |

## 3. 고정과 수정, 정보의 갱신

[원문 사실] 위치·orientation·2축 scale·opacity·색과 primitive 수를 수정한다. pose와 RGB는 고정이며 normal consistency의 비교 대상은 현재 장면이 만드는 normal/depth다. 렌더→기하/RGB 손실→Gaussian 수정의 피드백이 있다. RGB·SfM 파일은 재사용하고 depth/normal은 갱신한다(§5). 공식 train에서 normal 손실은 iteration>7000에 켜지며 densification/pruning이 별도로 수행된다.

[우리 추론] 평면 primitive의 자유도 제한은 표면 설명을 단순화한다. 외부 prior 보존의 hard constraint는 아니다. normal 제약을 풀면 세부 자유도와 잡음이 함께 증가할 수 있고, pose까지 풀면 카메라–형상 식별성을 새로 검증해야 한다. 최종 TSDF mesh가 training으로 되돌아가는 경로는 확인한 원방법에 없다.

## 4. 실제 검증 범위

[원문 사실] DTU 15장면·Tanks and Temples 6장면의 표면, Mip-NeRF360의 NVS 및 계산 성능을 평가한다. 부록에는 synthetic NVS도 있다. Table 4의 Deep Blending은 비교 방법이다. §6의 ablation은 두 regularizer와 median/expected depth, TSDF/Poisson 차이를 분리한다. §7은 영상과 기하 사이의 trade-off를 인정한다.

[미평가] 기존 자산의 유효 부분별 보존율, 항공영상 관측오류와 낡은 prior가 함께 있는 조건, 시간적 현재성. 데이터별 exact split IDs 및 지금 받은 코드의 paper-run 재현은 본 감사에서 미확인이다. smooth surface 또는 좋은 NVS를 건축 세부 복원으로 환산하지 않는다.

## 5. 남은 오류와 전달 경로

[저자 해석·관측된 한계] §7은 반투명 표면, texture 위주 densification의 작은 기하 누락, regularization의 과평활화를 명시한다. Appendix C Fig.12는 glass와 밝은 표면의 구멍을 보인다. [원문 사실] Table 5는 추출 방법만 바꿔도 기하 평가가 달라짐을 보여준다.

[우리 추론] 사진의 정보 부족→RGB 중심 primitive 배치→법선/깊이 제약→median depth 및 TSDF 표면에서 세부 소실이 가능한 경로다. 각 항의 원인 기여는 모든 장면에서 분리되지 않았다. voxel·truncation, pose, 반사, 원영상 해상도도 대안이다. prior 시기 오류는 범위 밖이다.

## 6. 공백 후보와 기각 조건

[우리 추론] 구조 보존과 관측 세부의 동시 개선은 AGS-Mesh·GeoGS 및 기존 mesh 정제가 가까운 대안이다. 최소 비교는 같은 초기 기하·영상에서 2DGS와 기존 depth/normal 감독, adaptive 감독을 맞추고 추출만 바꾼 별도 대비를 둔다. 최종 surface와 GS NVS를 각각 평가한다. 추출 설정이나 기존 감독 조합으로 잔여 오류가 사라지면 새 표현/재판단 기여를 기각한다. 이 카드의 공식 fork는 문헌 확인 대상이며 프로젝트 구현 선택을 바꾸지 않는다.
