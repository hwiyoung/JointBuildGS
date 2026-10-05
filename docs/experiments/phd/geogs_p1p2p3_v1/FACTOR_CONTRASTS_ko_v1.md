# GeoGS 깊이·보호 요인 대비표

- 작성일: 2026-09-08
- 작업: `PHD-GEOGS-P1P2P3-v1`
- 상태: `DESCRIPTIVE_FACTOR_CONTRAST_TABLES_READY`
- 실제 범위: `PRIMARY18_SUPPLEMENTAL_INCOMPLETE`
- `scientific_verdict: null`

고정된 여섯 조건의 결과가 모두 확보된 뒤, 기존 지표의 차이를 P1/P2/P3별로 계산하는 추가 보고 도구다. 초기 설계와 코드는 지역별 품질·UAS를 열기 전에 작성했으며, 아래 실제 실행 기록은 봉인·평가 완료 후 추가했다. 원래 학습·추출·평가·사례 선택 코드와 동결 계약은 바꾸지 않는다. 새 학습 조건이나 새로운 점수는 만들지 않는다.

## 고정 대비

`N`은 원 구조 보호, `R`은 보호 완화다. 아래 숫자는 refinement의 prior 깊이 손실 가중치다. 각 지역·지표·평가 범위를 고정한 채 다음 아홉 대비를 모두 출력한다.

| 대비 | 계산식 | 수 |
|---|---|---:|
| 보호를 고정한 깊이 완화 | `M(0.0005,N)-M(0.005,N)`, `M(0,N)-M(0.005,N)` 및 같은 두 식의 `R` 조건 | 4 |
| 깊이를 고정한 보호 완화 | 각 깊이에서 `M(d,R)-M(d,N)` | 3 |
| 차이의 차이 | 각 낮은 깊이 `d`에서 `[M(d,R)-M(0.005,R)]-[M(d,N)-M(0.005,N)]` | 2 |

정확한 조건 ID·계수·순서는 `scripts/phd/geogs_p1p2p3_v1/analysis/factor_contrasts.py`의 `mapping()`에 있다. 실제 실행마다 그 내용을 `mapping.json`으로 저장한다. 반복 실행 `native_repeat_1`은 포함하지 않는다.

양수는 해당 지표의 증가를 뜻한다. precision/recall/F1·PSNR·SSIM은 높은 방향, 거리·LPIPS는 낮은 방향을 함께 표기한다. 표면적 자체에는 단조로운 품질 방향을 부여하지 않는다. 관측 UAS에서 먼 면적 추정치는 관측 참조와의 불일치량이며 확인된 잘못된 잔존 구조 면적이 아니다. 차이의 차이는 깊이 완화 효과가 보호 조건에 따라 얼마나 달라졌는지 나타내므로 단순한 품질 향상 점수로 읽지 않는다.

## 입력·식별·결측 처리

원 계약에서는 실행 전 `FinalizationGate.candidate_seal()`이 정확한 18개 주 비교와 세 지역 native 반복, 필수 표면 및 선택 추출 상태를 확인한다. 실제 실행에는 UAS 개방 전에 추가·봉인된 `evaluation_completion_v2.json`의 정확한 `PRIMARY18_SUPPLEMENTAL_INCOMPLETE` 범위가 적용됐다. 18개 주 비교는 모두 필수이며, P1/P2 반복의 CUDA OOM 실패와 P3 미시작을 명시적으로 보존하고 평가 가능한 반복 지역은 빈 목록이다. 임의 부분집합을 허용한 것이 아니다. 그 뒤 성공한 summary receipt의 seal·설정·allocator·repeat·resource·completion 바인딩을 확인한다. 아래 두 CSV는 해당 receipt에 기록된 SHA256·bytes와 일치해야 하며 계산 후에도 계약·seal·CSV·summary receipt의 동일성을 다시 확인한다.

- `evaluation/summary/geometry_primary_1024.csv`: final iteration 30000의 실제 triangle surface, raw/post를 분리한다. 다섯 표본화·참조밀도 조합과 여섯 거리 임계값을 각각 유지한다. 원 ALS/MVS 점군 및 파생 prior 표면 행은 요인 대비 대상에서 제외하고 제외 수를 기록한다.
- `evaluation/summary/render_all_images.csv`: `final`만 사용하고 두 평가 범위 `full_frame`, `fixed_prism_projected_bbox`를 분리한다. `evaluation_index`, 이름, 원 사진 SHA, image/camera ID, seed, 고정 ROI 및 pixel count를 대비에 참여하는 조건 사이에서 대조한다. anchor 렌더 행은 별도로 제외 수를 기록한다.

