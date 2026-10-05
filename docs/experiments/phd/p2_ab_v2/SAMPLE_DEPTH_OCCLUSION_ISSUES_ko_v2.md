# P2 외부 전경과 COLMAP map 감사

2026-09-07. 비확증 개발, `scientific_verdict: null`. 기존 source·출력 수정 없음.

## 1. P2만 비교한 깊이 경고와 전체 장면 재검사

초기 P2 MVS front-depth와 COLMAP global depth를 비교했을 때 435뷰의 signed gap
중앙값이 +88.768 m였고 400뷰는 +190.965 m였다. 이를 곧바로 가림에 사용하지 말고
계보·단위 문제를 확인하자는 임시 경고를 B와 root에 전달했다. **이 값만으로 깊이
파일의 좌표나 단위가 틀렸다고 확정할 수 없다.** P2 밖의 가까운 물체가 앞을 가리면
이 정도 차이는 정상이다. 이어 296뷰가 -0.0092 m로 일치함을 확인하고 전역 scale
오류라는 해석을 배제하지 않은 초기 경고를 보완했다. 임의 scale 보정은 하지 않았다.

같은 exact937 계보의 전체 native MVS 43,926,567점을 각 카메라에 투영해 P2 밖까지
포함한 front-depth를 추가 계산했다. 그 결과는 다음과 같다. 분모는 P2 MVS가 투영된
깊이 지도 픽셀 중 전체 MVS와 COLMAP depth가 모두 존재하는 픽셀이다.

| 뷰 | 분모 | 전체 MVS−COLMAP depth 중앙 (m) | 절대차 ≤1 m | P2보다 >1 m 앞인 전체 MVS | 그중 P2 밖 |
|---|---:|---:|---:|---:|---:|
| 435 | 3,307 | -0.3955 | 1,317 (39.8%) | 3,289 | 3,289 |
| 400 | 2,004 | -0.3131 | 1,296 (64.7%) | 2,004 | 2,004 |
| 296 | 184,484 | -0.0093 | 176,661 (95.8%) | 137 | 136 |

435의 원본 crop을 직접 확인하면 큰 굴뚝과 가까운 건물들이 시야를 덮는다. 전체 MVS
전경의 XY도 P2 밖에 있으며, P2만의 깊이와 global depth 사이의 큰 차이는 **P2 밖
전경 가림**이라는 설명을 지지한다. 이에 초기 사용 보류는 전역 단위 오류의 확정이
아니었다고 정정하고, B에 이 검사 결과를 전달했다. 435/400의 잔여 오차 꼬리는 크므로
모든 depth 픽셀의 정확성까지 통과한 것은 아니다. 이 검사는 같은 영상 계보의 수치
대조이며 독립 참조에 의한 실제 오차 보증도 아니다.

이 발견은 입력 crop의 모든 픽셀이 원본에서 유효하다는 것과, P2 표면이 실제로
보인다는 것이 다르다는 뜻이다. 원본 RGB의 100% valid mask는 가림 mask가 아니다.
기존 66개 뷰를 투영 가능하다는 이유만으로 모두 P2 현재 표면의 증거로 세지 않는다.

## 2. v2 전용 좌표 adapter와 조건부 가림

[sample_depth_mapping.py](../../../../scripts/phd/p2_ab_v2/sample_depth_mapping.py)는
기존 파일을 변경하지 않는 별도 reader와 ray adapter다.

