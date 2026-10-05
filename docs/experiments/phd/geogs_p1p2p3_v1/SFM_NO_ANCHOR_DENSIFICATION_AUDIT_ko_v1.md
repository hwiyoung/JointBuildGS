# SfM 초기화·anchor 생략 Gaussian 증가 감사

`scientific_verdict: null` · `status: PASS_READONLY_CODE_TRACE_AUDIT` · 2026-09-10

**확인된 것은 densification 설정값의 증가가 아니라, 같은 증가 규칙이 다른 초기 분포·loss 단계·보호 멤버십에 적용된 결과다.** SfM 실행은 초기 점이 훨씬 적지만, 동일 global iteration 8,000에서 P1/P2/P3의 Gaussian 수가 prior 초기화 실행의 2.79/1.38/3.24배였다. native 보호는 실제로 적용됐고 opacity prune도 작동했다. 개별 clone/split/prune 및 loss별 gradient 기록이 없으므로 이 세 변화의 인과 기여도는 분리하지 못한다.

이 감사는 실패가 보존된 **최초 `no_anchor_sfm_v1`**과 원 prior 초기화 `D005_Pnative`를 비교한다. 현재 실행 중인 memory recovery v2의 궤적은 읽거나 변경하지 않았다. 코드·설정·manifest·trace·작은 초기 PLY만 사용했다. reference geometry, 이미지 픽셀, checkpoint tensor, GPU, renderer와 학습 실행은 사용하지 않았다. 설정 변경을 실행하거나 권장값을 정하지 않는다.

## 1. 정확한 비교 계보

아래 `T`는 다음 외부 artifact의 절대 경로다.

`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`

- 원 실행 배치는 `T/contracts/runtime_layout_allocator_v2.json`으로 해석했다. P1의 8,000까지는 `T/runs/P1/D005_Pnative`, 이후는 `T/runs_allocator_v2/P1/D005_Pnative`다. P2/P3은 각각 `T/runs_allocator_v2/P*/D005_Pnative`의 연속 실행이다.
- SfM 최초 실행은 `T/no_anchor_sfm_v1/runs/P*/SFM_noanchor_D005_Pnative`다. 세 실행 모두 `receipt.json`에 실패가 보존돼 있다. 아래 마지막 기록은 OOM 직전의 **마지막 100-step trace**이며 실제 실패 iteration과 같다고 단정하지 않는다.
- 원 science config SHA256: `b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4`. SfM config SHA256: `42c741c8682a7830bd53cde3add9a93b41030f1dcb718b9e2f23d78389834c13`.
- 각 원 실행의 `model/input.ply`가 `T/inputs/P*/initialization/lod2_pcd.ply`와 byte-equal임을 확인했다. SfM 각 `receipt.json`의 `original_input_manifest_sha256`도 같은 지역 `T/inputs/P*/input_manifest.json`과 일치했다. prior depth·DA3·보호용 PLY를 다른 자료로 바꾼 실행은 아니다.
- 원 `sources/GeoGS-state-camera-v1/scene/gaussian_model.py`와 `no_anchor_sfm_v1/source/scene/gaussian_model.py`는 byte-equal이다. 공통 SHA는 `4be070008683ba1943de9e22d1f4d1a9c194aef56010c0b3186d0bd7f6aadb9a`다. 공통 `arguments/__init__.py` SHA는 `059113ea23d1905b750b9849f95aafb1f7ea3f644f8a261a656535454ec0c71c`다.

## 2. 초기 분포·크기·보호 멤버십

| 지역 | prior 초기 점 | SfM 초기 점 | 초기 scale 중앙값 prior → SfM, m | SfM 초기 보호 | prior 8k 보호 / 전체 |
|---|---:|---:|---:|---:|---:|
| P1 | 93,583 | 4,412 | 0.220 → 0.629 | 519 / 4,412 (11.76%) | 236,015 / 1,136,384 (20.77%) |
| P2 | 93,497 | 5,665 | 0.269 → 0.779 | 1,437 / 5,665 (25.37%) | 114,521 / 1,625,820 (7.04%) |
| P3 | 94,644 | 19,398 | 0.296 → 0.471 | 3,236 / 19,398 (16.68%) | 226,262 / 1,235,876 (18.31%) |

