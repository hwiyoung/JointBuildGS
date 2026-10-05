"""Publishable static companion to the frozen input-distance diagnostic."""
import html
import json
from pathlib import Path


root = Path('/out')
receipt = json.loads((root / 'receipt.json').read_text())
assert receipt['status'] == 'PASS_PAIRED_INPUT_DISTANCE_DIAGNOSTIC'
records = {r: json.loads((root / (r + '_summary.json')).read_text()) for r in ['R1', 'R2', 'R3', 'R4', 'R5']}


def table(source, judgment, region=None):
    lines = ['<table><thead><tr><th>구역</th><th>표본 수</th><th>MVS–GeoGS</th><th>국소 prior 0</th><th>DA3–GeoGS</th></tr></thead><tbody>']
    for name, data in records.items():
        if region and name != region: continue
        ids = [z['id'] for z in data['metadata']['zones']] if region else ['ALL']
        for zid in ids:
            rows = {r['branch']: r for r in data['rows'] if r['zone'] == zid and r['source'] == source and r['judgment'] == judgment}
            if not rows: continue
            label = name if zid == 'ALL' else zid + ' · ' + rows['mvs']['zone_name']
            lines.append('<tr><td>' + html.escape(label) + '</td><td>' + format(rows['mvs']['n'], ',') + '</td>' +
                         ''.join('<td>%.3f m</td>' % rows[b]['median_m'] for b in ['mvs', 'local_prior0', 'da3']) + '</tr>')
    return ''.join(lines) + '</tbody></table>'


body = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>R1–R5 결과 분석</title><style>
body{font:16px/1.65 system-ui,sans-serif;margin:0;background:#f3f5f7;color:#162335}main{max-width:1200px;margin:auto;padding:32px 24px}section{background:white;border:1px solid #dae0e6;border-radius:12px;padding:24px;margin:24px 0}h1{font-size:30px;line-height:1.3}h2{margin-top:0}a{color:#185b9f}nav{display:flex;gap:20px;flex-wrap:wrap}table{width:100%;border-collapse:collapse;margin:16px 0}th,td{border-bottom:1px solid #dde3e9;padding:10px;text-align:right}th:first-child,td:first-child{text-align:left}img{width:100%;height:auto}.note{background:#fff4dc;padding:16px;border-left:4px solid #d89b28}.muted{color:#566578}details{margin:16px 0}summary{cursor:pointer;font-weight:600}@media(max-width:600px){main{padding:16px 8px}section{padding:12px}table{font-size:12px}th,td{padding:5px}}
</style><main><h1>R1–R5 결과 분석</h1><p>2026-09-18 · 기본 15조건 30k 학습·TSDF 추출·게시 완료</p>
<p class="note"><b>입력 일치도에 대한 1차 진단</b><br>기존에 검토한 동일한 MVS·prior 표본에서 각 결과 메쉬까지의 거리를 비교했다. 독립 기준 기하에 대한 정확도 점수가 아니다. 가까운 기존 면이 남아 있으면, 위에 새 플로터가 생겨도 이 거리는 작게 나올 수 있다.</p>
<nav><a href="#correction">보정 후보</a><a href="#preservation">보존 후보</a><a href="#R1">R1</a><a href="#R2">R2</a><a href="#R3">R3</a><a href="#R4">R4</a><a href="#R5">R5</a><a href="zone_metrics.csv">전체 수치 CSV</a><a href="RESULT_ko.md">상세 보고서</a></nav>
<section><h2>확인한 결과</h2><ul><li>국소 prior 해제 결과는 기본 MVS 대조군과 대체로 비슷하다. R1·R2 보정 후보의 동일 표본 평균 거리 변화는 약 −2 mm였다.</li><li>DA3는 R3–R5 보존 후보에서 prior와 현재 MVS 양쪽 입력과의 거리가 커졌다. 매끄러운 외관과 표면 위치 보존을 따로 확인해야 한다.</li><li>R3·R5의 실제 해제량은 82픽셀·1픽셀이다. R4 보정 후보는 27개여서 중앙값 감소와 평균 거리 증가가 함께 나타난다.</li><li>R1 Z06의 추가 공중 조각은 별도 진단 대상이다. 같은 GPU의 prior 유지/해제 대조는 이 기본 15조건에 포함하지 않았다.</li></ul></section>
<section id="correction"><h2>보정 후보 → 현재 MVS 표본 거리 중앙값</h2>'''
body += table('mvs', 2) + '<p class="muted">표본 수가 작은 R3·R4·R5는 효과를 일반화하기 어렵다. R5의 작은 보정 후보 집합에서는 DA3가 더 가까워지는 반대 사례도 있다.</p></section>'
body += '<section id="preservation"><h2>보존 후보 → prior 표본 거리 중앙값</h2>' + table('prior', 1) + '<p class="muted">prior 정확성 인증을 뜻하지 않는다. 보존 후보는 입력 관계와 원영상 검토에 따른 가설이다.</p></section>'
for name, data in records.items():
    meta = data['metadata']
    body += '<section id="%s"><h2>%s 구역별 결과</h2><p>해제 마스크: %s장, 합계 %s픽셀 · 파란 변화는 해당 입력에 가까워짐, 빨간 변화는 멀어짐.</p>' % (name, name, meta['masked_views'], format(meta['masked_pixels'], ','))
    body += '<img loading="lazy" src="%s_input_distance.png" alt="%s 동일 입력 표본 거리 지도">' % (name, name)
    body += '<details><summary>보정 후보 구역별 수치</summary>' + table('mvs', 2, name) + '</details>'
    body += '<details><summary>보존 후보 구역별 수치</summary>' + table('prior', 1, name) + '</details></section>'
body += '<section><h2>분석 범위</h2><p>원본 fuse.ply hash 확인 · 전체 기존 입력 표본 사용 · 조건마다 동일한 표본·구역·후보 · 10m 거리 cap · 출력/입력 변경 없음. 방향·가림을 보장하는 대응면 검사는 아니며, 입력→메쉬 최단거리만으로 추가 면·구멍·topology를 판정하지 않는다.</p><p>독립 현재 기하 정확도, 변화 정답 및 추가 R1 원인 대조의 결론은 남아 있다. scientific_verdict: null.</p></section></main></html>'
(root / 'index.html').write_text(body)
print('PASS static report: five regions, two overview tables, ten zone tables and five maps')
