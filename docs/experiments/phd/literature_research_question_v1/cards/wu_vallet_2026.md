# Wu & Vallet (2026) — Image LiDAR based change detection and updating

- 검토일: 2026-09-09. `scientific_verdict: null`.
- 서지·버전: Teng Wu, Bruno Vallet, *Image LiDAR based change detection and updating for urban 3D reconstruction*, ISPRS Annals XI-2-2026, **385–392**, 2026-07-03 공개, peer-reviewed final. [출판사](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.html), [원문 PDF](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf).
- PDF SHA256: `c57f088755b21fb437f14e103d5222dc228eecf6306addaa8f2f92cc20f51f86` (8쪽, 39,061,976 bytes).
- 공식 코드: 원문이 예고한 [ChangeUpdateJN](https://github.com/whuwuteng/ChangeUpdateJN)를 2026-09-09 확인. 공개 [GitHub API](https://api.github.com/repos/whuwuteng/ChangeUpdateJN) HTTP404. **현재 공개 접근 불가**이며 부재·미구현의 증거는 아니다. 논문 원문 기반 local 재구현과 저자 코드 동일성을 주장하지 않는다.
- 비교 역할: **가장 가까운 전체 기하 갱신 경쟁자 중 하나**. 선택 모듈 참고에 한정하지 않고 최종 갱신 점군과 공통 표면 후단까지 비교한다.

## 1. 문제와 입출력

**[원문 사실]** 정밀한 과거 ALS를 최신 aerial image geometry로 변화 위치만 갱신한다. 입력은 LiDAR/GPS time/trajectory, oriented RGB; 파생물은 두 sensor meshes와 PSMNet 시차·다중 뷰 점군이다. LiDAR가 영상보다 오래됐지만 더 정확하고 피복이 넓다는 실험 조건이다. [§3, pp.386–387, Fig.1–6](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf#page=2).

**[우리 분석]** 이 연구의 영상 기하는 완전히 독립적인 image-only 증거가 아니다. LiDAR에서 stereo 학습 label을 만들므로 감독 계보를 기록해야 한다. 임의 외부 사전학습 checkpoint의 정확한 버전은 원문에서 확인되지 않는다. UAV·광역·낮은 품질 prior 전반이 검증된 것도 아니다.

## 2. 기여의 위치

| 요소 | 판정 | 실제 역할 / 근거 |
|---|---|---|
| 입력·전처리 | 기존 사용 + 적용 구성 | LiDAR/image training data, SGM noisy-label 필터; §3.2/4.2 |
| 좌표·카메라·정합 | 기존 사용 | GCP 정렬 가정, GPS-time trajectory 보간; §3.1/4.1 |
| 표현 | 기존 sensor mesh + 새 적용 | LAS/LAZ에서 scan time 기반 scanline 복원; §3.1/Fig.2 |
| 관측모형·렌더링 | 기존 사용 + 규칙 조정 | Wu2023 mesh ray tracing, aerial 2.5D 신축 시 과거 지면 제거; §3.3/Fig.6 |
| 증거·감독·제약 | 새 전체 구성 | consistent/changed/single와 static LiDAR 우선·change image 사용 |
| 초기화·최적화·모델 변경 | 기존 사용 + workflow | PSMNet 재학습, multi-view intersection; 최종 point replacement |
| 추출·후처리 | 기존 사용 | 작은 영역 필터·점군 fusion; §4.3 |

## 3. 무엇을 고정하고 수정하는가

**[원문 사실]** noisy LiDAR label로 학습하면 실제 신축에서 stereo가 실패하고 SGM과 1px 불일치 label을 제거한 뒤 재학습하면 개선된다. 최종 변화에서 옛 점을 제거하고 영상 점을 더한다. 미변화부와 LiDAR-only는 보존한다. [§4.2/Fig.8, §3.3/Fig.6](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf#page=4).

```text
RGB+ALS → training labels ← SGM 검정/기각 → PSMNet 재학습
RGB+fixed cameras → stereo/multi-view geometry → image sensor mesh
ALS+time/trajectory → LiDAR sensor mesh
양 mesh → 거리/광선 변화 → 면적 정제 → 옛 점 제거+새 점 추가
```

**[우리 분석]** 학습 감독의 갱신 경로가 실제 존재하므로 “앞단 결과가 전혀 수정되지 않는다”는 비판은 틀린다. 반면 최종 ray 판정이나 fused result가 camera·trajectory·PSMNet·label filter를 다시 수정하는 반복 경로는 원문에서 확인되지 않는다. 논문은 대칭적인 source별 국소 정밀도 posterior를 추정하는 대신 실험 조건상 LiDAR 품질 우위를 사용한다.

정합 고정은 계산·pose/shape 혼동을 줄인다. 이를 풀면 잘못된 mesh에 맞춰 정밀한 ALS를 움직일 수 있다. **[우리 추론]** change 영역의 image 품질이 나쁘면 변경 허용과 정확한 복원이 분리될 수 있다. 단, 이를 고치기 위해 GS나 별도 판단 모듈이 꼭 필요하다는 결론은 아니다.

## 4. 실제 검증 범위

**[원문 사실]** Grenoble ALS2021/영상2024, Lyon ALS2021/영상2023; 약10pts/m², 20cm RGB, GCP 정렬. 모든 가용 stereo samples를 학습에 사용해 overfit 가능성을 인정한다. 변화 GT를 수동 주석하지 않았고 업데이트 품질 정량평가는 future다. [§4.1–4.2, §5, pp.388–390](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf#page=4).

**[평가 감사]** Fig.8의 noisy/clean label, Fig.10→11 및14→15의 작은 영역 정제는 효과를 보여주는 정성 contrast다. controlled ablation 수치표, 독립 변경/기하 GT, hold-out reconstruction, net rescue/regression, 표면 정확도·완전성·렌더와 계산량의 통합 정량평가는 확인되지 않는다. 도시 두 사례의 질적 갱신 성공을 독립 일반화 성능으로 표현하지 않는다. 점군 출력과 full mesh/texture 성과도 구분한다.

## 5. 남은 오류와 전달 경로

| 상태 | 근거와 해석 | 전달 경로 / 대안 원인 |
|---|---|---|
| **관측된 실패와 개선** | [원문 사실/저자 해석] 변화에 의한 noisy training label, 재학습 후 개선; §4.2/Fig.8 | ALS 불일치→감독 오염→stereo 오기하 |
| **관측된 잔여 실패** | [저자 해석] Fig.15(b) 정제 후에도 벽 불일치 오탐; §4.3.2 | image mesh/벽 표현 차이→ray conflict→잘못된 change |
| **관측된 어려움** | [저자 해석] 가림·수목에서 실패/오탐, 큰 mesh의 ray 비용; §5 | 점군·mesh 품질→검정→fusion; 계산 자원 증가 |
| **미확인** | [우리 분석] 위 벽 오탐에서 matching/정합/meshing 각각의 원인별 기여 | geometry·ray predicate·filter를 통제한 추가 비교 필요 |
| **미평가/범위 밖** | [원문 사실] rural update, UAV 지속성, full mesh는 후속 방향 | 이 조건에서 실패가 입증됐다는 뜻 아님 |

근거: [§4.3–5와 Fig.10–16, pp.389–392](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf#page=5). **실제 저자 잔여 오류는 확인됨**. JointBuildGS v5/v7 P1–P3의 수치와 오류는 이 원문에 존재하지 않으며 동일 원방법의 실패율로 인용하지 않는다.

## 6. 연구 공백 후보

**이미 해결:** ALS 구조 재사용, 신규 관측으로 변화부 교체, 비관측 보존, 잘못된 감독 label 기각, 다중 뷰 기하, 작은 영역 오탐 제거. full mesh 연결은 Wu2023에도 있다.

**후보 [방법론적 가능성+검증 부족]:** 벽·가림·수목·정합 잔차가 겹칠 때 기존 mesh/label 개선 이후에도 실제 구조 손상이 남는가? `강한 matcher+existing confidence/semantic filter+Wu2023 quality selection+common reconstruction`이 직접 반증 비교다. 새 소스 판단을 부착하기 전에 image production과 검정 각각의 효과를 나누어야 한다.

**최소 비교/기각:** 동일 meshes를 고정한 판단 비교와 원생성기부터의 end-to-end 비교를 병행한다. prior-only/image-only/union/Wu/Wu+기존 정제/수정 후보를 같은 입력·참조·출력에 맞춘다. 독립 현재 기하 및 변화 주석으로 올바른 유지·잘못된 삭제·잘못된 추가와 성공영역 손상, 복원 정확도/피복/외관을 평가한다. 기존 정제로 해소되거나 향상이 matcher 교체에만 귀속되면 신규 판단 알고리즘의 공백 주장은 기각한다. 이번 카드 작성은 새 실행 권한이 아니다.
