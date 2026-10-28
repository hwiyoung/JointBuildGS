"""Assemble the offline visual handover; fail rather than conceal missing assets."""
import base64
import csv
import html
import json
import shutil
from pathlib import Path
from common import *

def main():
    web=DOC/'보기';data=[]
    for site in SITES:
        data.append(json.loads((web/f'data_{site}.json').read_text()))
    cases=[c for d in data for c in d['cases']];assert len(cases)==7
    results=[dict(id=r,label=n) for r,n in zip(RESULTS,['판정 끔','판 2','판 4'])]
    allrows=json.loads((DOC/f'tables/recount_{PRIOR}.json').read_text())['rows']
    summary=[]
    for site in SITES:
        for r in RESULTS:
            value=next(x for x in allrows if x['site']==site and x['result']==r and x['cell']=='0~3')
            cell0=next(x for x in allrows if x['site']==site and x['result']==r and x['cell']=='0')
            cell2=next(x for x in allrows if x['site']==site and x['result']==r and x['cell']=='2')
            q=json.loads((OUT/'renders'/site/r/'iteration_30000/quality.json').read_text())
            summary.append(dict(site=site,result=r,within_tau_pct=value['within_tau_pct'],floating_pct=value['floating_pct'],
                cell0_within_tau_pct=cell0['within_tau_pct'],cell2_within_tau_pct=cell2['within_tau_pct'],
                no_surface_pct=value['no_surface_pct'],eval_psnr_db=q['eval_psnr_db'],eval_views=len(q['evaluation']),
                area_m2=value['area_m2'],patches=value['patches']))
    gate_counts={site:json.loads((OUT/'diagnostics'/site/f'lt_dynnow_{PRIOR}_s0/receipt.json').read_text())['gate_counts'] for site in ['R1rep_b10','B173nb_b10']}
    r1,b173=(gate_counts[s]['all_own_dead_fraction'] for s in ['R1rep_b10','B173nb_b10'])
    state=dict(task_id=TASK,stage='가-1',stage_status='PARTIAL_A1_VISUALS',at=now(),cases=cases,results=results,
        summary=summary,maps=[dict(site=s,path=d['map']) for s,d in zip(SITES,data)],
        gate=dict(status='PASS' if min(r1,b173)>=.7 else 'FAIL',threshold=.7,R1_fraction=r1,B173_fraction=b173,
            stage_B='이번 발주에서 실행하지 않음: 사용자 확정',scientific_verdict=None),scientific_verdict=None)
    save(web/'data.json',state)
    (web/'data.js').write_text('window.FLOATDIAG_DATA='+json.dumps(state,ensure_ascii=False,separators=(',',':'))+';\n')
    assets={}
    for c in cases:
        for res in RESULTS:
            for flavour in ['colour','float']:
                name=c['id']+'__'+res+'__'+flavour+'.glb';p=web/'3d'/name
                assert p.exists() and p.stat().st_size<4000000
                assets[name]=base64.b64encode(p.read_bytes()).decode()
    (web/'models.js').write_text('window.FLOATDIAG_GLB='+json.dumps(assets,separators=(',',':'))+';\n')
    shutil.copyfile(Path(__file__).with_name('viewer.js'),web/'viewer.js')
    esc=html.escape
    lines=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>뜬 면 진단 · 실제 3차원 결과</title><style>',
        'body{margin:0;background:#f7f7f4;color:#23282c;font:16px/1.65 system-ui,sans-serif}main{max-width:1400px;margin:auto;padding:32px}h1{font-size:34px;line-height:1.25}h2{margin-top:56px;border-top:1px solid #ccc;padding-top:22px}h3{font-size:23px}a{color:#155b8c}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:10px;border-bottom:1px solid #d8d8d4;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#ecece8}img,video,canvas{max-width:100%;height:auto}canvas{display:block;width:100%;background:#fafafa;touch-action:none;border:1px solid #ddd}.viewer-controls{display:flex;gap:12px;flex-wrap:wrap}select,button{font:inherit;padding:8px 12px;border:1px solid #aaa;border-radius:4px;background:white}figure{margin:24px 0}figcaption,.viewer-status{font-size:14px;color:#4a5054}.note{background:#efeee7;padding:16px}.scroll{overflow:auto}.case-links{display:flex;gap:16px;flex-wrap:wrap}nav a{margin-right:20px}.number{white-space:nowrap}@media(max-width:700px){main{padding:16px}h1{font-size:27px}th,td{padding:6px;font-size:13px}}</style>',
        '<main><p>PHD-MAIN-FLOATDIAG-v1 · 가-1</p><h1>지붕 위에 뜬 면을 실제 결과에서 본다</h1>',
        '<p>같은 사례, 같은 카메라로 판정 끔·판 2·판 4를 비교한다. 아래 숫자는 저장된 채점 패치에서 다시 계산했다.</p>',
        '<nav><a href="#stage">지금 어디</a><a href="#summary">요약 표</a><a href="#cases">3차원과 사례</a><a href="#maps">지도</a><a href="#gate">관문</a></nav>',
        '<h2 id="stage">지금 어디</h2><table><tr><th>큰 단계</th><th>발주 시점 상태</th></tr><tr><td>방법 1단계: 불확실도·MVS 유효 확률</td><td>정함</td></tr><tr><td>사전 정보 유효 확률</td><td>사용자 결정 대기</td></tr><tr><td>다이내믹 손실 학습 없는 시험</td><td>통과</td></tr><tr><td>LOSSTRAIN 학습 시험</td><td>항공 LiDAR 채점 완료</td></tr><tr><td>뜬 면 진단</td><td>이 발주</td></tr><tr><td>1단계 값을 넣은 확인용 19동</td><td>별도 발주</td></tr></table><table><tr><th>이 발주</th><th>상태</th></tr><tr><td>가-1 실제 3차원 보기</td><td>이 묶음</td></tr><tr><td>가-2 원인 셈</td><td>진행 중</td></tr><tr><td>단계 나 학습 4회</td><td>관문 미달·이번 발주에서 실행하지 않음</td></tr></table>',
        '<p class="note">R1 보존 띠: 잠근 보이는 넓이 기준을 충족하는 사진이 없으면 실사 칸은 확인 불가로 남긴다. 메시 색은 수직 높이, 채점 표는 바깥 법선을 따라 처음 만난 면을 사용한다. 두 구분은 동일한 값이 아니다.</p>',
        '<h2 id="summary">요약 표</h2><p>비율의 분모는 각 단위의 채점 허용 패치 넓이이다. 숫자를 누르면 해당 단위의 지도와 사례로 이동한다.</p>',
        '<div class="scroll"><table><thead><tr><th>단위 · 결과</th><th>τ 안 %</th><th>뜬 면 %</th><th>다듬기 τ 안 %</th><th>보존 τ 안 %</th><th>면 없음 %</th><th>평가 PSNR dB</th></tr></thead><tbody>']
    names={r['id']:r['label'] for r in results}
    for row in summary:
        link='#map-'+row['site'];cells=[]
        for k in ['within_tau_pct','floating_pct','cell0_within_tau_pct','cell2_within_tau_pct','no_surface_pct','eval_psnr_db']:
            value='확인 불가' if row[k] is None else f'{row[k]:.2f}'
            cells.append(f'<td><a class="number" href="{link}">{value}</a></td>')
        lines.append('<tr><td>'+esc(row['site']+' · '+names[row['result']])+'</td>'+''.join(cells)+'</tr>')
    lines+=['</tbody></table></div><h2 id="cases">3차원과 사례</h2><div class="case-links">']
    for c in cases:lines.append(f'<a href="#case-{esc(c["id"])}">{esc(c["id"])}</a>')
    lines.append('</div>')
    for c in cases:
        lines += [f'<section id="case-{esc(c["id"])}"><h3>{esc(c["id"])}</h3><div data-viewer="{esc(c["id"])}"></div>',
            '<p>빨강: 참값보다 τ 넘게 위 · 회색: τ 안 · 연파랑: 그 밖 · 연회색: 참값 또는 τ 없음. 가벼운 보기용 메시이며 원래 자른 PLY는 전체 전달 묶음에 들어간다.</p>',
            f'<figure><img loading="lazy" src="{esc(c["plate"])}" alt="{esc(c["id"])} 사진·실제 메시·숫자"><figcaption>사례 범위와 단위 전체의 숫자를 나란히 표시했다. 사례 범위는 서로 겹칠 수 있어 넓이를 더하지 않는다.</figcaption></figure>',
            f'<figure><img loading="lazy" src="{esc(c["captures"]["mesh"])}" alt="{esc(c["id"])} 메시 일곱 각도"><figcaption>모든 결과에 같은 카메라와 조명을 사용했다.</figcaption></figure>',
            f'<figure><img loading="lazy" src="{esc(c["captures"]["gaussian"])}" alt="{esc(c["id"])} 가우시안 일곱 각도"><figcaption>가우시안 색 렌더. 학습 사진이 없는 각도에서는 흐려 보일 수 있다.</figcaption></figure>',
            f'<video controls loop preload="none" poster="{esc(c["captures"]["mesh"])}" src="{esc(c["video"]["mp4"])}"></video><p><a href="{esc(c["video"]["gif"])}">돌려 보기 GIF</a></p></section>']
    lines.append('<h2 id="maps">지도</h2>')
    for site,d in zip(SITES,data):
        lines.append(f'<section id="map-{site}"><h3>{site}</h3><div style="position:relative"><img loading="lazy" style="display:block;width:100%" src="{esc(d["map"])}" alt="{site} 뜬 면 지도">')
        areas=json.loads((web/('mapareas_'+site+'.json')).read_text())['rectangles']
        for b in areas:
            lines.append(f'<a href="#case-{esc(b["case"])}" aria-label="{esc(b["case"])} 지도 상자" style="position:absolute;left:{b["x"]*100:.5f}%;top:{b["y"]*100:.5f}%;width:{b["w"]*100:.5f}%;height:{b["h"]*100:.5f}%;outline:1px solid transparent"></a>')
        lines.append('</div><div class="case-links">')
        for i,c in enumerate(d['cases']):lines.append(f'<a href="#case-{esc(c["id"])}">{i+1}. {esc(c["id"])}</a>')
        lines.append('</div></section>')
    lines+=['<h2 id="gate">관문</h2><p>관문 1 미달: <a href="#map-R1rep_b10">R1 11.64% (109,965 / 945,076 화소)</a>, <a href="#map-B173nb_b10">B173 주변 30.59% (89,532 / 292,704 화소)</a>. 각각 70% 이상이라는 정의를 유지한다. 사용자 지시에 따라 이번 발주에서는 단계 나를 실행하지 않는다.</p>',
        '<h2>기대·기준과 나란히</h2><p>가-2 진단 표는 묶음 ②에 담는다. 단계 나 결과는 이번 발주 범위 밖이다. scientific_verdict: null.</p>',
        '<h2>생기는 과정</h2><p>확인한 기존 저장본은 15,000회와 30,000회이다. 앞 반복 확인은 발주문 4.7의 조건부 작업으로 남아 있다.</p>',
        '<p><a href="data.json">반올림 전 값과 출처</a></p></main><script src="data.js"></script><script src="models.js"></script><script src="viewer.js"></script></html>']
    (web/'index.html').write_text('\n'.join(lines)+'\n')
    total=sum(p.stat().st_size for p in web.rglob('*') if p.is_file());assert total<150000000,total
    save(DOC/'provenance/viewer_A1_files.json',dict(at=now(),bytes=total,files=[dict(path=str(p.relative_to(web)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(web.rglob('*')) if p.is_file()],
        status='FILES_BUILT_BROWSER_QA_PENDING',scientific_verdict=None))
    print('offline viewer built',total,'bytes; browser QA pending')

if __name__=='__main__':main()
