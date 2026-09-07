# P1·P2 저장 깊이를 통한 DA3와 refinement의 원인 경계

`task_id: PHD-GEOGS-CAUSAL-FOLLOWUP-v1` · `scientific_verdict: null`

현재 자료는 **refinement의 잔여 오류를 곧바로 DA3의 오류로 동일시하는 해석을 지지하지 않는다.** P1의 관측 가능한 바닥에서는 DA3가 prior보다 현재 표면에 가까운 수정을 제안하지만 깊이가 여전히 부족하고, GeoGS의 낮은 prior 가중치 결과는 DA3보다 더 깊어지면서도 현재 표면까지 도달하지 않는다. P2의 큰 형상 수정에서도 DA3와 GeoGS가 현재 방향으로 움직인다. P2 반복 골에서는 DA3가 얕은 방향을 제안하고, 최종 **학습 결과에서 저장한 expected depth부터** anchor보다 얕아지는 대응이 있다. 서로 다른 위치에서 DA3의 도움이 되는 방향과 불리할 수 있는 방향이 공존한다.

이는 고정된 입력과 이미 저장된 깊이에 대한 사후 진단이다. DA3 교체/제외나 손실 개입 실험을 하지 않았으므로 단독 원인을 확정하지 않는다. UAS는 평가용 위치와 비교 깊이에만 사용했고, 학습·마스크·척도 보정·설정 선택에 전달하지 않았다.

## 1. 조사 범위와 실제 자료 연결

외부 원자료 루트는 다음과 같다.

`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`

- P1: train 98장 / evaluation 15장; prior와 DA3는 각각 98개.
- P2: train 57장 / evaluation 9장; prior와 DA3는 각각 57개.
- prior anchor는 `extraction_resource_v3/primary/P*/D005_Pnative/auxiliary/anchor_512/model/train/ours_8000/vis/`의 TIFF다. 해당 생성 receipt와 `contracts/candidates_sealed_v1.json`의 계보를 확인했다.
- 최종은 `runs_allocator_v2/P*/<condition>/model/train/ours_30000/vis/`의 TIFF다. `D005_Pnative`, `D0005_Pnative`, `D0_Prelease`를 읽었다. 모든 단계에 지역별 전체 train 깊이가 있다.
- 사진 이름 정렬 순서를 `shuffle=False`인 공식 renderer, dataset reader와 대조했고, 선정된 모든 사진에 대해 단계별 저장 `gt/NNNNN.png`의 RGB 픽셀이 실제 train JPG와 정확히 같음을 확인했다. 파일 이름 순서만 추정하여 연결하지 않았다.
- 사용한 prior·DA3의 SHA256을 해당 input receipt와 확인했다. 사용 source의 camera adapter·renderer·export 함수 SHA256을 실제 render receipt의 implementation hash와 확인했다.
- `completed_prefix8000_v1/`의 깊이는 **SFM no-anchor 보조 진단**이다. 처음 파일 검색에서 발견했지만 생성 invocation으로 계보를 확인한 뒤 이번 prior-anchor 대응에서 제외했다.

본 감사의 재현 입력은 [config](../../../../configs/phd/geogs_causal_followup_v1/da3_audit.json), 구현은 [script](../../../../scripts/phd/geogs_causal_followup_v1/da3_audit.py)다. 최종 수치는 [규약 보완 CSV](analysis/da3_convention_corrected_v2/da3_probe_depths.csv), 좌표·원 참조 ID·선정 규칙·입력 SHA·한계는 [JSON](analysis/da3_convention_corrected_v2/da3_evidence.json)에 있다. 3개 진단점 × 3개 카메라 × 6개 깊이 = 54행, 입력 파일 125개를 읽었으며 모든 읽은 파일의 전후 SHA가 같았다.

## 2. 비교량과 픽셀 규약

깊이의 단위는 모두 camera Z의 미터다. 다음 차이는 반드시 유지한다.

