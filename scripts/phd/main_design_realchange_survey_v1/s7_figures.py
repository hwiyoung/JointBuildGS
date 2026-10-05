"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 7: summary map and final row specs.

  figures/fig1_summary_map.png   whole image-supported domain: R1-R5, B0, candidates
                                 coloured by the analyst reading and marked by prior basis
  final_spec.json                region rows (R1-R5), real-change candidate rows,
                                 excluded-example rows and the B0 row for s5_rows.py
scientific_verdict: null."""
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np

for f in ('/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSansCJK-Bold.ttc'):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams['font.family'] = ['Noto Sans CJK JP', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
figdir = out / 'figures'; figdir.mkdir(exist_ok=True)
D = dict(np.load(out / 'derived.npz'))
g = cfg['grid']; res = g['res_m']
ext = [g['e_min'], g['e_max'], g['n_min'], g['n_max']]
regs = json.loads((out / 'regions.json').read_text())
rcfg = json.loads(Path('/repo/' + cfg['inputs']['region_config_repo']).read_text())
colors = {r['id']: r['color'] for r in rcfg['regions']}
cands = list(csv.DictReader(open(out / 'candidates.csv')))
tv = {r['tid']: r for r in json.loads((out / 'targets_views.json').read_text())}
meta = {r['tid']: r for r in json.loads((out / 'rows' / 'rows_meta.json').read_text())}

# ---------------- summary map ---------------------------------------------------------------
import scipy.ndimage as ndi
cov = ndi.binary_fill_holes(ndi.binary_closing(D['uls_cov'], iterations=4))
dom = ndi.binary_fill_holes(ndi.binary_closing(D['in_dom'], iterations=4))
rgb = np.where((D['uls_cov'])[..., None], D['rgb_uls'], (D['rgb_mvs'] * 0.55).astype(np.uint8))
rgb = np.where((D['uls_cov'] | ((D['rgb_mvs'].sum(-1) > 0) & dom))[..., None], rgb, 255).astype(np.uint8)
fig, ax = plt.subplots(figsize=(12.5, 14))
ax.imshow(rgb, origin='lower', extent=ext, interpolation='bilinear')
xx = np.linspace(ext[0], ext[1], rgb.shape[1]); yy = np.linspace(ext[2], ext[3], rgb.shape[0])
ax.contour(xx, yy, cov.astype(float), [0.5], colors='#00e5ff', linewidths=1.6, linestyles='-')
ax.contour(xx, yy, dom.astype(float), [0.5], colors='w', linewidths=1.4, linestyles='--')
for rid in ('R1', 'R2', 'R3', 'R4', 'R5'):
    c = np.array(regs[rid]['corners_epsg25832'] + [regs[rid]['corners_epsg25832'][0]])
    ax.plot(c[:, 0], c[:, 1], color=colors[rid], lw=3.0)
    k = np.argmax(c[:4, 1])
    ax.text(c[k, 0], c[k, 1] + 3, rid, color='k', fontsize=15, weight='bold', ha='center', va='bottom',
            bbox=dict(boxstyle='round,pad=0.2', fc=colors[rid], ec='k', lw=0.8))
b0 = regs['B0crop']['crop_epsg25832']
ax.plot([b0[0], b0[2], b0[2], b0[0], b0[0]], [b0[1], b0[1], b0[3], b0[3], b0[1]], color='w', lw=2.0, ls=(0, (5, 3)))
bb = np.array(tv['B0_building']['poly'] + [tv['B0_building']['poly'][0]])
ax.plot(bb[:, 0], bb[:, 1], color='w', lw=1.6)
ax.text(b0[2] + 2, b0[1] + 4, 'B0 크롭\n(4959323)', color='w', fontsize=10, weight='bold', ha='left', va='bottom',
        bbox=dict(boxstyle='round,pad=0.2', fc='k', ec='none', alpha=0.55))
style = {
    'REAL_removed': dict(c='#1f5fbf', label='실제 변화: 철거·제거·낮아짐'),
    'REAL_added': dict(c='#d62728', label='실제 변화: 신축·증축'),
    'REAL_TEMP': dict(c='#ff9f1c', label='실제 변화: 임시 시설로 보임'),
    'REAL_SMALL': dict(c='#ff7fbf', label='실제 변화: 작음(문턱 근처)'),
    'UNCERTAIN': dict(c='#ffe14d', label='판정 보류'),
    'TRANSIENT': dict(c='#9e9e9e', label='제외: 크레인·차량·수증기·나무'),
    'EDGE': dict(c='#cfcfcf', label='제외: 외벽 경계 띠'),
    'LOD2_ONLY': dict(c='#9b59b6', label='LoD2만 다름(항공 LiDAR = 현재)'),
}
marker = {'ALS': '^', 'ALS+LoD2': 'o', 'LoD2': 'D', '-': 'X', '?': 's'}
used = set()
for r in cands:
    cat = r['category']
    if cat == 'REAL':
        key = 'REAL_removed' if float(r['d_uls_als'] or 0) < 0 else 'REAL_added'
    else:
        key = cat
    st = style[key]
    used.add(key)
    big = cat.startswith('REAL') or cat == 'UNCERTAIN'
    ax.scatter(float(r['e']), float(r['n']), s=230 if big else 55, marker=marker.get(r['basis'], 'o'), c=st['c'], edgecolors='k',
               linewidths=1.2 if big else 0.6, zorder=6 if big else 5)
    if big:
        name = 'Z08' if r['tid'] == 'R1_Z08' else r['tid']
        ax.annotate('%s %s' % (name, r['type_ko'].split('(')[0]), (float(r['e']), float(r['n'])), xytext=(9, 7), textcoords='offset points',
                    fontsize=9.5, weight='bold', color='k', bbox=dict(boxstyle='round,pad=0.15', fc='w', ec='none', alpha=0.85), zorder=7)
h1 = [Line2D([], [], marker='o', ls='', mfc=v['c'], mec='k', ms=10, label=v['label']) for k, v in style.items() if k in used]
h2 = [Line2D([], [], marker=m, ls='', mfc='w', mec='k', ms=10, label=l) for m, l in
      (('o', '두 사전 정보 모두와 다름'), ('^', '항공 LiDAR(2022)와만 다름'), ('D', 'LoD2와만 다름'), ('X', '건물 변화 아님'))]
h3 = [Line2D([], [], color='#00e5ff', lw=1.5, label='드론 LiDAR(참값) 덮는 범위'), Line2D([], [], color='#777777', lw=1.4, ls='--', label='현재 영상 MVS 범위(흰 점선)'),
      Line2D([], [], color='#777777', lw=2.0, ls=(0, (5, 3)), label='B0 크롭(r8~r10 장면, 흰 긴 점선)')]
leg1 = ax.legend(handles=h1, loc='lower left', fontsize=9, title='색 = 판독(분석자, 사람 검수 전)', title_fontsize=9, framealpha=0.92)
ax.add_artist(leg1)
leg2 = ax.legend(handles=h2 + h3, loc='lower right', fontsize=9, title='모양 = 어느 사전 정보와 다른가', title_fontsize=9, framealpha=0.92)
ax.set_xlim(690700, 691200); ax.set_ylim(5335820, 5336410)
ax.set_xlabel('E (EPSG:25832, m)'); ax.set_ylabel('N (EPSG:25832, m)')
ax.ticklabel_format(useOffset=False, style='plain')
ax.set_title('실제 변화 조사 요약 — 2022 항공 LiDAR·LoD2 대 2024-12-17 현재(드론 LiDAR 참값·영상 MVS)\n'
             '후보 = 드론 LiDAR 기준 |차이| > 2.5 m·연결 넓이 ≥ 25 m²(식생 제외) + R1 Z08; 바탕 = 드론 LiDAR 색(없는 곳은 MVS 색, 어둡게)', fontsize=11.5)
fig.tight_layout()
fig.savefig(figdir / 'fig1_summary_map.png', dpi=130)
plt.close(fig)
print('summary map ok')

# ---------------- final row specs ------------------------------------------------------------
c = {r['tid']: r for r in cands}


def rc(rid):
    return regs[rid]['corners_epsg25832']


def title_of(tid, head):
    r = c[tid]
    return '%s\n드론 LiDAR 기준: 항공 LiDAR와 %s m, LoD2와 %s m 차이(중앙값), 넓이 %s m²  |  덮는 영상 %s장(연직 %s·경사 %s), 깊이 일치 %s장' % (
        head, r['d_uls_als'], r['d_uls_lod2'], r['area_m2'], r['views_cover'], r['views_cover_nadir'], r['views_cover_oblique'], r['views_depth_consistent'])


spec = {'regions': [], 'candidates': [], 'excluded': [], 'b0': []}
spec['regions'] = [
    dict(tid='ROW_R1', poly=rc('R1'), poly2=[tv['R1_Z08']['poly']], line=meta['R1_Z08']['line'], view_tid='R1_Z08', margin=6,
         title=title_of('R1_Z08', 'R1 — Z08 안뜰: 2022 항공 LiDAR에만 있던 높이 약 4 m 구조물이 사라짐(항공 LiDAR 기준 변화, LoD2 기준 변화 없음)'),
         note='분홍 = R1 경계, 검은 점선 = Z08. LoD2 지도에서 Z08은 LoD2가 "건물 없음"이라 MVS의 지면 위 높이(약 0)를 보인다.'),
    dict(tid='ROW_R2', poly=rc('R2'), poly2=[tv['C11']['poly']], line=meta['C11']['line'], view_tid='C11', margin=6,
         title=title_of('C11', 'R2 — B173(DEBY_LOD2_4959326) 지붕 재건: 양쪽 날개 박공(약 21~23 m) → 녹화 평지붕(약 15.5 m)'),
         note='가운데 톱날 채광 지붕은 2022·LoD2·2024가 같다. 바뀐 것은 양쪽 날개.'),
    dict(tid='ROW_R3', poly=rc('R3'), poly2=[tv['B_R3_4959460']['poly'], tv['C04']['poly']], line=meta['B_R3_4959460']['line'], view_tid='B_R3_4959460', margin=6,
         title='R3 — 실제 변화 없음(대표 단면: DEBY_LOD2_4959460). 동쪽 경계에 새 5.3 m 덮개 구조물 C04가 걸침(중심은 경계 밖 1 m)',
         note='4959460 지붕은 항공 LiDAR·드론 LiDAR·MVS가 일치; LoD2만 옥상 돌출부 일부를 빠뜨림(C28).'),
    dict(tid='ROW_R4', poly=rc('R4'), poly2=[tv['B_R4_4906988_91']['poly']], line=meta['B_R4_4906988_91']['line'], view_tid='B_R4_4906988_91', margin=6,
         title='R4 — 실제 변화 없음(대표 단면: AX-10이 "변화"로 둔 4906988·4906991; 세 자료 높이 일치)',
         note='R4의 큰 차이는 LoD2가 옥상 구조·지붕 일부를 빠뜨린 곳(C31·C32)과 나무. R4 북쪽 14 %는 MVS·드론 LiDAR 밖.'),
    dict(tid='ROW_R5', poly=rc('R5'), poly2=[tv['C12']['poly']], line=meta['C12']['line'], view_tid='C12', margin=6,
         title=title_of('C12', 'R5 — 실제 건물 변화 없음. 두 건물 사이 2022 나무 수관(약 14 m)이 지금 없음(C12, 항공 LiDAR 다중반사 95 %)'),
         note='단순 높이 차이 선별은 이런 나무 제거를 변화로 잡는다. 항공 LiDAR 다중반사·분류로 구조물과 나무를 가른다.'),
]
for tid, head in (('C05', 'C05 — DEBY_LOD2_4907510 철거(높이 약 3 m 단층, 평면 119 m²), 지금 맨흙'),
                  ('C06', 'C06 — DEBY_LOD2_4907508 철거(높이 약 3.7 m, 평면 131 m²), 철거 잔해·공사 펜스'),
                  ('C02', 'C02 — DEBY_LOD2_4907207 지붕 일부 약 +3 m(증축 후보), 드론 LiDAR 피복 61 %'),
                  ('C04', 'C04 — R3 동쪽 경계: 통로 위 새 5.3 m 구조물(흰 덮개, 임시 시설로 보임)'),
                  ('C27', 'C27 — 건물 모서리 옆 새 약 3 m 낮은 구조물(작음, 차양·창고류로 보임)')):
    spec['candidates'].append(dict(tid='ROW_' + tid, poly=tv[tid]['poly'], line=meta[tid]['line'], view_tid=tid, title=title_of(tid, head)))
for tid, head in (('C08', 'C08 제외 — 2022 크레인(항공 LiDAR에만 40 m 넘는 가는 구조)'),
                  ('C03', 'C03 제외 — 굴뚝 수증기(드론 LiDAR에만 38 m 반사, MVS 없음)'),
                  ('C01', 'C01 제외 — 드론 LiDAR 취득 때 도로의 차량'),
                  ('C07', 'C07 제외 — 외벽 경계 띠(드론 LiDAR 지붕 미피복)'),
                  ('C22', 'C22 LoD2만 다름 — 긴 곡면 지붕을 LoD2가 평면으로 근사'),
                  ('C33', 'C33 LoD2만 다름 — LoD2 9 m, 2022·2024 모두 4.3 m'),
                  ('C10', 'C10 제외 — 2022 곡면 지붕 끝 위 나무 수관(약 19~23 m, 다중반사 93 %)이 지금 없음')):
    spec['excluded'].append(dict(tid='ROW_' + tid, poly=tv[tid]['poly'], line=meta[tid]['line'], view_tid=tid, title=title_of(tid, head)))
spec['b0'] = [dict(tid='ROW_B0', poly=regs['B0crop']['corners_epsg25832'], poly2=[tv['B0_building']['poly']], line=meta['B0_building']['line'],
                   view_tid='B0_building', margin=4,
                   title='B0 크롭(r8~r10 장면) — 대상 건물 DEBY_LOD2_4959323: 네 자료 일치, 실제 변화 없음',
                   note='분홍 = B0 크롭(ALS 크롭 사각형), 검은 점선 = 대상 건물 평면.')]
allt = spec['regions'] + spec['candidates'] + spec['excluded'] + spec['b0']
(out / 'final_spec.json').write_text(json.dumps({'targets': allt, 'groups': {k: [t['tid'] for t in v] for k, v in spec.items()}}, ensure_ascii=False, indent=1))
print('spec', len(allt))