두 보호 열은 **적용 시점이 다르다**. prior는 8,000-step anchor 뒤 재구성된 전체 Gaussian에 매칭하고, SfM은 학습 전 초기 Gaussian에 한 번 매칭한다. 따라서 초기 SfM 보호 비율만 보고 항상 더 약하다고 판단하면 안 된다. SfM의 보호점 수 519/1,437/3,236은 각 마지막 trace까지 유지되며, 8,000 시점 전체 대비 비율은 0.0164/0.0642/0.0809%로 낮아진다. 새로 생긴 점의 보호 비트는 false이고 재매칭은 반복하지 않는다.

두 초기화는 같은 `GaussianModel.create_from_pcd()`를 거친다. scale은 세 최근접 이웃까지의 제곱거리 평균의 제곱근, 두 평면 축에 동일하게 주어지며, opacity는 둘 다 0.1, rotation은 난수로 시작한다. prior에만 더 큰 초기 opacity를 준 차이는 없다. 여기서 prior scale은 정확한 초기 XYZ에서 CPU 3-NN으로 재계산한 값이고, SfM scale은 저장된 iteration-0 Gaussian PLY의 실제 값이다. CPU 3-NN과 저장된 SfM scale의 최대 차이는 지역별 3.69/1.78/3.26 μm 미만이었다. CUDA float 연산과 CPU double 재계산의 bitwise 일치를 주장하지 않는다.

| 지역 | prior XYZ min → max, scene-local m | SfM XYZ min → max, scene-local m |
|---|---|---|
| P1 | (-44.43,-45.98,-47.05) → (26.77,33.98,-18.59) | (-48.00,-45.96,-72.78) → (31.99,33.98,-10.64) |
| P2 | (87.71,61.05,-49.02) → (182.49,156.95,-17.11) | (85.03,61.02,-67.52) → (182.80,156.97,-22.67) |
| P3 | (-81.30,-66.94,-48.74) → (2.05,36.96,-16.84) | (-85.00,-66.99,-89.34) → (4.97,37.00,-3.30) |

SfM의 Z 범위가 더 넓다. 이 차이가 triangulation 오차인지, 서로 다른 가시 표면인지, 다른 시기의 자산 차이인지는 이 감사로 판별하지 않는다. `initialization_manifest.json`은 이미 scene-local인 SfM 좌표에 translation 0, scale 1을 적용했음을 기록하고, 초기 audit는 Gaussian XYZ와 SfM float32 순서 일치를 확인한다. 이중 world-shift 적용 오류라는 근거는 없다.

SfM은 동일 regional context와 최소 두 training-track 관측 조건으로 원 COLMAP SfM을 선택했다. 원 SfM의 역사적 full-source image 영향은 남아 있어 엄밀한 confirmatory image-only 초기화라고 부르지 않는다. prior는 ALS-derived surface에서 100,000점을 샘플하고 training-camera 가시성을 통과한 약 94,000점을 썼다. 같은 수·분포의 초기점에 anchor만 생략한 실험이 아니다.

| 지역 | camera extent, m | clone/split scale 경계, m | 초기 scale이 경계보다 큰 비율 prior → SfM | 초기 scale 최대 prior → SfM, m |
|---|---:|---:|---:|---:|
| P1 | 200.77 | 2.008 | 0.0192% → 11.4914% | 6.02 → 28.94 |
| P2 | 268.43 | 2.684 | 0.0160% → 1.7299% | 6.80 → 23.69 |
| P3 | 212.43 | 2.124 | 0.0254% → 2.7322% | 4.21 → 25.40 |

camera extent는 공통 training-camera 중심에서 최대 거리×1.1로 재계산했다. 실제 split에는 scale 조건 외 **gradient threshold와 비보호 조건**도 필요하므로, 이 표는 실제 split 비율이 아니다. SfM의 더 성긴 공간 분포와 큰 scale tail은 split 양상이 달라질 수 있는 근거이며, 기여도는 아직 추측이다.

## 3. 스케줄과 native 증가·삭제 규칙

공통 defaults는 `densify_from_iter=500`, `densification_interval=100`, `densify_until_iter=15000`, `densify_grad_threshold=0.0002`, `percent_dense=0.01`, `opacity_cull=0.05`, `opacity_reset_interval=3000`다. 세 SfM invocation에도 `--densify_until_iter 15000` 외 이 값들을 낮추거나 증가시키는 override가 없다.