- `depth_intrinsics(view)`: 기존 1400×1013 RGB K에 실제 map 크기 1024×741의
  축척을 적용한다. COLMAP 원 코드도 축별 새 크기/기존 크기로 focal과 principal
  point를 함께 조정한다. [COLMAP 3.9.1 Image::Rescale](https://raw.githubusercontent.com/colmap/colmap/3.9.1/src/colmap/mvs/image.cc)
- `sample_depth_rays(view, uv, current_K, depth)`: 현재 B crop/resize K의 역행렬로
  ray를 만들고 depth K로 투영한다. 3뷰의 native점에서 이 결과와 직접 depth K
  투영의 최대 오차는 3.5×10⁻¹³ px 미만이었다. depth는 camera Z로 비교한다.
- `nearest_known`, `all_four_known`, `footprint_min_z`, `footprint_max_z`를 별도로
  돌려준다. 0·비유한 값·화면 밖은 unknown이다.
- B가 선택한 개발용 가림 조건은 같은 ray의 2×2 표본이 모두 알려져 있고,
  그중 가장 먼 depth에 1 m를 더해도 초기 표현보다 앞인 경우다. 1 m는 보정된
  확률·오차 상한이 아니라 명시한 개발 조건이다. Unknown을 prior 기각이나
  현재 사용 승인으로 바꾸지 않는다. 가림 경계의 dilation도 별도 승인 없이
  unknown 영역으로 전파하지 않는다.

이 sample 감사의 픽셀 분모와 B의 gsplat pixel-center·renderer support 분모는 다르다.
B 결과에는 전체 support, 알려진 depth, unknown, 제외 픽셀을 별도로 기록해야 한다.
실제 앞물체를 확인하는 조건부 가림 사용과 MVS를 prior의 기하 감독으로 사용하는
것을 구분한다. A가 기각한 소스를 새 정답 감독으로 복귀시키는 승인이 아니다.

## 3. 기존 다채널 normal reader 불일치

`src/stage2/colmap_io.py:read_array`는 depth 1채널에서는 이번 별도 reader와
비트 단위로 같다. 그러나 normal 3채널을 `(height,width,3)`으로 바로 reshape한다.
COLMAP의 저장 순서는 채널별 영상 plane이며, 공식 reader는 이에 맞게 reshape와
축 교환을 한다. [COLMAP 3.9.1 공식 reader](https://raw.githubusercontent.com/colmap/colmap/3.9.1/scripts/python/read_write_dense.py)

실제 435·400·296 `.geometric.bin` normal 파일을 두 순서로 읽어 대조했다. 공식
순서의 nonzero normal은 세 파일 모두 길이 1과의 차이가 0.01 이내인 비율이 100%였다.
기존 순서는 각각 약 0.806%, 1.075%, 0.282%였다. 파일 경로와 SHA 및 전체 분포는
`COMMON-DEPTH-AUDIT-v1/depth_audit_receipt.json`에 남겼다.

기존 reader와 과거 결과는 수정하지 않는다. 이번 B 전경 mask는 depth만 사용하므로
이 다채널 불일치의 영향은 없다. 이번 v2는 native 원점 normal과 새 map API의 구분을
유지한다. 다른 과거 결과가 실제로 이 경로를 실행했는지, 어떤 결과에 얼마만큼
영향을 줬는지는 이번 증거로 추정하지 않는다. 공통 샘플에 저장된 native normal의
기원·정확성도 이 3개 image map의 parsing 검사로 대신 검증하지 않는다.

## 4. 실행과 산출물

외부 root는 `phase-payloads/phd/p2_ab_v2/`다.

- `PHD-P2-AB-V2-COMMON-DEPTH-AUDIT-v1`: 3뷰 P2 zbuffer·depth·normal parsing 대조,
  source/config snapshot, `depth_audit_receipt.json`.
- `PHD-P2-AB-V2-COMMON-GLOBAL-DEPTH-AUDIT-v1`: 전체 native MVS의 3뷰 front-depth,
  source/config snapshot, `global_depth_audit_receipt.json`.
- 실행 source: [sample_depth_audit.py](../../../../scripts/phd/p2_ab_v2/sample_depth_audit.py),
  [sample_global_depth_audit.py](../../../../scripts/phd/p2_ab_v2/sample_global_depth_audit.py).
- 실행 config: [sample_depth_audit_v1.json](../../../../configs/phd/p2_ab_v2/sample_depth_audit_v1.json),
  [sample_global_depth_audit_v1.json](../../../../configs/phd/p2_ab_v2/sample_global_depth_audit_v1.json).
- 동일 동결 Docker image `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`,
  Python 3.11.15, NumPy 1.26.4, OpenCV 4.10.0,
  Git HEAD `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`. source/config snapshot이
  미커밋 실행 코드까지 고정한다. 두 실행 모두 UAS/LoD2 참조를 읽지 않았다.

전체 장면 감사 중 source-support 밖의 `inf-inf` 계산에서 NumPy RuntimeWarning이
출력됐다. 그 픽셀은 명시한 `known` mask로 제외돼 표의 분모·차이에는 포함되지
않는다. 실행은 정상 종료했고 해당 경고를 숨기거나 원래 receipt를 덮어쓰지 않았다.

같은 RGB pixel과 전경을 연결한 3뷰 그림은
`PHD-P2-AB-V2-COMMON-DEPTH-FIGURE-v1/view_{435,400,296}_depth_context.png`에 있다.
원본 crop, P2-only MVS, 전체 MVS, COLMAP depth를 같은 카메라 Z 색 범위로 비교한다.
435에서는 RGB의 굴뚝과 두 global depth의 가까운 깊이 위치가 일치한다. 그림은 표시
전용이며 source·깊이·선정 조건을 바꾸지 않았다. 별도
[source](../../../../scripts/phd/p2_ab_v2/sample_depth_figure.py),
[config](../../../../configs/phd/p2_ab_v2/sample_depth_figure_v1.json)와 해당 외부 root의
`figure_receipt.json`에 입력·출력·환경 해시를 기록했다.