| 자료 | 저장량과 규약 | 이번 비교에서의 한계 |
|---|---|---|
| ALS prior `raw_depth` | 공식 Open3D pinhole ray의 `t_hit`; receipt의 `depth_frame=CAMERA_Z_METERS`. 픽셀 중심은 `u+0.5,v+0.5` | GS 정수 픽셀 광선과 반 픽셀 차이가 있다. 좁은 골 경계에서 중요할 수 있다 |
| DA3 `raw_depth` | 입력 카메라 척도로 복원된 camera Z, 840×602 추론 깊이를 1400×1013으로 cubic 확대 | 원 격자·확대 보간의 규약이 있다. 정확한 국소 표면·가시성·척도 정확도를 보증하지 않는다 |
| Anchor/final `depth_*.tiff` | 원본 `surf_depth`를 float32 TIFF로 저장. source 기본 `depth_ratio=0.0`과 invocation의 무변경을 확인했으므로 alpha로 정규화한 **expected depth** | 여러 기여 표면이 섞일 수 있다. first-hit, median depth, 메쉬 표면과 동일하지 않다 |
| UAS probe | 저장 평가 표본의 3D 좌표를 `R X+t`로 투영한 camera Z | 원표본의 평가용 투영 깊이다. 그 표본이 해당 시점의 첫 가시 표면이라는 독립 증거가 아니다 |

따라서 표는 **같은 저장 배열 인덱스**를 연결한 결과다. exact same-ray 비교라고 주장하지 않는다. 원 배열 재보간이나 정합 보정을 수행하지 않았고, 반 픽셀의 영향을 감추지 않기 위해 원 인덱스와 5×5 주변 유효값 범위도 전부 저장했다. `world_endpoint_z`는 prior의 반 픽셀 규약을 반영한 v2만 사용한다.

근거 코드: 공식 `LoD2Depth/raycasting.py:53–91`; 실행 wrapper `scripts/phd/geogs_p1p2p3_v1/input/prior_native.py:141–179`; 실행 source `gaussian_renderer/__init__.py:140–154`, `arguments/__init__.py:104`, `utils/mesh_utils.py:102–117,335–348`, `utils/render_utils.py:278–281`, `jbgs_camera_adapter.py:14–30`.

## 3. P1의 낮은 바닥과 P2의 큰 형상 수정

사후에 고정한 단면 위치 근처에서 기존 UAS 평가 표본 1개를 선택하고, 이 점을 포함하는 train 카메라를 광선의 수직 성분 순으로 정렬했다. 깊이 결과를 보고 카메라를 선택하지 않았다. 다음은 그중 해석 가능한 관측이다. 카메라 Z는 카메라마다 기준이 달라 **행 사이 절댓값을 성능 비교하지 않는다.**

| 진단 위치 / 실제 train 사진 | 현재 참조점 투영 Z | prior | DA3 | anchor | D005 native | D0005 native | D0 release |
|---|---:|---:|---:|---:|---:|---:|---:|
| P1 바닥, `DJI_20241217084553_0100_D.JPG`, (819,478) | 74.671 | 69.974 | 72.093 | 70.057 | 70.453 | 72.927 | 73.168 |
| P2 변화부, `DJI_20241217091243_0144_D.JPG`, (995,442) | 60.404 | 56.104 | 58.389 | 56.043 | 58.233 | 58.777 | 58.558 |
| 같은 P2 변화부, `DJI_20241217091135_0110_D.JPG`, (1043,500) | 60.461 | 56.946 | 59.731 | 56.357 | 58.401 | 59.761 | 59.795 |

단위 m. P1 참조 xyz=`[-7.9439,-14.9673,-41.8268]`, original reference ID 574061. P2 참조 xyz=`[134.0359,127.0372,-27.6533]`, original reference ID 1123591. 전체 정밀도와 다른 선정 카메라도 CSV에 남겼다.

**원자료 관찰:** P1 사진 (819,478)에서는 인접 건물에 가려지지 않은 포장 바닥을 확인했다. P1의 prior/anchor는 이 낮은 면보다 약 4.6–4.7m 앞쪽 깊이에 있고, DA3는 약 2.58m 앞쪽이다. D0005의 저장 깊이는 약 1.74m 앞쪽까지 수정되어 D005보다 개선되지만 목표 표면까지 내려가지는 않는다. P1을 “전혀 수정되지 않았다”고 표현하면 부정확하다.

**우리 추론:** 이 시점에서 DA3 target 자체도 현재 면의 깊이에 못 미친다. 그러나 final D0005가 DA3보다 깊게 도달하므로 GeoGS가 DA3 깊이를 그대로 복사했다고 볼 수 없다. RGB·prior·다른 관측·정규화·구조 보호와의 결합 결과를 조사해야 한다. P2 변화부도 DA3와 final이 prior/anchor보다 현재 방향으로 이동한다. 두 지역의 차이를 DA3라는 모듈의 존재 여부만으로 설명할 수 없다.

