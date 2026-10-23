"""Append completed Stage-A tables while retaining the pre-MVS partial report."""
import datetime as dt
import json
from analysis_common import O,DOC
from preflight import sha,dump

def main():
    target=DOC/'중간보고_v1.md';marker='\n## 단계 가 완료 보완 기록\n'
    original=target.read_text().split(marker)[0].rstrip()+'\n'
    tables=DOC/'tables'
    cells=json.loads((tables/'맞는쪽칸_넓이.json').read_text())['rows']
    excluded=json.loads((tables/'건물에_붙지않은_패치.json').read_text())['rows']
    lines=[marker.strip(),'','- 보완 시각: '+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        '- scientific_verdict: null','',
        '위 중간 보고는 MVS 시작 전에 남긴 당시의 PARTIAL 기록이다. 새 구역의 사전 정보 정합에 학습 영상 전용 깊이가 필요해, 사전 정보 오차와 시험 자리 계산을 MVS 뒤 CPU에서 완료했다. 최초 범위·나눔과 이 계산 순서 예외를 보존한다. 아래 값과 표는 [이 발주에서 냄]이다.','',
        '| 사전 정보 | 정하는 곳 패치 수 | 표면 넓이 m² | 참값을 정한 패치 수 | 사전 정보가 틀린 덩어리 ≥1 m² | 작은 덩어리 수 | 작은 넓이 m² |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for prior in ['LoD2','ALS']:
        rows=[r for r in cells if r['prior']==prior]
        q=json.loads((tables/f'사전정보_틀린자리_{prior}.json').read_text())
        lines.append(f"| {prior} | {sum(r['patches'] for r in rows):,} | {sum(r['area_m2'] for r in rows):,.2f} | "+
            f"{sum(r['patches'] for r in rows if r['cell']!='no_gt'):,} | {len(q['rows']):,} | {q['small_count']:,} | {q['small_area_m2']:,.2f} |")
    lines+=['','참값을 정하지 못한 경우는 점 없음·면 없음·점 부족·평면 실패를 구분해 `tables/참값_유무사유.json`에 남겼다.','',
        '| 사전 정보 | 건물에 붙지 않은 패치 수 | 넓이 m² |','|---|---:|---:|']
    for r in excluded:lines.append(f"| {r['prior']} | {r['unattached_patches']:,} | {r['unattached_area_m2']:,.2f} |")
    lines+=['','사전 정보 오차 덩어리·gt_p의 사분위수·참값 점 밀도는 `tables/사전정보_틀린자리_*.json`, 크기와 부호별 넓이는 `tables/사전정보_크기부호_*.json`, 건물별 비율 상위 30동은 `tables/사전정보_건물상위30_*.json`에 있다. 전체 정하는 곳의 패치별 값은 외부 작업 폴더의 `patch_values/`에 있다.','',
        '![LoD2 사전 정보 오차](figures/사전정보_틀린곳_지도_LoD2.png)','',
        '![항공 LiDAR 사전 정보 오차](figures/사전정보_틀린곳_지도_ALS.png)','',
        '확인용 결과는 이 보완에도 포함하지 않았다. 전체 단계 나 결과와 기존 값 비교는 `본실험_넓히기0단계_보고_v2.md`에 있다.']
    target.write_text(original+'\n'+'\n'.join(lines)+'\n')
    dump(O/'gates/interim_completed.json',dict(status='PASS',report_sha256=sha(target),
        original_partial_record_retained=True,stage_a_completion_after_mvs=True,scientific_verdict=None))
    print('intermediate report completed with retained partial history')

if __name__=='__main__':main()
