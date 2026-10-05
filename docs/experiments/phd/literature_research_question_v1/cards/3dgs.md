# 3DGS — 표현·최적화·렌더링 기준선

검토일 2026-09-09 · `scientific_verdict: null` · 역할: 영상 복원의 직접 기준선 후보, 이종 기하 갱신의 구성요소.

## 근거와 버전

- Kerbl, Kopanas, Leimkühler, Drettakis, *3D Gaussian Splatting for Real-Time Radiance Field Rendering*, ACM TOG 42(4), 2023, DOI [10.1145/3592433](https://doi.org/10.1145/3592433).
- 검토 전문: [arXiv 2308.04079v1 HTML](https://arxiv.org/html/2308.04079v1). §4 표현, §5 및 Appendix B 최적화, §6 렌더러, §7.1–7.4 평가·한계. Table 1 전체 비교, Table 3 ablation, Fig.11–12 잔여 artifact. HTML에는 고정 인쇄 페이지가 없어 절·표·그림을 locator로 사용한다. PDF 접근 오류는 [이슈](../ISSUES_ko_v1.md)에 기록한다.
- [공식 구현](https://github.com/graphdeco-inria/gaussian-splatting/tree/54c035f7834b564019656c3e3fcc3646292f727d), 확인 HEAD `54c035f7834b564019656c3e3fcc3646292f727d`. [train.py](https://github.com/graphdeco-inria/gaussian-splatting/blob/54c035f7834b564019656c3e3fcc3646292f727d/train.py#L129)를 직접 읽었다. 현재판에는 depth regularization·exposure optimizer 등이 추가돼 있어 **2023 논문 실험 코드와 동일하다고 보지 않는다**.

## 1. 문제와 입출력

[원문 사실] 보정된 여러 RGB로 새 시점 영상을 빠르게 생성한다. 실제 관측은 RGB, 카메라와 SfM 희소점은 파생 추정이다. 외부 3D prior·사전학습 기하 모델은 원논문의 필수 입력이 아니다. 출력은 색·불투명도를 갖는 Gaussian 장면이다. 같은 정적 장면을 설명할 수 있는 뷰·카메라 정합을 전제한다(§3–5).

[우리 추론] 무색 ALS와 현재 영상의 상보성 평가는 외부 입력 경로를 추가한 별도 방법이 필요하다. 그 추가 경로의 실패를 원 3DGS의 실패로 셈하지 않는다.

## 2. 기여의 위치

`새`는 논문이 제안하는 요소이며 독립적인 최초성 판정이 아니다.

| 요소 | 판정과 내용 |
|---|---|
| 입력·전처리 | 기존 사용: SfM sparse 초기화 |
| 좌표·카메라·정합 | 기존 사용: 보정 pose; 새 정합 기여 확인 안 됨 |
| 표현 | 새 구성: 최적화 가능한 비등방 Gaussian·opacity·SH |
| 관측모형·렌더링 | 새: visibility-aware tile rasterization; projection·alpha blending은 선행 기반 |
| 증거 사용·감독·제약 | 기존 사용: L1·D-SSIM 영상 손실 |
| 초기화·최적화·모델 변경 | 새: 연속 파라미터 최적화와 clone/split/prune의 결합 |
| 추출·후처리 | 미확인: 원문에 평가된 표준 최종 mesh producer 없음 |

## 3. 고정과 수정, 정보의 갱신

[원문 사실] 위치·회전·scale·opacity·SH와 primitive 수를 바꾼다. 입력 사진·카메라·SfM 결과 파일을 재추정하지 않고, SfM점에 대응해 시작한 Gaussian은 이동할 수 있다. 렌더→RGB 손실/위치 gradient→파라미터 및 밀도 변경→새 렌더의 내부 피드백이 있다. 반복마다 가시성·잔차·Gaussian 집합이 바뀌며 사진은 재사용한다(§5, Appendix B).

[우리 추론] 카메라를 고정하면 장면 적합이라는 하위 문제를 분리할 수 있다. 이를 풀면 pose 오차를 줄일 가능성과 형상·카메라가 서로 오차를 흡수할 가능성이 함께 생긴다. 이는 본 논문이 입증한 pose 개선 효과가 아니다. 렌더 손실 피드백을 SfM 재수행 또는 외부 자산 수정과 혼동하지 않는다.

## 4. 실제 검증 범위

[원문 사실] Mip-NeRF360·Tanks and Temples·Deep Blending의 장면별 학습과 미사용 뷰에서 영상 품질, 시간·FPS·메모리를 비교한다. Plenoxels·Instant-NGP·Mip-NeRF360 등과 비교하고 초기화·비등방성·SH·밀도 제어를 ablation한다(§7, Tables 1–3). NVS 성공이 확인된 범위다.

[미평가] 독립 현재 기하에 대한 정확도·완전성·국소 비악화, 실제 시기 변화, roof 세부와 textured mesh의 기하 품질은 이 평가로 확정되지 않는다. 학습 뷰 제외는 독립 장면 일반화와 다르다.

## 5. 남은 오류와 전달 경로

[원문 사실·관측된 실패] 약관측 영역의 길쭉한 Gaussian·얼룩 및 시점 전환 시 popping을 보고한다(§7.4, Fig.11–12). [저자 해석] 큰 Gaussian, culling과 정렬의 단순화가 popping에 관여한다.

[우리 추론] 약관측/pose 오류→비식별 형상→RGB 손실로 허용되는 잘못된 Gaussian→후속 표면 추출의 오류가 가능한 경로다. 이 논문에서 그 전체 경로를 원인별로 분리 검증한 것은 아니다. 부족한 시차, 반사, 초기점 피복도 대안 원인이다. 외부 prior 오보존은 원입력 범위 밖이다.

## 6. 공백 후보와 기각 조건

[우리 추론] RGB 적합이 표면 개선을 보장하는지는 검증 질문이다. 이미 2DGS·VCR-GauS가 표면 표현·감독을 개선하므로 “3DGS 기하가 나쁨”만으로 새 방법을 정당화하지 않는다. 최소 비교는 같은 영상의 MVS→mesh, 3DGS, 2DGS/VCR-GauS에서 공통 지원영역·추출 설정·평가를 맞추는 것이다. 외부 구조 추가가 필요하면 같은 정보로 기존 prior 방법도 포함한다. 기존 표면 방법이 정확도·완전성·외관·비악화를 충족하면 새 GS 표현의 필요성 후보를 기각한다.
