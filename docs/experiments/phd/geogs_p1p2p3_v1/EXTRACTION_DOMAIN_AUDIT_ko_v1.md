# 공식 TSDF 깊이 범위 입력 감사

`PHD-GEOGS-P1P2P3-v1` · 입력 전용 진단 완료 · `scientific_verdict: null`

공식 카메라 기반 TSDF 깊이 절단은 일부 학습 시점에서 고정 평가 prism을 전부 포함하지 않는다. P2에서는 57개 시점 중 24개가 prism 전체를 절단값보다 멀리 둔다. 이 시점에서 해당 prism 위치의 카메라-Z 깊이 표본은 공식 bounded TSDF 입력으로 사용할 수 없다. 나머지 28개는 prism 깊이 전체를, 5개는 일부를 포함하므로, 이 사실만으로 최종 표면 결손이나 GeoGS의 실패를 예측할 수 없다.

## 실제 입력 검사

| 지역 | 학습 카메라 | 공식 `depth_trunc` (m) | prism 깊이 전체 포함 | 일부 포함 | 전체가 절단값 초과 | 카메라 뒤쪽 |
|---|---:|---:|---:|---:|---:|---:|
| P1 | 98 | 173.37518684841817 | 61 | 37 | 0 | 0 |
| P2 | 57 | 258.29307070814457 | 28 | 5 | 24 | 0 |
| P3 | 137 | 157.04527210517023 | 67 | 69 | 1 | 0 |

모든 292개 학습 시점에서 고정 prism의 영상 내 투영 bounding rectangle은 비어 있지 않았다. 실제 COLMAP 바이너리에서 복원한 공식 float32 world-to-view 행렬과 봉인 분할 명세에서 복원한 행렬은 292개 모두 byte 단위로 동일했다. RGB·깊이 지도·학습 모델·추출 표면·UAS는 읽지 않았다. 출력 경로 외에 입력이나 실행 설정을 변경하지 않았다.

| 지역 | 공식 focus 좌표 (shifted EPSG:25832, m) | 카메라-focus 최소 거리 (m) | 전체 prism 카메라-Z 범위 (m) |
|---|---|---:|---|
| P1 | (0.0556525211, −13.9518330829, −57.3011455108) | 86.68759342420908 | 41.6266757743–186.4399409499 |
| P2 | (80.0925768331, 87.1530216735, −95.1472352545) | 129.14653535407228 | 49.4081054425–353.4882748725 |
| P3 | (−19.2473994086, −22.7119594883, −54.0325045354) | 78.52263605258511 | 18.6575067361–217.8263987173 |

실제 입력으로 생성한 [P1 깊이 구간 그림](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/P1_camera_depth_intervals.png), [P2 그림](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/P2_camera_depth_intervals.png), [P3 그림](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/P3_camera_depth_intervals.png)을 모두 열어 표시를 확인했다. 가로축은 공식 파일명 stem 순서의 학습 시점, 세로 선은 prism 8개 모서리의 카메라-Z 최솟값과 최댓값, 점선은 해당 지역의 동일한 공식 절단값이다. 대표 시점을 골라 그린 그림이 아니라 모든 학습 카메라를 표시했다.

## 공식 경로와 대응

고정 source는 `GeoGS-state-camera-v1`이며 원 GeoGS commit은 `db40c95c657ec03ff21c83cb99cf39f4e90247a6`이다. 공식 `scene/colmap_loader.py`의 `read_extrinsics_binary`, `qvec2rotmat`, `utils/graphics_utils.py`의 `getWorld2View2`, `utils/render_utils.py`의 `focus_point_fn`을 변경 없이 CPU에서 실행했다.

`render.py`는 카메라 순서를 섞지 않고 학습 카메라를 `GaussianExtractor`에 전달한다. 이 감사도 같은 파일명 stem 정렬과 봉인 학습 멤버십을 사용한다. 공식 `getWorld2View2`가 반환하는 float32 행렬을 NumPy에서 역행렬로 변환하고, `estimate_bounding_sphere`와 같은 축 반전을 적용한 pose를 `focus_point_fn`에 전달했다. 카메라 중심과 focus 간 거리의 최솟값을 radius로 사용하며, `depth_trunc = 2 × radius`다. 이 radius는 평가 prism이나 대상 건물을 포함하도록 계산한 반경이 아니다.

공식 기본식 `voxel_size = depth_trunc / mesh_res`, `sdf_trunc = 5 × voxel_size`를 적용하면 다음과 같다. 각 쌍은 voxel/sdf 길이(m)다.

