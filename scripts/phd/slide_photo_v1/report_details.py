"""Compact, source-linked handoff notes assembled from the delivered figure records."""
from common import *

def details():
    rows=['### 전달 상태와 사용 제한','',
      '**파일 산출: PNG 10장과 대응 JSON 10개. 설명 목표 충족: PARTIAL.** 그림 다·가·라는 독립 판독에서 핵심 비교가 읽혔다. 그림 마는 글자 없는 위치 사진으로 제공한다. 보존 면을 좁은 지붕으로 읽는 한계와 상속의 가림 관계가 남았다. 그림 나는 고정 B173 단면이 요청한 결합 실패 결론을 뒷받침하지 않는다.','',
      '- 3쪽 첫 지붕의 100%는 깊이 격자 **20화소**에 대한 값이다. 그중 참조점이 있는 화소는 4개이고, 나머지 80%는 칠하지 않았다. 이 값을 넓은 지붕 전체의 결측률로 설명하지 않는다.',
      '- 6쪽 상속: 벽 53과 가림 면 38의 소유 ID가 모두 `DEBY_LOD2_4959326`이다. 옅은 칠은 확인된 **같은 건물 지붕**이다. 발주문의 이웃 건물 가림 조건은 충족하지 못했다. 사진 한 장으로 벽의 현재 존재나 상속의 성공을 확인할 수 없다.',
      '- 12쪽: **R1에서는 결합이 낮은 LoD2 면을 유지하고 본 방법이 참조에 가까운 방향이 확인된다. B173에서는 결합도 참조에 가까워 두 사례를 같은 결론으로 묶지 않는다.**',
      '- 다의 14.6 cm와 34 cm는 선택한 면/덩어리 전체의 중앙값이다. 확대 단면의 특정 한 점 또는 표시된 모든 점의 간격을 뜻하지 않는다.','',
      '### 사진·시점·범위','', '|그림|학습 영상 / 시점|원본 자른 상자 [x0,y0,x1,y1]|','|---|---|---|']
    change=load(DOC/'figures/figS_c_change.json')
    rows.append(f'|다·변화|{change["view"]["training_view"]} / 기울기 {change["view"]["selection"]["tilt_deg"]:.2f}°|점군 XY {change["bounds_xy"]}; 두 줄 동일|')
    for name,label in [('figS_c_repr','다·표현'),('figS_c_specular','다·영상'),('figS_e_aim_keep','마·보존'),('figS_e_aim_correct','마·보정'),('figS_e_aim_refine','마·다듬기'),('figS_e_aim_inherit','마·상속')]:
        d=load(DOC/'figures'/f'{name}.json');p=d['photo'];rows.append(f'|{label}|{p["view"]}|{p["crop_box_px"]}|')
    a=load(DOC/'figures/figS_a_image_limits.json')
    for label,r in zip(['가·지붕','가·벽','가·금속'],a['panels']):rows.append(f'|{label}|{r["photo"]["view"]}|{r["photo"]["crop_box_px"]}|')
    d=load(DOC/'figures/figS_d_gs_real.json');s=d['selection']
    rows += [f'|라|{s["view"]}|공통 깊이 격자 {s["crop_box_grid_px"]}; 다섯 칸 동일|','',
      '상자는 회전 전 원본 좌표다. 금속 면 사진, 그림 라의 다섯 칸, 상속 사진은 표시할 때 90° 회전했다. 그림 마의 마지막 크기 조정 범위도 각 JSON의 `final_fit_box_after_rotation_px`에 있다.','',
      '### 그림 가의 화소 수와 비율 [이 발주에서 냄]','',
      '|자리|화소 수|깊이 없음 %|틀림 %|참조 없음 %|τ cm|','|---|---:|---:|---:|---:|---:|']
    for label,r in zip(['B0 평지붕 면 42','R1 벽 19','선택 금속 벽'],a['panels']):rows.append(f'|{label}|{r["pixels"]}|{r["missing_share"]*100:.3f}|{r["wrong_share"]*100:.3f}|{r["unknown_gt_share"]*100:.3f}|{r["tau_m"]*100:.2f}|')
    rows += ['', '분모는 해당 범위의 전체 깊이 화소다. 깊이 없음은 관측 마스크를 포함해 계산하고, 틀림은 참조 z-buffer가 실제로 채워진 화소에서만 센다. 참조 없는 화소는 결측·오류 모두 칠하지 않는다. 결측과 틀림이 100%가 되도록 정규화하지 않았다. 일 0은 패치 법선 방향 차이, 그림 가는 카메라 깊이 차이를 쓰므로 두 숫자는 서로 다른 정의다.','',
      '### 그림 라의 표시 설정','',
      f'원본에서 B0 평가 패치 {s["projected_eval_patch_fraction"]*100:.2f}%가 들어온 시점을 선택했다. 자른 화면의 B0 점유율은 {s["eval_crop_share"]*100:.2f}%, 관측 검사 통과 깊이 몫은 {s["pass_share"]*100:.2f}%다. 깊이 세 칸의 공통 색 범위는 {d["depth_colour_range_m"][0]:.3f}–{d["depth_colour_range_m"][1]:.3f} m다. 실제 PLY의 위치·회전·축 길이를 읽고 타원의 표시 크기만 0.25배로 줄여 {d["gaussian_display"]["shown"]}개를 표시했다. 저장된 iteration_30000 RGB·깊이를 사용했으며 GPU 렌더와 학습을 실행하지 않았다.','',
      '### 그림 나의 원본 일치·방향 점검','',
      '사진 자르기, 단면 시작·끝·띠 폭, 입력 0.25m 높이와 위치는 REGIONFIG 최종 파일을 그대로 썼다. 각 결과의 메시 경로와 모든 절단 선 좌표는 그림 JSON에 있다. 높이로 선을 삭제하지 않았고, 축 범위는 모든 입력·참조 높이를 포함한다. 축 밖 선 개수도 JSON에 남겼다.','',
      '|단면|방법|τ 안 %|참조 표본 수|','|---|---|---:|---:|']
    b=load(DOC/'figures/figS_b_correction_sections.json')
    for ex in b['examples']:
        for o in ex['outputs']:rows.append(f'|{ex["example"]["site"]}|{o["name"]}|{o["within_tau_share"]*100:.3f}|{o["point_count"]}|')
    ov=b['examples'][1]['viscmp_v1_overlap']
    rows += ['', f'R1 단면은 VISCMP-v4 V1의 점선 패치 범위와 교차한다. 원본 단면 시작에서 {ov["inside_s_range_m"][0]:.3f}–{ov["inside_s_range_m"][1]:.3f} m 사이이며, 1 cm 이하 간격의 표본 검사에서 {ov["sample_fraction"]*100:.2f}%가 그 범위 안에 있다. 단면을 옮기지 않았다.',
      '표의 τ 안 비율은 참조점→메시의 한 방향 거리다. 잘못된 면이 추가로 남은 경우를 그 비율만으로 판단할 수 없다. 각 점의 저장된 DIST71 `r_tau`를 사용했다.','',
      '고정된 0.25m 칸 중심에서 입력과 참조의 높이 차가 0.5m를 넘는 칸을 사후 점검했다. B173의 35칸에서 결합 선의 참조까지 가장 가까운 연직 간격 중앙값은 0.116m이고, 사전 정보까지는 4.643m다. R1의 18칸에서는 결합 선이 사전 정보에 0.016m, 참조에 0.975m이며 본 방법은 참조에 0.093m다. 이는 그림의 방향을 확인하는 보조 계산으로, 동일 표면 대응이나 공식 성능 판정이 아니다. 전체 교점·정의는 [section_direction.json](qa/section_direction.json)에 있다.','',
      '### 재현과 전달','',
      '실행기는 `bash scripts/phd/slide_photo_v1/run_cpu.sh <로그이름> <스크립트> [인자]`다. 원본 저장소와 외부 artifacts는 읽기 전용, 이번 작업 출력 경로만 쓰기 가능으로 실행했다. 입력 계산 순서는 잠금 → task0_scan gt → 전역 가시성·입력 면 준비 → task0_scan mvs/components → 사진·독립 재질 판독 → 최종 선택이다. 그림은 `draw_c_legacy.py`, `draw_c_specular.py`, `draw_a.py`, `draw_d.py`, `draw_e.py`, `draw_b.py`로 그린다. 선택·가림 보충 설정을 함께 적용해야 하며, 이미 존재하는 설정 잠금을 덮어쓰면 안 된다.',
      'ZIP에는 그림·JSON·보고서·설정·이번 스크립트와 SHA-256 구성 목록이 있다. 원본 사진 ZIP, 입력 깊이·점군, 거대 메시와 중간 가시성 캐시는 포함하지 않는다. 원본 경로와 입력 해시는 `input_lineage.json` 및 그림 JSON에 있다. 네이티브 후보 사진은 외부 payload의 `task0/native_crops/`, 재검사에 쓴 예전 무효 후보는 `task0/invalidated_v2/`에 보존한다.',
      '누적 커밋: 일 0 `e9992ef7`, 다 `6df317a4`, 가 `a8e7a0e0`, 라 `35700558`, 마 `6b10e5ce`. 마지막 커밋은 그림 나, 최종 표시 수정과 검증 기록을 함께 담는다.','']
    return rows