- 실제 densify/prune 호출은 600,700,…,14,900으로 총 144회다. prior의 75회는 anchor 단계이고 69회는 refinement 단계다. SfM의 144회는 모두 refinement 단계다. `freeze_onlybldg`는 전체 densification을 멈추지 않는다.
- prior는 iteration≤8,000에서 RGB/SSIM + prior depth 0.08, DA3 weight 0을 쓴다. SfM은 iteration1부터 prior depth 0.005 + DA3 depth 0.05와 dynamic controller를 사용한다. 실제 SfM DA weight는 이후 0.0475(P1/P2), 0.045125(P3)로 감소했다.
- normal regularizer 0.05는 둘 다 global iteration>7,000부터 활성화된다. SfM은 refinement 첫 7,000 step에는 normal term이 없는 반면 prior의 refinement는 이미 normal term이 활성화된 상태에서 시작한다. `lambda_dist=0`은 공통이다.
- 현재 단계의 **전체 loss backward**가 만든 view-space Gaussian gradient norm을 누적·평균하여 threshold와 비교한다. loss 값의 크기만으로 해당 항의 densification 기여도를 판단할 수 없다.
- 작은 scale의 대상은 clone, 큰 scale의 대상은 두 개로 split하고 원점을 삭제한다. 둘 다 보호점은 제외한다. 새 Gaussian의 보호 비트는 false다. completion은 꺼져 있어 prior 점을 대량 삽입하는 별도 경로가 원인은 아니다.
- opacity는 3,000마다 최대 0.01로 reset되고, 다음 densification/prune은 opacity<0.05를 삭제한다. 보호점은 prune에서 제외한다. 전체 point cap이나 ROI 경계에 따른 Gaussian 삭제는 이 경로에 없다.
- 초기 XYZ crop과 별개로 RGB loss는 full image이며 depth loss에도 해당 ROI mask를 전달하지 않는다. full-frame supervision이 초기 공간 밖으로 점을 늘리게 했는지는 현재 위치별 birth 기록이 없어 미확정이다.

**공통 pruning 제약:** `densify_and_prune()`는 clone→split 뒤 `max_radii2D>20`을 계산하지만, 두 경로가 호출하는 `densification_postfix()`가 `max_radii2D`를 먼저 모두 0으로 만든다. 따라서 해당 호출 순서에서 screen-size prune 항은 효력이 없다. opacity 및 `scale>0.1*camera_extent`의 world-size prune은 남아 있다. 이는 원 prior/SfM 양쪽 동일 코드의 제약이며, SfM 증가 차이의 단독 원인이라고 주장하거나 수정하지 않았다.

## 4. 같은 iteration·camera의 실제 궤적

| 지역 | 초기 prior / SfM | 3k prior / SfM | 8k prior / SfM | 마지막 공통 기록 | 그 시점 prior / SfM | SfM / prior |
|---|---:|---:|---:|---:|---:|---:|
| P1 | 93,583 / 4,412 | 577,272 / 980,940 | 1,136,384 / 3,166,612 | 10,700 | 1,695,347 / 5,845,082 | 3.45× |
| P2 | 93,497 / 5,665 | 692,439 / 442,348 | 1,625,820 / 2,237,962 | 14,400 | 3,144,220 / 9,264,498 | 2.95× |
| P3 | 94,644 / 19,398 | 657,537 / 748,802 | 1,235,876 / 3,998,320 | 8,700 | 1,223,719 / 5,835,785 | 4.77× |

원 prior 실행의 14,900→30,000 point count는 P1 6,033,926, P2 4,093,957, P3 4,799,188로 고정된다. 최초 SfM 실행은 모두 그 종료 시점에 도달하기 전에 실패했다. 따라서 표의 마지막 값을 SfM 30k 결과로 표시하면 안 된다.

공통 100-step trace의 camera 이름은 P1 107/107, P2 144/144, P3 87/87이 같았다. 아래 600–8,000의 75개 같은 camera/iteration 기록에서 계산한 중앙값은 loss 환경의 차이를 보여준다. 전체 iteration 평균이나 loss별 gradient 분해는 아니다.

