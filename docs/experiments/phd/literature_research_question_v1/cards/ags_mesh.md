# AGS-Mesh — 잡음 깊이·법선 감독과 추출의 분리

검토일 2026-09-09 · `scientific_verdict: null` · 역할: 구조·세부 복원의 구성요소 경쟁 방법. 항공 ALS와 native 입력이 다르다.

## 근거와 버전

- Ren et al., *AGS-Mesh: Adaptive Gaussian Splatting and Meshing with Geometric Priors for Indoor Room Reconstruction Using Smartphones*, 3DV 2025. 검토판 [arXiv 2411.19271v2, 2024-12-16](https://arxiv.org/html/2411.19271v2), [PDF](https://arxiv.org/pdf/2411.19271v2).
- §3–4·Fig.3·식4–10(PDF pp.3–5): 입력과 DNC/ANR. §4.4(pp.5–6): meshing. Tables 1–2(p.7), Tables 3–4 및 Fig.5(p.8): 성능·ablation·악화 시각화. Appendix A: 설정, E: 한계.
- [공식 구현](https://github.com/XuqianRen/AGS_Mesh/tree/93fda851a20cf0bd5fce642c46da0c83c637165e), HEAD `93fda851a20cf0bd5fce642c46da0c83c637165e`. [train.py:127](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py#L127)–181과 [depth_normal_consistency.py](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/depth_normal_consistency.py#L41)를 직접 확인. README는 DN-Splatter 통합판도 연결한다. 두 구현을 같은 바이트로 취급하지 않는다.

## 1. 문제와 입출력

[원문 사실] 실내 smartphone RGB와 sensor depth로 Gaussian 장면·mesh를 복원한다. 센서 깊이는 측정 이후 기기 처리된 관측이며, depth normal은 파생 기하, Omnidata normal은 사전학습 정보가 결합된 영상 추정이다. 기존 시기의 ALS/LoD는 입력하지 않는다. 낮은 depth 해상도·원거리·가장자리 오류를 인정하며 RGB-depth 정합·카메라를 제공받는다(§3–4).

## 2. 기여의 위치

| 요소 | 판정과 내용 |
|---|---|
| 입력·전처리 | 새: DNC 필터 구성; sensor/mono normal 생성은 기존 활용 |
| 좌표·카메라·정합 | 기존 사용: 제공/전처리된 camera·좌표 |
| 표현 | 기존 사용: 2DGS·Splatfacto |
| 관측모형·렌더링 | 기존 사용: GS RGB/depth/normal renderer |
| 증거 사용·감독·제약 | 새: DNC와 ANR의 선택적 depth/normal 감독 |
| 초기화·최적화·모델 변경 | 새 일정/감독 결합; Gaussian 최적화는 기존 기반 |
| 추출·후처리 | 새 결합: depth-adaptive TSDF·normal 가중·IsoOctree; octree 자체는 기존 |

## 3. 고정과 수정, 정보의 갱신

[원문 사실·코드 확인] raw depth와 predicted normal을 다시 측정/학습하지 않는다. **DNC는 depth-normal과 pseudo-normal 비교로 만든 전처리 confidence**, ANR는 현재 rendered normal과 pseudo-normal 비교로 갱신되는 감독 선택이다. train.py에서 depth confidence는 camera에서 읽고, normal confidence는 현 반복에서 계산한다. Gaussian 위치·방향·크기·색·opacity·개수는 수정된다. mask 이전/이후 일정도 구분된다.

[우리 추론] 고정 prior를 쓰는 이유는 센서·추정기 산출물을 supervision으로 이용하기 위해서다. ANR가 supervisor의 영향은 바꾸지만 원 normal estimator까지 학습하지 않는다. 그 자유도를 풀면 prior 자체가 장면의 오류에 적응할 수도 있다. 후단→감독 피드백은 있으나 DNC 원자료·pose 재추정과 최종 mesh→GS 피드백은 확인되지 않는다.

## 4. 실제 검증 범위

[원문 사실] MuSHRoom 6실내와 ScanNet++에서 기하·NVS를 검증한다. MuSHRoom은 매 10번째 frame 평가와 다른 카메라 trajectory 평가를 구분한다. reference mesh, accuracy/completion/Chamfer/normal/F1@5cm와 PSNR·SSIM·LPIPS를 사용한다. Tables 1–4는 DN-Splatter·2DGS 등의 비교 및 depth/normal/DNC/ANR/추출 효과를 나눈다. Gaussian 수와 추출 부담도 다룬다.

[우리 분석] Table 3은 F1 개선과 normal consistency 악화가 함께 가능함을 보여준다. 모든 품질축의 동시 개선으로 읽지 않는다. 실제 건물 시기변화·오정합 ALS·구조별 비악화율은 미평가이며 실내 성능을 항공조건으로 옮길 수 없다.

Table 3 ablation의 분모는 3개 장면 평균이며 Table 1–2의 6개 장면과 다르다. 이 세 장면의 exact IDs는 이번 감사에서 미확인이다.

## 5. 남은 오류와 전달 경로

[저자 해석] Appendix E: IsoOctree는 mesh를 간결하고 매끈하게 하지만 전체 기하 품질을 일관되게 올리지 않는다. [원문 사실·관측된 악화] Fig.5의 두 방법 영상 오차 차이 지도에는 개선·악화 화소가 모두 있다.

[우리 추론] 두 normal의 일치는 절대 높이 검정이 아니므로 평행한 잘못된 면이나 상관된 prior 오류를 놓칠 수 있다. 잘못된 GS normal→ANR supervisor 기각→부정확한 normal 유지의 가능성은 있으나 **실패가 확인된 사실은 아니다**. 다른 원인은 센서 registration, normal domain gap, TSDF 설정이다. 외부 prior 현재성은 범위 밖이다.

## 6. 공백 후보와 기각 조건

[우리 추론] “저품질 prior를 최적화 중 완화한다”는 이미 해결된 기능이다. 후보는 위치/경계 오류가 normal 일치 아래 남는 조건의 식별과 최종 surface 영향이다. 같은 증거에서 DNC+ANR, VCR-GauS, NeuRIS식 photo gate, 고정 confidence 및 제안 규칙을 비교한다. 동일 모델의 TSDF/IsoOctree를 별도 대비해 추출 이득을 분리한다. 기존 게이트와 추출 조합으로 구조 손상·세부 오류가 해소되면 새 감독 규칙의 필요성을 기각한다.
