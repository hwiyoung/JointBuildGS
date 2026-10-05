# NeuRIS — 재구성 기하로 법선 감독을 검정하는 feedback

- 상태: 문헌 감사, 2026-09-09. `scientific_verdict: null`.
- 식별: Wang et al., *NeuRIS: Neural Reconstruction of Indoor Scenes Using Normal Priors*, ECCV 2022, proceedings pp.139–155. 확인한 arXiv **2206.13597v2, 2022-10-16**, 17쪽 및 ECCV supplement 7쪽. 아래 본문 쪽수는 PDF 상대쪽수다.
- 원문: [본문](https://arxiv.org/pdf/2206.13597v2), [ECCV supplement](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920139-supp.pdf), [저자 프로젝트](https://jiepengwang.github.io/NeuRIS/).
- 공식 코드: [jiepengwang/NeuRIS](https://github.com/jiepengwang/NeuRIS/tree/fab2cc4ca45847fbee7490e978d3c60c582123b1), commit `fab2cc4ca45847fbee7490e978d3c60c582123b1` (2026-08-09). source read-only, 실행 없음.
- 확인 본문 PDF SHA-256: `b26b21d35264cd26cbd159c81a9d54d047bd84b53e1ce1e703a4002162899dba`. 원문은 임시 열람용이며 저장소에 재배포하지 않았다.
- 비교 지위: **prior를 후단 사진검정으로 기각하는 구성요소의 직접 경쟁**. 기존 ALS/LoD 갱신의 동등 입력 방법은 아니며, SDF는 표현 대안이다.

## 1. 문제와 입출력

실내의 무텍스처 큰 면과 얇은 구조를 함께 복원한다. 실제 관측은 calibrated RGB; 법선은 그 RGB에서 사전학습 모델로 예측한 **파생 prior**다. 기구축 외부 독립기하를 입력받지 않는다. 출력은 SDF 표면·렌더 RGB/법선/깊이. 시기 내 정적 장면과 camera calibration, 국소 평면 patch warp가 전제다. 얇은 구조에서 부정확한 normal prior를 빼도 영상의 세부 단서가 남는다는 관찰에 기대고 있다. [본문 §3, pp.5–9](https://arxiv.org/pdf/2206.13597v2)

모델 prior는 정상 실내 구조에 대한 학습 지식이다. 사전학습 단안법선의 공간방향 정보와 현재 영상의 직접 측정기하를 같은 증거 유형으로 세면 안 된다. 본문은 법선 네트워크를 자체 분할로 재학습했으며, supplement는 1180/433 scene split 및 같은 물리 장면의 다른 sequence도 test로 분리했다고 명시한다. [supp. §1, p.2](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920139-supp.pdf)

## 2. 기여의 위치

| 요소 | 분류 | 내용 |
|---|---|---|
| 입력·전처리 | 사용 | 기존 단안법선 모델·영상 sampling; 법선망 재학습 |
| 좌표·카메라·정합 | 사용 | calibrated pose; camera 재최적화 경로는 미확인 |
| 표현 | 사용 | NeuS형 SDF MLP·color MLP |
| 관측모형·렌더링 | 사용 | NeuS 기반 미분 가능 volume rendering, 깊이·법선 계산 |
| 증거 사용·감독·제약 | 새+사용 | 렌더 기하의 NCC photo-consistency로 법선 감독 선택; 기존 NCC/Eikonal 사용 |
| 초기화·최적화·모델 변경 | 새+사용 | coarse prior fit 뒤 adaptive check; SDF·color 반복학습, sphere initialization |
| 추출·후처리 | 사용 | zero-level marching cubes; 평가 가시성/GT coverage cleaning |

근거: [본문 §3·§4.1, Fig.2](https://arxiv.org/pdf/2206.13597v2), [renderer.py의 추출](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/models/renderer.py#L24), [supp. §1](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920139-supp.pdf). 새 기여 표기는 저자의 방법 구성이지 최초성 판정이 아니다.

## 3. 무엇을 고정하고 무엇을 수정하는가

| 종류 | 변수·증거 | 이유·해제시 예상 영향 |
|---|---|---|
| 수정 | SDF·color network 및 그 렌더 깊이/법선, sampled ray의 prior 사용 상태 | 영상·법선 정보 반영; 충분한 시작 기하 이후 검정 |
| 고정 | 입력 RGB·camera·단안법선 값, 사전학습 법선망 | 문제의 식별범위를 줄임; 함께 풀면 pose/표면/prior가 서로 오차를 상쇄할 수 있음(우리 추론) |
| 강한 선택 | 한 번 불신된 normal prior는 후속 사용에서 제외 | 초기 법선의 세부 과평활을 줄이지만 재채택은 제한 |
| 재사용/갱신 | 관측·prior는 재사용, 렌더 surface와 NCC는 갱신 | 새 관측을 얻는 반복이 아니라 기존 관측 재해석 |

흐름: `RGB→단안법선(고정)`과 `SDF/color→렌더 depth/normal→neighbor patch NCC→법선 감독 gate→SDF/color`가 연결된다. **후단 추정이 감독 선택을 고치는 실질 feedback**이다. 다만 원문 Eq.6 뒤(p.8)는 한 번 기각한 prior의 후속 미사용을 명시한다. 현재 소스도 [exp_runner.py L329–406](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L329)에서 `current confidence AND previous confidence AND normal difference<30°`를 사용하고, 기각 confidence를 1로 저장한다.

구현 세부 차이: 코드 check에는 `normal_peak`·`point_peak`가 쓰이고 평가 자체는 `no_grad`이다. 따라서 'NCC loss를 통해 camera/단안법선망으로 gradient가 흐른다'는 설명은 틀린다. 또한 `normals_gt`라는 코드 변수명은 여기서 입력 예측법선이며 정답법선 주입을 뜻하지 않는다.

## 4. 실제 검증 범위

| 항목 | 확인 사항 |
|---|---|
| 학습·평가 | ScanNet test 8장면, 장면당 약150–600 RGB, 실험 기준 camera; NVS 500별도뷰. Hypersim·Replica·자체 iPhone 실내는 추가 정성 예시 |
| 비교 | COLMAP, NeuS, VolSDF, NeRF, NerfingMVS, DeepV2D, Atlas, NeuralRecon. 일부 실패 장면은 평균에서 빠져 동일 분모가 아님 |
| 효과 분리 | Table 3 F-score: NeuS 0.284, +normal 0.724, +geo-check 0.736. prior 기여와 adaptive 기각의 증분을 구별 가능 |
| 산출/계산 | 표면 Accuracy/Completeness/Precision/Recall/F-score·법선·depth·NVS. 약10시간/RTX2080Ti, 60k+100k iterations |
| 한계 | 시기간 외부기하 검증, 정합오차 factorial, 국소 improvement↔degradation transition·risk calibration은 미평가 |

근거: [본문 §4, Tables 1–3, pp.9–14](https://arxiv.org/pdf/2206.13597v2). [supp. §1·§3, pp.1–3](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920139-supp.pdf)는 평가 mesh를 camera-visible/GT-observed 영역으로 잘라 5cm threshold로 정밀도·재현율을 구함을 밝힌다. DeepV2D는 GT depth scale 보정을 받으므로 honest 입력이 동일하다고 해석하지 않는다. 이 평가 가림 처리는 재구성 방법의 완전성 입증과 분리해야 한다.

## 5. 남은 오류와 전달 경로

| 구분 | 조건·오류 | 경로와 대안 해석 |
|---|---|---|
| 원문 사실·관측된 ablation 실패 | normal 무조건 사용 시 chair leg 소실, adaptive법에서 회복 | 단안 prior 과평활→법선 감독→얇은 표면 손상. Fig.6, p.13를 PDF 이미지로 확인 |
| 저자 관찰·실패 위험 서술 | 저조도, 크게 기운 시선, 벽의 그림에서 법선오류/재구성 artifact | 관측/사전학습 분포→부정확한 법선과 불충분 사진단서. 범주별 실패율·독립 scene 수는 미확인 |
| 원문 사실·수치 안정성 문제 | 무텍스처 patch의 NCC 불안정 | 분자·분모가 작아지는 문제를 numerator offset으로 완화; 모든 textureless 조건 실패 아님 |
| 우리 추론·미평가 | 잘못된 초기 표면이나 camera 때문에 올바른 prior가 기각될 가능성 | 현재 렌더 기하를 사용하는 검정과 기각의 지속성; pose·초기화·가림 등 경쟁 원인 분리가 필요 |

근거: [본문 §4.3](https://arxiv.org/pdf/2206.13597v2), [supp. §1–2, p.2](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136920139-supp.pdf). 실제로 관측하지 않은 자기확증 실패를 논문 사실로 적지 않는다. 일반적인 잔여오류가 모든 prior-guided 방법의 불가피한 한계라는 주장도 하지 않는다.

## 6. 연구 공백 후보

이미 해결된 부분은 **영상이 지지하지 않는 기하 prior의 선택적 기각, 평활 구조와 얇은 세부의 병행 복원, 렌더 기하→감독 선택 feedback**이다. GS로 옮기거나 외부 ALS normal로 바꾸는 것만으로 신규성이 생기지 않는다.

후보는 관측오류·정합오류·자산오류가 함께 있을 때 prior 기각이 국소 최종 기하오차 감소로 이어지는 조건과, 최초 기각 뒤 재검토의 실제 필요성이다. 이는 아직 우리 가설이며, NeuRIS의 직접 실패 증명이 아니다.

최소 비교는 고정가중, NCC 단회 gate, NeuRIS식 지속 기각, 동일 증거로 재채택을 허용한 gate, 강한 순차 정합+gate를 같은 표현·예산으로 비교하는 것이다. 외부prior 품질과 현재영상 강/약, 가림, 작은 pose오차를 분리하고 양쪽 정상 조건도 포함한다. 최종 표면·세부 개선뿐 아니라 원래 유효한 면의 악화도 측정해야 한다.

기각 조건: 기존 persistent gate가 재판정만큼 좋으면 재판정 필요성을 접는다. gain이 단지 더 좋은 initialization/pose에서 오면 판단방식 기여로 주장하지 않는다. textureless의 joint evidence로 오류원인이 식별되지 않으면 자동 수정 주장을 줄이고 보류/추가관측으로 제한한다.
