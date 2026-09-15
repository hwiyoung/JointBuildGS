"""Render completed, reference-only diagnostics for the existing local viewer."""
import argparse
import html
import json
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);args=ap.parse_args();root=args.root
read=lambda name:json.loads((root/name).read_text())
receipt=read('receipt.json');assert receipt['status']=='PASS_UAS_REFERENCE_DISTANCE_DIAGNOSTIC'
body='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>드론 LiDAR 기준 비교와 R1 악화 위치</title><style>body{font:16px/1.7 system-ui;margin:0;background:#f2f5f8;color:#19283b}main{max-width:1200px;margin:auto;padding:24px}section{background:white;padding:24px;margin:20px 0;border-radius:12px}img{width:100%;height:auto}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:right}td:first-child,th:first-child{text-align:left}.note{padding:16px;background:#fff2ce}a{color:#1768a8}summary{cursor:pointer}nav{display:flex;gap:18px;flex-wrap:wrap}</style><main>
<h1>드론 LiDAR 기준 비교와 R1 악화 위치</h1>
<p>동결된 R1–R5 결과를 동일한 현재 UAS LiDAR 표본으로 평가했습니다. 기존 MVS 입력 거리 표와는 기준점·표본 집합이 다릅니다.</p>
<p class="note">2024-12-17 nadir 원본의 고정 0.25m 3D 복셀마다 실제 첫 점 하나를 사용합니다. 수치는 LiDAR 점→메시 삼각형 최단거리이며 모든 높이·분류를 포함합니다. 지붕만의 정확도나 실제 변화 정답은 아닙니다. 과거와 동일한 수치 좌표계를 사용하며, 추가 정합·수직 보정은 적용하지 않았습니다.</p>
<nav><a href="#R1mask">R1 악화 위치</a><a href="#R1section">R1 단면</a><a href="#R2section">R2 단면</a><a href="uas_zone_metrics.csv">전체 수치 CSV</a></nav>
<section id="R1mask"><h2>R1: 악화 관측은 Z08 안뜰 지면을 보는 픽셀</h2>
<p>실제 prior 해제 마스크의 2,342,258개 픽셀을 입력 MVS 지면 위치로 되돌려 표시했습니다. 308,082개(13.15%)는 MVS 깊이 절대 잔차가 1m 넘게 증가했습니다. 반복 시점의 관측 수이며 독립적인 3D 점 수가 아닙니다.</p>
<img src="R1_masked_localization.png" alt="R1 Z08 안뜰에 집중된 잔차 악화 지도">
<p>색은 MVS 잔차 변화이며 LiDAR 오차가 아닙니다. 빨간 영역이 플로터의 3D 위치라는 뜻도 아닙니다. 같은 지면을 보는 광선의 앞쪽에 다른 Gaussian이 기여할 수 있습니다.</p></section>'''

for region in ['R1','R2','R3','R4','R5']:
    rows=read(region+'_uas_summary.json')['rows'];ref=read('reference_receipt.json')['regions'][region]
    body+='<section id="'+region+'"><h2>'+region+' · LiDAR 기준 구역별 거리 중앙값</h2>'
    body+='<p>원본 영역 내 '+format(ref['native_count'],',')+'점 → 고정 복셀 표본 '+format(ref['sampled_count'],',')+'점. Z는 XY 위치 상자이며 표본에 여러 높이의 표면이 포함될 수 있습니다.</p>'
    body+='<table><tr><th>구역</th><th>LiDAR 표본</th><th>MVS–GeoGS</th><th>국소 prior 0</th><th>DA3–GeoGS</th></tr>'
    for zone in dict.fromkeys(r['zone'] for r in rows):
        group={r['branch']:r for r in rows if r['zone']==zone}
        body+='<tr><td>'+zone+'</td><td>'+format(group['mvs']['n'],',')+'</td>'
        for b in ['mvs','local_prior0','da3']:
            body+='<td>'+('%.3f m'%group[b]['median_m'] if group[b]['n'] else '기준점 없음')+'</td>'
        body+='</tr>'
    body+='</table><img src="'+region+'_uas_map.png" alt="'+region+' 동일 LiDAR 표본의 결과 메시 거리 지도"></section>'
    if region in ['R1','R2']:
        body+='<section id="'+region+'section"><h2>'+region+' · 같은 위치에서 자른 단면</h2><p>검정 점: 드론 LiDAR. 초록 ×: 입력 MVS. 파랑: MVS–GeoGS. 주황: DA3–GeoGS. 보라: 국소 prior 0. 위 그림의 빨간 선에서 메시를 수직으로 잘랐습니다. 수직 확대 범위 밖 형상은 이 단면 그림에서 생략되며 수치 평가에는 포함됩니다.</p><img src="'+region+'_section.png" alt="'+region+' 실제 메시 단면과 LiDAR 중첩"></section>'

if (root/'case_locations.json').exists():
    body+='''<section id="preservation-case"><h2>실제 보존 문제를 검토할 위치: R1 Z07</h2><p>부채꼴 건물의 국소 표면, 객체축 u=[42,44], v=[14,16], local z=[−34,−32]m입니다. 이 고정 2m 셀의 LiDAR 155점에서 prior까지 거리 중앙값은 0.122m, 기본 MVS–GeoGS는 1.608m, prior0는 1.718m, DA3는 2.109m입니다.</p><img src="R1_Z07_preservation_case_v2.png" alt="R1 Z07에서 prior와 LiDAR가 맞지만 GS 표면이 위에 있는 사례"><p>검정 점은 LiDAR, 초록 선은 prior, 청록 ×는 입력 MVS 표본입니다. 평가에서 발견한 위치이며 새로운 학습 마스크가 아닙니다. MVS 입력 오류 때문에 생겼다는 원인까지 이 거리로 확정하지 않습니다. 나머지 위치별 평가도 <a href="case_locations.json">동일한 기준으로 보존</a>했습니다.</p></section>'''
body+='''<section><h2>Z와 보정·보존 후보의 뜻</h2><p>Z는 검토 위치를 나눈 상자입니다. 그 안의 후보 색은 학습 전 MVS/prior 관계, 관측 지지, 국소 형상과 영상 검토로 만든 가설입니다. 기본 결과가 실제로 틀렸다는 판정이나 두 소스의 정확성 정답이 아닙니다.</p><p>예: 같은 픽셀에서 prior depth=48m, MVS depth=52m이면 prior가 카메라 쪽으로 4m 앞입니다. 현재 규칙은 MVS 지지 ≥3시점, 카메라 범위 ≥5m, prior가 1m 넘게 앞인 관계 비율 ≥67%를 요구합니다. 서로 다른 가림 표면일 수도 있으므로 그 자체로 과거 구조가 틀렸다고 판정하지 않습니다.</p></section>
<section><h2>해석 범위</h2><p>LiDAR 기준 수치는 학습 입력과 분리한 평가입니다. 한 방향의 최단거리는 추가 면·플로터를 놓칠 수 있습니다. 원본 EPSG:32632와 작업 EPSG:25832 사이의 datum/epoch 정밀도 및 절대 오차는 별도 검증되지 않았습니다. 평가 결과를 기존 마스크·가중치·학습에 반영하지 않았습니다. scientific_verdict: null.</p><p><a href="receipt.json">평가 receipt</a> · <a href="reference_receipt.json">LiDAR 원본·표본 계보</a> · <a href="R1_masked_localization.json">악화 위치 상세</a></p></section></main></html>'''
(root/'index.html').write_text(body)
print('PASS UAS report: five region tables/maps, two exact sections, R1 localization')
