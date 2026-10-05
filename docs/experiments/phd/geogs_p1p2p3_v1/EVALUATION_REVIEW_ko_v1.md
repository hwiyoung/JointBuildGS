# GeoGS 세 지역 평가 설계 독립 검토

2026-09-08 · `PHD-GEOGS-P1P2P3-v1` · 실행 전 검토 · `scientific_verdict: null`

이 문서는 실험 결과가 아니다. 계획의 평가 조건을 고정할 때 해결할 사항과 실제 결과의 최소 준비 요건을 기록한다. [전문 감사](PAPER_AUDIT_ko_v1.md), [v5 프로토콜](../wu_vallet_matched_v5/PROTOCOL_ko_v5.md), [v7 결과](../wu_vallet_synthesis_v7/RESULTS_AND_CONTRIBUTION_ko_v7.md), `configs/phd/wu_vallet_matched_v5/evaluation_v5.json`과 기존 evaluator의 gate를 읽었다. 이전 코드·입력·산출물은 변경하지 않았다.

## 1. 3×2 제어 계획 검토

refinement 깊이 계수 `0.005 / 0.0005 / 0`와 구조 보호 `native / full release`를 교차하는 6조건은 깊이와 보호의 개별 효과 및 상호작용을 분리하는 데 적합하다. 0.0005는 코드 기본값의 1/10인 **이번 실험의 사전 선택값**이며 원문에서 최적값이라고 제안한 수치가 아니다. 동일한 8,000회 anchor 이후 30,000회까지 진행하면 초기화·anchor에 대한 노출은 공통이고, refinement 제어 효과를 비교할 수 있다.

필수 확인은 다음과 같다.

1. 완전 anchor는 정확히 어느 연산 뒤인지 정한다. 8,000회 loss/optimizer·density control·보호 집합 생성의 순서가 checkpoint와 어긋나면 시작 상태가 달라진다. 모델·optimizer뿐 아니라 tensor 순서, mask, gradient hook, RNG, 카메라 표본 추출 stack, scheduler 및 adaptive-depth 이력을 보존한다.
2. `full release`는 α=1뿐 아니라 보호된 Gaussian의 clone/split/prune 제한도 해제한다. native 상태 복원은 hook의 대상 tensor와 mask 길이가 현재 parameter와 일치하는지 검증한다. SH·opacity 등 원래 허용되는 갱신을 별도 새 제어로 변경하지 않는다.
3. 원본 uninterrupted native와 분기 native가 같은 자료·seed·30,000회에서 일치하는지 먼저 확인한다. GPU 비결정성이 있으면 tensor hash 동일성만 요구하거나 허용오차를 결과에 맞춰 넓히지 않는다. 독립적인 짧은 restart 동등성 검사와 학습 로그·표면·렌더 편차를 함께 남기고, 분기 원인이 분리되지 않으면 `same_anchor_effect` 해석을 보류한다.
4. anchor의 추출 mesh와 고정 평가 시점 렌더를 저장한다. 기본 최종 저장만으로는 refinement에서 어느 변화가 발생했는지 확인할 수 없다.
5. 0깊이/full release도 prior 초기화·anchor에서 출발한다. 명칭은 refinement 제약 해제이며 image-only가 아니다. 한 seed는 제어 진단이다. seed 변동성·일반화·통계적 우위는 별도 반복 검증이 필요하다.

## 2. 표면 거리와 점군 거리의 구분

기존 Wu v5는 전체 native point의 최근접 거리 평가다. 그 source gate·hash 기록은 유용하지만, 이를 Gaussian 중심점에 적용하는 것으로 새 최종 표면 평가를 충족할 수 없다. UAS가 점군이고 GeoGS가 삼각 mesh일 때 양방향은 정확히 같은 종류의 연산이 아니다.

| 방향·입력 | 계산 제안 | 해석 |
|---|---|---|
| UAS→GeoGS mesh | BVH/raycasting acceleration을 이용한 각 유효 UAS점의 정확한 최근접 **삼각면** 거리 | UAS가 실제 관측한 표면의 재현·완전성. mesh 정점까지의 거리가 아님 |
| GeoGS mesh→UAS | 면적 균등 표본의 UAS 최근접점 거리; 표본 면적 가중 평균·분위수·문턱 통과율 | 참조가 점 표본이므로 유한 UAS 밀도에 영향받는 surface-to-point discrepancy |
| ALS·영상 native point→UAS, 역방향 | 기존 원점 거리 계산을 별도 native-point 표에 유지 | 입력 원점의 차이. 최종 표면과 표현·밀도가 동일하다고 가정하지 않음 |
| 실제 공급 ALS mesh·영상 mesh→UAS, 역방향 | 위 GeoGS와 같은 표면 샘플링·삼각면 거리 정책 | 입력의 표면화 손실을 포함한 공통 표현 비교; native와 차이를 함께 제시 |
| Gaussian centers↔UAS | 보조 표로만 산출 | primitive 배치 진단이며 최종 표면 성능 아님 |