**가려진 관측을 제외하는 이유:** 선정 규칙의 P1 두 번째 사진 `DJI_20241217103051_0002_D.JPG`의 투영점 (582,440)은 실제 사진에서 앞쪽의 높은 긴 곡면 지붕 위에 놓인다. 현재 낮은 바닥의 투영 깊이는 97.15m인데 prior/DA3/GS 모두 약 57–58m인 것은 그 앞면과 일관된다. 이는 바닥 깊이를 40m 틀렸다는 증거가 아니다. 세 번째 `...103057_0005...`도 약 38m 앞면을 지지한다. 두 행을 삭제하지 않았으며 가시성 미확인/가림 사례로만 남긴다. 앞쪽 ray surface와 뒤의 UAS 표본을 구분하지 않으면 DA3 오류를 과장할 수 있다.

## 4. P2 반복 골: 학습 깊이에서 이미 나타나는 얕아짐

선택 참조 xyz=`[134.0010,96.6321,-31.1562]`, original reference ID 501624. 동일한 물리적 위치를 세 train 사진에서 투영했다.

| train 사진 / 픽셀 | 현재 참조점 투영 Z | prior | DA3 | anchor | D005 native | D0005 native | D0 release |
|---|---:|---:|---:|---:|---:|---:|---:|
| `...091249_0147...`, (844,469) | 63.939 | 62.910 | 62.047 | 63.204 | 62.533 | 62.470 | 62.401 |
| `...091251_0148...`, (855,612) | 63.734 | 62.357 | 60.772 | 62.320 | 61.799 | 61.636 | 61.835 |
| `...091247_0146...`, (837,326) | 64.098 | 63.206 | 62.347 | 63.594 | 62.767 | 62.672 | 62.658 |

**원자료 사실:** 세 시점 모두 DA3가 anchor보다 얕다. 최종 expected depth도 anchor보다 얕아졌다. D0005의 anchor 대비 변화는 각각 약 −0.735m, −0.684m, −0.921m다. 따라서 이 관측량의 변화가 TSDF/후처리에서 처음 발생했다고 할 수 없다.

**사진 확인:** 원 train 사진 0147, 0148, 0146을 직접 열었다. 투영 위치는 반복 곡면 사이의 좁고 어두운 골/면 경계다. 반복 구조가 사진에 있다는 사실은 확인되지만, UAS의 낮은 특정 표본이 실제 영상의 첫 가시 표면인지와 골의 가장 낮은 부분이 얼마나 노출되는지는 사진만으로 확정하지 않았다. 세 사진은 DA3 batch 1로 같아서 독립적인 depth context 검증도 아니다.

**원인에 대한 한계:** prior의 같은 인덱스 깊이도 UAS보다 얕고, 5×5 주변에는 ray miss와 여러 깊이가 섞여 있다. 초기/anchor 단면의 다중면, 구조 깊이의 ray 선택, DA3의 좁은 형상 표현, expected-depth 혼합, 학습 중 opacity 변화, 추출이 모두 가능한 전달 경로다. “정확한 골이 완전히 들어 있었는데 DA3가 처음 파괴했다”는 결론은 현재 근거보다 강하다. DA3는 얕아짐을 강화할 수 있는 후보이고, 이를 분리하려면 같은 광선 규약과 가시성으로 감독·학습 깊이를 대응한 뒤 최소 개입을 설계해야 한다.

## 5. 기존 DA3 유효값·척도 감사의 현재 의미

[기존 유효값 감사](../geogs_p1p2p3_v1/DA3_DEPTH_VALIDITY_AUDIT_ko_v1.md)와 [척도 규약 감사](../geogs_p1p2p3_v1/DA3_SCALE_CONVENTION_AUDIT_ko_v1.md)를 색인으로 삼고 실제 `runtime/da3/depth_validity_audit_v1/summary.json`, 최종 inference receipt, 공식 DA3 코드, 실행 wrapper를 다시 읽었다.

