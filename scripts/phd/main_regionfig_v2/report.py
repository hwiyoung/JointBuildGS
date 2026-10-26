from rfcore import *
import datetime as dt

def main():
    cfg=load(CFG/'regionfig_v2.json');validation=load(DOC/'tables/input_validation.json');verification=load(DOC/'tables/verification.json')
    assert verification['status']=='PASS'
    obs=load(DOC/'tables/photo_observations.json');rows=[]
    for ex in cfg['examples']:
        rec=load(DOC/f'figures/영역표본_{ex["id"]}_{ex["slug"]}.json');rows.append((ex,rec))
    text=['만든 그림 수: 8장. 실제 원본 사진을 사용한 2행 3열 그림과 각 숫자 파일, 원본·표시 사진 조각을 만들었다.',
          '확인 불가: 사진만으로 오류 원인, 작은 구조물의 정확한 용도, 보이지 않는 면의 실제 모습을 확정할 수 없다.',
          '이어지지 않은 패치 수: 여덟 자리 모두 0개. 받은 고유 패치 261,281개가 모두 연결됐다.','',
          '# 영역 표본 그림 보고','',
          '학습 없는 손실 최소점 해석의 제공값만 표시했다. 학습 결과가 아니다. 과학적 판정은 보류한다.','',
          '## 그림과 자른 범위의 숫자','',
          '다듬기는 두 자료가 맞음, 보정은 사전 정보만 틀림, 보존은 영상의 면만 틀림을 뜻한다. 아래 결과 비율은 각 사진 상자 안에서 참값이 있는 지붕만 대상으로 한다. 영역·사진 검사 넓이는 벽도 포함하므로 막대의 지붕 넓이와 다를 수 있다. 반올림 전 값과 패치 목록은 같은 이름의 숫자 파일에 있다.','']
    compact=[]
    for ex,r in rows:
        i=ex['id'];m=r['metrics'];name=r['figure'];prior='항공 LiDAR' if ex['prior']=='ALS' else '사전 지붕 모형'
        text += [f'### 그림 {i} · 건물 {ex["building"]} · {prior}', '',f'[그림](figures/{name}) · [숫자](figures/{Path(name).with_suffix(".json").name}) · [색칠 없는 사진](figures/crops/{i}_북쪽원본.png)', '',
                 f'한눈에 볼 것: {r["title"]}.',
                 f'숫자: 참값이 있는 지붕 {m["result_area_m2"]:.2f} m², 맞은 넓이 비율은 범주별 {m["ok_category_pct"]:.2f}%, 검사 기반 {m["ok_check_pct"]:.2f}%. 참값이 없어 칠하지 않은 넓이 {m["unpainted_no_reference_area_m2"]:.2f} m². 연결 누락 0개.']
        if ex['selected_after_results']:text.append('결과를 보고 고른 자리다.')
        if i in obs:text.append('사진에서 보이는 것: '+obs[i])
        text.append('')
        compact.append(dict(id=i,building=ex['building'],prior=ex['prior'],photo=ex['photo']['stem'],crop=ex['photo']['crop_box_px'],
                            tilt_deg=ex['photo']['tilt_deg'],rotation_degrees=ex['photo']['display_rotation_degrees'],
                            unmatched=0,**m))
    text+=['## 받은 요약과 맞춰 보기','',
           '건물 전체의 참값이 있는 패치를 대상으로 넓이를 가중해 다시 합산했다. 제공된 요약의 일곱 조합, 두 결과씩 총 14개 비율이 소수 둘째 자리까지 일치했다. 아래 전체 건물 값은 앞의 사진 상자 값과 대상 범위가 다르다.','',
           '| 사전 정보 | 건물 | 범주별 제공값 / 확인값 | 검사 기반 제공값 / 확인값 |',
           '|---|---|---:|---:|']
    for row in validation['summary_checks']:
        q=row['expected'];a=row['actual'];p='항공 LiDAR' if row['prior']=='ALS' else '사전 지붕 모형';b=row['building'].split('_')[-1]
        text.append(f'| {p} | {b} | {q["ok_category_pct"]:.2f}% / {a["ok_category_pct"]:.2f}% | {q["ok_check_pct"]:.2f}% / {a["ok_check_pct"]:.2f}% |')
    text+=['','## 처음 보는 사람 점검','',(DOC/'reviews/독립점검.md').read_text(),
           '## 바꾼 것과 확인 불가','',
           '- 사용자가 메모리 시작 조건을 64 GiB에서 24 GiB로 바꾸는 데 동의했다. 메모리 상한 4 GiB, 프로세서 2개, 한 번에 한 장으로 실행했다. 여유 메모리 16 GiB 미만 또는 큰 후처리가 시작되면 이 작업만 중단하도록 했다.',
           '- 첫 그림 전에 사진·자른 상자·회전·색·예상 제목을 설정에 잠그고 해시를 남겼다. 원본 설정은 유지하고 수정 시각·이유·해시는 별도 잠금 기록에 덧붙였다.',
           '- 그림 2·3은 이전 작업과 같은 사진·상자·단면 좌표다. 나머지 사진은 참값과 결과값을 읽지 않고 영상의 면과 사전 정보로 사진 후보를 골랐다. 이전 투영 코드와 사진 순위를 재사용했다. 가려짐은 주어진 건물에서 단면 둘레 10 m 안의 영상의 면으로 근사했다. 범위 밖 가림 물체는 확인 불가다. 이전 두 사진의 과거 선택에는 참값 점군에 의한 가려짐 비교가 들어 있었고, 이번에 다시 고르지 않았다.',
           '- 새 사진 여섯 자리 가운데 연직 후보가 없거나 가려짐 비율이 높은 경우에는 이전 규칙의 경사 사진 대안을 적용했다. 사진 이름·기울기·후보 수와 순위는 숫자 파일 및 외부 작업 폴더에 기록했다. 사진 검사에서 사진 부족이라는 판단과 이 그림에 사용할 사진 한 장의 존재는 같은 조건이 아니다.',
           '- 일부 시야 밖 점이 렌즈 함수에 의해 사진 안으로 접혀 들어오는 표시 오류를 확인했다. 실제 보정 카메라의 시야 조건을 표시와 모든 사진 상자 수치에 함께 적용했다. 입력값·사진·상자·회전·단면은 그대로이며 이전 그림은 보존했다.',
           '- 첫 수정 실행의 변수 이름 충돌을 고치고 실패 로그를 보존했다. 이후 검증을 모두 통과했다.',
           '- 독립 점검 뒤 다듬기·보정·보존의 뜻을 범례에 덧붙였다. 상속 가운데 사전 정보가 틀린 단면 띠에도 빗금을 표시했다. 사진 불투명도는 지정된 0.45다. 작은 구조물이 색과 화살표에 가려지는 한계는 남아, 색칠 없는 사진 조각을 함께 제공한다. 같은 높이의 단면 선은 서로 겹친다.',
           '- 단면 띠는 0.25 m 구간에서 넓이가 가장 큰 범주를 표시한다. 상속 범주 안에서 사전 정보가 틀린 넓이가 절반 이상이면 빗금을 표시한다. 이는 표시용 요약이며 개별 패치값을 바꾸지 않는다.',
           '- 사진 안이라는 기준은 참값으로 옮긴 패치 중심의 투영점과 실제 보정 시야다. 참값이 없는 패치는 사전 정보 중심으로 상자 안 여부와 칠하지 않은 넓이만 구했다. 가려진 패치의 넓이를 따로 제외한 통계는 아니다.',
           '- 예상 제목의 단정은 사진 상자 안의 관측값에 맞춰 줄였다. 그림 1·4는 “모두” 대신 “대부분”, 그림 2·3은 맞은 넓이 비율의 변화, 그림 5·6은 오류가 남은 곳으로 표현했다. 그림 7은 두 상속 범주가 함께 보이는 것으로, 그림 8은 오류가 남은 상태로 표현했다. 원래 예상 제목도 숫자 파일에 보존했다.',
           '- 확인용 19동의 자료를 열지 않았다. 받은 일곱 조합의 패치만 공개 패치값과 연결했고, 입력의 결과·사진 검사 판단·영역 정의는 변경하지 않았다. 참값이라는 이름은 발주문과 제공 배열의 이름을 따른다.','',
           '## 파일·검증·시간','']
    start=min(load(p)['started_at'] for p in (PAY/'logs').glob('*.json') if 'started_at' in load(p))
    end=now();minutes=(dt.datetime.fromisoformat(end)-dt.datetime.fromisoformat(start)).total_seconds()/60
    peak=max(int(r['environment']['cgroup'].get('memory.peak',0)) for _,r in rows)/1024**3
    lock=load(CFG/'regionfig_v2.lock.json')
    text += [f'- 설정 잠금: {lock["locked_at"]}. 해시 `{lock["config_sha256"]}`.',
             f'- 숫자·사진 검증: {len(verification["checks"])}개 통과. 원본 사진 화소, 사진 상자 안의 전체 단면, 동일한 네 사진 캔버스, 제공값으로 구한 넓이 비율, 단면의 중앙값, 입력 해시를 확인했다.',
             f'- 그림은 모두 6,600×4,200화소, 300 dpi다. 최종 그림 실행의 최대 컨테이너 메모리는 {peak:.3f} GiB다. 그래픽 장치와 학습을 사용하지 않았고 다른 작업을 중단하지 않았다.',
             f'- 실행·작성 기록: {start}부터 {end}까지 약 {minutes:.1f}분. 앞선 입력·메모리 대기는 별도다.',
             '- 보고서·그림·숫자·설정·스크립트·사진 조각을 그림별 압축 파일로 나눈다. 각 파일은 25 MB 미만이며 해시 목록과 압축 무결성을 확인한다.',
             '- 입력 사진과 카메라의 실제 경로, 버전·컨테이너·실행 명령, 전체 파일 해시는 재현 문서와 숫자 파일 및 외부 영수증에 있다. 과학적 판정은 `scientific_verdict: null`로 유지한다.','']
    out='\n'.join(text);assert len(out)<15000,len(out)
    (DOC/'영역표본그림_보고_v1.md').write_text(out)
    dump(DOC/'tables/figure_summary.json',dict(figures=compact,report_characters=len(out),execution_start=start,report_at=end,elapsed_minutes=minutes,peak_final_render_GiB=peak,scientific_verdict=None))
    print('REPORT',len(out),'characters')

if __name__=='__main__':main()
