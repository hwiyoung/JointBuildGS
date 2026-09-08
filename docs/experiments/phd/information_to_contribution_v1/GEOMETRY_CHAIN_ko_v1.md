# 기하 정보가 복원으로 전달되는 경로와 기여의 조건

작성·원문 재확인: 2026-09-09 · 범위: 문헌 및 공식 코드 정적 분석 · `scientific_verdict: null`

이 문서는 **기존 자산의 기하 정보와 영상의 기하·외관 정보를 실제 결과에 전달하는 경로**를 검토한다. 연구 대상을 지붕, GS, 구조 손상 또는 반복 최적화로 결정하지 않는다. LoD2+영상인 GS4Buildings·GeoGS는 입력이 가까운 방법이며, RGB-D·monocular prior·SDF를 쓰는 다른 방법은 원인과 해결 구성요소의 경쟁 문헌이다. 표현을 바꿨다는 이유로 후자의 이미 해결한 원인을 새 공백으로 재선언하지 않는다. 이 분석은 새 실험의 실행 계획이나 권한이 아니다.

## 1. 정보가 있다는 말과 추정할 수 있다는 말의 연결

아래는 문헌에서 사용한 정보의 역할을 종합한 **우리의 문제 분석**이다. 모든 자산과 모든 영상이 이 정보를 충분히 제공한다는 주장은 아니다.

| 정보 | 실제로 제한할 수 있는 기하 자유도 | 성립 조건과 제한 | 잘못 읽었을 때의 문제 |
|---|---|---|---|
| 좌표가 있는 기존 표면·점 | 위치·규모·관측이 약한 영역의 공간적 지지 | 좌표 정합, 그 위치에서의 유효성, 측정/모델링 오차 범위가 필요 | 특정 시기 자산의 존재를 현재 형상의 독립 검증으로 사용 |
| 일반화된 면·구조·연결 | 저주파 형상, 면 방향, 연결된 구조의 후보 | 모델에 생략된 요소와 실제 없는 요소를 구분해야 함 | 세부가 생략된 평면을 모든 화소의 정밀 표면 위치로 감독 |
| 영상의 동명점·패치 대응과 알려진 카메라 | 조건이 충분한 곳의 깊이·경계·국소 형상 | 시차, 해상도, 가림, 반복 무늬, 반사, 카메라 오차에 좌우됨 | 영상에 보이는 무늬 또는 외곽을 이미 식별된 3D 세부로 취급 |
| 영상 색·방향별 외관 | 현재 관측된 외관과 재투영 적합도 | 조명·노출·반사와 기하의 분리가 필요 | RGB 적합도 개선을 표면 정확도 개선으로 대체 |
| MVS 깊이·법선 | RGB 대응 정보를 명시적으로 요약한 표면 후보 | 전처리에서 선택·정제된 결과이며 원 영상의 모든 가설을 보존하지 않음 | MVS와 같은 RGB의 일치를 서로 독립인 두 증거로 계산 |
| 사전학습 깊이·법선 | 영상과 학습 분포를 이용한 형태·방향 후보 | domain gap, 척도, 뷰별 일관성, 출력 해상도 영향 | 학습된 추정을 같은 시기의 직접 깊이 관측과 동등하게 취급 |

따라서 '두 소스가 다른 오차를 가진다' 다음에는 **어느 자유도가 한 소스만으로 불충분하고 다른 소스의 어떤 정보로 제한되는가**가 들어가야 한다. 이어서 정합·가시성·척도·표현 변환을 통과한 뒤에도 그 정보가 살아 있는지 확인한다. 관측으로 구별 불가능한 형상을 prior의 가정으로 채운 경우, 결과가 맞을 수는 있어도 영상으로 검증된 현재 기하라는 결론은 따로 필요하다.

## 2. 이미 밝혀진 전달 경로와 실제 해결

표의 **관찰**은 원문 결과, **개입**은 저자 ablation, **해석**은 저자 원인 설명, **추론**은 우리의 미검증 분석이다. ablation은 해당 실험 조건의 효과를 지지하며 모든 조건에서 유일한 원인을 증명하지 않는다.