| 지역 | mesh_res=512 | mesh_res=1024, 주 비교 | mesh_res=2048 |
|---|---|---|---|
| P1 | 0.3386234118 / 1.6931170591 | 0.1693117059 / 0.8465585295 | 0.0846558530 / 0.4232792648 |
| P2 | 0.5044786537 / 2.5223932686 | 0.2522393269 / 1.2611966343 | 0.1261196634 / 0.6305983172 |
| P3 | 0.3067290471 / 1.5336452354 | 0.1533645235 / 0.7668226177 | 0.0766822618 / 0.3834113089 |

해상도 민감도는 voxel/sdf 길이를 바꾸지만 동일한 깊이 절단값을 유지한다. 따라서 512/1024/2048 비교만으로 절단값 밖의 깊이 표본을 복구하는 것은 아니다. 위 수치는 카메라 메타데이터에서 계산한 값이며, 각 실제 추출 로그의 실행값과는 최종 실행 검증에서 별도로 대조한다.

## 해석 범위와 후속 분석

- prism은 기존 고정 half-open 범위다. 여기서는 선형 카메라-Z의 범위를 구하려고 그 폐포의 8개 모서리를 사용했다. 제외되는 상한 면에서 보수적인 경계 검사가 되며, 포함된 체적 비율을 계산한 결과가 아니다.
- 깊이 범위 포함은 영상에서의 실제 관측·가시성·가림 없음·정확한 렌더 깊이·표면 복원 성공을 보장하지 않는다. 투영 rectangle도 실제 silhouette나 정확한 frustum 교차 검사가 아니다. 이 보조 검사는 봉인 K와 공식 float32 외부표정을 사용했다.
- 일부 포함 시점에서는 깊이 극값을 만드는 모서리가 영상 밖에 있을 수 있다. 따라서 이 카메라 개수를 실제 표면 손실률로 바꾸지 않는다. 절단값보다 가까운 잘못된 표본이나 다른 카메라가 만드는 TSDF 표면까지 불가능하다는 뜻도 아니다.
- 이 제한은 같은 지역의 원설정·제어 변경·anchor·바닐라 반복에 공통이다. 표면의 실제 결손·잘못된 잔존·세부 변화가 관찰되면, 학습 제어와 이 추출 범위 제약을 구분해 해석한다. 지역별 카메라 배치와 절단값이 다르므로 지역 간 결과 차이를 제어 효과만으로 돌리지 않는다.
- 본 실행의 깊이 절단과 과학 설정은 그대로 유지한다. 향후 절단 범위 영향 자체를 분리할 필요가 생기면 결과에 맞춘 재설정 없이 별도 사전 조건으로 검증해야 한다. 이 입력 감사는 반복 재판단의 필요성이나 효과를 입증하지 않는다.

## 재현과 원자료

실행 스크립트는 [extraction_domain.py](../../../../scripts/phd/geogs_p1p2p3_v1/input_diagnostics/extraction_domain.py), 실행 명령은 `bash scripts/phd/geogs_p1p2p3_v1/input_diagnostics/run_extraction_domain.sh`다. 출력이 존재하면 재실행을 거부한다. CPU 2개·메모리 3 GiB·네트워크 차단·읽기 전용 컨테이너에서, 필요한 카메라/분할/manifest 파일만 읽기 전용으로 연결했다. 실제 Python 구간은 2.7058466608초, peak RSS는 434,110,464 bytes였다.

고정 Docker image ID는 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`다. 원자료는 외부 task의 `input_diagnostics_v1/extraction_domain_v1/`에 있다.

- [292개 시점 CSV](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/per_training_view.csv): SHA256 `2c4e207db699c2923a7a202510ed0ab49d8d6da45f54190d8fcca9010c9e946a`.
- [지역별 summary JSON](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/summary.json): SHA256 `cf5c44072bf13ccb23302a47d00846db7182f6ac1ff2201aef3fc26ede56e2d6`.
- [실행 receipt](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/receipt.json), [방법·공식 source hash](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/policy.json), [입력 hash ledger](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/input_ledger.json).
- [행렬 byte 비교 추가 확인](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/input_diagnostics_v1/extraction_domain_v1/byte_equality_verification.json): 본 진단의 float32 값 비교에 이어 `tobytes(order='C')`로 292개 모두 동일함을 확인했다. 같은 고정 Docker image의 CPU 검사이며 실행 source `verify_camera_bytes.py`와 그 hash를 별도 보존했다.
- 실행 script snapshot SHA256 `757bb44dadafcacf9ea747f8ce93028f3f2b3d7aab3be754b4fa4aa3eeb6d5a6`, 과학 config SHA256 `b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4`.

각 산출물·실제 실행 script·실행 명령·config snapshot의 hash는 receipt에 기록했다. input ledger의 지역 manifest SHA는 기존 봉인값과 정확히 일치함을 확인한 뒤 계산을 진행했다. 이 문서는 입력/추출 범위 진단이며 세 지역의 실제 정량·정성 결과 분석을 대체하지 않는다.
