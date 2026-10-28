"""Promote the delivered A1 viewer to A2; preserve the exact delivered snapshot."""
import html
import json
import shutil
from common import *

def main():
    assert (OUT/'packages/A1_delivered.json').exists()
    web=DOC/'보기';history=OUT/'history/viewer_A1';history.mkdir(parents=True,exist_ok=False)
    for name in ['index.html','data.json','data.js']:shutil.copyfile(web/name,history/name)
    state=json.loads((web/'data.json').read_text());page=(web/'index.html').read_text();newcases=[]
    for site in SITES:newcases+=json.loads((web/f'A2_{site}.json').read_text())['cases']
    for c in state['cases']:
        row=next(r for r in newcases if r['case']==c['id']);page=page.replace(c['plate'],row['plate']);c['plate']=row['plate'];c['diagnostics']=row['values']
    gates=json.loads((DOC/'tables/gate.json').read_text());expect=json.loads((DOC/'tables/expectations.json').read_text())['rows']
    state.update(stage='가-2',stage_status='STAGE_A_DELIVERED_WITH_EXPLICIT_UNAVAILABLE_FIELDS',at=now(),gate=gates,expectations=expect)
    state['unit_diagnostics']={s:{k:json.loads((DOC/'tables'/f'{k}_{s}.json').read_text()) for k in ['forces','gradients','photo']} for s in SITES}
    state['four_depths']={s:json.loads((DOC/'tables'/f'four_depths_{s}_ALS.json').read_text()) for s in SITES}
    state['multiview']={s:json.loads((DOC/'tables'/f'multiview_summary_{s}_ALS.json').read_text()) for s in SITES}
    state['tsdf_update']=json.loads((DOC/'provenance/tsdf_update_behavior.json').read_text())
    page=page.replace('· 가-1</p>','· 단계 가 완료</p>').replace('<td>이 묶음</td>','<td>묶음 ① 전달</td>').replace('<td>진행 중</td>','<td>묶음 ②</td>')
    page=page.replace('가-2 진단 표는 묶음 ②에 담는다.','가-2 진단 표와 완성 사례 판은 이 묶음 ②에 포함했다.')
    start=page.index('<h2>기대·기준과 나란히</h2>');end=page.index('<p><a href="data.json">',start)
    lines=['<h2 id="diagnostics">단위별 힘·기울기·다섯 구분</h2>']
    esc=html.escape
    for site in SITES:
        lines.append(f'<section id="diagnostic-{site}"><h3>{site}</h3>')
        for key,label in [('classes_A2','다섯 구분'),('forces_A2','r/σ와 깊이 항의 힘'),('gradients_A2_v2','중심 기울기')]:
            lines.append(f'<figure><img loading="lazy" src="img/{site}_{key}.jpg" alt="{site} {label}"><figcaption>{label} · 반올림 전 수치와 표본 수는 data.json과 전달 표에 있다.</figcaption></figure>')
        lines.append('</section>')
    lines+=['<h2 id="four-depths">같은 화소 광선의 네 깊이</h2>',
        '<p>메시에 넣은 깊이는 ① 학습 surf_depth이며, 이 실행에서는 ④ 불투명도 가중 평균과 정확히 같다. ②는 원래 메시 전체의 첫 교차, ③은 렌더러 누적 불투명도 0.5다. 미교차·0.5 미도달은 확인 불가로 남긴다. 사례 판에는 판정 끔과 판 4의 같은 색 범위 깊이 줄, 판 4의 네 깊이 줄, ①−② 분포가 있다.</p>',
        '<h2 id="expectations">진단 전 기대와 측정값</h2><p>기대의 성립 여부와 과학 판정은 적지 않았다. 고친 판은 이번 발주에서 실행하지 않았다.</p><div class="scroll"><table><tr><th>기대</th><th>단위·결과·사례</th><th>기준</th><th>값</th><th>N</th></tr>']
    for r in expect:
        link=r['figure'].removeprefix('보기/');value='확인 불가' if r['value'] is None else f'{r["value"]:.5g}'
        lines.append('<tr><td>'+esc(r['expectation'])+'</td><td>'+esc(r['site']+' · '+r['result']+' · '+r['case'])+'</td><td>'+esc(r['prewritten_rule'])+f'</td><td><a href="{esc(link)}">{value}</a></td><td>{r["n"]}</td></tr>')
    lines+=['</table></div><h2 id="multiview">사진마다 보는 추가 확인</h2>',
        '<p>사진 수는 각 결과 자신의 뜬 면 패치 첫 만남 점을 투영한 대표 화소에서 센다. 힘 비율은 기존 관문의 전체 패치 화소 중 실제 렌더가 참값+τ 위인 화소에서 센다. 두 분모는 다르다. 기존 관문 정의·값은 그대로다. 사진 수는 가림으로 사진을 제외하지 않으며 동일 물리적 표면의 사진 관찰을 증명하지 않는다.</p>']
    for c in state['cases']:
        for key,label in [('map','뜬 면을 본 사진 수 지도'),('examples','뜬 면과 지붕을 본 사진의 색·깊이')]:
            lines.append(f'<figure><img loading="lazy" src="img/{c["id"]}_multiview_{key}_A2.jpg" alt="{c["id"]} {label}"><figcaption>{label}</figcaption></figure>')
    lines+=['<p>TSDF 확인: Open3D 0.19.0은 현재 사진의 깊이 점 주변에서 지정한 블록만 갱신한다. 이전에 열렸어도 현재 지정되지 않은 블록은 그대로다. 같은 런타임의 2 m→4 m 시험에서 앞쪽 TSDF 표본 6,588개가 정확히 같았고, 2 m→2.1 m 겹침 시험에서는 바뀌었다. 사례별 원인 판정은 하지 않았다.</p>',
        '<h2 id="formation">생기는 과정</h2>',
        '<p>저장본 15,000·30,000회와 조건부 재실행 500회 간격을 구분한다. 기존 손실의 첫 실행은 3,100회 불투명도 건강 기준으로 중단됐다. 사용자가 승인한 한 번의 재시도만 그 기준을 기록 전용으로 두었다. NaN·실행 오류와 다른 원래 검사는 유지했다. 선은 저장된 시점을 연결한 것이며, 그 사이 발생 시각은 확인할 수 없다. 주 시점 렌더 화소 비율은 메시의 넓이 점수가 아니다.</p>']
    for case in ['R1-뜬면-1','R1-뜬면-2']:
        for suffix in ['formation_A2','formation_depth_A2','formation_population_A2']:
            lines.append(f'<figure><img loading="lazy" src="img/{case}_{suffix}.jpg" alt="{case} 생기는 과정"></figure>')
    lines.append('<p>scientific_verdict: null. R1 보존 띠의 기준 통과 실사와 기존 모델의 생성 반복은 확인 불가다.</p>')
    page=page[:start]+'\n'.join(lines)+page[end:]
    for r in gates['rows']:
        if r['gate3_below_10pct']:
            page=page.replace('<h2 id="gate">관문</h2>',f'<h2 id="gate">관문</h2><p><strong>{r["site"]}: 판 4 지붕 깊이÷사진 기울기 {100*r["gate3_roof_depth_over_photo"]:.2f}% · 10% 아래</strong></p>')
    (web/'data.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (web/'data.js').write_text('window.FLOATDIAG_DATA='+json.dumps(state,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n')
    (web/'index.html').write_text(page)
    total=sum(p.stat().st_size for p in web.rglob('*') if p.is_file());assert total<150000000,total
    save(DOC/'provenance/viewer_A2_files.json',dict(at=now(),bytes=total,source_A1=str(history),scientific_verdict=None))
    print('A2 offline viewer built',total,flush=True)

if __name__=='__main__':main()
