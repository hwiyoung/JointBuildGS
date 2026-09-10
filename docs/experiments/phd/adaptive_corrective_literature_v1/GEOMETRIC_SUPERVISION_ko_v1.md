# 학습 중 기하 감독 제어: 선행 해결책과 남는 원인

- 검토일: 2026-09-10
- 상태: 원문·공식 소스 읽기, 실행·성능 재현 없음. `scientific_verdict: null`.
- 연구 목적은 현재 기하·관측 가능한 세부·외관의 복원이다. 유효 구조 보존과 필요한 수정은 그 목적을 실현하는 방법 원리와 평가 기준이다.
- 기존 문헌 카드는 링크를 찾는 색인으로만 사용했다. 아래 arXiv 본문 및 고정 공식 소스를 이번에 재열람했다. 네 저장소의 공개 HEAD는 조회 시점에 아래 pin과 같았다.
- 네 방법 모두 오래된 ALS/LoD/DSM과 현재 항공영상이라는 동일 입출력의 직접 실행 비교군은 아니다. **감독 제어·표현의 구성요소 경쟁 방법**이며, GeoGS 이식은 원방법 재현과 별도로 명명해야 한다.

## 1. 동일 양식 근거 카드

### NeuRIS — ECCV 2022

근거: [arXiv 2206.13597v2](https://arxiv.org/html/2206.13597v2), §3.1–3.3·식6·Fig.2, §4.1–4.2·Table 1·Fig.6. 공식 pin `fab2cc4ca45847fbee7490e978d3c60c582123b1`; [exp_runner.py L329](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L329).

1. **문제·입출력·가정 [원문 사실]:** 정합된 실내 RGB에서 SDF 표면·외관을 복원한다. 법선은 학습 모델의 영상 추정이며 독립 기존 측정기하가 아니다. 법선 모델은 해당 train/test 분할로 재학습했다. 정적 장면·카메라와 국소 평면 warp를 전제한다.
2. **기여 위치:** 아래 공통 8요소 표 참조. 초기 prior 감독 후 현재 깊이·법선의 다시점 NCC로 감독을 기각한다.
3. **고정·수정·피드백 [원문·코드]:** 영상·법선 맵·카메라는 고정, SDF·색은 수정. `현재 표면→사진 검정→법선 감독→다음 표면` 경로가 있다. 코드에는 현재 NCC·이전 confidence·법선 차이 검사가 함께 있다. 기각한 prior는 재채택하지 않는다.
4. **검증 [원문 사실]:** ScanNet 8실, 약150–600장/실. 표면 accuracy/completeness/F-score, 법선·렌더 및 prior/gate ablation. 비교 방법 중 일부는 실패 장면을 제외해 평균 분모가 다르다.
5. **남은 오류 [우리 추론·미평가]:** 초기 기하·가림·카메라 오차로 유효 prior를 기각하면 감독 부재가 지속될 수 있다. 실제 발생 빈도나 독립 과거 자산에서의 손상은 이번 원문 확인으로 입증하지 못했다. 단계적이라는 이유로 단방향으로 분류하지 않는다.
6. **공백 후보·기각 [우리 설계]:** 고정가중, NCC 지속기각, 동일 NCC의 재채택 허용을 동일 GS·입력·예산에서 대비한다. 재채택만으로 문제가 사라지면 새 복합 판단의 필요성을 기각한다. 정상 prior 조건의 악화와 잘못된 prior의 수정 모두 평가한다.

### AGS-Mesh — 3DV 2025

근거: [arXiv 2411.19271v2](https://arxiv.org/html/2411.19271v2), §4.1–4.4·식4–10·Fig.3, Tables 1–4, Appendix A·E·Fig.9. 공식 pin `93fda851a20cf0bd5fce642c46da0c83c637165e`; [train.py L127](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py#L127).

1. **문제·입출력·가정 [원문 사실]:** 스마트폰 실내 RGB·센서 깊이·사전학습 단안 법선으로 GS·mesh를 복원한다. 센서 깊이와 그 파생 법선, 예측 법선을 구별한다. 동기화·정합된 입력을 사용하며 원거리·경계 센서 오류를 다룬다.
2. **기여 위치:** DNC 깊이 필터·ANR 법선 필터와 추출이 중심이다. 아래 8요소 표 참조.
3. **고정·수정·피드백 [코드 확인]:** DNC 맵은 전처리되어 고정, ANR는 현 GS 깊이 유래 법선과 예측 법선으로 매 sampled view에서 재계산된다. 이전 기각을 누적하는 조건이 없어 재포함 가능하다. GS 변수는 수정하되 센서·법선 추정기·카메라는 다시 추정하지 않는다.
4. **검증 [원문 사실]:** MuSHRoom·ScanNet++의 기하와 NVS, 감독·필터·추출 ablation. 평가 시선과 다른 trajectory를 구분한다. 처리 시간도 보고한다. 기존 자산의 현재성 및 국소 비악화율은 미평가다.
5. **남은 오류:** [저자 한계] IsoOctree 추출의 전체 기하 개선은 일관되지 않는다(App.E). [우리 추론·미평가] 방향이 일치해도 평행한 높이 오류는 남을 수 있다. DNC/ANR의 이런 실패가 실제 입증됐다는 뜻은 아니다.
6. **공백 후보·기각 [우리 설계]:** DNC와 ANR를 따로 이식하고 같은 추출을 유지한다. 방향 일치·위치 불일치 조건에서 실패를 확인한 뒤 photo gate와 비교한다. 기존 필터 조합으로 보존·수정이 달성되면 신규 제어 필요성을 기각한다.

### VCR-GauS — NeurIPS 2024

근거: [arXiv 2406.05774v2](https://arxiv.org/html/2406.05774v2), §3.2–3.4·식10–14, §4.2·Table 4·Figs.6–7, **Appendix B·Fig.13**. 공식 pin `aa715d19bfacfa9d491f477c572eab1839dcee3e`; [trainer.py L261](https://github.com/HLinChen/VCR-GauS/blob/aa715d19bfacfa9d491f477c572eab1839dcee3e/trainer.py#L261).

1. **문제·입출력·가정 [원문 사실]:** RGB·COLMAP sparse 초기화·예측 법선에서 GS 표면·렌더를 복원한다. 독립 측정 prior는 없다. 렌더 법선이 여러 시선의 예측을 집약한다는 가정으로 시선별 신뢰도를 산정한다.
2. **기여 위치:** D-Normal이 법선 감독을 위치에 전달하며, confidence·교차 깊이·분할도 수정한다. 아래 표 참조.
3. **고정·수정·피드백 [코드 확인]:** pseudo-normal은 고정, 렌더 법선과의 cosine confidence는 반복 갱신한다. confidence 계산은 `detach/no_grad`이며 별도 confidence network 학습이 아니다. Gaussian 위치·방향·크기·개수 수정에 감독을 연결한다.
4. **검증 [원문 사실]:** TNT·Replica·DTU 기하, Mip-NeRF360 NVS·시간. Table 4는 D-Normal·confidence·교차 깊이·densification 효과를 분리한다. Figs.6–7의 floaters·돌출은 기능 제거 ablation의 실패다.
5. **남은 오류:** [저자 한계] 거의 모든 시선의 법선이 틀리면 실패하며 미관측 영역과 반투명 표면에도 한계가 있다(App.B). [관측된 실패] Fig.13 반투명 창. [우리 추론] 일관성이 정확성을 보증하지 않는 조건은 독립 기구축 기하의 역할을 검토할 근거다.
6. **공백 후보·기각 [우리 설계]:** confidence만과 confidence+D-Normal을 분리 이식한다. 다수 예측의 공통 오류에서 유효 prior가 추가 정보를 제공하는지 검사한다. 전달 경로 수정만으로 해결되면 새 타당성 추정의 필요성을 기각한다.

### DebSDF — TPAMI 2024, 추가 경쟁 연구

근거: [arXiv 2308.15536v3 PDF](https://arxiv.org/pdf/2308.15536v3), **§3.2·p.6**, §3.3–3.5, **§4.4.1·Table 4·Fig.9·pp.12–13**, §5·p.14. [HTML](https://arxiv.org/html/2308.15536v3)은 §III-B·IV-D, Table IV 표기다. 공식 pin `4580c8e1c9872e65f6cb9fc55607162f57ab7a54`; [loss.py L236](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/loss.py#L236), [network.py L357](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/network.py#L357).

1. **문제·입출력·가정 [원문 사실]:** calibrated RGB·단안 depth/normal에서 SDF 표면을 복원한다. 기존 독립기하는 없다. 다중뷰·모달리티 일관성을 prior 타당성의 대리로 삼는다.
2. **기여 위치:** 불확실성이 prior 감독·ray sampling·smoothness에 작용하며 SDF→density 편향도 수정한다. 아래 표 참조.
3. **고정·수정·피드백 [코드 확인]:** depth/normal 맵은 고정. SDF·외관·시선 의존 uncertainty를 학습한다. 높은 uncertainty에서 기하 감독 gradient를 차단해도 uncertainty 학습은 계속한다. sampling 맵은 정해진 시점에 갱신한다.
4. **검증 [원문 사실]:** ScanNet·ICL-NUIM·Replica·TNT, DTU의 표현 변환 ablation. Table 4·Fig.9는 필터→sampling→smoothness→density 변환을 비교한다. Table 5는 uncertainty 마스크별 기하 평가다. 독립 변화 라벨에 따른 비악화 평가는 아니다.
5. **남은 오류:** [저자 해석] 틀린 prior의 낮은 uncertainty와 맞는 prior의 높은 uncertainty가 가능하다(p.6). [ablation에서 관측·저자 해석] 필터·sampling·smoothness만으로 남은 얇은 구조 손상을 density 변환이 추가 개선한다(pp.12–13). 이를 완성 DebSDF의 미해결 실패나 GeoGS의 원인으로 바꾸어 말하지 않는다.
6. **공백 후보·기각 [우리 설계]:** 불확실성 선택 오류와 표현/gradient 전달 오류를 분리해야 한다. GeoGS에는 학습형 감독 제어를 이식하되 SDF 변환을 그대로 이식할 수는 없다. 기존 제어와 표현 개선 조합이 문제를 해결하면 새로운 복합법의 필요성을 기각한다.

## 2. 기여 위치 비교

`새`는 해당 논문이 제안한 구성요소라는 뜻이며, 세계 최초성 판정이 아니다. 사용자 양식의 ‘초기화·최적화·모델 변경’을 아래에서 두 열로 나누어 8요소로 표시했다.

| 요소 | NeuRIS | AGS-Mesh | VCR-GauS | DebSDF |
|---|---|---|---|---|
| 입력·전처리 | 기존 법선 예측 사용 | 새 DNC; 기존 센서·예측 사용 | 기존 SfM·법선 사용 | 기존 단안 depth/normal 사용 |
| 좌표·카메라·정합 | 기존 calibrated camera 사용 | 기존 제공 정합 사용 | 기존 COLMAP 사용 | 기존 calibrated camera 사용 |
| 표현 | 기존 NeuS SDF·색 사용 | 기존 GS 기반 사용 | 기존 Gaussian 기반·새 표면 유도 | 기존 SDF·새 uncertainty 출력 |
| 관측모형·렌더링 | 기존 NeuS 사용 | 기존 GS 렌더 사용 | 새 교차 깊이 결합 | 새 곡률 기반 density 변환 |
| 증거·감독·제약 | 새 NCC prior gate | 새 DNC·ANR | 새 D-Normal·confidence | 새 masked uncertainty·smoothness |
| 초기화·최적화 | 기존 초기화·새 2단계 감독 | 기존 GS·새 감독 일정 | 기존 최적화·새 감독 경로 | 새 uncertainty sampling·warm-up |
| 모델 변경 | 기존 네트워크 최적화 | 기존 GS densification 사용 | 새 크기·분할 전략 | 고정 network 구조 사용 |
| 추출·후처리 | 기존 표면 추출 사용 | 새 adaptive TSDF·기존 IsoOctree 결합 | 기존 TSDF 사용 | 기존 Marching Cubes 사용 |

## 3. 연구 목적에 대한 연결 — 우리 분석

**‘국소적으로 반영을 달리한다’는 기능 자체보다, 그 규칙이 실패하는 조건을 설명해야 한다.** 읽은 연구는 다음 세 지점을 분리하도록 요구한다.

| 연결 | 근거의 상태 | 우리 조건에서 확인할 질문 |
|---|---|---|
| 영상·기하 불일치 → 감독 신뢰도 | NeuRIS/AGS/VCR/DebSDF가 이미 제어 | 초기 모델과 다르다는 이유로 정확한 감독을 버리는가? 가림·정합으로 생긴 불일치와 구별 가능한가? |
| 신뢰도 → 실제 기하 변수 수정 | VCR의 D-Normal ablation, DebSDF의 renderer ablation | 올바른 감독이 보호 제약·변수 결합·합성 깊이 때문에 필요한 수정에 이르지 못하는가? |
| 수정 → 최종 복원·비악화 | 평균 성능과 구성요소 효과는 검증, 이 연구의 혼합 prior 조건은 미평가 | 같은 건물의 유효 구조·오류·결손에서 개선과 악화를 동시에 설명하는가? |

불일치 원인의 이름을 명시적으로 예측하지 않아도 위 제어를 구현할 수 있다. 다만 ‘원인을 분류하지 않음’과 ‘정확성을 보증함’은 동의어가 아니다. 상관된 예측 오류에서는 일관성만으로 증거의 타당성을 결정하기 어려울 수 있다. 독립 기구축 기하가 이를 보완하는지, 반대로 낡은 기하가 잘못된 합의를 강화하는지를 같은 평가로 확인해야 한다. 이는 후보 질문이며 현재 P1/P2/P3의 원인 확정이 아니다.

최소 비교 순서는 동일 GeoGS·입력·추출에 **최선 전역 설정 → 기존 국소 gate/연속 confidence → 기존 학습형 uncertainty 제어 → 제안 규칙**이다. 필요한 경우 감독 선택과 수정 제약을 교차해 효과를 분리한다. 정상 prior·유효 세부 조건에서 기존 방법의 성공을 포함하며, 제안법이 동등 손상에서 더 복원하거나 동등 복원에서 덜 손상시키지 못하면 차별성 주장을 기각한다. 정확성 GT는 평가 전용으로 유지한다.

## 4. 확인 범위와 이슈

- 논문 원문·공식 코드의 읽기만 했다. 프로젝트 의존성 실행, 학습·렌더·추론·새 방법 실험은 없었다.
- NeuRIS ECCV supplement URL은 이번 web 열람에서 internal error였다. 그 supplement에만 있는 실패 설명은 이번 근거 카드에 재사용하지 않았다.
- VCR PDF endpoint도 이번 web 열람에서 internal error였으나 동일 v2 HTML의 본문·Appendix B를 확인했다.
- DebSDF PDF는 16쪽, HTML은 절·표의 로마숫자 표기 등 편집 형태가 달랐다. 핵심 한계와 ablation 문장을 PDF에서도 대조했으며 쪽수는 PDF의 1부터 세는 상대쪽수다. 두 경로의 파일 전체 동일성을 주장하지 않는다.
- 최초 VCR GitHub API 출력 축약에서 `curl: (23) Failed writing body`가 발생했다. 파이프 수신측 `head` 조기 종료였으며 전체를 읽는 `sed`로 재조회해 동일 pin을 확인했다.
- 공식 코드 공개 HEAD 및 세부 경로를 읽었지만 논문 수치의 충실 재현 여부를 실행으로 확인하지 않았다. 마스크 재포함 여부·detach 경로처럼 직접 보인 사실만 구현 근거로 사용한다.

`scientific_verdict: null`