| 문헌·정보 → 사용 | 실제로 확인된 성공과 원인 개입 | 남은 오류의 상태와 다음 연결 |
|---|---|---|
| **GS4Buildings**: LoD2 면·깊이·법선 → 초기 표본·감독; RGB → Gaussian 기하·색 최적화 → TSDF mesh | **관찰:** 9개 건물군 평균 M3C2 .405→.272, 가림 구조의 완전성 개선. Fig6의 충분 관측 얇은 구조는 MVS가 더 잘 포착. coarse prior의 강한 정규화 때문이라는 부분은 **해석**. [§3, §4.4, Tables2–4, Fig6](https://arxiv.org/html/2508.07355v1) | 세부 손실은 관찰됐지만 초기 표본·감독·capacity·추출 중 단일 원인은 분리되지 않았다. 이 현상을 출발점으로 삼더라도 **후속 GeoGS로 이미 해소되는 범위부터 제외**해야 한다. |
| **GeoGS**: LoD2 구조 + DA3 영상 깊이 → anchor/protection + 적응 시각 깊이 감독 → mesh | **개입:** Table6은 LoD 초기화만의 효과와 지속 감독·보호·시각 깊이를 구분. 보호 제거 F1@.5 .788→.775, DA3 제거 .788→.772. **관찰:** Table7의 높이/수평 이동·일부 면 결손에도 해당 지역의 기하 지표가 비교적 안정. Table3 평균 향상과 Region9의 2DGS 대비 악화가 공존. [출판 원문 §3.4, §5.2/5.4/5.5, Tables3/6/7; PDF11/15/16](https://doi.org/10.1016/j.isprsjprs.2026.07.011) | Region9 악화의 직접 원인은 **미확인**. 큰 오정합은 §6의 한계 분석이며 Table7을 실패 증거로 바꾸지 않는다. 세부·보호를 이미 함께 다루므로 '같이 최적화한다/보호한다'가 추가 기여가 될 수 없다. |
| **DN-Splatter**: sensor depth 또는 aligned learned depth + predicted normal → depth/normal 감독·초기화 → mesh | **개입:** Table6은 같은 기반의 depth loss를 비교. edge-aware 손실은 depth 오차를 낮추지만 PSNR은 L1보다 낮다. Table7은 같은 loss/초기화 전략에서 2DGS sensor depth F1 .8886, monocular depth .5446, no depth .6039. [v3 §4.1, §5.3, Tables4–8](https://arxiv.org/html/2403.17822v3) | 정보 출처와 감독 형식을 바꾸는 것이 이미 강한 해결책이다. 관찰된 차이는 sensor와 learned depth의 정보 가치가 같지 않음을 보이나, 모든 외부 ALS가 더 낫다는 뜻은 아니다. Table4 smoothness 추가가 모든 지표를 개선하지 않는다. |
| **AGS-Mesh**: sensor depth와 monocular normal → DNC 전처리; 현재 surface normal → ANR 감독 선택; 이후 adaptive meshing | **개입:** Table3의 depth+normal F1 .8880→DNC .9061→ANR .9092. IsoOctree .9157. 반면 NC .8962→.8927→.8888. §E에서 추출 변경이 항상 전체 품질을 높이지 않음을 명시. [v2 §4, Table3, AppendixA.2/E](https://arxiv.org/html/2411.19271v2) | noisy prior 선택과 추출 개선은 **이미 해결한 기능**. 두 평행면의 위치 오차를 normal 일치가 판별하지 못한다는 것은 **기하적 추론**이지 이 논문의 관찰 실패가 아니다. 새 gate가 필요하다는 결론 전에 기존 DNC/ANR 및 직접 depth 검사를 적용할 여지가 남는다. |
| **VCR-GauS**: predicted normal → intersection depth에서 유도한 D-Normal → 위치 갱신 | **분석+개입:** 기존 rendered-normal 감독의 제한된 위치 갱신 경로를 보강. Table4 full F1 .40, D-Normal 제외 .30, confidence 제외 .36; Fig6은 표면 밖 Gaussian 감소를 제시. [v2 §3.3, AppendixA.2, Table4, Figs6–7](https://arxiv.org/html/2406.05774v2) | **감독 정보가 있어도 원하는 위치 자유도를 충분히 갱신하지 못하는 문제의 기존 해결**이다. 기존 normal loss가 위치 gradient를 전혀 주지 않는다고 쓰지 않는다. 새로운 표현의 같은 현상에는 우선 이 경로의 적용 가능성을 검토한다. |
| **HelixSurf**: RGB → MVS → SDF → depth/normal을 다시 MVS에 제공 → 재매칭 → SDF | **개입:** Table3 MVS depth RMSE .147→.106; Table2 textureless 처리 유지 시 ordinary→regularized MVS에 따라 최종 F1 .735→.755. **관찰·해석:** SupplementH/Fig12의 무텍스처 곡면 artifact는 smooth-normal 가정과 관련. [v2 §4.1–4.2, Tables2–3, SuppH](https://arxiv.org/html/2302.14340v2) | 후단 표면으로 앞단 기하를 수정하는 경로와 그 효과가 **이미 존재**한다. 동일 RGB의 재사용도 계산한 대응·기하는 바꿀 수 있다. 외부 자산 활용이나 현재성은 이 실험의 범위 밖이며, 순환 오류 증폭은 여기서 관측됐다고 말할 수 없다. |
| **DebSDF**: calibrated RGB + learned depth/normal → view-dependent uncertainty로 prior 기각·sampling·smoothness 조절 + SDF→density 보정 | **개입:** TableIV/Fig9는 prior filtering 뒤에도 남는 thin geometry를 sampling/smoothness와 rendering 변환으로 보완. TableVIII/Fig12는 **prior 없이 SDF→density만 변경**한 DTU 비교까지 제공한다. TableV는 mesh와 volume-rendered depth/normal을 따로 보고한다. [v3 §III-B–E, IV-C/D, TablesIV/V/VIII](https://arxiv.org/html/2308.15536v3) | '부정확한 prior 기각만으로 부족하고 표현·렌더 경로도 중요하다'는 원인과 해결이 이미 있다. v3 §V의 384×384 제한과 prior 단순 확대의 오류는 **저자 보고**. 더 높은 해상도 적용만으로 새 방법론 공백이 되지 않는다. |

이 표는 하나의 원인으로 수렴하지 않는다. 위치 감독 경로의 약함, 잘못된 감독, 제한된 대응 추정, 렌더 변환, 최종 표면 추출은 **서로 다른 곳에서 생기는 병목**이다. 또한 정보가 부족한 경우의 구조 prior 성공을, 정보가 충분한 경우의 prior 악화로 지우지 않는다.

## 3. 고정된 입력과 수정 가능한 결과를 구별한 구현 확인

| 확인한 구현 | 원 증거가 고정이어도 수정되는 것 | 확인한 경로·버전 |
|---|---|---|
| GS4Buildings | Gaussian 위치·방향·크기·색·개수, 렌더 잔차 및 depth median scale. LoD2 mesh·camera 자체의 수정과 구별 | [train.py](https://github.com/zqlin0521/GS4Buildings/blob/f0be3e257ee6f58e42d1aa3258810c7b78866a7d/train.py#L147), `f0be3e257ee6f58e42d1aa3258810c7b78866a7d`. 공개 depth weight는 5k–7k 증가 뒤 유지: 논문 phase2 서술과 별도 확인이 필요 |
| GeoGS | Gaussian과 DA3 loss의 가중 제어. offline LoD2/DA3/camera를 다시 추론하지 않음. 보호는 기하 gradient 감쇠와 density 변경 제한 | [train.py](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L603), `db40c95c657ec03ff21c83cb99cf39f4e90247a6`. gradient 배율을 Adam 이동 배율로 등치하지 않음 |
| AGS-Mesh | DNC confidence를 읽어 depth를 선택하고, 현 surface normal에서 ANR 선택을 다시 계산; Gaussian 수정 | [train.py](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py#L119), `93fda851a20cf0bd5fce642c46da0c83c637165e` |
| VCR-GauS | 고정 predicted normal에 대해 현재 rendered normal의 일치로 confidence를 갱신하고 depth/normal loss로 Gaussian 수정 | [trainer.py](https://github.com/HLinChen/VCR-GauS/blob/aa715d19bfacfa9d491f477c572eab1839dcee3e/trainer.py#L261), `aa715d19bfacfa9d491f477c572eab1839dcee3e` |
| HelixSurf | 추정 surface를 export하여 앞단 PatchMatch 입력을 바꾸고 실제 재매칭. camera/RGB 고정과 양립 | [surface export](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/scripts/train.py#L561), [next_mvs.sh](https://github.com/Gorilla-Lab-SCUT/HelixSurf/blob/3b46727bf76b4f089afbc79a37a6fb37dc9c66c2/run_scripts/next_mvs.sh#L20), `3b46727bf76b4f089afbc79a37a6fb37dc9c66c2` |
| DebSDF | 고정 monocular targets를 평가하는 uncertainty·mask·surface가 갱신됨. sampling용 uncertainty map도 정해진 시점에 다시 생성. 별도 prior network 재학습과 구별 | [loss.py](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/loss.py#L238), [refresh](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/training/debsdf_train.py#L298), [curvature mapping](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/network.py#L569), `4580c8e1c9872e65f6cb9fc55607162f57ab7a54` |

DN-Splatter의 [공식 저장소](https://github.com/maturk/dn-splatter/tree/97588b4290128ce7ba6fdbfaac3020b42b17de4c)는 HEAD와 README의 통합 구조까지만 이번에 확인했다. AGS-Mesh 통합 코드가 포함되어 있으므로 현재 기본 실행을 원 DN-Splatter 논문의 동일 조건으로 간주하지 않는다. 여기서 논한 DN-Splatter ablation은 논문 근거이며 새 코드 재현 결과가 아니다.

## 4. 남은 현상에서 기여로 가기 전 제거할 네 가지 설명

아래는 **우리의 원인 분리 제안**이다. 모든 논문을 한꺼번에 실행하자는 계획이 아니다. 한 실제 현상의 입력·출력 계약에 맞는 가까운 비교부터 적용하며, 해당 조건을 받지 못하는 방법은 직접 순위 비교보다 구성요소 또는 별도의 적응판으로 검토한다. GT를 사용하는 진단 교체는 평가 전용 참고점이며 배포 가능한 방법의 입력이 아니다. 주어진 후보/교체 조건의 결과를 모든 연속 재추정의 일반 상한으로 간주하지 않는다.

| 검토할 현상 | 가장 가까운 후보 제거 대비 | 무엇이 나오면 기존 설명으로 충분한가 | 남아야 추가 기여를 논할 수 있는 것 |
|---|---|---|---|
| 영상에서 포착할 수 있는 형상이 prior 결합 뒤 사라짐 | 문서·코드 일치 GeoGS 또는 직접 대응 방법 → 동일 입력의 prior 가중·마스크·정합 정제; 초기화/감독/보호·density는 별도 요인으로 구분 | 기존 설정 또는 고정 국소 가중으로 유효 영역 품질을 유지하며 복원되면, 새 판단·반복을 요구하는 후보를 기각 | 기존 정제 뒤에도 반복되는 오류와, 특정 감독 또는 제한 규칙을 바꿨을 때만 해소되는 대응 관계 |
| prior/normal이 적절해도 표면 위치나 얇은 구조가 틀림 | 원 추정기의 감독 경로 수정(VCR 또는 DebSDF가 이미 해결한 경로), 충분한 sampling/capacity, 같은 후단 추출 | 기존 gradient·rendering·sampling 보정으로 해결되면, 소스 선택 오류라는 설명을 기각 | 알려진 경로 보정으로 설명되지 않는 새 병목. 고유한 자유도·스케일·조건의 분석이 있어야 하며 단순 이식은 방법론 신규성으로 확정하지 않음 |
| MVS 결손/오류가 후단 표면에도 남음 | 강한 MVS 정제 → 고정 MVS 기반 표면 추정 → HelixSurf식 재매칭의 기존 효과를 확인 | 기존 재매칭 또는 한 번의 정제로 충분하면 새 반복법의 필요성 기각. 추가 영상에서만 해결되면 정보 획득 조건 문제 | 같은 허용 정보에서 기존 재추정도 놓치는 대응/가시성/표현 제약이 확인되고 새 처리가 이를 해소 |
| 중간 기하가 개선되어도 최종 mesh는 악화 | 같은 최종 상태의 depth/normal/표면 직접 평가와 TSDF·적응 추출을 비교; 해상도·truncation·crop 통제 | 추출만 바꾸어 해결되면 새로운 융합 optimizer 필요성을 기각 | 기존 추출 조정으로 충분하지 않은 정보 손실과, 중간·최종 지표를 함께 개선하는 원인에 맞춘 변경 |

네 대비 모두에서 **같은 정보·실행량·출력 범위의 비교**가 중요하다. raw ALS와 LoD2의 입력 변환, sensor depth와 learned depth의 정보량, 더 많은 training images, 서로 다른 mask·추출 해상도가 바뀌면 새 규칙의 효과와 섞인다. 평균 이득뿐 아니라 어느 부분을 복원했고 어느 부분이 악화됐는지 확인하되, 악화가 반드시 개선의 비용이었다는 인과를 미리 넣지 않는다.

## 5. 기존 JointBuildGS 결과를 이 연결에 넣을 수 있는 범위

[현재 P2 검토](../geogs_p1p2p3_v1/P2_REVIEW_ko_v1.md)와 [요인 대비](../geogs_p1p2p3_v1/FACTOR_CONTRASTS_ko_v1.md)는 실제 완료된 ALS 파생 입력 18조건을 기록한다. P2의 native 보호에서 depth .005→.0005는 ROI 평균 PSNR +5.462163dB와 final1024 raw F1@.5 .6141→.5238을 함께 보였다. 이는 **이미 있는 두 출력의 비동행 현상**으로 활용할 수 있다. 그러나 좋은 외관을 얻기 위해 구조를 반드시 희생했다는 인과, coarse prior가 진짜 세부를 억제했다는 인과, 원래 LoD2 GeoGS의 실패는 이 숫자만으로 확정되지 않는다.

이 로컬 사례에는 ALS 표면화, 좌표계, 공통 anchor, adaptive DA3, density 보호, 512/1024 추출 및 후처리가 관여한다. 보호 해제도 gradient와 density 제한의 묶음이다. 같은 조건의 완성된 반복 쌍은 없으며 보조 P1/P2는 CUDA OOM, P3은 미시작이다. 따라서 위 표의 **어느 비교를 먼저 좁힐지 정하는 현상 근거**이며 신규성이나 단일 원인의 증거가 아니다. 이번 작업은 해당 지표나 payload를 재계산하지 않았다.

## 6. 현재 근거로 끊김 없이 말할 수 있는 연결

기존 기하는 영상에서 약하게 정해지는 위치와 구조를 제한할 수 있고, 영상은 자산에 없거나 달라진 관측 가능한 형상과 외관을 제공할 수 있다. 이 상보성의 실제 이득은 여러 기존 방법에서 이미 확인되었으므로 그 이용 자체는 추가 기여의 근거가 아니다. 다만 정보가 입력에 존재하더라도 대응 추정, 감독이 연결되는 자유도, 최적화의 표본 배분, 렌더 변환과 표면 추출에 따라 최종 복원에 전달되지 않는 경우가 있으며, 이 중 상당수 원인과 개선은 VCR-GauS·DebSDF·HelixSurf 등에서 이미 분리되었다. 따라서 남은 실패를 발견했을 때는 가까운 기존 보정으로 설명하고 해결할 수 있는 부분부터 제외해야 한다. 그 뒤에도 허용된 입력이 정답을 구별할 수 있는데 특정 조건과 추정 규칙의 관계 때문에 정보가 쓰이지 않는다면, 그 관계를 규명하고 기존 해결 범위를 넘어서는 처리를 검증하는 것이 방법론적 기여 후보가 된다. 반대로 기존 처리로 해소되면 그 방법 후보를 접고, 정보 자체가 부족하면 필요한 관측·적용 가능 범위를 밝히는 질문으로 정리해야 한다. 현재 문헌만으로는 하나의 새 원인이나 GS·명시적 판단·반복의 필요성이 확정되지 않지만, 어떤 결과가 그 주장을 성립시키거나 기각하는지까지는 연결할 수 있다.

## 7. 확인 범위와 읽기 오류 기록

- 기존 `literature_research_question_v1` 카드와 `complementarity_v1`은 탐색 색인으로만 사용했다. 위 주장에 해당하는 원문 본문·표와 고정 공식 코드를 다시 읽었다. 문헌 평가 결과를 독립 재현 결과로 표시하지 않았다.
- GeoGS 출판 PDF는 기존 Docker 전문 추출과 원본을 이용했다. 원본 SHA256 `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`. HelixSurf는 arXiv v2 PDF/Supplement와 이번 HTML을 함께 확인했다. DebSDF는 검색어의 ICCV 가정을 채택하지 않고 **TPAMI2024, arXiv v3 2024-07-11**을 확인했다.
- DN-Splatter 공식 학회 PDF의 web 열기는 Internal Error였다. arXiv v3 전문으로 해소했다. `/tmp` 초기 파일 탐색에서 무관 서비스 디렉터리 권한 오류가 발생하여 알려진 문헌 경로로 한정했다. HelixSurf의 `scripts/next_mvs.sh` 경로는 존재하지 않아 `run_scripts/next_mvs.sh`로 바로잡았다. VCR 임시 파일 이름 추정도 존재하지 않아 고정 공식 raw 소스를 사용했다. 서비스나 권한은 변경하지 않았다.
- 새 방법·학습·렌더·scene 실험을 실행하지 않았다. 문헌 코드 clone과 정적 읽기만 수행했다. 이 문서의 새 비교들은 실행되지 않은 원인 분리 제안이다.
