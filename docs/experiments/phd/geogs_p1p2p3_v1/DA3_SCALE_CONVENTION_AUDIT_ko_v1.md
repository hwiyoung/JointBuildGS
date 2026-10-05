# DA3 반환 깊이·척도·픽셀 규약의 코드 감사

`task_id: PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

공식 DA3 commit `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`와 실제 실행 wrapper를
읽어 확인했다. 이 감사는 새 추론·깊이 재생성·정합 보정을 수행하지 않는다.

- `src/depth_anything_3/api.py:327–339`는 모델 입력용 외부 표정을 첫 카메라에
  상대화하고 카메라 중심 거리의 median으로 정규화한다. `api.py:341–365`는
  모델 반환 후 **입력** 궤적을 **예측** 궤적에 Umeyama Sim(3)로 맞춘 척도를 구하고,
  예측 깊이를 그 척도로 나눈 뒤 반환 외부 표정을 입력 외부 표정으로 교체한다.
  `utils/pose_align.py:85–91, 174–210`의 ref/est 인자 방향과 나눗셈은 일관된다.
  wrapper의 척도 역수 적용 오류는 확인되지 않았다.
- 반환 외부 표정과 입력 표정이 같다는 wrapper 검사(`da3/infer.py:175`)는 API의
  최종 반환 계약 확인이다. API가 값을 교체하므로 예측 궤적의 정합 오차가 작았다는
  증거는 아니다. 현재7/8장 batch에서는 API의10장 기준보다 작아 RANSAC을 사용하지
  않는다. 입력 카메라 중심 rank3만으로 예측 궤적이나 scale 추정의 안정성까지
  보증할 수 없다.
- `model/da3.py:377–416`의 nested 모델은 metric branch와 상대 깊이를 먼저
  least-squares scale로 연결하며 깊이와 표정 translation을 함께 조정한다. 그 뒤
  앞의 API 입력 표정 척도 복원이 적용된다. 두 단계를 혼동하지 않는다.
- 깊이는 camera Z 규약이다. `utils/export/glb.py:241–245`는
  `K^-1 [u,v,1] * depth`로 역투영하며 ray를 단위벡터로 정규화하지 않는다.
  `utils/geometry.py:434` 이후도 정수 픽셀 격자를 사용한다. Euclidean ray 길이와
  직접 같은 값이라고 가정하면 안 된다.
- `utils/io/input_processor.py:232–246, 262–275`는 boundary resize와14배수 resize에서
  K의 첫 행을 폭 비율, 둘째 행을 높이 비율로 조정한다. 별도 half-pixel principal-point
  보정은 없다. 이번 동일 크기 입력은1400×1013에서840×602가 되며, 동일 batch 내
  서로 다른 크기로 인한 추가 center crop은 없다. 확대는 공식 GeoGS의
  `INTER_CUBIC`을 그대로 사용했다. 최종 배열 전체에 대한 바이트 재검증은 별도
  [유효값 감사](DA3_DEPTH_VALIDITY_AUDIT_ko_v1.md)에 기록했다.

보존된 각 `da3/<region>/balanced_v2/batches/batch_NNN.npz`에는 처리 해상도 K,
반환 외부 표정, 원 입력 K/외부 표정, 깊이·confidence·영상 이름이 있다. 최종 입력
폴더의 inference receipt는 이 batch 산출물의 SHA를 연결한다.

재현 한계도 남는다. API의 Umeyama 척도와 교체 전 예측 표정은 반환 자료에 노출되지
않았고 저장되지 않았다. nested 모델의 별도 `scale_factor`는 `Prediction`에 존재하지만
당시 wrapper가 저장하지 않았다(`specs.py:45`, `utils/io/output_processor.py:63–74`).
따라서 보존된 최종 자료만으로 당시 두 척도 요인을 정확히 분리·역산할 수 없다.
동일 영상·K·표정에 대한 서로 다른 batch의 깊이 차이는 batch 문맥 민감도 진단이며,
그 차이를 Umeyama만의 영향 또는 multiview forward만의 영향으로 단정하지 않는다.

이 한계를 확인하기 위해 현재 입력을 다시 생성하거나 평가 참조로 척도를 보정하지
않았다. 새로 계측하는 재실행은 기존 입력과 구분한 별도 후속 진단이어야 한다.
