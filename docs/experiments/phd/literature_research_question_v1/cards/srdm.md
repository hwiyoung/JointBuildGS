# SRDM — Huang et al. (2018)

- 검토일: 2026-09-09. `scientific_verdict: null`.
- 서지: Xu Huang, Rongjun Qin, Changlin Xiao, Xiaohu Lu, *Super resolution of laser range data based on image-guided fusion and dense matching*, ISPRS JPRS 144, 105–118. [출판본 DOI](https://doi.org/10.1016/j.isprsjprs.2018.07.001).
- 확인 버전: 저자 공개 22쪽 원고, 표제에 “To Appear…subject to minor editorial works”. 아래 페이지는 **이 원고의 PDF 페이지**다. [원문](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf), [출판사 서지·초록](https://www.sciencedirect.com/science/article/pii/S092427161830193X).
- 코드: 원문·출판사와 제목/SRDM+저자+GitHub 검색에서 이 논문의 공식 실행 저장소를 확인하지 못했다. 코드가 없다고 단정하지 않는다. 로컬 `srdm_p1p2p3_v1`은 별도 재구현이며 이 카드의 저자 결과 근거가 아니다.
- 비교 역할: **직접 경쟁하는 기하 복원 방법**. 완성 textured mesh/GS 비교에는 동일 표면·텍스처 후단이 필요하다.

## 1. 문제와 입출력

**[원문 사실]** 희소하고 정밀한 laser range와 고해상도 stereo를 결합해 고밀도 시차·3D 점군을 만든다. 실제 관측은 laser와 영상, 파생물은 정합된 epipolar 영상과 sparse laser disparity다. 외부 사전학습은 제안법에 없다. 전처리에서 subpixel 정합을 요구하지만 취득시점 일치, 모든 LiDAR 점의 무오류는 요구하지 않는다. 시간차·가림·경계 blunder를 명시적으로 다룬다. [§3, pp.3–4; §4.1, pp.13–15](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=3).

**[우리 분석]** 이는 사용자의 “오차·표현 수준이 다른 기하와 영상의 상보성” 자체를 이미 다룬다. 시차가 정의되지 않는 완전 비관측 영역까지 현재 표면을 인증하는 방법으로 확장 해석하지 않는다.

## 2. 기여의 위치

`새 기여`는 저자가 제안한 요소이며 문헌 전체 최초라는 판정이 아니다.

| 요소 | 판정 | 실제 역할 / 근거 |
|---|---|---|
| 입력·전처리 | 기존 방법 사용 | histogram blunder filtering, epipolar projection; §3.1 |
| 좌표·카메라·정합 | 기존 방법 사용 | Zhang et al.의 multi-feature adjustment; §3 도입 |
| 표현 | 기존 방법 사용 | pixel disparity/MAP-MRF; 새로운 3D primitive 아님 |
| 관측모형·렌더링 | 기존 방법 사용 + 새 구성 | HOG+Census, LiDAR 제약, 강도 기반 smoothness; §3.2.1 |
| 증거·감독·제약 | 새 기여 | 약한 prior 검정→불일치 제거→절단 강제약; §3.2.3–4 |
| 초기화·최적화·모델 변경 | 새 기여 + 기존 기반 | non-local orthogonal cost propagation 및 2단계; 동적계획 기반 §3.2.2 |
| 추출·후처리 | 기존 방법 사용 | 시차 삼각측량·TIN 시각화; §4.1 |

## 3. 무엇을 고정하고 수정하는가

**[원문 사실]** 추정 변수는 dense disparity `D`다. 첫 추정으로 LiDAR 시차와 2px 초과 차이나는 점을 제외하고 두 번째 추정에 `C′`를 사용한다. 강한 제약도 식22에서 절단되어 잔여 prior를 절대 고정하지 않는다. 정합·영상은 이후 고정한다. [§3.2.3–4, pp.11–13, 식18–22](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=11).

```text
영상·LiDAR → 정합/rectification → 약한 LiDAR 유도 D1
                                     ↓ 비교·기각
                            C → C′ → 탐색범위+강제약 → D2 → 점군
```

**[우리 분석]** `D1→C′`는 복원 결과가 감독 사용 범위를 수정하는 경로다. “두 단계라 단방향”이라는 분류는 틀린다. 반면 `D2→pose/C′ 재평가`의 외부 반복은 원문에서 확인되지 않는다. 같은 영상 비용이 검정과 복원에 재사용된다. 이를 독립적인 posterior validation이라고 부르면 안 된다.

정합을 고정하면 카메라–깊이 자유도의 혼동과 비용을 줄일 수 있다. 풀면 실제 형상 불일치를 pose가 흡수할 위험이 있다. `C′`를 고정하면 감독이 안정적이나 1차 오기각을 되돌릴 기회가 줄어든다. 이는 **예상 trade-off**이며 본 논문의 실패율 실측이 아니다.

## 4. 실제 검증 범위

**[원문 사실]** Toronto에서 시간차·경계 이상치·가림 제거, Piano/Moshan에서 downsampling과 CPGM/CPSGM 및 image-only 비교, Vaihingen에서 구조·그림자·반복 텍스처를 시험한다. 5×5 조건 시차 오차는 Piano 0.329px/Moshan 0.324px; 지붕 예시는 image-only 0.75px→0.40px다. [§4, Fig.7–14, pp.13–19](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=13).

**[평가 감사]** 저자의 비교는 prior 밀도·propagation·입력 유무 효과를 다룬다. 기준은 원해상도에서 일관성 검사를 통과한 range disparity이며 감독과 완전히 독립한 현재 3D reference라는 조건은 아니다. 항공 도시의 변화 유형별 precision/recall, 유효 구조의 pass→fail, risk–coverage, textured surface 정확도·렌더 성능을 이 결과로 입증할 수 없다. 새 학습 split은 필요 없는 비학습 추정법이지만 scene/parameter 선택의 독립성은 별개다. 계산 복잡도와 pyramid 가속은 설명되나 공통 자원 실측 비교는 추가 확인이 필요하다.

## 5. 남은 오류와 전달 경로

| 상태 | 근거·원인 구분 | 전달 경로 / 다른 가능한 원인 |
|---|---|---|
| **관측된 실패** | [저자 해석] 균일 강도인데 실제 시차 jump가 있는 곳의 mismatch를 결론에 보고; §5 p.20 | 강도 유사성→작은 시차 변화 제약→경계 오차. 수치·사례별 분해는 미제공 |
| **미평가** | [우리 추론] 약한 영상과 틀린 prior가 같은 오답을 지지할 조건 | D1 오판→C′ 오선택→탐색/감독→D2. 관측 실패로 선언 금지 |
| **미평가** | [우리 추론] 과도한 정합 잔차와 실제 변화의 혼합 | rectification 오차가 prior 기각으로 전달될 수 있음. 관측 부족·광도 변화도 대안 원인 |
| **범위 밖** | [우리 분석] 최종 현재 textured mesh 인증·LoD2 usability | 고밀도 점군 성공을 최종 산출물 성공으로 복사하지 않음 |

실패 출처: [§5, p.20](https://cpb-us-w2.wpmucdn.com/u.osu.edu/dist/4/28638/files/2018/07/LiDAR_and_Image_paper-V3_close_to_final-28lqxo6.pdf#page=20). **잔여 오류 자체는 저자가 보고했다.** 로컬 P1 재구현의 부적격 영상쌍 결과를 위 실패에 합산하지 않는다.

## 6. 연구 공백 후보

**이미 해결:** prior로 결손·잡음을 보완하면서 불일치 prior를 기각하고 세부를 복원하는 일반 기능. 이것을 GS로 옮기는 사실만으로 신규성이 생기지 않는다.

**후보 [방법/검증 미분리]:** 동일 강도–상이 깊이 경계, 정합 잔차, 약한 관측이 겹칠 때 기존 edge-aware/segmentation 제약 뒤에도 구조 악화가 남는가? 먼저 SRDM native, 동일 비용의 경계 보강, 다중 stereo 검정, Zhou식 재매칭, 공통 표면 후단을 비교해야 한다. 이들로 해소되면 새로운 판단 모듈 필요성은 기각한다.

**최소 비교:** 원입력·camera·해상도·후단을 고정하고 `image-only / SRDM / SRDM+기존 경계처리 / 수정 후보`; 올바른 prior와 오류 prior, 영상 충분/부족, 정합 양호/잔차를 분리한다. 오류 prior 제거와 올바른 prior 오제거, 표면 정확도·완전성·세부 및 계산량을 함께 잰다. 수정이 기존 성공영역을 악화시키거나 단순 보강과 같으면 알고리즘 공백 주장을 접는다. 실행은 다음 별도 승인 범위다.