| 지역 | raw prior-depth L1 중앙값 prior → SfM | weighted prior-depth 중앙값 prior → SfM | weighted DA3 중앙값 prior → SfM |
|---|---:|---:|---:|
| P1 | 0.928 → 12.187 | 0.0742 → 0.0609 | 0 → 0.4626 |
| P2 | 1.712 → 7.668 | 0.1370 → 0.0383 | 0 → 0.3325 |
| P3 | 1.270 → 12.615 | 0.1016 → 0.0631 | 0 → 0.2617 |

SfM은 더 큰 raw prior-depth 차이를 허용하는 동시에 DA3 항을 처음부터 최적화했다. 더 낮아진 RGB/DA3 loss와 늘어난 Gaussian 수가 함께 보이지만, 이것만으로 추가 점이 유효한 표면인지 artifact인지 판단할 수 없다.

점 수는 opacity 주기와 함께 큰 폭으로 감소했다가 다시 증가한다. SfM P1은 9,000→9,100에 5,448,167→1,771,689, P2는 12,000→12,100에 6,424,139→2,430,972, P3은 6,000→6,100에 2,998,018→1,467,226이었다. 따라서 **prune 전체가 꺼져 있다**는 설명은 실제 trace와 맞지 않는다. clone/split/prune 개별 개수가 없으므로 이 순감소를 전부 opacity 항의 삭제 수로 해석하지 않는다.

## 5. 확인된 사실과 남은 검증 질문

확인된 사실은 공통 증가 규칙, 더 성기고 넓은 SfM 초기 분포, stage2 전체 144회 densification, 초기 소수 보호점의 고정 멤버십, 주기적 대규모 감소·재증가, 공통 screen-size pruning의 순서 제약이다. 이 조합은 증가 차이를 설명할 구체적 메커니즘을 제공한다. 초기 point count만으로 최종 수가 결정되거나 보호가 조용히 빠졌다는 근거는 없다.

아래는 **설정 변경 제안이 아니라 후속 검증 질문**이다. 현재 runtime·값·실행은 유지했다.

1. clone/split 직전 eligible 수, gradient 분위수, scale 분류, 각 prune 원인을 따로 기록하면 어느 경로가 순증가를 주도하는가?
2. 새 Gaussian의 위치와 생성 계보를 full-frame 및 context 경계에 대조하면, 증가가 유효한 국소 세부인지 초기 범위 밖의 설명 시도인지 구분되는가?
3. 초기화·anchor·fresh schedule·보호 멤버십을 각각 고정하는 별도 비교가 있을 때 어느 요인의 영향이 유지되는가? 현재 실험은 이 네 요소를 동시에 바꾸므로 순수 anchor 필요성 ablation이 아니다.
4. 원 native screen-size pruning의 값이 clone/split 후 소실되는 순서를 별도 synthetic fixture에서 검증하면 예상한 pruning 정책과 일치하는가? 해당 구현을 바꾼 결과를 원 실행과 섞지 않고 별도 계보로 평가할 수 있는가?
5. 동일 camera의 loss가 비슷해진 후에도 SfM의 큰 비보호 집합이 더 많이 복제되는지, loss별 view-space gradient 진단으로 확인할 수 있는가?

이 감사는 설정 최적화, reference 기반 선택, temporal valid/stale 판정, 최종 형상 품질과 anchor 필요성의 과학적 결론을 제공하지 않는다.

## 6. 근거 코드와 재현 범위

아래 파일은 모두 `T/no_anchor_sfm_v1/source/` 기준이다. 원 공통 코드와 hash 일치를 앞에서 확인했다.

| 근거 | 파일·행 |
|---|---|
| 같은 초기 Gaussian scale/opacity/rotation | `scene/gaussian_model.py:126–149` |
| 3-NN 평균 제곱거리 | `submodules/simple-knn/simple_knn.cu:151–183` |
| common learning-rate / densification defaults | `arguments/__init__.py:109–134` |
| full-image RGB 및 depth / normal 시작 | `train.py:824–861` |
| stage2 및 depth weighting | `train.py:899–977` |
| global densification 스케줄 / reset | `train.py:1074–1110` |
| prior 단계 종료 후 한 번 매칭 | `train.py:1174–1204` |
| SfM 처음 한 번 보호 적용 | `jbgs_no_anchor.py:103–151` |
| 새 보호 bit=false / stats 초기화 | `scene/gaussian_model.py:380–394` |
| clone/split/prune와 gradient 통계 | `scene/gaussian_model.py:396–464` |
| opacity reset | `scene/gaussian_model.py:212–215` |

