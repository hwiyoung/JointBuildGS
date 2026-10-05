# GeoGS의 MVS depth 감독과 PGSR 기하 loss 개발 실험

2026-09-14 · `PHD-GEOGS-MVS-PGSR-v1` · `scientific_verdict: null`

사용자는 기존 COLMAP depth, P1/P2/P3 공간 crop, prior 깊이 계수 .005/.0005,
native 구조 보호를 선택했다. 이 문서는 그 지시를 별도 소스·입력 결박·출력으로
구체화한다. 기존 GeoGS/LC 작업과 정본 E1–E6 조건을 수정하지 않는다.
기존 GeoGS를 기반으로 하라는 이번 지시에 따라 해당 실험의 공식
diff-surfel-rasterization을 유지한다. 정본 gsplat 구현 정책을 바꾸는 작업은 아니다.

## 질문과 비교

각 지역의 완전한 Anchor8k에서 같은 22,000 refinement step을 비교한다.

| 조건 | 현재 depth 감독 | normal / 다중 시점 제약 | 역할 |
|---|---|---|---|
| 기존 G | DA3 | 기존 GeoGS normal | 봉인된 대조 결과 |
| M | 기존 COLMAP MVS | 기존 GeoGS normal | depth 교체 효과 |
| MG | 같은 MVS | PGSR 방식 svgeo + mvrgb + mvgeom | 기하 loss 묶음의 추가 효과 |

각 조건에 prior .005/.0005와 native 보호를 적용한다. 기존 대조 6개와 신규 12개다.
M→MG는 normal 식·계수 교체까지 포함한 묶음 효과이며 세 loss의 개별 기여를
분리한 ablation은 아니다. Prior·MVS 파일 자체, 카메라 정합·시간적 유효성 변수를
최적화하는 실험도 아니다. 두 고정 기하 감독과 현재 RGB를 받아 GS 기하를 최적화한다.

## 구현 명세

[현행 설정 v2](../../../../configs/phd/geogs_mvs_pgsr_v1/experiment_v2.json)가 수치를 소유한다.
최초 v1은 GPU 이전 입력 준비 실패 기록과 함께 보존했다. v2는 이웃 없는 카메라의
처리를 명시하며 실험 조건·기하 loss 계수·이웃 선정 수치 자체는 바꾸지 않는다.

- 기존 RGB는 1400×1013, native MVS는 1024×741 camera-Z(m)다. 같은 정수 RGB ray를
  native K로 옮겨 nearest 조회하며 <=0/비유한값·범위 밖은 결손으로 유지한다.
  빈 픽셀을 prior/DA3/평면으로 채우지 않고 scale fitting도 하지 않는다.
- MVS는 고정 target이고 PGSR svgeo는 현재 GS depth로 만든 normal을 사용한다.
  native MVS normal을 별도 감독으로 더하지 않는다.
- 기존 GeoGS normal(.05, 1−dot)과 PGSR svgeo(.015, 영상 경계 가중 L1)를
  중복 합산하지 않는다. MG의 refinement에서 기존 normal 항을 교체한다.
- mvrgb(.15)는 실제 RGB의 grayscale patch LNCC, mvgeom(.03)은 현재 GS depth의
  왕복 픽셀 재투영 오차다. 기존 RGB reconstruction loss는 유지한다.
- loss 시작은 8001이다. PGSR 원코드의 >7000을 Anchor 안에 소급 적용하면
  같은 Anchor 비교가 깨지므로 기존 8000 상태를 그대로 유지한다.
- GeoGS world-frame 누적 normal을 올바르게 camera-frame으로 변환한다. expected
  surf_depth로 국소 평면을 구성하는 이식이며 PGSR의 unbiased depth renderer 전체
  재현이 아니다. 렌더러·Gaussian 표현·추출은 변경하지 않는다.
- 공식 최대 102,400 대신 4,096개 7×7 패치, microbatch 512를 결과를 보기 전에
  정한 자원 제한으로 사용한다. 유효 표본 수와 mask 감소를 실제 trace로 공개한다.
  항공영상에서 공식 거리 상한 1.5m를 그대로 쓰지 않고 train-only 실제 카메라
  기하와 MVS 지원의 in-frame overlap으로 최대 8개 neighbor를 결박한다.
- 광축 차이 <=30도, baseline/중앙 depth <=1의 동일 이웃 조건에서 P1/P2/P3 각각
  1/2/1장은 이웃이 없다. 해당 step은 RGB+MVS+svgeo만 계산하고 MV skip을 기록한다.
  비교 가능한 이웃을 강제로 만들지 않는다. 각 지역 전체의 실제 MV 활성은 필수다.