`accuracy/precision`은 참조로 평가할 수 있는 예측 표면의 문턱 이내 비율, `completeness/recall`은 유효 참조 표본의 예측 mesh까지 문턱 이내 비율로 분모를 명시한다. F1은 그 조화평균이다. 두 방향의 거리 연산과 밀도 통제가 다르다는 사실을 metadata에 저장하고, 정확한 양방향 연속 표면 거리라고 이름 붙이지 않는다. 참조 mesh가 없는데 만들었다고 가정하지 않는다.

참조의 국소 평면을 추가 활용하려면 독립적인 참조 표본의 support·normal 안정성·곡률/경계 제외 규칙을 먼저 고정해야 한다. 무제한 평면 확장은 실제 관측되지 않은 영역을 참조 표면으로 만들고 거리를 인위적으로 줄일 수 있다. 이번 최소 구현에서는 point-to-triangle과 area-sampled surface-to-point를 정직하게 구분하는 것으로 시작할 수 있다.

## 3. 밀도·피복·결손 통제

- 표면 표본은 triangle area 비례·고정 seed·고정 단위 면적당 밀도로 생성하고 실제 face ID·barycentric 좌표 또는 재생 가능한 표본 seed를 남긴다. 정점 수를 같게 하거나 mesh별 임의 동일 점 수만 사용하는 방식은 면적 가중을 보장하지 않는다. primary 표본 해상도와 더 조밀한 sensitivity를 실행 전 고정하고, 결과를 보고 변경하지 않는다.
- UAS의 전체 native-point 표와 고정 3D grid 기준의 공간 균형 표를 구분한다. 대표점은 실제 UAS 원점 중 선택하여 원행을 유지할 수 있다. grid의 원점·해상도·대표점 규칙을 공통으로 고정한다. XY만의 균등화는 지붕·벽·다층 표면의 중첩을 지우므로 전체 표면의 유일한 평가 단위로 삼지 않는다.
- UAS가 있는 곳만 mesh를 자른 뒤 점수를 계산하면 멀리 잘못 생성한 표면이 사라질 수 있다. 전체 고정 영역의 예측 surface area, 참조로 판정 가능한 area, 지원 불명 area를 함께 보고한다. 참조 지원 불명 예측을 자동 정답 또는 실패로 분류하지 않는다.
- nearest-UAS 거리만으로 참조 피복 부재와 잘못된 잔존 구조를 구분할 수 없다. 가까운 다른 높이의 지붕도 동일 XY에 있을 수 있다. reference-support mask는 센서 피복·표면 support 근거로 산출하며, 큰 편차라는 이유만으로 그 예측을 평가에서 제외하면 안 된다.
- 참조 영역에 prediction이 전혀 없으면 recall/F1은 0이며 reconstruction failure를 기록한다. reference가 없으면 reference-based metric은 `null/NA_REFERENCE_ABSENT`다. 계산 실패·표면 추출 실패·참조 부재를 서로 다른 상태로 저장한다. 빈 prediction의 accuracy는 분모 0이므로 null로 남겨도 recall/F1=0과 실패 상태를 함께 유지한다.
- 고정 prism과 경계 buffer/포함 규칙은 모든 조건에서 같다. mesh를 prism에 clip할 때 생성된 절단면·경계 삼각면의 인공 면적을 채점하지 않도록 실제 원래 표면 부분만 남긴다. UAS crop 경계 밖 참조가 필요하면 근거와 동일한 context 정책을 먼저 고정한다.

문턱은 논문과 연결되는 0.2/0.5m를 반드시 포함하고, 기존 개발과 연결되는 0.1/0.25/1/2m 등을 공통 sensitivity로 고정할 수 있다. 모든 문턱을 보고하며 구역별 유리한 값을 주지표로 고르지 않는다. mean·median·p90/p95, precision/recall/F1과 실제 유효 분모를 함께 기록한다.

