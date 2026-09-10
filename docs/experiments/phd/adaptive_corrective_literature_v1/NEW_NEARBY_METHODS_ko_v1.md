# 추가 탐색: 부분 기하 prior와 영상 기하 confidence

- 검토일: 2026-09-10. 원문·공식 소스 읽기만 수행. `scientific_verdict: null`.
- `새`는 논문이 제안한 구성이라는 뜻이며 독립적인 최초성 판정은 아니다.
- 두 방법의 입력·평가 계약을 그대로 우리 무색 기구축 자산+현재 항공영상 조건의 직접 비교라고 부르지 않는다.

## 1. EnerGS: Energy-Based Gaussian Splatting with Partial Geometric Priors

버전: [arXiv 2604.26238v1](https://arxiv.org/html/2604.26238v1), §3.1–3.5, §4.1 Assumptions 1–3, §5.1, Tables 1–2, Fig.2, Appendix C–D. [공식 코드](https://github.com/ucla-mobility/EnerGS/tree/a222ed59b05a56eecf7b7199e02eb80bcb288775), pin `a222ed59b05a56eecf7b7199e02eb80bcb288775`.

1. **문제·입출력·가정 [원문]:** 부분 LiDAR+RGB→GS·새 시점 영상. LiDAR occupied/free/unknown field는 파생 prior다. trusted 영역의 점유/빈 공간 판정을 신뢰한다. unknown은 센서 미관측이며 영상 미관측과 다르다.
2. **기여 위치 [원문]:** 아래 요소 표 참조.
3. **고정·수정 [원문]:** 기하 field는 고정. 위치는 기하 에너지, 공분산·불투명도·색과 densification은 사진 오차로 조정한다. free-space pruning을 추가한다.
4. **검증 [원문]:** KITTI/Waymo 정적 부분, 30k iterations, 매 4번째 test frame. PSNR/SSIM, LiDAR 복셀 기준 Leak/OccCov/Margin/Thick, Gaussian 수. 에너지·decoupling ablation. 독립 현재 표면의 국소 비악화 평가는 확인되지 않았다.
5. **잔여 오류:** [원문 수치] Table 1에서 PSNR 우위가 SSIM·Thick 등 모든 지표의 우위는 아니다. [미확인] 특정 잔여 형상 실패의 인과 분석은 이번 확인으로 확정하지 못했다.
6. **우리 후보·기각:** 과거 prior의 관측 존재가 현재의 정확성을 뜻하지 않는 조건에서, 고정된 신뢰 영역을 그대로 쓸 수 있는가. 이는 **적용 전제 차이**이며 EnerGS의 관측된 실패가 아니다. 같은 입력에서 기존 강건 에너지/연속 confidence만으로 보존·수정이 되면 새 원리 필요성을 기각한다. 현재 구조와 어긋나는 occupied/free 제약을 완화하더라도 유효 구조 손상이 증가하면 개선으로 인정하지 않는다.

| 요소 | 판정 |
|---|---|
| 입력·전처리 | 새: occupied/free/unknown field 구성; 기존 LiDAR·EDT 사용 |
| 좌표·카메라·정합 | 기존: 주어진 정합 입력; 정합 갱신 기여 미확인 |
| 표현 | 기존: 3DGS, 새: 부가 기하 에너지 field |
| 관측모형·렌더링 | 기존: GS 렌더 |
| 증거·감독·제약 | 새: 공간별 에너지·free-space 제약 |
| 초기화·최적화·모델 변경 | 새: gradient 분리·free pruning; 기존 densification 사용 |
| 추출·후처리 | 독립 mesh 추출 기여 미확인 |

**공식 구현 대조:** [train_energs.py](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/train_energs.py)에는 `loss.backward()` 뒤 `_xyz.grad = None`이 있다. 따라서 사진 손실이 기존 중심을 직접 이동시키는 통상 refinement와 구별한다. 렌더 가시성으로 coverage 상태는 갱신하되 입력 field의 점유 판정을 다시 추정하는 경로는 확인하지 못했다. argparse에서는 paper energy·free pruning 기본값이 True이며 legacy/ablation 옵션이 공존한다. README 옵션 표와 실행 기본값을 동일시하지 않는다. README는 field cache 생성 toolkit의 추가 공개를 예고하므로 전처리 포함 완전 재현 가능성은 미확인이다. 코드 실행은 하지 않았다.

**우리 해석:** LoD/DSM 표면만으로 원 LiDAR 광선이 통과한 빈 공간을 자동으로 알 수는 없다. 따라서 동일한 메쉬 표면을 주는 것과 동일한 관측 정보를 주는 것을 구별해야 한다. 이 논문은 공간별 prior 제어 외에 **어떤 변수에 어떤 감독을 전달하는가**도 이미 연구했음을 보여준다. 이론의 전제와 수렴 주장을 현재성·정합 오류가 섞인 prior의 정확성 보증으로 확장하지 않는다.

## 2. Confidence matters: Leveraging Multi-view Geometric Priors for GS-based Reconstruction

버전: [arXiv 2608.06117v1](https://arxiv.org/html/2608.06117v1), §3.1–3.2 식1–9, §4.1–4.6, Tables 1–3, Fig.5. [공식 코드](https://github.com/Zero-4869/ConfidenceMattersGS/tree/2f41455dad45d5e12e59b181429c275d5c5ad883), pin `2f41455dad45d5e12e59b181429c275d5c5ad883`.

1. **문제·입출력·가정 [원문]:** calibrated RGB·영상 파생 초기화·사전학습 VGGT 깊이/confidence→GS 표면·렌더. 독립 기존 자산은 없다. 깊이는 현재 GS 깊이에 affine 정합한다.
2. **기여 위치 [원문]:** 아래 표 참조.
3. **고정·수정 [원문·코드]:** 추정기 출력은 재사용하고 깊이 정합 및 GS를 갱신한다. confidence를 iteration 함수로 변환해 깊이·법선 감독에 적용한다. 추정기를 학습 중 재추론하는 경로는 확인되지 않았다.
4. **검증 [원문]:** DTU 15, TnT 6, Shiny Blender 기하 4개; 별도 NVS 평가. Table 3의 TnT ablation은 3개 장면 평균이다.
5. **실패·개선 [원문·저자 해석]:** 추정기 해상도에 따른 세부 손실을 confidence로 완화한다(Fig.5). Table 3의 TnT F1은 baseline .38, VGGT 무가중 .37, confidence 적용 .40. 이는 **해결한 ablation**이다. Table 1의 전체 TnT 평균은 baseline과 모두 .50이며 장면별 개선·악화가 섞인다. 악화 원인은 미확인이다.
6. **우리 후보·기각:** DA3 confidence나 기존 confidence 보정이 이미 충분한지 우선 비교해야 한다. 기존 confidence를 활성화·보정하는 것만으로 개선과 보존이 달성되면 추가 제어의 필요성을 기각한다. 추정기 confidence가 낮아도 독립 prior가 유효한 조건, 반대로 둘 다 잘못 확신하는 조건은 이 논문의 실증 범위와 분리해 검토한다.

| 요소 | 판정 |
|---|---|
| 입력·전처리 | 기존 VGGT 사용; 새 활용 구성 |
| 좌표·카메라·정합 | 기존 affine 정합 형식 사용; 새 감독 과정에 결합 |
| 표현 | 기존 PGSR GS |
| 관측모형·렌더링 | 기존 PGSR 평면 깊이·법선 |
| 증거·감독·제약 | 새: VGGT confidence 일정과 감독 구성; 기존 PGSR 제약 유지 |
| 초기화·최적화·모델 변경 | 기존 GS; 새 감독 일정 |
| 추출·후처리 | 기존 기반 파이프라인; 새 추출 기여 미확인 |

**공식 구현 대조:** [train.py L230–262](https://github.com/Zero-4869/ConfidenceMattersGS/blob/2f41455dad45d5e12e59b181429c275d5c5ad883/train.py#L230)에서 현재 렌더 깊이에 `align_depth`를 다시 적용한다. `mask_type=dynamic`은 VGGT confidence의 iteration 거듭제곱이다. 이 branch에서 깊이 affine 정합의 confidence>0.5 조건은 주석이며 실제 `loaded_mask`를 사용한다. 논문 Eq.1의 마스크와 이 branch를 동일시하지 않는다. 기본 옵션의 모든 조합·논문 실행 설정은 재현하지 않았다.

**우리 해석:** 사용자의 “영상 파생 감독을 일괄 적용하면 정확한 세부도 손상될 수 있다”는 가설을 지지하는 가까운 실증이다. 동시에 단순 confidence 해결책의 성공도 인정해야 한다. predictor confidence, 학습 중 모델과의 일치도, 독립 기존 자산의 현재 타당성은 서로 다른 양이며 동일 이름으로 합치지 않는다.

## 확인 한계

- 최신 preprint의 위 버전과 공식 공개 소스만 확인했다. 학회 표시는 저장소 README와 arXiv 버전 정보를 구분하며 심사 판정을 추론하지 않았다.
- raw 소스의 web 색인과 직접 HTTP 응답은 줄 수·검색 결과가 달랐다. 구현 문장은 고정 commit의 직접 HTTP 본문으로 대조했으며 웹 검색에서 confidence 문자열이 없다는 응답을 구현 부재로 해석하지 않았다.
- 두 저장소 모두 HEAD pin을 조회했지만 패키지 설치·프로젝트 실행·성능 재현은 하지 않았다.
- `scientific_verdict: null`