기하 13지표는 precision/recall/F1, 양방향 mean/median/p95/RMSE, 표면적, 관측 참조에서 먼 면적 추정치다. 렌더 4지표는 원 PSNR/SSIM, VGG LPIPS의 원 `[0,1]` 입력과 별도 `[-1,1]` 입력 결과다. 새 거리·렌더 품질을 계산하거나 Gaussian 중심점을 표면으로 바꾸지 않는다.

누락 행은 동결된 전체 격자와 평가 영상 수에 따라 `MISSING_ROW`로 남긴다. 평가 영상 전부에서 동일 인덱스가 사라져도 분모를 줄이지 않는다. 참조 부재, 렌더 실패, LPIPS 평가 불가 및 원 평가 상태는 각 operand의 원 상태와 함께 기록한다. 서로 다른 사진/카메라/ROI를 짝지으면 `PAIR_IDENTITY_MISMATCH`로 차이를 비운다.

빈 복원 표면이면서 참조가 있는 `RECONSTRUCTION_FAILURE`는 기존 평가 규칙을 유지한다. precision/recall/F1과 먼 면적 0은 CSV에 실제 기록되어 있어야 하며 누락 값에 0을 채우지 않는다. 순방향 거리는 표본 부재로 정의되지 않는다. 역방향은 원 evaluator의 참조점별 `+∞`이며, strict JSON 거리 요약 때문에 CSV 숫자 칸이 비어 있는 경우 이 기존 의미를 명시적인 infinity flag로 보존한다. 참조가 없는 기하의 품질값은 결측이고, 참조 없이도 정의되는 표면적은 별도 기술량으로 유지한다.

유한 차이만 숫자로 저장한다. 무한대는 부호 flag, `∞-∞`는 `UNDEFINED_INFINITY_CANCELLATION`, 결측·비정상 숫자는 해당 상태로 남긴다. 상호작용에서 서로 상쇄되는 무한대도 0으로 만들지 않는다. 각 행의 `operands_json`에 조건·계수·원 평가 상태·원 숫자 텍스트·해석한 숫자 상태를 담는다.

렌더 지역별 평균은 **해당 지역의 모든 선언 평가 영상 대비가 유한하고 식별이 일치할 때만** 계산한다. 하나라도 누락·실패·무한대가 있으면 전체 평균은 비우고 기대 수·유한 수·각 상태 수를 제공한다. 유한한 영상만 남긴 부분집합 평균, 지역 순위, 신뢰구간은 만들지 않는다.

## 실행과 산출물