## 4. 관찰 영역과 실제 오류의 이름

기존 P1/P2/P3 범위는 이미 결과를 본 개발 영역이다. `blind`나 confirmatory test로 부르지 않는다. 별도의 세부 영역은 **GeoGS 결과를 보기 전에 입력만으로** 고정할 수 있다. 과거 ALS/영상 기하 불일치는 ‘수정 필요 확정’이 아니라 ‘불일치 후보’다. 영상 지원 부족은 영상 수·각도·가시성 등 사전 고정 근거로 정의한다. prior/영상 일치도는 현재의 정답을 확정하지 않는다.

실제 ‘수정 필요/유지할 구조’ 해석은 모든 실행을 봉인한 후 평가 전용 현재 UAS와 동일 사진을 확인해 추가한다. 지역 전체의 source authority를 미리 정하지 않고, 참조 불확실성과 관측 부족이면 판단 불가로 남긴다. 이 평가 후 라벨은 loss·정합·seed·arm 선택으로 되돌리지 않는다. 결과로 선정한 개선·악화 사례는 그 선택 규칙과 전체 후보 수를 공개하며 독립 사전 사례와 구분한다.

잘못된 잔존·이중면 수치에는 reference-supported 현재 표면과 분리된 다른 출력면이 있다는 근거가 필요하다. 단일 nearest-distance 또는 2D 점유 셀만으로 구조를 세지 않는다. 다층 구조가 가능한 같은 XY에서 정상적인 두 표면을 오류로 자동 분류하지 않고, 고정 단면·현재 영상·reference support와 함께 판정한다.

## 5. 실제 렌더와 평가 영상 독립성

train/eval image ID와 파일 SHA, 카메라 ID·좌표, resize/crop/intrinsics 변환을 manifest로 고정한다. 초기화 가시성, DA3 depth, MVS·영상 mesh, 색 초기화가 읽는 영상 집합도 각각 기록한다. 평가 RGB를 제외해도 DA3/MVS가 그 영상을 이용했다면 전체 pipeline의 독립 optical holdout은 아니다. 기존 depth의 생성 영상 membership이 불명이면 `INDEPENDENCE_UNVERIFIED`로 표시하고, 정직한 독립 NVS 평가가 필요하면 train-only 입력으로 해당 파생물을 새로 생성해야 한다.

PSNR·SSIM·LPIPS는 동일 평가 RGB·카메라·출력 해상도·색 범위로 실제 공식 renderer 결과에 계산한다. full-frame 지표와 고정 regional projection crop 지표를 함께 낼 수 있으나 crop/mask는 결과 잔차를 보고 선택하지 않는다. prediction alpha가 낮다는 이유로 그 픽셀을 평가에서 빼지 않는다. LPIPS backbone·weights SHA·라이브러리 버전과 SSIM 구현을 기록한다. 평가 중 fitting·exposure 재조정이 있으면 모두 동일한 사전 규칙으로 공개한다.

## 6. 정성 화면과 최소 결과 준비 요건

비교 화면은 prior native/공급 표면, 영상 native/표면, anchor, GeoGS native, 변경 결과, UAS를 같은 3D 카메라로 보여야 한다. source 종류를 표시하고 과거 Wu 화면을 GeoGS 결과로 재사용하지 않는다. 동일 사진 시점에서는 사진·native renderer·변경 renderer와 고정 error map 범위를 나란히 제공한다. 정량용 표면과 화면 경량화를 위한 표본은 별도 식별한다.

단면 위치·폭·축척·색 범위·높이 기준을 조건 간 고정하고, 사용자가 파라미터를 확인할 수 있게 한다. P1/P2 과거면 잔존·현재면 회복, P3 구조 보완·영상 오류 유입·세부 회복을 각각 사례로 확인하되, 개선·유지·악화·판단 불가를 모두 찾고 선택 이유를 남긴다. 실제 mesh/이미지 로딩·동기 카메라·region/arm 전환·렌더 비교를 브라우저에서 검사하고 screenshot/log·URL/파일 경로·사용법을 제공한다.

최소 완료 결과는 다음으로 판단한다.

