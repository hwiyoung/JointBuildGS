# DA3 깊이 유효값 감사 v1

`task_id: PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

세 지역 학습 전용 DA3 최종 입력 292개를 전수 확인했다. 원 추론 해상도에서는
모든 값이 유한한 양수였으며, 원 영상 해상도로 올린 배열의 음수 5,077개는 공식
GeoGS `cv2.INTER_CUBIC` 보간을 다시 실행한 결과와 바이트 단위로 일치한다.
이번 음수는 보간 overshoot로 확인되었다. 원 DA3 기하의 정확성을 보증하는 검사는 아니다.

| 지역 | 전체 / 음수 포함 지도 | 원 해상도 음수 / 0 / 비유한 | 확대 후 음수 / 전체 픽셀 | 확대 후 유한 범위 (m) |
|---|---:|---:|---:|---:|
| P1 | 98 / 57 | 0 / 0 / 0 | 751 / 138,983,600 | −66.5295486 ~ 698.0660400 |
| P2 | 57 / 26 | 0 / 0 / 0 | 3,366 / 80,837,400 | −69.9515381 ~ 554.9788208 |
| P3 | 137 / 71 | 0 / 0 / 0 | 960 / 194,293,400 | −88.1793900 ~ 681.3936768 |

확대 후 0과 비유한 값도 세 지역 모두 0개다. 원 추론 깊이의 유한 범위는 P1
12.5297089~654.1454468m, P2 8.8179111~523.0744019m, P3 12.4808731~631.7114258m다.
각 지도는 최종 입력 receipt의 SHA256과 먼저 대조했으며, 원 추론 배열을
float32 `INTER_CUBIC`으로 확대하여 모든 픽셀과 배열 bytes를 비교했다.
292개 모두 동일하다. 원 배열과 최종 입력의 어느 픽셀도 변경하지 않았다.

공식 commit `db40c95c657ec03ff21c83cb99cf39f4e90247a6`의 `train.py:296`은
`isfinite(gt_depth) & isfinite(pred) & (gt_depth > 0)`을 사용한다. 따라서
음수 깊이는 원 손실에서 제외된다. 입력 봉인은 음수 개수와 원인을 기록하고,
공식 전처리가 실제로 생성하는 값을 임의로 clamp하지 않는다.

감사는 Docker `jointbuildgs:geogs-da3-3d835ec-v1`에서 GPU 없이 수행했다.
이미지 ID는 `sha256:4130d2597c2c3c2804a7cacb8302be948314bc37ba81a1a21383e1c8b7fbba73`이며,
NumPy 1.26.4, OpenCV 4.10.0을 사용했다. 세 지역 `da3/`만 읽기 전용으로
마운트했고, 사진·UAS·평가 참조는 접근하지 않았다. 첫 실행은 이미지의 Python
ENTRYPOINT에 `python`을 중복 지정하여 `/work/python` 파일 오류로 종료했다.
명시적인 `--entrypoint python`으로 수정한 재실행이 완료되었으며, 데이터는 변경되지 않았다.

외부 task root 아래 감사 산출물:

- `runtime/da3/depth_validity_audit_v1/per_image.csv`: 이름·카메라·batch·두 배열 hash,
  개수·범위·재보간 일치 여부·음수 원인.
- `runtime/da3/depth_validity_audit_v1/summary.json`: 지역 합계, 소스·모델 식별자,
  라이브러리 버전, 감사 script hash.
- summary SHA256: `6363c4458b0772def8d4f5b6532aad59e4d004e929c9fd06789a79d8c3e2d153`.

재실행은 새 출력 이름으로만 가능하다:

```bash
bash scripts/phd/geogs_p1p2p3_v1/da3/audit_depth_validity.sh depth_validity_audit_NEW
```

실행 script는 `scripts/phd/geogs_p1p2p3_v1/da3/audit_depth_validity.py`다.
이 감사는 입력 계약 확인이며 지역별 재구성 성능이나 과학적 결론을 대신하지 않는다.
