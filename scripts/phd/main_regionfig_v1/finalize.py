"""Write the requested short report, source-backed tables, review evidence and issue log."""
from common import *

def main():
    data=load(PAY/'prepared.json');c=load(CFG/'regionfig_v1.json');v=load(PAY/'verification.json');render=load(PAY/'render_receipt.json')
    lock=load(CFG/'regionfig_v1.lock.json');rows=data['examples'];ts=now()
    review1=(DOC/'검토_1차.md').read_text();review2=(DOC/'검토_2차.md').read_text()
    checks=['| 예 | 값 | 발주문 | 이번 계산 | 차이 | 점검 |','|---|---|---:|---:|---:|---|']
    names={'roof_patches':'띠 지붕꼴 패치 수','correction_patches':'보정 패치 수','prior_minus_gt_cm':'사전 정보 − 참값 (cm)','mvs_minus_gt_cm':'MVS − 참값 (cm)'}
    for r in rows:
        for k,a in r['comparison'].items():
            fmt=lambda x:str(int(x)) if 'patches' in k else f'{x:+.6f}'
            checks.append(f"| {r['id']} | {names[k]} | {fmt(a['expected'])} | {fmt(a['actual'])} | {fmt(a['delta'])} | {'PASS' if a['pass_check'] else 'PARTIAL'} |")
    table=['# 영역 예시 숫자','', '값은 입력 패치 배열에서 계산했다. 반올림 전 값, 선택 패치 번호, 단면 칸별 중앙값과 출처 SHA-256은 `영역예시_보정_숫자.json`에 있다.','',
           '| 예 | 띠 패치 | 보정 패치 | 사전 정보 − 참값 (cm) | MVS − 참값 (cm) | 영상 | 촬영 시각 (UTC) | 촬영 각 (°) | 자른 상자 (px) | 가려진 비율 |',
           '|---|---:|---:|---:|---:|---|---|---:|---|---:|']
    for r in rows:
        p=r['photo'];a=r['values'];table.append(f"| {r['id']} | {a['roof_patches']} | {a['correction_patches']} | {a['prior_minus_gt_cm']:+.9f} | {a['mvs_minus_gt_cm']:+.9f} | {p['stem']} | {p['utc_at_exposure']} | {p['tilt_deg']:.9f} | {p['crop_box_px']} | {100*p['occluded_fraction']:.9f}% |")
    table+=['','## 발주 값과 비교','']+checks+['','## 출처','']
    for r in rows:table.append(f"- {r['id']}: `{r['source']['path']}`; SHA-256 `{r['source']['sha256']}`.")
    table+=['- 좌표: EPSG:25832에서 [690953, 5336071, 604] m를 뺀 모델 좌표. 단면은 지붕꼴·평가 범위 패치, 너비 ±0.6 m.','- 높이 차이는 법선 거리 자체가 아니라 연직 높이 차이다. `mvs_a_status == 0`만 MVS에 사용했다.','- 사진 원본은 학습 장면의 같은 촬영본이다. 원본 FULL_OPENCV 모델의 표정과 학습 장면 표정의 최대 차이는 두 예 모두 0이다.','- 새 과학적 판정 없음. scientific_verdict: null.']
    (DOC/'tables/영역예시_보정_숫자.md').write_text('\n'.join(table)+'\n')
    (DOC/'tables/맞춰보기.md').write_text('\n'.join(checks)+'\n')
    (DOC/'tables/맞춰보기.json').write_text(json.dumps({r['id']:r['comparison'] for r in rows},ensure_ascii=False,indent=2)+'\n')
    photo_lines=[]
    for r in rows:
        p=r['photo'];photo_lines.append(f"- **{r['id']}** `{p['stem']}`. XMP 촬영 시각 `{p['utc_at_exposure']} UTC`, 광축–연직 {p['tilt_deg']:.3f}°, XMP 짐벌 {p['xmp_gimbal_pitch_deg']:.0f}°. 상자 {p['crop_box_px']}, {p['crop_size_px'][0]}×{p['crop_size_px'][1]}화소. 가려짐 {100*p['occluded_fraction']:.3f}% ({p['occluded_length_m']:.3f} m), 확인 불가 0%. 시야·4 m 범위를 통과한 {p['candidate_count_full_line']}개 중 연직 {p['nadir_candidate_count']}개에 순위를 적용했다.")
    start=dt.datetime.fromtimestamp((PAY/'baseline_git_status.z').stat().st_mtime,dt.timezone(dt.timedelta(hours=9)))
    seconds=(dt.datetime.fromisoformat(ts)-start).total_seconds()
    report=f'''2행×3열의 보정 그림을 만들었다. `figures/영역예시_보정.png` 또는 같은 이름의 PDF를 연다.
원본·표시 사진은 `figures/crops/`, 숫자와 출처는 `tables/`에 있다. 전달 ZIP은 외부 작업 폴더에 둔다.
그림·CPU 검증·두 번째 독립 점검은 PASS. 발주 숫자 대조는 B173 두 값이 달라 PARTIAL이며, scientific_verdict: null이다.

## 1. 그림과 숫자

![보정 예시](figures/영역예시_보정.png)

- 가: 띠 209패치, 보정 134패치. 항공 LiDAR − 참값 **+455.634143 cm**, MVS − 참값 **+0.799515 cm**.
- 나: 띠 231패치, 보정 63패치. LoD2 − 참값 **−101.606734 cm**, MVS − 참값 **−1.949133 cm**.

그림은 입력 셋만 표시한다. 전체 구간의 모든 MVS 점이 참값과 일치한다는 뜻은 아니다. 전환부의 국소 차이를 그대로 남겼다.

## 2. 맞춰 보기

{chr(10).join(checks)}

**B173 높이 차이의 원인 확인:** 보정 134패치의 `median(-gt_p)`는 +484.110141 cm로 발주 값과 일치한다. 그러나 발주 2.5절이 정한 연직 높이 차이 `median(-gt_p × normal_z)`는 +455.634143 cm다. 법선 연직 성분은 0.849~0.986이다. 지시된 높이 차이를 그림에 쓰고 두 값을 보존했다.

**B173 패치 수:** 지정 좌표로 구한 길이는 {rows[0]['length_m']:.12f} m다. 패치 71107의 진행 거리는 11.948907496432 m로 끝을 약 0.216 mm 벗어나 제외된다. 진단용으로 끝만 12 m까지 늘리면 210개다. 초안의 반올림 전 좌표·코드가 없으므로 원인을 확정하지 않는다. 최종 계산에는 지정 좌표를 그대로 썼다.

**초안 모양:** LiDAR가 높게 이어지다 약 9 m에서 내려오는 형태와 LoD2 단 경계가 MVS·참값보다 앞서는 형태는 같다. B173의 낮아지는 구간 요철은 완전히 같지 않다. 이번 그림은 [0, 0.25), [0.25, 0.5) … 칸의 중앙에 중앙값을 놓고, 마지막 칸은 정확한 끝에서 자른다. 초안 생성 코드·칸별 배열은 제공되지 않아 요철 차이의 정확한 원인은 확인 불가다. 세로축은 요청대로 각 단면 참값 최저 칸을 0 m로 옮겼다.

## 3. 처음 보는 사람 점검

두 하위 에이전트는 각각 제목·줄 제목을 숨긴 그림 파일 하나만 열었다. 코드·표·앞 점검 답을 주지 않았다. 다음은 답 전문이다.

### 첫 점검

{review1}
### 고친 것

첫 점검의 B173 시작점 연결이 불명확해 사진을 지도처럼 북쪽이 위가 되도록 회전하고 북쪽 표시를 더했다. 사진 선택·자른 상자·단면·수치·색은 그대로다. 원본 사진 조각의 화소는 바꾸지 않았다. 그림 회전 때 생긴 빈 모서리는 투명 처리해 흰 바탕을 유지했다.

### 두 번째 점검

{review2}
두 예 모두 “시작점이 같은 곳으로 읽힘”으로 확인됐다. 사진만으로 정확한 지붕 부재나 단차 경계를 확정하기 어렵다는 답도 유지한다.

## 4. 고른 사진과 근거

{chr(10).join(photo_lines)}

학습 영상은 `S0/fork_inputs/s61/<경우>/scene_<사전 정보>/images`, 카메라는 같은 장면의 `sparse/0/`에서 확인했다. 원본은 `phase-payloads/p0-audit/data/raw/uav/Images.zip`, 원본 카메라는 `data/work/mvs/triangulated/`다. 학습용은 1024×741이어서, 같은 촬영본의 5280×3956 원본을 자르고 해당 렌즈 모델로 투영했다. 고른 사진마다 학습·원본 표정의 차이는 0이며, 원본 조각은 원본 화소와 일치한다.

단면 전체가 학습 영상·원본 안에 있고 둘레 4 m 상자를 담을 수 있는 후보를 썼다. 연직 후보에서 가려진 길이가 가장 짧은 순, 투영된 선이 긴 순으로 골랐다. 두 예 모두 가려짐이 20% 아래라 경사 영상으로 넓히지 않았다. 모든 후보와 순위는 `candidates_a.json`, `candidates_b.json`에 있다.

## 5. 바꾼 것, 한계, 시간

- 최초 설정 잠금: {lock['locked_at']}. SHA-256 `{lock['config_sha256']}`. 첫 그림보다 앞선다. 원래 설정은 그대로 두고 `amendment_01/02.json`과 각각의 잠금 기록을 추가했다. 이전 그림·선택 기록은 외부 작업 폴더 `revision_01/02/`에 보존했다.
- 첫 시야 점검에서 렌즈 다항식을 보정된 시야 밖까지 적용한 후보가 발견돼 실제 학습 영상 안에 드는지도 확인하도록 고쳤다. 첫 그림에서는 B173 주변 4 m가 잘려, 발주 2.3절을 만족하는 후보만 받도록 보완했다. 가려진 선 조각의 점선이 끊겨 보이도록 연속 구간을 합쳤다. 독립 점검 후에는 표시 방향만 바꿨다.
- 가려짐은 단면 둘레 10 m의 참값을 원본 영상에 투영한 깊이 비교다. 4화소 격자, 주변 3×3 최소 깊이, 0.25 m 여유, 진행 거리 약 0.05 m 간격을 잠갔다. 점군 간격·단 경계 보간의 영향을 받는 근사이며, 범위 밖 가림 물체는 검사하지 못한다. 점선은 이 계산 결과다.
- 지도 점선 네모는 사진 상자를 단면 참값 중앙 높이의 평면으로 역투영한 범위다. 실제 여러 높이에서의 경계는 조금 다를 수 있다.
- 배열은 `U/patch_values/`의 고리 1.5 m, MVS 판 가다. 참값 가림 점군은 `S1/v3/box_gt/<경우>/gt_points.npz`다. 좌표는 EPSG:25832 − [690953, 5336071, 604] m, 북쪽은 +y다. 원본 전체 영상·점군은 전달 ZIP에 넣지 않는다.
- 검증 {len(v['checks'])}개 PASS: 설정·입력 SHA-256, 독립 띠 계산·중앙값, 같은 시작·끝 좌표, 투영 왕복, 원본 화소, 4 m 범위, 해상도, 300 dpi, CPU 제한. PNG는 5940×3540, PDF도 제공한다.
- 학습·GPU 사용 없음. Docker의 GPU 장치 없음, `CUDA_VISIBLE_DEVICES=''`, nice 19, 메모리 한도 7.5 GB를 확인했다. 가장 큰 그림 프로세스의 기록된 메모리는 약 0.74 GB다. 큰 참값 배열은 10만 점씩 읽어 필요한 범위만 남겼다.
- 다른 영역은 `examples`의 영역 이름·줄 제목·경우·좌표·띠 폭·칠할 칸·색을 추가해 같은 스크립트를 사용한다. 이번에는 두 예만 그렸다. 새 작업에서는 새 설정을 잠그며, 이번 잠금 파일을 덮어쓰지 않는다.
- 기록 범위: {start.isoformat()}~{ts}, 약 {seconds/60:.1f}분. 탐색·작성·두 번의 독립 점검을 포함한다. 실행별 로그는 ZIP의 `logs/`에 있다.
- 쓰기는 지정한 설정·스크립트·문서·외부 작업 폴더로 제한했다. 기존 결과·방법 코드·다른 작업의 변경 사항은 고치지 않았다. 커밋·푸시의 최종 결과와 커밋 번호는 외부 `delivery_receipt.json`과 ZIP에 기록한다.
'''
    assert len(report)<10000,len(report)
    (DOC/'영역예시그림_보고_v1.md').write_text(report)
    issues='''# PHD-MAIN-REGIONFIG-v1 확인 사항

| 항목 | 상태 | 확인 및 조치 |
|---|---|---|
| B173 발주 210패치 vs 209패치 | PARTIAL | 지정 좌표 유지. 끝을 0.216 mm 벗어난 패치 71107을 제외. 12 m 확장은 진단에만 사용. |
| B173 +484.1 cm vs +455.6 cm | 원인 확인 | 법선 거리와 연직 높이 차이의 차이. 지시된 연직 계산 유지, 둘 다 보고. |
| 원본 렌즈 모델 시야 밖 후보 | 해결 | 단면 전체가 학습 PINHOLE 영상 안에도 들어야 함. 첫 준비 결과를 보존. |
| 사진의 4 m 주변 범위 잘림 | 해결 | 전체 범위를 담는 후보만 사용. 원 설정 유지 및 amendment_01 기록. |
| B173 시작점 연결 불명확 | 해결 | 사진 북쪽을 위로 회전. amendment_02 기록. 두 번째 독립 점검 통과. |
| 가려짐·지도 사진 범위 | 한계 명시 | 국소 점군 깊이와 단일 높이 평면의 근사. |
| 초안 요철의 세부 차이 | 확인 불가 | 초안 생성 코드·칸별 배열 없음. 큰 형태만 육안 확인. |
| 탐색 경로 두 곳 없음 | 해결 | main_uncert_v1/common.py 대신 uc_common.py, 장면 최상위 sparse 대신 scene_*/sparse/0 확인. |

scientific_verdict: null
'''
    (DOC/'issues.md').write_text(issues)
    dump(DOC/'tables/독립검토.json',dict(first=dict(agent='/root/blind_figure_review',result='B173 connection unclear; R1 clear',answer_file='검토_1차.md'),
         second=dict(agent='/root/blind_figure_review_second',result='both starts read as same place',answer_file='검토_2차.md'),
         only_input='figures/검토용_제목숨김.png',reviewed_image_sha256=sha(DOC/'figures/검토용_제목숨김.png'),scientific_verdict=None))
    print('REPORT characters',len(report),'at',ts)

if __name__=='__main__':main()