정확한 후보 봉인과 summary 완료 후 저장소 루트에서 실행한다. 원 계약은 all21, 실제 완료 계약은 위의 primary18·보조 미완료 범위다. 실행 중인 orchestrator에는 연결하지 않았으므로 최종 분석 담당자가 이 명령을 별도로 실행한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_factor_contrasts.sh
```

Docker는 고정 이미지 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, CPU 2개·RAM 2 GiB, 네트워크·GPU 없음으로 실행한다. 입력은 해당 작업의 `contracts/`와 `evaluation/summary/`만 읽기 전용으로 마운트한다. UAS·영상·메시·학습 모델·원 작업 전체를 마운트하지 않는다. 기존 sealer의 검증을 계승하며 이 exporter가 학습·표면 producer payload를 다시 해시했다는 의미는 아니다.

출력은 외부 작업 루트의 새 경로 `evaluation/factor_contrasts_v1/attempt.XXXXXX/`다. 모든 실행은 별도 attempt를 사용하며 기존 표를 덮어쓰지 않는다.

| 파일 | 내용 | 고정 격자의 예상 행 수 |
|---|---|---:|
| `results/geometry_factor_contrasts.csv` | 지역·1024 raw/post·표본화·임계값·지표별 대비 | 21,060 |
| `results/render_per_image_factor_contrasts.csv` | 지역·평가 영상·범위·지표별 대비 | 3,168 |
| `results/render_regional_paired_contrasts.csv` | 전체 선언 영상에 대한 지역별 동일 영상 가중 평균 | 216 |
| `results/mapping.json` | 고정 조건 매핑·계수·부호 설명 | — |
| `results/receipt.json` | 입력/계약/소스/출력 SHA·bytes, 실행 버전, 결측 상태 수 및 제한 | — |

attempt에는 실제 코드 사본, launcher 사본, Docker 명령, 이미지 ID, Git HEAD, stdout/stderr, 종료 코드도 남긴다. 기술적 표 생성 완료는 과학적 결론이 아니다.

## 검증 기록

합성 검증은 다음 명령으로만 수행했다. task/UAS payload 없이 소스와 동결 설정의 사본만 Docker에 마운트한다.

```bash
bash scripts/phd/geogs_p1p2p3_v1/analysis/run_synthetic_validation.sh
```

최종 검증: `runtime/factor_contrast_validation_v1/attempt.N06xaP/test_receipt.json`, **28/28 PASS, 실패 0, skip 0**, 3.230초, Python 3.10.20. 실제 테스트 파일은 `tests/phd/geogs_p1p2p3_v1/test_factor_contrasts.py`다.

- 알려진 2×3 비가법 수치표의 주효과와 두 독립 전개의 차이의 차이가 일치했다.
- 기존 evaluator의 실제 거리·면적 보고 함수와 CSV writer에 합성 triangle/빈 표면/참조 부재를 넣어 호환성을 확인했다.
- 기존 `evaluate_render_set`의 실제 CSV와 `summarize.csv_write`에 합성 사진·미리 정한 합성 scorer를 사용해 상태·schema 호환성을 확인했다. 실제 native metric의 수치 정확도 검증을 대신하는 시험은 아니다.
- 실제 `FinalizationGate`에 정확한 동결 계약과 합성 all21 inventory를 적용했다. 누락된 P3 반복 및 필수 post 표면은 summary 접근 전에 거부됐다.
- `main()` 전체가 새 21,060/3,168/216행 표와 입력·출력 receipt를 만들고 선언 결측을 보존하는지 확인했다. 이 표는 임시 합성 자료이며 실제 지역 결과가 아니다.
- wrapper shell 구문 검사와 `git diff --check`를 통과했다.

이전 24개·27개 부분 검증의 성공 로그는 각각 `attempt.FEaFQq`, `attempt.0xY9xx`에 보존했다. 중복 시험 수를 합산하지 않는다. 이 합성 검증 시점에는 실제 지역 대비표 실행과 해석을 수행하지 않았다.

당시 합성 검증 분석 코드 SHA256: `351e5eeecec810fba4891ec8afb0e12dab722946ff88760966ca7028c981ca01`. 완료 계약 호환성이 추가된 실제 실행 사본의 SHA는 다음 절에 별도로 기록한다.

## 실제 실행과 산출물 확인

기존 명령을 한 번 실행해 종료 코드 **0**과 `DESCRIPTIVE_FACTOR_CONTRAST_TABLES_READY`를 확인했다. 실제 결과 영수증의 작성 시각은 2026-09-08 **22:41:01 KST**다. 기존 소스·실행기·설정은 수정하지 않았다. 입력 summary는 먼저 `TABLES_AND_ACTUAL_VIEWER_DATA_READY`로 닫힌 상태였다.

실제 출력 루트는 [evaluation/factor_contrasts_v1/attempt.ZMb3iK](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/factor_contrasts_v1/attempt.ZMb3iK)다. `results/receipt.json`, 코드 사본 8개, `launcher_snapshot.sh`, `command.sh`, `image_id.txt`, `git_head.txt`, stdout/stderr 및 `exit_code.txt`를 보존했다. 완료 후 출력 4개와 코드 사본 8개의 bytes/SHA를 영수증과 독립적으로 다시 대조해 모두 일치했다.

| 바인딩 | SHA256 |
|---|---|
| 후보 봉인 | `8fc78431dcdfc1bf803c0ac2db4a5bb2cad75c1c163ce2519b571d3710cd011d` |
| 완료 계약 v2 | `3e200db7de4cc171158b08deccffd3869bfd2d30c2a5b89805b86ad1903112c6` |
| 입력 summary receipt, 90,810 bytes | `c2e59578da3104bbd838a03c2cda8ed621da42f67c5be95ea304ec06c02c7455` |
| 입력 geometry_primary_1024.csv | `528cb46deceefa9a9dbadc7915700f58059f91c3005932fd72a607761aefc023` |
| 입력 render_all_images.csv | `f89f8b9ef081c1d041140bba54a6ea41a0a4053aa0225b68e96115171b431f46` |
| 실제 factor_contrasts.py | `236cd52314748402bb550881c7354763bed7458cfb710f4265f019f9db53b6f9` |
| 닫힌 results/receipt.json | `c0382630ae38ccb600c532c9b65e7ac0c611a34c5808e97f02da17e6c49f43a9` |

| 실제 결과 파일 | 행 수 | bytes | SHA256 |
|---|---:|---:|---|
| `results/geometry_factor_contrasts.csv` | 21,060 | 22,876,892 | `f96ca0367892c08b9c1d19c687b9c4eeadb0ebd6bb07cf90d0b7a6b8c065335e` |
| `results/render_per_image_factor_contrasts.csv` | 3,168 | 5,996,121 | `c97fac978123fc003b5c62dad8081bcaa0b1b19cdca26e130507e96f1042af14` |
| `results/render_regional_paired_contrasts.csv` | 216 | 59,317 | `d740dc23de85576f93557ac0fd4c9a7510b738e2eb9b4c6a13d45e9d1c589780` |
| `results/mapping.json` | — | 4,215 | `75ae7e5f034fe98c54e94775754ac3c856337cfefb59e607b5686625ae323c8b` |

기하 입력 조건 행은 기대 1,080/실제 1,080, 렌더는 기대 528/실제 528이었다. 기하 baseline 126행과 anchor 렌더 88행은 명시적으로 제외했다. 기하·사진별 대비는 모두 `FINITE`, 지역별 216행은 모두 `FINITE_ALL_DECLARED_IMAGES`다. 지역별 평가 사진 수는 P1 15장, P2 9장, P3 20장이며 이 분모 전체를 유지했다. 이 확인은 완료된 요약표의 기술적 대비 생성이며 새로운 UAS·영상·메시를 읽거나 지표를 재계산한 검증이 아니다.

## 실제 요인 대비의 관찰

다음은 **final 1024**, 표면 간격/참조 voxel 각각 0.1m, 거리 임계값 0.5m의 F1 차이다. 각 셀은 **raw / post**이며 숫자는 비율의 차이이지 퍼센트나 향상 판정이 아니다. 모든 아홉 대비를 제시하고, 512 anchor 비교와 섞지 않는다.

| 대비 | P1 raw / post | P2 raw / post | P3 raw / post |
|---|---:|---:|---:|
| 깊이 .005→.0005, N | −.146797 / −.145112 | −.090340 / −.080911 | +.014955 / −.019245 |
| 깊이 .005→.0005, R | −.184215 / −.172386 | −.081902 / −.072761 | +.024415 / −.005584 |
| 깊이 .005→0, N | −.137161 / −.140675 | −.071487 / −.052615 | +.010700 / −.020299 |
| 깊이 .005→0, R | −.197459 / −.218072 | −.090055 / −.082382 | +.002359 / −.034903 |
| 보호 N→R, .005 | +.025505 / +.018873 | −.014671 / −.009626 | −.011845 / −.010768 |
| 보호 N→R, .0005 | −.011913 / −.008401 | −.006233 / −.001476 | −.002386 / +.002894 |
| 보호 N→R, 0 | −.034792 / −.058524 | −.033238 / −.039393 | −.020187 / −.025371 |
| DiD, .005→.0005 | −.037418 / −.027274 | +.008438 / +.008150 | +.009459 / +.013661 |
| DiD, .005→0 | −.060297 / −.077397 | −.018568 / −.029767 | −.008341 / −.014603 |

Native 보호를 유지하고 깊이를 .005→.0005로 낮춘 대비의 **동일 사진 ROI 평균**은 다음과 같다. PSNR·SSIM 증가는 높은 방향, 두 LPIPS 감소는 낮은 방향이다. LPIPS의 `[0,1]` 입력과 `[-1,1]` 입력을 별도 값으로 유지한다.

| 지역 | ΔPSNR dB | ΔSSIM | ΔLPIPS native01 | ΔLPIPS signed11 |
|---|---:|---:|---:|---:|
| P1 | +4.032140 | +.098402 | −.074551 | −.074012 |
| P2 | +5.462163 | +.263274 | −.202660 | −.199382 |
| P3 | +1.483057 | +.045303 | −.028798 | −.026020 |

P1/P2에서는 이 깊이 완화의 ROI 렌더 평균 개선과 F1@.5 감소가 동시에 나타난다. P1 raw의 예측→UAS 평균은 1.258299→0.973611m로 낮아졌지만 UAS→삼각형 평균은 0.575526→0.895201m로 높아지고 recall@.5는 .629412→.347632로 낮아졌다. P2 raw도 두 방향 평균의 변화가 각각 −.052136m/+.269095m로 갈리고, post에서는 두 방향 모두 +.053246m/+.152478m로 높아졌다. 지표 하나나 한 방향 평균만으로 회복을 판정할 수 없다.

P3에서는 같은 깊이 변경으로 raw F1@.5가 .634312→.649268로 높아지지만 post는 .656942→.637696으로 낮아진다. Raw precision@.5는 .631418→.731881, recall은 .637233→.583413이다. 다섯 표본화 설정 모두에서 raw F1@.5 증가는 유지되지만 F1@.1은 감소하고, post F1@.5는 감소한다. 추출·후처리 범위와 임계값을 생략하면 반대 결론이 생긴다. P1은 같은 대비의 raw F1@2m가 다섯 설정 모두 증가하지만 P2는 다섯 설정 모두 감소한다. 이 범위들은 표본화 민감도이며 반복 변동·신뢰구간이 아니다.

사진 평균도 모든 시점의 개선을 뜻하지 않는다. 위 대비에서 ROI PSNR이 높아진 사진은 P1 13/15, P2 9/9, P3 9/20장이며, ROI SSIM은 각각 11/15, 8/9, 9/20장이다. P3는 평균이 높아져도 과반 11장의 PSNR·SSIM은 낮아졌다. P1의 사전 첫 인덱스 사진은 ROI ΔPSNR −.916140dB, ΔSSIM −.108606, ΔLPIPS01 +.138827, ΔLPIPS11 +.149248로 네 지표 모두 악화했다. 실제 포장선·설비·수목·곡면지붕 세부가 더 뭉개진 확인은 [P1 실제 비교 검토](P1_REVIEW_ko_v1.md)에 있다. 평균 변화와 개별 세부 손실을 함께 해석한다.

보호 완화의 방향은 깊이와 지표에 따라 달라진다. 위 F1 표에서 P1은 .005의 보호 완화만 양수이고 낮은 두 깊이는 음수다. P2의 .0005 DiD는 양수지만 해당 깊이 완화 자체는 두 보호 상태 모두 음수이며, 양의 상호작용이 기하 회복을 뜻하지 않는다. P3의 ROI PSNR DiD는 .0005에서 −.376166dB, 0에서 −.541280dB로, 보호 완화 상태에서 깊이를 낮출 때의 평균 PSNR 증가폭이 작았다. 이에 대응하는 F1 DiD의 부호는 깊이에 따라 달라진다. 이런 차이는 고정 제어 규칙하의 관측된 비가법 실행 차이이며 보호·깊이·실현 DA3 궤적의 순수 인과 효과를 분리한 결과가 아니다.

## 해석의 한계

공식 `train.py:907–987`의 DA3 dual-gate는 각 조건에서 실제 발생한 depth/RGB loss 이력에 따라 갱신된다. 초기값과 규칙이 같더라도 실현 DA3 가중치 궤적은 다를 수 있다. 이 대비는 **원 adaptive DA3 규칙을 유지한 전체 실행 차이**이며, DA3 궤적을 고정했을 때 prior 깊이나 보호가 미치는 순수한 직접 효과를 분리한 결과가 아니다.

보호 `native→release`는 위치·회전·크기 gradient 감쇠와 보호 Gaussian의 분할·복제·삭제 제한을 함께 바꾼다. 두 구성요소 각각의 단독 효과를 분리하지 못한다. 모든 조건에 ALS 초기화와 공통 anchor의 영향이 남으므로 `image-only`라고 부르지 않는다. 반복 재판단의 필요성이나 추가 효과도 이 대비에서 도출하지 않는다.

원래는 같은 anchor의 원 제어 반복과 함께 해석할 계획이었으나 실제 범위에서는 P1/P2 반복 학습 실패와 P3 미시작으로 **반복 품질 변동이 미측정**이다. 실패 기록을 제거하거나 주 조건 결과로 대체하지 않았으며, 작은 대비가 반복 변동을 넘는다고 판단할 근거가 없다. 기하/영상 지표와 실제 단면·참조 거리 지도·렌더를 함께 검토해야 하며, 개별 대비의 개선만으로 전체 복원 품질이 개선됐다고 결론내리지 않는다. `scientific_verdict: null`을 유지한다.