Docker image는 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`를 사용했다. 모든 계산은 `--network none --cpus 2 --memory 2g`, `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2`, task mount read-only, GPU 옵션 없이 수행했다. 최초 stdin introspection 명령은 `docker -i`가 없어 계산을 실행하지 않았고, 같은 명령을 `-i`로 다시 실행해 출력을 확인했다. 학습·runtime·입력 파일은 쓰지 않았다.

초기 PLY 계산은 `plyfile.PlyData.read()`로 XYZ를 읽고, `scipy.spatial.cKDTree(...).query(xyz,k=4,workers=1)`에서 자기 자신을 제외한 3개 거리의 RMS를 구했다. 실제 SfM scale은 Gaussian PLY의 `exp(scale_0)`와 비교했다. opacity는 sigmoid(opacity)로 복원했다. XYZ 범위는 전체 초기점의 축별 min/max다. trace는 JSONL 전체에서 같은 iteration key를 맞추고 camera 이름 일치를 검사했다. P1만 manifest가 지정한 anchor trace와 resumed trace를 이어 붙였다. loss 중앙값은 600≤iteration≤8,000의 100-step 기록을 사용하고, 각 행의 loss×그 행의 weight를 먼저 계산했다. 새 표면 계산·reference 최근접거리 계산은 하지 않았다.

| trace | SHA256 |
|---|---|
| `runs/P1/D005_Pnative/model/jbgs_trace.jsonl` | `f95ae3dffcece89a72be3e3737da4f2b6bb3547cbc15f1d0317111c2b192b0e8` |
| `runs_allocator_v2/P1/D005_Pnative/model/jbgs_trace.jsonl` | `fbdb423111995ddc0ed833e21c441eeb5a3b966d1088cb0298541b02d827a87e` |
| `runs_allocator_v2/P2/D005_Pnative/model/jbgs_trace.jsonl` | `74cefb1788214eff0ac6475b9bc50a7b2120fa4d84accd7b43a4ddb3fb2ae296` |
| `runs_allocator_v2/P3/D005_Pnative/model/jbgs_trace.jsonl` | `69149663322f127862038571591e8edcf6c532c8fea3ef41853c690424656b4e` |
| `no_anchor_sfm_v1/runs/P1/SFM_noanchor_D005_Pnative/model/jbgs_trace.jsonl` | `1f6bd76836b1b54ccd690447bf232e5f3ecf76e916e98263c2a7aed3263faaf4` |
| `no_anchor_sfm_v1/runs/P2/SFM_noanchor_D005_Pnative/model/jbgs_trace.jsonl` | `4b55b2d5bade512cfe5f1fd6a8f768fd1aac13b73df9f183c2b346d754a080b4` |
| `no_anchor_sfm_v1/runs/P3/SFM_noanchor_D005_Pnative/model/jbgs_trace.jsonl` | `69729aa67c7ffaf313f76379d9e4ed4b120807ad9afae538e90983f4554ead07` |

prior/SfM 초기 PLY 및 보호 증거는 각각 `T/inputs/P*/initialization/receipt.json`, `T/inputs/P*/scene/initialization_binding_receipt.json`, `T/no_anchor_sfm_v1/inputs/P*/initialization_manifest.json`, `T/no_anchor_sfm_v1/runs/P*/SFM_noanchor_D005_Pnative/model/jbgs_no_anchor/initialization.json`, 같은 폴더의 `iteration_0/receipt.json`과 `point_cloud.ply`에서 확인할 수 있다. SfM 초기 Gaussian PLY SHA256은 P1 `d2870481780ceab97b1ab4c8e73f385ea1f0f4bb0bc86ba300fa161b564c9fa3`, P2 `6356d66076f223775b9903bf5ad60aa1e35c93cbd6b6c8e15dcb787d031e986a`, P3 `b886f30468ee893efa39a96e1b4527ef58cb65fa9e2b587ec5a6c6c7a431ebfa`다.