1. 세 지역의 6조건과 공통 anchor, 버전·조건·명령·입력·완료 iteration·편차·실패 영수증이 존재한다. GPU peak allocated/reserved memory, wall time, rendering/extraction 시간·출력 크기를 별도 기록한다.
2. 실제 공식 경로의 최종 surface와 heldout renders가 있고, 실패한 조건도 상태 행과 결손으로 남는다. 미실행을 숫자 0으로 채우지 않는다.
3. `geometry_metrics.csv`, `render_metrics.csv`, `resources.csv`와 per-point/per-sample 거리·weight·membership·status의 NPZ/Parquet 등 기계 판독 원자료가 연결된다. 각 행에 region/arm/stage/seed, 표본/참조 hash, ROI, 문턱, 유효 분모를 넣는다.
4. 실제 단면·거리 지도·동일 시점 렌더 그림과 검증된 비교 화면을 제공한다. 평균 개선만으로 손상·결손 사례를 숨기지 않는다.
5. 관찰→입력 변환/제어 영향→원문 관계→추가 수정 필요성→후속 질문을 분리한 분석과 다음 세션 인계가 있다. 성능 우위·반복 재판단의 필요성·과학적 판정은 자동 확정하지 않는다.

## 7. 조기에 밝혀야 할 장애 요인

| 항목 | 현재 확인 또는 위험 | 해소 전 가능한 주장 |
|---|---|---|
| 완전 checkpoint | 원본 capture에 trainer·보호·RNG 전체 상태가 없음 | 동일 파일에서 시작했다는 사실만으로 같은 anchor 실행 동등성 보장 불가 |
| UAS 좌표·수직 기준 | 기존 v5 설정은 working EPSG:25832와 UAS header EPSG:32632, 기존 shift/ALS Z bridge 유지 및 새 datum/epoch 교정 없음을 명시 | 고정 frame 수치 편차. 독립 metadata로 연결을 확정하기 전 보정 완료 절대 정확도라고 부르지 않음 |
| reference surface coverage | UAS 원점은 완전한 연속 표면이 아님 | 지원된 참조에 대한 거리·recall. 큰 NN 거리만으로 철거/잔존 확정 불가 |
| optical holdout | 기존 파생 depth/mesh의 생성 영상 목록을 확인해야 함 | membership 불명 결과는 독립 NVS로 표기 불가 |
| ALS→mesh 변환 | raw ALS와 LoD2 구조 표면은 입력 성질이 다름 | 공식 학습기+ALS 입력 변경 진단. 원 LoD2 방법의 완전 재현 성능과 구분 |
| 실제 결과 부재 | 실행·추출·렌더 완료 전 | 계획·문헌 검토·CPU probe만으로 실험 분석 완료 판정 불가 |

이 장애 요인의 기술적 점검·허용된 입력 준비는 진행할 수 있다. 해소되지 않은 근거를 UAS fitting이나 사후 유리한 조건 선택으로 메우지 않는다. 비교 가능 범위와 남은 미확인 항목을 결과의 상태로 명시한다.

## 8. 실행 평가 코드 독립 검토 추가 기록

`evaluation/run_evaluation.py`와 `seal_candidates.py`를 참조 payload 접근 없이
검토했다. 다음 사항을 새 코드에 반영했다.

- 후보 봉인은 원래 학습 전 input manifest의 split·카메라 파일·평가 사진·공급
  ALS 표면 hash를 재검증하고 후보 봉인 파일 목록에 포함한다. 실행 receipt의
  지역·조건·phase·config·input manifest 식별자도 일치해야 한다. 실제 저장 렌더의
  크기·RGB 모드와 원 사진에 대응하는 공식 GT export 픽셀을 확인한다.
- 점군 baseline의 역방향 원자료 이름을 `reference_to_prediction_point_distance`로
  명확히 했다. 공통 그림 접근에는 `reference_to_candidate_distance`를 사용한다.
  mesh의 `reference_to_triangle_distance`와 혼동하지 않는다.
- 원점 voxel 선택 후 원행 복구, 알려진 거리, 참조 부재와 복원 실패, 빈 결과 그림,
  잘못된 문턱/비유한 입력, 카메라·split 변경, 다른 phase/input receipt를 포함한
  합성 fixture 8개가 Docker에서 통과했다(1.226초). 별도 실제 공식 캐시 VGG를
  사용하는 렌더 평가 검증 12개도 통과했다. 지역 성능을 측정한 테스트는 아니다.

