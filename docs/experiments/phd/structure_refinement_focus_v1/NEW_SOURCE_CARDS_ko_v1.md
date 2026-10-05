# 추가 문헌 근거 카드

2026-09-09 · `scientific_verdict: null`

확인 범위가 다른 것은 ‘미확인’으로 남긴다. ‘새 기여’는 저자가 제시한 기여 위치이며 분야 최초성의 독립 판정이 아니다. 실제 장면을 실행하지 않았다. 이미 검토한 문헌은 [기존 카드 색인](../literature_research_question_v1/README.md)을 따른다.

## A. SurfFill

**버전·근거:** *SurfFill: Completion of LiDAR Point Clouds via Gaussian Surfel Splatting*, [arXiv v2, 2026-05-28](https://arxiv.org/html/2512.03010v2), [출판판 DOI](https://doi.org/10.1016/j.cag.2026.104637), [공식 프로젝트](https://linus-franke.com/surffill/). 아래 본문 위치는 arXiv v2를 기준으로 한다. 공식 코드 commit `4849b5b6bd5fb5279913f7cec8e68de09f808e90` 정적 확인.

1. **문제·입출력·가정:** scanner 전처리를 거친 LiDAR 점군과 정합된 사진으로 결손을 보완한 점군을 만든다. 영상 normal·uncertainty는 사전학습 모델의 파생 정보다. 주된 조건은 스캔 결손이며 과거 구조 최신화와 구별한다. 위치: §3–4·Fig1/3.
2. **기여 위치:** 밀도 ambiguity와 집중 성장·필터/샘플링은 새 기여. 2DGS 표현·미분 가능 렌더링과 normal 추정기는 기존 사용. chunking은 기존 접근 활용. 자세한 요소 분류는 아래 공통 표.
3. **고정/수정·피드백:** 학습 Gaussian은 수정한다. 최종 입력 LiDAR 분기는 그대로 합친다. [학습 변수](https://github.com/qy21gafy/SurfFill/blob/4849b5b6bd5fb5279913f7cec8e68de09f808e90/scene/gaussian_model.py#L168), [입력→별도 초기화 점군](https://github.com/qy21gafy/SurfFill/blob/4849b5b6bd5fb5279913f7cec8e68de09f808e90/preprocess/preprocess_scene.py#L14), [최종 합성](https://github.com/qy21gafy/SurfFill/blob/4849b5b6bd5fb5279913f7cec8e68de09f808e90/scene/combineLiDAR.py#L4). 정확한 입력 보존이 목적이며, 이를 풀면 보존을 별도로 검증해야 한다는 것은 우리 추론이다.
4. **검증:** 합성·제거형 참조와 실제 스캔. Table1 component ablation, Table2 기하·시간, Fig10 초기화 대조, Fig11 pose 영향. 기하 평가는 완전 참조에 대한 completion이며 원래 점군과 독립인 실제 장면 전체 GT는 제한된다. NVS held-out 분할은 이번 카드에서 미확인.
5. **남은 오류·전달:** full 결과의 국소 noise와 관측 희소·pose noise 영향은 §6.2–7에서 확인. 잘못된 기존 면의 삭제·이동은 미평가. 그 면이 입력에 있으면 최종 합성에 남는다는 것은 코드 기반 추론으로, 관찰된 실패가 아니다.
6. **공백 후보와 기각:** 구조 보존+세부 보완은 이미 해결 대상으로 삼았다. 부분 오류 구조에 대한 질문은 적용 조건 차이다. 기존 입력 정제·변화 처리 후 SurfFill이라는 단순 조합까지 비교해 추가 필요성이 없으면 새 방법 주장을 기각한다.

코드 세부 주의: [filter_points.py:150–174](https://github.com/qy21gafy/SurfFill/blob/4849b5b6bd5fb5279913f7cec8e68de09f808e90/scene/filter_points.py#L150)는 후보와 후보 이웃의 nearest-LiDAR 거리 합을 사용한다. 개별 점의 1 cm 이내 여부만으로 무조건 제거한다고 단순화하지 않는다. 입력 전 점 보존은 센서 raw 전 점 보존과 다르다.

**비교 지위:** LiDAR+RGB→보완 점군은 직접 경쟁에 가깝다. 원래 연구의 다른 표현·입력 오류·항공 관측·최종 mesh/외관까지 동일 조건으로 입증한 것은 아니다.

## B. LI-GS

**버전·근거:** *LI-GS: Gaussian Splatting with LiDAR Incorporated for Accurate Large-Scale Reconstruction*, [arXiv v1, 2024-09-19](https://arxiv.org/html/2409.12899v1), [공식 프로젝트](https://changjianjiang01.github.io/LI-GS/), [RA-L 출판 DOI](https://doi.org/10.1109/LRA.2024.3522846). 아래 절·표는 v1 기준. 공식 구현은 이번 검토에서 미확인. 제목이 유사한 다른 Li-GS와 구별한다.

1. **문제·입출력·가정:** 함께 수집한 LiDAR·영상·IMU로 큰 장면의 mesh와 렌더를 복원한다. 정제한 전역 LiDAR, pose, 평면 GMM과 depth/normal은 파생 정보다. semantic sky mask에 학습 정보 사용. 시기 불일치 prior의 조건과 다르다. §IV-A.
2. **기여 위치:** GMM 초기화·지속 감독, 기하 기반 밀도 제어·추출이 집중 지점. surfel 표현·렌더·SLAM/정합 도구·Poisson은 기존 사용. §IV-B–D.
3. **고정/수정·피드백:** Gaussian 위치·형상·개수는 바뀐다. 전처리 GMM을 감독·성장/제거·추출에 재사용한다. 최종 관측이 GMM/전처리 정합을 갱신하는 경로는 미확인. coarse-to-fine은 §IV-D의 추출 필터를 가리킨다.
4. **검증:** 자체 6개 장면, 매 8번째 영상 test. 기하 참조는 같은 플랫폼으로 얻어 정제한 조밀 점군. TablesIII–IV 기하/렌더/시간, TableV 초기화·GMM 감독 ablation. 독립 센서 GT나 부분 오류 prior 검증으로 확대하지 않는다.
5. **남은 오류·전달:** TableV의 감독 제거 악화는 full 실패가 아니다. full에서 부분 오류 prior가 남는 원인·경로는 미확인. 고정 GMM의 오류가 반복 감독·추출에 영향을 줄 가능성은 우리 추론이다.
6. **공백 후보와 기각:** 입력 자체의 부분 오류 조건에서 고정 GMM의 타당 범위를 질문할 수 있다. 정합·입력 정제로 충분한지 비교하고, 동시 수집 강점을 오류 prior 복원에 이미 입증한 것으로 쓰지 않는다.

**비교 지위:** LiDAR+영상→표면 복원의 가까운 경쟁. 센서 구성·입력 전처리·참조 계보를 맞추거나 차이를 명시해야 한다. LI-GS의 [공식 프로젝트](https://changjianjiang01.github.io/LI-GS/)는 LiDAR FoV 밖 보완도 주장하므로, 다른 논문의 관련연구 요약만 보고 ‘결손 보완 불가’로 단정하지 않는다.

## C. Cross-Temporal 3DGS

**버전·근거:** *Cross-temporal 3D Gaussian Splatting for Sparse-view Guided Scene Update*, [AAAI 2026 공식 페이지](https://ojs.aaai.org/index.php/AAAI/article/view/37217), [출판 PDF](https://ojs.aaai.org/index.php/AAAI/article/view/37217/41179). 아래 페이지는 PDF 1부터 세며, Methodology·Fig2는 PDF3–5, 실험은 PDF5–7. 공식 구현은 이번 검토에서 미확인.

1. **문제·입출력·가정:** 과거 사진·pose·GS와 소수 현재 사진으로 장면 GS를 갱신한다. 과거 원본 영상은 추가 실제 관측이다. 무색 기존 점군+현재 사진보다 더 많은 정보가 있다.
2. **기여 위치:** 시기 간 정합, 간단한 적응에 의한 confidence 초기화, confidence와 재구성의 반복이 기여. 3DGS 표현·렌더는 기존 사용.
3. **고정/수정·피드백:** 재구성↔confidence→감독 영역의 명시적 반복 경로가 있다. 원본 사진은 재사용한다. 후단에서 카메라 정합을 다시 추정하는 경로와 정적 영역 고정의 구현 세부는 미확인.
4. **검증:** 합성 1·실제 4개 장면; 과거 100장, 현재 train8/test4. Tables1–4는 영상·시간, 정합/confidence/반복 및 관측 수 비교. 독립 metric 표면 정확도를 입증한 표는 이번 확인에서 없다.
5. **남은 오류·전달:** 반복 제거 ablation의 악화를 full 잔여로 옮기지 않는다. 잘못된 confidence가 metric 표면에 남긴 손상은 미확인.
6. **공백 후보와 기각:** 판별과 재구성 반복 자체는 공백이 아니다. 과거 사진 없이 가능한 제어인지와 최종 표면 영향은 별도 질문이다. 입력 차이만으로 신규성을 선언하지 않는다.

**비교 지위:** 과거 GS·영상 사용이 허용되는 갱신 비교와 피드백 구성요소 참고. 무색 외부 기하만 있는 조건의 직접 동등 비교로 두지 않는다.

## 공통 기여 위치 비교

| 요소 | SurfFill | LI-GS | Cross-Temporal 3DGS |
|---|---|---|---|
| 입력·전처리 | 새: ambiguity 기반 초기화 분포; 기존: scanner preprocessing | 새: GMM 구성/초기화; 기존: 센서 처리 | 기존: 시기별 사진·기하; 새: 결합 절차 |
| 좌표·카메라·정합 | 기존 사용; 새 pose 추정 기여 미확인 | 기존 SLAM·BA·영상 정합 사용 | 새: 시기 간 정합 설계; 기존 정합 연산 사용 |
| 표현 | 기존 2DGS surfel | 기존 surfel + 새 평면 GMM 활용 | 기존 3DGS |
| 관측모형·렌더 | 기존 미분 가능 렌더링 | 기존 미분 가능 렌더링 | 기존 미분 가능 렌더링 |
| 증거·감독·제약 | 새: ambiguity·영상 uncertainty의 집중 사용; 기존 normal 추정기 | 새: GMM 및 LiDAR 감독 설계; 기존 photo/sky 구성 | 새: confidence 기반 감독·갱신 |
| 초기화·최적화·모델 변경 | 새: 집중 성장·제어; 기존 densification 요소도 사용 | 새: GMM 초기화·기하 기반 성장/제거 | 새: 간단한 적응→confidence→반복 감독 |
| 추출·후처리 | 새: 보완점 필터·샘플링; 기존 점군 합성 | 새: GMM 기반 추출 필터; 기존 Poisson | 독립 metric mesh 추출 기여 미확인 |

‘새’와 ‘기존’이 같은 셀에 함께 있는 것은 의도적이다. 방법의 요소를 하나로 배정하지 않고 구성 자체의 기여와 재사용한 연산을 구분한다.
