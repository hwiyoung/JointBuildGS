"""Make an inspectable local report from the validated existing-result comparison."""
import json
from pathlib import Path
out=Path('/out');m=json.loads((out/'metrics.json').read_text());val=json.loads((out/'validation.json').read_text())
assert val['status']=='PASS_REFERENCE_IDS_METRICS_AND_CONTROLS'
roles=['global_0005','regional_0005','regional_005']
names={'ground':'P1 보정 지면','roof_strip':'P1 지붕 띠 전체','roof_tip_west':'P1 빨간 끝 / 서측','roof_middle':'P1 주황 중앙','roof_tip_east':'P1 파란 끝 / 동측','target_roof':'대상 지붕'}
parts=['''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>전역·영역별 감독 검증</title>
<style>body{font-family:system-ui,sans-serif;color:#172b40;background:#f5f7fa;margin:0}main{max-width:1180px;margin:auto;padding:28px}section{background:white;padding:24px;margin:22px 0;border:1px solid #dce3eb;border-radius:12px}h1{font-size:28px}h2{font-size:23px}p,li{line-height:1.75}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:10px;text-align:left;border-bottom:1px solid #ddd}th{background:#edf2f7}img{max-width:100%;height:auto}a{color:#165eab}.scroll{overflow-x:auto}.note{color:#516275;font-size:14px}.summary{padding:16px;background:#eaf3ff;border-left:4px solid #2874ba}@media(max-width:650px){main{padding:12px}section{padding:12px}table{font-size:12px}}</style><main>
<h1>기존 결과 검증: 전역 MVS ↔ 영역별 MVS</h1>
<p>두 주 비교 조건 모두 <b>prior 0.0005 · native 보호 · 30,000회</b>. 같은 지역의 원본 UAS 점을 0.1m voxel에서 선택해 모든 조건에 동일하게 사용했습니다. 신규 학습은 없습니다.</p>
<p class="summary"><b>P1:</b> 지면 보정을 유지하면서 지붕 끝 손상이 부분적으로 줄었습니다. <b>P2:</b> 지붕은 소폭 개선됐습니다. <b>P3:</b> 지붕 GT 거리는 증가했습니다. 지역별 효과가 다릅니다.</p>
<p><a href="/app/weights.html?comparison=prior">기존 prior 비교 뷰어</a> · <a href="metrics.json">전체 측정값</a> · <a href="config.json">고정 평가 범위</a> · <a href="validation.json">입력·점 ID·조건 검증</a></p>''']
for region,r in m['regions'].items():
    parts.append(f'<section><h2>{region}: 같은 GT 점에서 원본 mesh까지의 거리</h2><p>평균 거리, 단위 cm. 낮을수록 해당 관측 표면에 가깝습니다. 수직 높이 오차와는 다릅니다.</p><div class="scroll"><table><tr><th>평가 부위</th><th>GT 점 수</th><th>전역 / .0005</th><th>영역별 / .0005</th><th>영역별 / .005 참고</th></tr>')
    for name,s in r['rois'].items():
        if name=='all_reference':continue
        cells=''.join(f"<td>{s['surface'][k]['mean_abs']*100:.1f}</td>" for k in roles)
        parts.append(f"<tr><td>{names[name]}</td><td>{s['reference_count']:,}</td>{cells}</tr>")
    parts.append('</table></div>')
    if region=='P1':parts.append('''<p>빨간·파란 끝 모두 전역 조건보다 GT 거리가 줄었습니다. 파란 끝에서 감소가 더 컸고, 중앙 변화는 작았습니다. 하지만 prior .005보다 손상이 남아 있습니다.</p><p class="note">끝은 뷰어에 보이는 지붕 띠의 양쪽 부분입니다. 실제 건물 전체의 끝선으로 확정한 범위는 아닙니다. 아래 사진에 정확한 평가 위치를 표시했습니다. 단면은 각 XY에서 위에서 처음 만나는 표면이며, 지붕이 빠진 곳에서는 바닥이 나타날 수 있습니다.</p><img src="P1_roof_scope_profiles.png" alt="P1 지붕 띠 평가 위치와 두 단면">''')
    if region=='P2':parts.append('<p>대상 지붕 평균은 26.1→24.1cm로 줄었지만 GT 50cm 이내 비율은 85.8→85.9%로 거의 같습니다. 지붕의 큰 형태가 비슷하게 보이는 관찰과 맞습니다. 주변부에는 개선과 악화가 함께 있습니다.</p>')
    if region=='P3':parts.append('<p>대상 지붕 평균은 16.7→19.6cm, 중앙값은 8.9→10.7cm로 증가했습니다. 아래 지도에서는 지붕 길이 방향의 일부 띠에서 악화가 보입니다. 영역별 감독의 보존 성공 사례로 판단할 근거가 없습니다.</p>')
    parts.append(f'<img src="{region}_gt_comparison.png" alt="{region} 전역과 영역별 감독의 GT 거리 지도"><p class="note">지도 오른쪽: 파랑은 GT 거리 감소, 빨강은 증가. 색은 ±50cm에서 포화됩니다. 지도는 관측 GT 전체 높이의 투영이며, 표의 지붕 집계는 고정 XY와 Z 범위를 함께 적용합니다.</p>')
    parts.append('<details><summary>MVS 감독신호와의 일치도</summary><p>동일 학습뷰의 동일 R1 유효 픽셀에서 expected camera-Z depth 평균 절대차입니다. GT 표와 평가 표본·거리 정의가 다릅니다. 단위 cm.</p><table><tr><th>영상</th><th>전역 / .0005</th><th>영역별 / .0005</th></tr>')
    for view in r['views']:
        s=view['subsets']['R1']['fit_mvs'];parts.append(f"<tr><td>{view['camera']}</td><td>{s['global_0005']['mean_abs']*100:.1f}</td><td>{s['regional_0005']['mean_abs']*100:.1f}</td></tr>")
    parts.append('</table>')
    for view in r['views']:
        tail=Path(view['camera']).stem[-6:];parts.append(f'<img src="{region}_{tail}_depth_comparison.png" alt="{region} {tail} depth 변화">')
    parts.append('</details></section>')
parts.append('''<section><h2>해석 범위</h2><ul>
<li>P1 전체 관측점 평균은 74.9→84.9cm로 증가했습니다. 지면·끝 지붕의 국소 개선을 P1 전체 개선으로 확대하지 않습니다.</li>
<li>GT→mesh 단방향 거리는 실제 GT 관측 부위의 적합도입니다. 관측이 없는 영역의 정확성이나 과잉 표면까지 완전히 평가하지 않습니다. 단면과 상부 첫 표면 진단을 함께 보존했습니다.</li>
<li>같은 Anchor SHA, native 보호, prior 계수와 TSDF 추출 설정을 확인했습니다. 과거 전역 P2/P3의 기록된 MVS 계수는 0.0475/0.05, 이번은 고정 0.05입니다. 비교는 기존 두 정책 전체의 결과이며 마스크 효과만 분리한 인과 실험은 아닙니다.</li>
<li>평가 범위는 거리 측정 전에 고정했습니다. UAS는 평가에만 사용했고 학습 마스크·가중치·입력은 변경하지 않았습니다. 반복 실행 변동은 미측정이며 과학적 판정은 null입니다.</li></ul></section></main></html>''')
(out/'report.html').write_text(''.join(parts))