후속 분석의 정직한 층화는 prior–UAS 일치/불일치라는 평가 전용 기하 관계,
ALS/MVS 표본 지원 유무, train 카메라 투영 기회 수를 구분한다. 투영 기회 수는
가림·텍스처·노출을 보장하지 않는다. 실제 수정 필요/유지/관측 부족은 사진·입력·
참조를 함께 검토하고 판단 불가를 허용한다. 이 라벨을 학습·정합·제어 선택으로
되돌리지 않는다. 층화 전체 분모와 사례 선택 규칙을 기록한다.

메모리상 `sample_surface`는 면적/spacing² 개의 표본을 만들고, clip은 일부
삼각형을 Python 객체로 확장한다. 0.05m 표본에서 10,000m² 표면은 약 400만
표본이므로 수백 MB 이상과 원 mesh·BVH 공간이 필요하다. 자원 한계가 발생하면
실패를 기록하며, 점수에 따라 밀도나 ROI를 줄이지 않는다. baseline NPZ도 사전
식별자를 검증해야 하며, 읽은 뒤의 hash 기록만으로 사전 고정이 증명되지는 않는다.

## 9. 전체 추출 실패와 평가 영역 내부 결손의 구분

현재 후보 봉인은 모든 고정 조건의 학습·렌더·메시 추출이 기술적으로 완료된
`PASS` 산출물을 요구한다. 따라서 정상적으로 추출된 전체 메시가 고정 평가
영역에서 비어 있는 경우는 `RECONSTRUCTION_FAILURE`와 참조가 있을 때의 F1=0으로
평가하지만, 전체 메시 생성 자체의 OOM·import·런타임 오류는 이 단계에 도달하지
못한다. 이런 기술적 미가용을 참조 부재 NA나 자동 기하 F1=0으로 바꾸지 않는다.
조건을 조용히 생략하지 않고 실패 영수증을 보존하며, 복구 가능한 실행 오류는
새 경로에서 복구한다. 복구 후에도 전체 기하 출력이 불가능하면 별도의 명시적
실패 평가 계약이 필요하므로 현재의 엄격한 전체 후보 봉인을 통과한 것으로
보고하지 않는다. 이 정책은 아직 관측되지 않은 전체 추출 실패를 성능 판정으로
미리 단정하지 않는다. `scientific_verdict: null`을 유지한다.
위 전체 최종 표면의 필수 조건은 유지한다. 이후 실제 보조 추출 OOM에 대해 [별도 자원 계약](EXTRACTION_RESOURCE_AMENDMENT_ko_v3.md)을 고정했다. 선택 anchor1024/final2048만 확인된 MEMCG 실패를 명시적으로 가용성 표에 남길 수 있으며, 필수 final1024/final512/공통 anchor512의 실패는 계속 봉인을 차단한다.

## 10. 고정 참조 prism의 해석 범위

참조 생산 코드 `scripts/phd/wu_vallet_regions_v4/evaluate_regions.py`는 UAS를 이미 고정 XYZ prism으로 잘라 `reference.npz`에 저장하고 모든 점의 해당 범위 소속을 검사한다. 이 확인에서는 코드만 읽었고 UAS payload는 열지 않았다. 이번 평가는 이 동일한 봉인 참조를 사용한다.

따라서 국소 XY셀에 관측 UAS 점이 없다는 사실만으로 센서 미피복·가림·실제 빈 공간·고정 Z 범위 밖의 현재 표면을 구분할 수 없다. 이를 자동으로 과거 구조의 유효/무효 또는 시간적 변화 정답으로 바꾸지 않는다. 경계 부근 거리는 prism 밖 참조를 포함한 전체 공간의 정확도가 아니라 고정 관측 집합에 대한 거리다. 원래의 공통 범위와 파일은 유지하며, 실제 사진·단면과 함께 이 해석 한계를 보고한다.

## 11. 기록된 시간의 측정 구간

지역 `train/render/metrics_receipt.json`의 `wall_seconds`는 `run_regional_phase.py:150–250`의 단계 driver clock 구간이다. 원 subprocess 실행에 더해 이 구간의 기록 작성·종료 감시·종료 후 산출물 확인과 SHA 계산을 포함한다. 순수 GPU 최적화 시간이나 원 subprocess만의 시간이라고 부르지 않는다. Docker 시작과 그 전에 이루어진 입력/소스 확인, 추출 잠금 대기 등은 같은 구간에 전부 포함되는 것이 아니므로 전체 작업의 경과 시간과도 구별한다. 기존 표의 원 필드명과 값은 보존하고 이 정의를 함께 제공한다.