- 원 추론 배열은 양의 유한 깊이다. 확대 후 일부 음수는 cubic overshoot와 바이트까지 일치했고 GeoGS의 finite-positive mask에서 제외된다. 이번 선정 픽셀의 DA3는 모두 양의 유한값이다. 이 픽셀들의 잔여 오차를 음수 보간 문제로 설명하지 않는다.
- DA3 commit `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`, 모델 revision `8615eefb62f2db4f8d6ebaa59160086981672829`. GeoGS commit `db40c95c657ec03ff21c83cb99cf39f4e90247a6`와 명시된 camera/state adapter 계보다.
- DA3 `api.py:327–365`의 입력 궤적 정규화 및 Umeyama 척도 복원과 `utils/pose_align.py:78–90`의 참조/추정 방향은 일관된다. wrapper의 역수 오류가 확인된 것은 아니다.
- 반환 표정이 입력 표정과 같은 것은 API가 반환 값을 교체하기 때문이다. 예측 표정이 정확했다는 검증이 아니다. 사용한 7/8장 batch에서는 10장 이상일 때의 RANSAC이 적용되지 않는다.
- 교체 전 예측 표정, API의 당시 Umeyama scale, nested 모델의 별도 scale factor는 현재 보존 배열에 없다. 지금 원인을 각각 분해할 수 없으며, 이를 복구하려고 추론을 다시 돌리지 않았다.
- 기존 full-ROI prior/DA3 차이는 출처 간 차이 진단이다. 가림·표면 불일치가 섞인 전체 ROI 차이를 곧 DA3 정확도라고 사용하지 않는다. 이번 P1의 가림 사례가 그 구분의 실제 예다.

## 6. 다음 원인 확인과 기각 조건

1. P1의 관측 가능한 바닥과 P2 변화부에서 더 많은 독립 train 시점을 실제 가시성 기준으로 대응한다. “투영됨”을 “가시적임”으로 바꾸어 말하지 않는다. 충분한 current depth/다중 시점 조건이 없으면 정보 부족을 그대로 남긴다.
2. P2 골은 pixel-center 차이와 expected/median/first-hit 차이를 먼저 정리한다. 기존 저장 expected depth만으로 표면 하나의 위치를 보증하지 않는다. 현재 ray-depth에 실제로 정확한 골 정보가 도달하지 않았다면 최초 문제는 refinement 이전일 수도 있다.
3. DA3·prior 보호·초기 상태·표현·추출 중 변경할 하나의 원인을 정한 뒤 동일 기준점과 성공·실패 구간을 포함한 비교를 제안한다. 이번 세션에서는 실행하지 않는다.
4. 가시성과 규약을 맞추자 차이가 사라지거나 기존 제어/기존 추출로 보존과 수정이 함께 회복되면 새 업데이트 마스크의 필요성 주장은 약해진다. DA3를 제거/개선했을 때만 반복적으로 회복되면 DA3 입력/사용 방식의 설명이 강해지고, 정확한 DA3에서도 보호 때문에 수정이 막히면 업데이트 허용 제어의 설명이 강해진다.

이번 결과는 마스크의 신규성이나 우위를 검증하지 않는다. 특히 판별 가능한 정보가 아직 감독으로 전달되지 않는데 단순히 업데이트를 허용해도 올바른 수정 방향이 생기는 것은 아니다.

## 7. 실행·보존 기록

Docker `jointbuildgs:geogs-official-db40c95-compat-v1`, image ID `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, NumPy 1.26.4/Pillow 12.2.0을 사용했다. 네트워크/GPU/새 의존성 없이 CPU 2개, 메모리 2GiB, source/repository 읽기 전용 마운트로 실행했다. 출력은 이 새 분석 경로뿐이다.

첫 Docker 실행은 이미지의 기본 working directory `/workspace/geogs`를 읽기 전용 마운트에서 만들려다 container init에서 실패했다(exit 125). `-w /tmp`를 명시한 실행은 완료했다. 원자료를 읽기 전에 발생한 실행 환경 오류이며 원자료 변경은 없다. 몇 개의 추정 파일명 검색은 존재하지 않아 `rg --files`로 실제 경로를 찾았다.

처음 생성한 `analysis/da3_evidence.json`과 `analysis/da3_probe_depths.csv`는 초안으로 보존한다. 반 픽셀 규약을 명시하고 prior의 world endpoint 계산에 이를 반영한 최종 v2는 `analysis/da3_convention_corrected_v2/`다. **camera-Z 원값은 두 버전에서 동일**하며, 최종 해석과 재현에는 v2를 사용한다. script는 기존 출력 JSON을 덮어쓰지 않는다.

재현 명령은 source를 `/source:ro`, repository를 `/workspace:ro`, 이 문서의 `analysis/`를 `/out:rw`로 마운트한 위 Docker 이미지에서 다음과 같다. 출력 경로는 기존에 없는 이름이어야 한다.

```bash
python /workspace/scripts/phd/geogs_causal_followup_v1/da3_audit.py \
  --source /source --output /out/da3_NEW \
  --config /workspace/configs/phd/geogs_causal_followup_v1/da3_audit.json \
  --image-id sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
```

새 학습·장면 렌더·DA3 추론·메쉬 추출·정합·참조 기반 mask 생성은 모두 0회다. `scientific_verdict: null`을 유지한다.
