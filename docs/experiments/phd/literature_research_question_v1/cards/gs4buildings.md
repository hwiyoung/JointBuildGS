# GS4Buildings — 근거 카드

`reviewed_at: 2026-09-09` · `scientific_verdict: null` · 직접 비교 후보: LoD2→2DGS→mesh. ALS를 직접 입력하는 방법과는 입력 변환을 분리해야 한다.

## 원문·버전·확인 범위

- Zhang, Wysocki, Jutzi, **GS4Buildings: Prior-Guided Gaussian Splatting for 3D Building Reconstruction**, ISPRS Annals X-4/W6-2025, 249–256, 2025. [출판사/CC BY 4.0](https://doi.org/10.5194/isprs-annals-X-4-W6-2025-249-2025), [공식 PDF](https://isprs-annals.copernicus.org/articles/X-4-W6-2025/249/2025/isprs-annals-X-4-W6-2025-249-2025.pdf), [기관 PDF](https://publikationen.bibliothek.kit.edu/1000187024/169623991). 본 카드는 8쪽 전문과 아래 공식 구현을 읽었다. 페이지는 인쇄 페이지, 괄호는 PDF 페이지다.
- **코드 공개 확인:** 2026-09-09 `git ls-remote` 및 실제 shallow checkout으로 HEAD `f0be3e257ee6f58e42d1aa3258810c7b78866a7d` 확인. 커밋 날짜 2026-08-25, 메시지 `Add GS4Buildings training, evaluation, and data-prep code`. [고정 공식 소스](https://github.com/zqlin0521/GS4Buildings/tree/f0be3e257ee6f58e42d1aa3258810c7b78866a7d). 검색 엔진/HTML 캐시의 `Code coming soon`은 현재 상태로 사용하지 않는다. 실행은 하지 않았다.
- 이번 읽기에 사용한 공식/기관 공개 PDF의 SHA256: `7f08486f708646ca2a929f8d7ccb53f8829605f3368d5f40c599d9ccd8904005`. 출판사 웹 PDF 재열기 오류 후 기관 제공 PDF와 Docker pypdf 추출을 사용했다.
- 근거 강도: `원문 사실`=본문/표가 직접 기술; `구현 사실`=고정 소스 정적 확인; `저자 해석`=원문의 원인 설명; `우리 추론`=아래 검증 후보. 원문의 주장과 독립 재현을 구별한다.

## 1. 문제와 입출력

가림·희소 시점 때문에 영상 기반 건물 표면이 결손되는 문제에 대해, LoD2로 구조를 보완하면서 외관과 mesh를 복원한다. 실제 관측은 UAV RGB, 외부 자산은 LoD2 건물 mesh, 파생 정보는 면 표본·raycast depth/normal/validity mask, 카메라는 별도 추정/제공값이다. 이 방법의 본체에 사전학습 depth network는 없다. 2DGS의 함수·표현상 정규화는 외부 관측과 구별한다. [§3.1–3.3, pp250–252/PDF2–4, Fig2, 식1–12]

전제는 정합된 LoD2와 알려진 카메라, 충분히 유효한 건물 면, 초기 표본이 최소 k시점에서 보이는 조건이다. SfM sparse 초기화는 대체하지만 카메라 정확성까지 불필요해지는 것은 아니다. 논문 실험 pose/MVS는 Pix4Dmatic이다. LoD2가 모든 건물 세부나 현시점 형상을 정확히 담는다는 검정은 없다. raycast mask는 mesh 교차 유효성이고 수목·차량에 대한 실제 영상 가시성/현재성 판정과 같지 않다. [§3.1–3.2; §4.2 p253/PDF5]

## 2. 기여의 위치

`N=논문이 제안한 기여`, `U=기존 방법 사용`, `?=미확인`; N은 학위 신규성 인정이 아니다.

| 요소 | 구분과 근거 |
|---|---|
| 입력·전처리 | **N+U**: LoD2 면적 비례 표본과 다중뷰 가시성으로 초기점 생성하는 GS 결합은 제안; trimesh/Open3D sampling/raycast는 기존 도구. §3.1 식1–3 |
| 좌표·카메라·정합 | **U/?**: 공통 좌표계 변환·보정 카메라 사용; 독자적 정합/pose optimizer의 새 기여는 확인되지 않음. §3.2, §4.2 |
| 표현 | **U**: planar elliptical 2D Gaussian, 2DGS. §3.3 식5–6 |
| 관측모형·렌더링 | **U**: ray–splat intersection와 alpha compositing, LoD2 raycasting. §3.2–3.3 식4,7 |
| 증거 사용·감독·제약 | **N+U**: building depth/normal 감독과 mask 결합; L1/cosine, 2DGS distortion/normal은 기존 형식. 식8–12 |
| 초기화·최적화·모델 변경 | **N+U**: prior 초기화, 시간별 loss scheduling, building-only/enhanced; 기본 GS density control/optimizer 재사용. §3.1,3.3 |
| 추출·후처리 | **U**: 2DGS TSDF fusion+Marching Cubes. 독자적 CityGML/LoD2 추론은 없음. §3.3 |

## 3. 무엇을 고정하고 무엇을 수정하는가

| 대상 | 실제 역할·수정 여부 |
|---|---|
| RGB·LoD2 mesh·depth/normal/mask·카메라 | 입력/전처리 결과로 고정. 강한 구조 지지를 유지하려는 설계. 유효성 판단으로 prior 면 자체를 바꾸는 경로는 확인되지 않음 |
| Gaussian | 중심·회전/접평면·scale·opacity·색/SH 추정, clone/split/prune로 개체 수 변경 |
| depth scale α | 논문 식10의 조정 인자; 공개 코드에서는 매 view/iteration `median(prior)/median(rendered)`로 재계산. 별도 독립 scale 관측이나 camera BA가 아님 |
| loss weights | 시간표로 변경. evidence의 원 bytes는 그대로, 현재 Gaussian에서 depth/normal/RGB와 잔차를 매번 다시 렌더 |

**정보 흐름:** `LoD2 + camera → 표본/깊이/법선/mask → GS 초기화·감독 ↔ 렌더·RGB·depth/normal residual → GS 변경 → TSDF mesh`. 최적화 내부 feedback은 존재한다. 뒤쪽 관측이 LoD2 또는 카메라 추정을 갱신하는 upstream 경로는 확인되지 않는다. 초기화가 고정이어도 Gaussian이 고정된 것은 아니다. prior 제약을 풀면 세부 회복 가능성과 가림 영역 구조 손실 가능성이 함께 생긴다는 것이 검증할 교환관계다.

**논문과 현재 구현을 별도로 해석:** 논문 §3.3은 Phase2에서 prior loss weights를 점감한다고 기술한다. 그러나 [공개 train.py L168–213](https://github.com/zqlin0521/GS4Buildings/blob/f0be3e257ee6f58e42d1aa3258810c7b78866a7d/train.py#L168)은 depth를 5k–7k에 증가시킨 뒤 유지하고 normal만 7k–9k에 0.1배로 줄인다. [arguments L124–125](https://github.com/zqlin0521/GS4Buildings/blob/f0be3e257ee6f58e42d1aa3258810c7b78866a7d/arguments/__init__.py#L124)의 기본값은 depth=.05, normal=0이며 [scripts/train.sh](https://github.com/zqlin0521/GS4Buildings/blob/f0be3e257ee6f58e42d1aa3258810c7b78866a7d/scripts/train.sh)도 이를 override하지 않는다. 따라서 제공된 기본 CLI만으로 논문의 full depth+normal 조건을 재현했다고 부를 수 없다. 저자 실험 config를 별도 확보해야 한다. 이 차이는 문서/코드 감사 결과이며 논문 성능의 반증은 아니다.

## 4. 실제 검증 범위

- TUM2TWIN 1,179장 영상 집합 중 9개 건물군, 약 10–30장/군. 정확도는 영상과 동시 취득 laser reference, completeness는 LoD2와 구조적으로 일관된 LoD3-derived reference. 서로 다른 참조를 쓰므로 두 수치를 동시점 독립 완전성 증거 하나로 합치지 않는다. [§4.1 pp252–253/PDF4–5]
- 30k iteration, Pix4Dmatic MVS와 2DGS 비교. 출판 본문에 정확한 train/test image membership·seed·split 개수는 확인되지 않는다. 현재 [dataset_readers L358–376](https://github.com/zqlin0521/GS4Buildings/blob/f0be3e257ee6f58e42d1aa3258810c7b78866a7d/scene/dataset_readers.py#L358)의 `eval` 기본 every-8th split은 저자 당시 membership을 증명하지 않는다.
- Table1–3(pp253–255/PDF5–7): 평균 NVS 거의 유지(PSNR 17.190→17.369), 평균 M3C2 2DGS .405→.272, LoD3 VOC .185→.223. Table4(PDF7)는 SfM init, depth 제거, normal 제거를 비교하지만 동일 최종 모델이 서로 다른 추출로 얼마나 달라지는지, 복합 오류의 원인별 효과, 국소 비악화를 분리하지 않는다.
- **성공과 악화:** Table2 scene6에서 2DGS→GS4B CD .728→.857, M3C2 .059→.161; Table1 scene6 PSNR 13.449→12.870. Fig6/scene1은 completeness@.5 .428→.547이나 M3C2 .376→.384. 평균 향상은 전 구역 비악화 증거가 아니다.
- building-only primitive 71.8% 감소는 compactness 결과이며 보편적 runtime/메모리 개선이나 비건물 복원 동등성을 보장하지 않는다. currentness, systematic prior perturbation, per-surface risk calibration, LoD2 product pass는 이 논문에서 평가되지 않았다.

## 5. 남은 오류와 전달 경로

| 조건·오류 | 증거와 상태 | 전달 경로·대안 원인 |
|---|---|---|
| 풍부한 texture/시점의 얇은 부재·창·문·eave 세부 손실 | **원문 관찰**, §4.4 pp254–256/PDF6–8, Fig6; coarse prior/강한 정규화 원인은 **저자 해석** | coarse LoD2→depth/normal 제약→표면 평활화. **우리 추론:** 초기 표본, GS capacity, TSDF도 원인 후보; 분리 ablation 없음 |
| 비건물 영역 최종 image loss | 오류 잔존 및 prior 미제공 연관은 **저자 해석**, §4.4 | 건물 중심 표본/감독→비건물 지원 부족; 단독 인과 입증 아님 |
| 모든 관측 부족 건물의 현시점 정확도 | **미평가** | LoD3 completeness는 시간 유효성 인증이 아님 |
| 큰 오정합·철거/신축 prior | **미평가** | 실패가 관찰됐다고 쓰지 않음. 실험 가정 확장 후보 |

## 6. 연구 공백 후보

**이미 해결:** 구조 prior로 초기화/감독, 가림 영역 복원, geometry/appearance 함께 추정, scheduling, mask 기반 소형화. 이 기능이나 GS 접속만으로 신규성을 주장할 수 없다. **가장 가까운 개선은 후속 GeoGS**이며 visual depth·구조 보호·적응 가중을 이미 추가했다.

남는 후보는 **검증 부족과 방법 한계의 결합**: 충분히 관측되는 세부와 유효하지만 관측 부족한 구조가 섞일 때, 강한 기존 정규화/GeoGS 대비 국소 손상 감소와 결손 보완을 동시에 개선할 수 있는가. 최소 비교는 공통 입력·추출에서 GS4B 문서 일치 설정, 현재 공개 코드 설정, GeoGS, 단순 confidence mask/weight 처리이며 영상-only·prior-only도 포함한다. 깊이/법선·초기화·추출을 따로 바꾸고 구조 유지/세부 개선/악화/유보를 모두 보고한다. **기각 조건:** GeoGS 또는 단순 국소 가중으로 교환관계가 해소되거나 새로운 방법의 이득이 다른 구역 악화·추출 차이·입력 추가에서만 생기면 이 공백을 축소/기각한다. 반복·명시 판단 모듈의 필요성은 아직 도출되지 않는다.