특히 `run_regional_phase.py:61–63`의 봉인 입력 전체 파일 SHA 재검증과 실제 allocator 확인은 이 clock 시작 전이다. Docker container의 실행 지속 시간이 영수증의 단계 wall보다 길 수 있으며, 그 차이를 지표 계산 정지나 순수 최적화 비용으로 해석하지 않는다. 원 wrapper/queue 기록과 단계 영수증의 시간은 각각의 측정 구간대로 제시한다.

`jbgs_trace.jsonl`의 `elapsed_seconds`는 계측 모듈의 `STARTED` 이후 누적 시간이다. 초기화·복원·이전 보고/저장·대기 영향이 포함되며 각 학습 step의 순수 비용이 아니다. trace 기록은 해당 회차의 별도 완전 상태 capture/save보다 먼저 이루어지므로 마지막 trace가 최종 저장 이후까지의 시간을 나타내지 않을 수 있다. 단계 wall과 마지막 trace의 차이도 최종 capture만의 비용으로 단정하지 않는다. 처음부터 실행한 조건과8,000회 anchor 재개 조건의 시작점, 공통 anchor 비용, 실패 시도 및 선택 추출 비용을 각각 유지한다.

최종 자원 CSV의 `resource_measurement_scope`와 `resource_measurement_definitions.json`은 같은 기존 RSS 열에서도 driver의 회수된 child 최대·학습 process 자체 peak·지정 renderer PID의 `wait4` 값을 구분한다. PyTorch CUDA counter·장치 전체 주기 표본·auxiliary cgroup 표본/누적 정점도 별도 범위다. 원 수치·행은 유지하고 정의JSON을 summary 영수증의 SHA/크기 목록에 연결한다. 개별 보조 추출 wall과 부모 auxiliary wall의 포함 범위 및 합산 금지는 [자원 측정 정의와 검증](RESOURCE_MEASUREMENTS_ko_v1.md)을 따른다.

## 12. 실제 정성 검토에서 채울 근거

모든 후보의 봉인과 정량·그림 생성을 마친 뒤 에이전트가 실제 화면을 확인하여 관찰 기록을 작성한다. 이는 김휘영의 과학적 판정을 대신하지 않는다. `scientific_verdict: null`을 유지하며 다음 항목을 최종 사례 표와 분석에 채운다. 현재 이 절은 검토 절차이며 실제 사례 결과가 아니다.

| 기록 | 필수 근거 |
|---|---|
| 사례 식별·선택 | region, condition, case ID, 고정 선택 규칙, 전체 후보 수, raw/post와1024/512 구분 |
| 실제 확인 자료 | 그림·뷰어 경로, 사용한 실제 photo ID, 동일 단면의 위치·폭·축척, 관측 참조의 존재 |
| 관찰된 변화 | 현재 참조의 재현, 참조에서 먼 추가 표면, 구조 결손, 외관을 각각 개선·유지·악화·판단 불가로 기록 |
| 의미별 영역 | 수정 필요를 뒷받침하는 현재 관측, 유지할 구조의 현재 사용 가능성, 영상 관측 부족의 가림·해상도·시점 근거를 구분 |
| 구현·제어 연결 | 같은 anchor와 같은 입력에서 바뀐 요인, 실제 loss/protection trace, raw→post와 추출 범위 영향; 확인 원인과 가능한 설명을 구분 |
| 한계·후속 질문 | 참조 피복·좌표·변환·관측 부족으로 결론이 제한되는 부분과 별도 검증할 질문 |

최대 거리 감소로 선택된 사례도 추가 잔존 표면을 만들 수 있다. 그러므로 한 방향의 거리가 좋아졌다는 사실만으로 사례 전체에 개선 라벨을 부여하지 않는다. 양방향 거리·동일 단면·높이층과 실제 사진을 함께 확인하고, 축마다 결과가 다르면 그대로 기록한다. 자동 XY 빈 셀과 높이 간격을 실제 구멍·잘못된 이중 표면의 확정 건수로 바꾸지 않는다.

수정 필요·유지할 구조·관측 부족을 확인할 근거가 없는 사례는 해당 의미를 판단 불가로 남긴다. 원하는 현상이 없으면 확인하지 못했다고 보고하며 다른 사례를 유리하게 대체하지 않는다. 이 관찰 기록을 제어값·범위·정합·seed·주 결과 선택에 되돌려 사용하지 않는다. 제약 완화의 관찰 효과와 반복 재판단의 추가 효과는 별개 질문이다.
