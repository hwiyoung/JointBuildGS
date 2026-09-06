# C v2 — 독립 B 비교의 평가

2026-09-07. B 학습 전 프로토콜. `scientific_verdict: null`.

**실행 중 확인된 renderer 계약 오류와 정정:** 첫 12조건은 screen-only 저역 필터의
alpha를 ray–plane 기하 깊이의 지지로도 사용했다. 실제 grazing ray 감사에서 부당한
수천 m 깊이와 해당 gradient 분기 오류를 확인했다. 이 깊이로 학습·관측 마스크도
구성했으므로 기존 수치는 방법 성패에 사용하지 않는다. 기존 실행·UI QA·부분 C를
보존하며 `CORRECTED` 실행만 최종 비교에 사용한다. 수정은 UAS 점수에 따른 튜닝이
아니라 유효 교차 지지와 미분 계약의 복구다. 최초 프로토콜과 정정 전 소스는 별도
`ROOT-AUDIT-v1/evaluation_protocol_before_reference_v3`와 중지 C 소스 snapshot에 남는다.

수정에서는 화면 RGB 합성과 plane-hit 기하 합성을 분리한다. 기하 존재·깊이·법선은
독립 geometry mass로 정의하며, 공통 mask 안의 존재/누락도 `geometry_mass≥0.5`로
계산한다. RGB alpha coverage는 별도 필드다. tile culling/중심깊이 순서·겹층 기대깊이의
한계는 남으므로 유효 plane 기여만 사용한다는 사실을 정확한 단일 현재 표면 보장으로
확대하지 않는다. 동일 XYZ의 exact 거리 계산 캐시와 CPU 병렬화는 지표 정의를 바꾸지 않는다.

B의 과거 ALS 구조 가정은 A가 확보한 현재 사용 판정이 아니다. 이번 C는 동일
P2에서 B의 변수·관측·재구성 결과를 비교하며 새 A 전체 성능으로 해석하지 않는다.

## 비교 분모

같은 ALS G0의 source projection, geometry fixed, color fixed, soft prior,
structured detail을 비교한다. image-only는 별도의 MVS G0이므로 초기화·source와
최적화를 합한 효과로 구분한다. v1 대비 수치 변화는 원영상 해상도·표현·관측
분모가 달라 순수 방법 효과로 해석하지 않는다.

## 세 축과 현재 정확성

1. **구조 유지:** B의 고정 source 구조 성분·표면 정의에서 이동·법선·존재·경계
   변화를 확인한다. 변수를 고정한 결과, 제한을 만족한 결과와 현재 정확성을 구분한다.
2. **현재 외관:** 같은 평가 카메라의 실제 사진과 gsplat 초기/최종 렌더를 비교한다.
   초기 고정 support, 공통 support 및 전체 valid crop의 차이와 누락을 명시한다.
3. **세부:** detail·법선 자유도가 실제로 변했는지와, 그 변화가 참조와 일치했는지를
   구분한다. 변수 변화 또는 이미지 오차 감소만으로 세부 복원 성공이라고 하지 않는다.
4. **현재 기하:** B가 읽지 않은 기존 공통 UAS 참조를 이용해 prediction→reference
   거리와 고정 reference→prediction 회복/누락을 함께 계산한다. source 보존과 별개다.

UAS 비교는 기존 local numeric frame을 그대로 사용하는 개발 진단이다. datum/epoch와
센서별 절대 정확도가 보정됐다고 주장하지 않으며 GT 정합으로 B 결과를 수정하지 않는다.

소스 초기화와 표현 밀도가 다른 비교에는 주 실행 ALS `geometry_fixed`와 MVS
`image_only`의 **학습 전 조건부 observation support 합집합**을 고정 공통 ray-mask로
사용한다. 별도 density 실행도 같은 mask에 평가한다. 저장된 8-bit RGB PNG와 alpha로
MAE/PSNR·표면 존재/누락을 집계하고, B 내부 float-image 점수와 구분한다. 같은 카메라·
crop·target bytes를 검사한다. 이 mask의 앞가림 처리도 current MVS와 카메라 오차에
의존하므로 인증 면적이 아니다. 전체 사각 crop에는 P2 밖 배경·전경도 포함되므로 그
오차를 P2 복원 품질 하나로 해석하지 않는다. 이 규칙은 B 본 학습 전 가림 검토에서 추가했다.

## 세부의 제한적 수치 진단

같은 P2 XY 영역을 0.25/0.5/1 m 격자로 고정한다. 각 격자의 점 Z 중앙값에서
상하좌우 네 이웃 중앙값의 평균을 뺀다. 이상적인 균일 격자에서 affine 높이의 잔차는
0이다. 실제 불규칙 표본의 cell-median은 평면에서도 비영 잔차가 생길 수 있으므로,
거친 이동과 국소 높이 변화를 구분하는 제한적인 진단으로 사용한다. 격자 간격은 개발용
표시/분해 규모이며 판정 합격 문턱이나 데이터의 인증 정밀도가 아니다.

초기·최종·참조의 다섯 격자가 모두 존재하는 동일 stencil에서 잔차 오차·진폭을
비교한다. 동시에 참조 전체 eligible stencil 분모에서 초기/최종 결손 수를 남긴다.
출력이 사라진 영역을 제거해 세부 오차가 개선된 것처럼 해석하지 않는다.

위 paired stencil은 arm별이므로 그 오차로 arm 간 순위를 정하지 않는다. 추가로 모든
비교 arm의 초기·최종·참조가 함께 존재하는 **단일 교집합 stencil**의 점수를 출력한다.
교집합 밖 참조 분모와 각 arm의 결손도 남긴다. 교집합 점수는 그 좁아진 관측 범위의
비교이며 전체 P2 세부 복원 우월성이 아니다. 이 보완은 첫 UAS 결과 열람 전 검토에서 고정했다.

prediction→reference 거리는 각 arm의 추출 표본 분모이며, reference→prediction은
같은 UAS 점 분모다. 가려진 prior의 추출 표면도 기하 평가에 포함된다. 이 점수를
현재 영상으로 확인한 면적이나 A의 현재 사용 적격성 판정으로 해석하지 않는다.

이 계산은 **2.5D cell-median 높이 진단**이다. 벽·겹층·밀도 차이·참조 잡음·격자
aliasing의 영향을 받으므로 모서리/용마루 복원 전체를 인증하지 않는다. 실제 사진,
Gaussian 형상, 같은 위치의 단면과 함께 읽고 필요하면 구체적 형상별 평가를 후속 설계한다.

## 실행·표현 검증

실제 저장된 전체 Gaussian의 중심·크기·quaternion·opacity·색을 새 화면에 연결한다.
브라우저의 3σ kernel/중심 깊이 합성 화면과 정확한 gsplat 렌더 이미지를 구분한다.
학습 카메라·원영상·crop·초기화가 비교 arm에서 같은지, detail이 활성화되고 갱신했는지,
선택/유보 조건을 B가 만들어낸 것으로 오인하지 않는지 검증한다. 참조 오차로 손실이나
표본을 다시 고른 결과를 원래 비교와 섞지 않는다.