- 정상/빈 mask, image border, 가림 후보, 낮은 alpha와 grazing ray를 검산한다.
  별도 sampling RNG를 사용해 기존 camera/densification RNG를 소비하지 않는다.
- 기존 adaptive visual-depth controller는 MVS 잔차를 입력으로 받는다. 실제 계수를
  기록하고, 과거 코드의 `da_*` 필드는 호환 이름임을 명시한다. 계수가 분기마다
  달라지면 입력/loss의 직접 효과와 controller 반응을 분리해서 해석한다.

PGSR 근거: [논문 v2 §IV-B 및 보충자료 2DGS 비교](https://arxiv.org/html/2406.06521v2),
[고정 공식 train.py](https://github.com/zju3dv/PGSR/blob/de24f1a38b350387e8d8fe381b2cd70c1ae946e7/train.py),
[인자](https://github.com/zju3dv/PGSR/blob/de24f1a38b350387e8d8fe381b2cd70c1ae946e7/arguments/__init__.py).

## 입력 확인과 해석 범위

실제 read-only Docker 감사에서 train map 참조 P1 98, P2 57, P3 137개(고유 영상 184개)
모두 존재하고 봉인 SHA와 일치했다. RGB도 전부 일치하며 K/R/t는 native COLMAP과
최대 절대 차이 0이다. native K는 두 축의 실제 크기 비율을 적용한 K와 일치한다.
원 입력 해시와 카메라 계약을 신규 preparation receipt에 다시 결박한다.

MVS full-raster 유효 비율 중앙값은 P1 76.72%, P2 74.43%, P3 78.46%다.
이 값은 건물/변화부 피복이나 정확도가 아니다. 음수와 0 결손을 감독하지 않는다.
역사 MVS의 최종 생성 neighbor 명단은 복구되지 않았고 `.cfg`의 auto20은 실제
최종 membership 증거가 아니다. 기존 depth를 개발 입력으로 재사용한다는 사용자
선택에 따라 진행하며 독립 평가영상 기반 재구성 성능이라고 주장하지 않는다.
지역 사이 train/eval 소속이 겹치는 영상도 있어 세 crop을 독립 held-out으로 합치지 않는다.

## 단계별 실행과 검증

1. CPU Docker: native depth parser/재투영/결손과 독립 합성 평면·warp·gradient 검사.
2. source와 입력·neighbor graph를 별도 출력에 봉인. 원 source/input/Anchor read-only.
3. 실제 Anchor 복원 뒤 짧은 GPU 실행으로 활성 loss·유효 표본·gradient·메모리 확인.
   실행 실패는 원 로그와 issue에 남긴다. 첫 기술 결과를 봉인한다.
4. 기술 gate가 통과한 정확한 source/config만 본 비교 대상으로 삼는다. 새로운
   설정 revision 없이 실패를 피하려고 해상도·학습량·보호·추출을 바꾸지 않는다.
5. raw mesh, 실제 렌더, 같은 좌표·참조점 ID의 단면/지도와 원표로 평가한다.

P1은 과거 지붕 잔존과 현재 바닥 높이·연결, P2는 큰 변화와 골/곡면 세부,
P3는 유효 구조 보존·결손 증가를 함께 본다. MVS 감독잔차 감소만으로 개선이라고
판정하지 않는다. UAS/LoD 참조는 학습·mask·neighbor 선택·threshold 조정에 쓰지 않는다.
기하 loss는 틀린 높이에서도 일관될 수 있으며 native 보호가 큰 수정을 제한할 수 있다.
따라서 이번 결과가 실패해도 단순히 MVS 부정확 또는 joint optimization 불가능으로
귀속하지 않는다. 과학적 판정은 별도다.

## 백그라운드 실행과 완료 보고

사용자의 후속 지시 “백그라운드로 돌게하고 결과가 끝나면 보고하자”에 따라
사전검증→신규 12개 학습→추출·평가·보고서 생성을 백그라운드 큐로 연결한다.
변화 없는 주기적 진행 알림은 보내지 않는다. 최종 보고서 생성 또는 실행 실패에만
현지 GNOME 데스크톱 알림을 보낸다. 이 세션에는 Codex 자동 task 재호출 도구가 없어
자동 채팅 답변 생성으로 표시하지 않는다. 보고서·로그·큐 상태는 외부 task 경로에 저장한다.
