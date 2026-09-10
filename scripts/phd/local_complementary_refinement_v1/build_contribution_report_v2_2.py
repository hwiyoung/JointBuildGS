"""Serve an additive scientific report through the existing read-only packet server.

Never updates current.json, existing packets, training sources, or services.
"""
import argparse
import csv
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(head, rows):
    return '<div class="table"><table><thead><tr>' + ''.join('<th>' + html.escape(str(x)) + '</th>' for x in head) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(x)) + '</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def document(text):
    """Render this owned report's prose/headings/pipe tables without external dependencies."""
    lines = text.splitlines(); blocks = []; i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            blocks.append(f'<h{level}>' + inline(line[level:].strip()) + f'</h{level}>'); i += 1
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [x.strip() for x in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', x) for x in cells): rows.append(cells)
                i += 1
            blocks.append(table(rows[0], rows[1:]))
        else:
            paragraph = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|')):
                paragraph.append(lines[i]); i += 1
            blocks.append('<p>' + inline(' '.join(paragraph)) + '</p>')
    return '\n'.join(blocks)


def main():
    p = argparse.ArgumentParser()
    for name in ['analysis', 'report', 'site', 'qa']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    assert Path('/.dockerenv').exists()
    receipt = json.loads((a.analysis/'receipt.json').read_text())
    assert receipt['status'] == 'PASS_SEALED_CONTINUOUS_CONTRIBUTION_DIAGNOSTIC'
    for item in receipt['outputs']:
        assert sha(a.analysis/item['path']) == item['sha256']
    out = a.site/'packets'/'packet_contribution_v2_2_r2_20260911T025441_538040Z'
    out.mkdir(parents=True, exist_ok=False)
    (out/'assets').mkdir(); (out/'downloads').mkdir()
    inputs = [dict(path=str(p), sha256=sha(p)) for p in [a.analysis/'receipt.json', a.report, Path(__file__), a.qa]]
    for path in sorted(a.analysis.iterdir()):
        if not path.is_file(): continue
        folder = 'assets' if path.suffix == '.png' else 'downloads'
        shutil.copyfile(path, out/folder/path.name)
    shutil.copyfile(a.qa, out/'downloads'/'independent_qa_receipt.json')
    shutil.copyfile(a.report, out/'downloads'/a.report.name)
    shutil.copyfile(Path(__file__), out/'downloads'/Path(__file__).name)
    with (a.analysis/'continuous_metrics.csv').open() as f: metric = list(csv.DictReader(f))
    with (a.analysis/'all_geometry.csv').open() as f: geom = list(csv.DictReader(f))
    fields = ['sample_to_full_ref_3d', 'ref_to_full_mesh_3d']
    means = {}
    for row in metric:
        if row['mesh_kind'] == 'raw' and row['domain'] == 'whole':
            means.setdefault((row['region'], row['candidate']), {})[row['direction']] = float(row['mean_m'])
    dominance = []
    for (region, name), values in means.items():
        if not name.startswith('LC_'): continue
        competitors = [(n, v) for (r, n), v in means.items() if r == region and n.startswith('D') and n.split('_P')[-1] == name.split('_P')[-1]]
        better = [n for n, v in competitors if all(v[k] <= values[k] for k in fields) and any(v[k] < values[k] for k in fields)]
        dominance.append(dict(region=region, candidate=name, prediction_mean_m=values[fields[0]], reference_mean_m=values[fields[1]], dominating_sampled_globals=';'.join(better), scientific_verdict=''))
    assert len(dominance) == 13 and sum(bool(r['dominating_sampled_globals']) for r in dominance) == 9
    with (out/'downloads'/'observed_global_comparators.csv').open('x') as f:
        w = csv.DictWriter(f, fieldnames=list(dominance[0])); w.writeheader(); w.writerows(dominance)
    fig, axes = plt.subplots(3, 2, figsize=(13, 13), layout='constrained')
    for rr, region in enumerate(['P1', 'P2', 'P3']):
        region_values = [v for (r, n), v in means.items() if r == region and n != 'ANCHOR']
        xmax = max(v[fields[0]] for v in region_values)*1.12
        ymax = max(v[fields[1]] for v in region_values)*1.12
        for cc, mode in enumerate(['native', 'release']):
            ax = axes[rr, cc]
            for (r, name), v in means.items():
                if r != region or not name.endswith('_P' + mode): continue
                local = name.startswith('LC_')
                coefficient = name.split('_P')[0].replace('LC_D', '').removeprefix('D')
                label = ('LC ' if local else 'G ') + {'005': '.005', '0005': '.0005', '0': '0'}[coefficient]
                ax.scatter(v[fields[0]], v[fields[1]], marker='^' if local else 'o', color='#B05D19' if local else '#285A85', s=50)
                offset = ({'005': (12, 9), '0005': (14, 30), '0': (14, -18)} if local else
                          {'005': (-12, -13), '0005': (-12, 14), '0': (-12, -25)})[coefficient]
                ax.annotate(label, (v[fields[0]], v[fields[1]]), xytext=offset, textcoords='offset points', fontsize=9,
                            ha='left' if local else 'right', arrowprops=dict(arrowstyle='-', color='#777777', linewidth=.55))
            ax.set(xlim=(0, xmax), ylim=(0, ymax), title=f'{region} / {mode}', xlabel='Predicted samples to observed reference mean (m)', ylabel='Same reference to reconstructed mesh mean (m)')
            ax.grid(color='#DDDDDD', linewidth=.5)
            ax.text(.04, .94, 'Lower-left: smaller distances', transform=ax.transAxes, va='top', fontsize=9)
    fig.suptitle('Raw TSDF512: observed tradeoffs across global prior settings and LC\nBlue circles: G; orange triangles: LC. Finite development grid, no repeat or spatial-effect isolation.', fontsize=13)
    fig.savefig(out/'assets'/'continuous_tradeoffs.png', dpi=150); plt.close(fig)
    rows = []
    for row in sorted(dominance, key=lambda r: (r['region'], r['candidate'])):
        g = next(x for x in geom if x['region'] == row['region'] and x['candidate'] == row['candidate'] and x['mesh_kind'] == 'raw' and float(x['threshold_m']) == .5)
        before = next(x for x in geom if x['region'] == row['region'] and x['candidate'] == row['candidate'].removeprefix('LC_') and x['mesh_kind'] == 'raw' and float(x['threshold_m']) == .5)
        rows.append([row['region'], row['candidate'], f"{float(g['f1']) - float(before['f1']):+.5f}", f"{row['prediction_mean_m']:.3f}", f"{row['reference_mean_m']:.3f}", row['dominating_sampled_globals'] or '관측 세 G 중 없음'])
    supplement = '<h2 id="figures">직접 비교 그림과 전체 13조건 표</h2><p>그림을 누르면 원본을 엽니다. G .005 / .0005 / 0과 LC를 같은 단면에 나란히 놓았습니다. D005=.005, D0005=.0005, D0=0입니다.</p>'
    supplement += '<figure><a href="assets/continuous_tradeoffs.png"><img src="assets/continuous_tradeoffs.png" alt="지역과 보호별 양방향 연속 평균 거리 비교"></a><figcaption>같은 지역의 native/release는 축 범위가 같습니다. 가까운 표식의 정확한 값은 아래 표와 CSV를 봅니다.</figcaption></figure>'
    supplement += table(['지역', 'LC 조건', '대응 G 대비 F1 Δ', '예측→참조 평균 m', '참조→mesh 평균 m', '두 평균 모두 낮은 동일 보호 G'], rows)
    for region in ['P1', 'P2', 'P3']:
        for mode in ['native', 'release']:
            name = f'{region}_{mode}_sections.png'
            supplement += f'<figure><a href="assets/{name}"><img src="assets/{name}" alt="{region} {mode} 고정 단면 일곱 조건"></a><figcaption>{region} / {mode} — 같은 위치·폭·축척. 미평가 조건은 빈 예측을 표시합니다.</figcaption></figure>'
    supplement += '<h2 id="downloads">수치·명세·재현 자료</h2><ul>' + ''.join(f'<li><a href="downloads/{p.name}">{html.escape(p.name)}</a></li>' for p in sorted((out/'downloads').iterdir())) + '</ul>'
    style = 'body{margin:0;background:#faf9f6;color:#242424;font:17px/1.8 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:32px 24px 80px}h1{font-size:32px;line-height:1.45;margin-top:26px}h2{font-size:24px;margin-top:44px}p{max-width:1000px}a{color:#245e94}nav{display:flex;gap:22px;flex-wrap:wrap}code{background:#eeeef0;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere;font-size:.88em}.table{overflow-x:auto;margin:24px 0}table{width:100%;border-collapse:collapse;font-size:15px;line-height:1.6}th,td{text-align:left;border-bottom:1px solid #d4d4d4;padding:10px 12px}th{background:#f0eee9}figure{margin:36px 0}img{width:100%;height:auto;background:white}figcaption{font-size:14px;color:#555}li{overflow-wrap:anywhere}@media(max-width:600px){main{padding:16px}h1{font-size:25px}h2{font-size:21px}body{font-size:16px}table{min-width:800px}}'
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LC 기여 면밀 분석 — 검증 13조건</title><style>' + style + '</style><main><nav><a href="#figures">비교 그림·13조건 표</a><a href="#downloads">원수치 다운로드</a><a href="http://localhost:8906/">기존 3D 뷰어</a></nav>' + document(a.report.read_text()) + supplement + '</main></html>'
    (out/'index.html').write_text(page)
    final = dict(status='PASS_ADDITIVE_CONTRIBUTION_REPORT_BUILT', scientific_verdict=None, current_pointer_modified=False,
                 source_snapshot=receipt['config']['review_packet'], source_snapshot_receipt_sha256=receipt['config']['review_receipt_sha256'],
                 analysis_receipt_sha256=sha(a.analysis/'receipt.json'), evaluated_conditions=13, observed_two_mean_dominated=9,
                 browser_validation='separate receipt required', inputs=inputs,
                 outputs=[dict(path=str(p.relative_to(out)), sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()])
    (out/'receipt.json').write_text(json.dumps(final, indent=2) + '\n')
    print(json.dumps(dict(status=final['status'], packet=str(out), scientific_verdict=None)))


if __name__ == '__main__':
    main()
