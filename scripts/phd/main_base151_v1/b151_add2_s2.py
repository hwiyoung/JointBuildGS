"""PHD-MAIN-BASE151-v1 addendum 2 section 2 report items (GTJUDGE environment; writes /gtjudge/add2/). Before = b151_2DGS_s0 cell 3 (324 training
images); after = a2_2DGS_<tag> cell 3 (the listed training images; same 38 test images, same settings). Both read from the 4.2 score rows (ALS GT).

  python b151_add2_s2.py <tag>
    s2_cell3            item 1: the a2_17_cell3 rows of before and after (copied from a2_17_cell3.json; run b151_add2_ef_tables.py a2_2DGS_<tag> first)
    s2_buildings        item 2: cell-3 buildings (building cell 3 as in 1-4, flat roof rows with point_cell 3 >= 200): low-oblique training images that see
                        the roof (the 1-5 rule) in the before / after list; flat roof s median (point_cell 3 rows, finite s) before / after
    s2_scatter          item 2: x = added low-oblique images seeing the roof, y = s median after - before
    s2_B173nb           item 3: the 55,619 B173nb flat roof site rows of addendum 1 (d_prev: site rows |n_z| >= 0.985, case 0, cell 3) mapped to their gt151
                        rows; s median and share within tau (site row tau) of the 4.2 score rows before / after, next to the d_prev values
    s2_cell3_map        item 4: the 1-7 map, before and after side by side
scientific_verdict: null
"""
import json
import sys

import numpy as np

sys.path.insert(0, '/b151s')
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import b151_tables42 as T42  # noqa: E402
from b151_add2 import A, GROUPS, cams, dump, image_table, project, roof_samples, table  # noqa: E402
from b151_add1 import FLAT_NZ, O, in_cell, site_map  # noqa: E402
import b151_common as BC  # noqa: E402

BEFORE = 'b151_2DGS_s0'


def main(tag):
    BC.cfg('score151')
    after = f'a2_2DGS_{tag}'
    g = dict(np.load(O / 'gt151_ALS.npz'))
    g['bcode'] = np.unique(g['building'], return_inverse=True)[1]
    r3 = g['point_cell'] == 3
    flat = (~g['wall']) & (g['normal'][:, 2] >= .985) & (g['case'] == 0)
    S = {}
    for run in [BEFORE, after]:
        z = T42.load(run, 'ALS', g)
        assert z is not None, run
        S[run] = z['s_main']
    # item 1
    t17 = json.loads((A / 'a2_17_cell3.json').read_text())['rows']
    rows1 = [r for r in t17 if r['run'] in (BEFORE, after)]
    assert len(rows1) == 2, 'run b151_add2_ef_tables.py ' + after + ' first'
    table('s2_cell3', rows1, f'2-1: cell 3, ALS GT, the 1-7 rule; before = {BEFORE} (324 training images), after = {after} (the {tag} list)')
    # item 2
    cm = cams()
    imgs, _gz, _sp = image_table(cm, g)
    st = json.loads((A / 'state.json').read_text())
    before_list = st['cell_lists']['3']['position'] + st['cell_lists']['3']['visibility']
    after_list = json.loads(open(f'/b151/add2/scenes/{tag}/split.json').read())['train']   # /b151 = OUT (read only)
    rs = roof_samples(g, np.random.default_rng(0))
    out = []
    for nm, idx in rs.items():
        if st['building_cell'][nm] != 3:
            continue
        m = r3 & flat & (g['building'] == nm)
        if m.sum() < 200:
            continue
        P = g['xyz'][idx]
        lo = lambda L: sorted(n for n in L if imgs[n]['group'] == 'low_oblique' and project(cm[n], P).mean() >= .5)
        b, a = lo(before_list), lo(after_list)
        r = dict(building=nm, flat_roof_rows_in_cell3=int(m.sum()), see_low_oblique_before=len(b), see_low_oblique_after=len(a), added=len(set(a) - set(b)))
        for key, run in [('before', BEFORE), ('after', after)]:
            v = S[run][m]; f = np.isfinite(v)
            r[f's_median_{key}'] = float(np.median(v[f])) if f.any() else None
            r[f's_finite_{key}'] = int(f.sum())
            r[f'within_tau_pct_{key}'] = float(100 * (f & (np.abs(np.where(f, v, 0)) <= g['tau'][m])).mean())
        r['s_change'] = r['s_median_after'] - r['s_median_before'] if r['s_median_after'] is not None and r['s_median_before'] is not None else None
        out.append(r)
    out.sort(key=lambda r: r['building'])
    table('s2_buildings', out, '2-2: cell-3 buildings (building cell 3 = cell of most of its GT rows, as in 1-4; flat roof rows with point_cell 3 >= 200): '
          'low-oblique training images that see the roof (half of up to 200 roof sample points, seed 0, inside the image in front, no occlusion check) in the '
          f'before list (cell 3, 324) and the after list ({tag}, {len(after_list)}); flat roof s median over the point_cell 3 rows with finite s; '
          's_change = after - before')
    # item 3
    sd = O / 'scenes' / 'B173nb_b10__ALS'
    sr = np.load(sd / 'rows.npz')
    nn = sr['normal'] * np.sign(sr['normal'][:, 2:3] + 1e-12)
    gi, si = site_map(g, 'B173nb_b10', sr['xyz'])
    to_g = np.full(len(sr['xyz']), -1); to_g[si] = gi
    case0 = np.zeros(len(sr['xyz']), bool); case0[si] = g['case'][gi] == 0
    fm = (~sr['wall']) & (np.abs(nn[:, 2]) >= FLAT_NZ) & case0 & in_cell(sr['xyz'][:, :2], 3)
    gidx = to_g[fm]
    assert (gidx >= 0).all()
    tau = sr['row_tau_m'][fm]
    prev = {r['family']: r for r in json.loads((O / 'add1' / 'd_prev.json').read_text())['rows'] if r.get('site') == 'B173nb_b10' and r.get('cell') == 3}
    rows3 = []
    for label, run in [('2DGS 건물 단위(덧붙임 1 d_prev 2DGS_30000)', None), ('b151_2DGS_s0 (덧붙임 1 d_prev, 4.1 자리 메시)', None),
                       ('전: b151_2DGS_s0 (4.2 채점 줄)', BEFORE), ('후: ' + after + ' (4.2 채점 줄)', after)]:
        if run is None:
            p = prev['2DGS_30000' if '건물 단위' in label else BEFORE]
            rows3.append(dict(row=label, flat_rows=p['flat_case0_rows'], s_median=p['s_median'], within_tau_pct=p['within_tau_pct'], no_surface=p['no_surface'],
                              source='d_prev (4.1 site distances)'))
            continue
        v = S[run][gidx]; f = np.isfinite(v)
        rows3.append(dict(row=label, flat_rows=int(len(v)), s_median=float(np.median(v[f])) if f.any() else None,
                          within_tau_pct=float(100 * (f & (np.abs(np.where(f, v, 0)) <= tau)).mean()), no_surface=int((~f).sum()),
                          source='4.2 score rows (gt151 rows matched to the site rows by equal coordinates)'))
    table('s2_B173nb', rows3, '2-3: B173nb flat roof site rows of addendum 1 (|n_z| >= 0.985, case 0, cell 3: 55,619 rows); first two rows = the addendum 1 values '
          '(4.1 site meshes); the before / after rows read the 4.2 score rows (cell-3 unit meshes) of the matched gt151 rows; tau = the site row tau')
    # figures
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from pathlib import Path
    for f in Path('/fonts').rglob('NotoSansCJK*.ttc'):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    (A / 'figures').mkdir(parents=True, exist_ok=True)
    pts = [r for r in out if r['s_change'] is not None]
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.axhline(0, color='#999999', lw=.8)
    ax.scatter([r['added'] for r in pts], [r['s_change'] for r in pts], s=18, color='#2166ac')
    ax.set_xlabel('늘어난 영상 수(지붕을 보는 낮고 비스듬한 학습 영상, 후 − 전)')
    ax.set_ylabel('평지붕 s 중앙값 변화 (m, 후 − 전)')
    ax.set_title(f'칸 3 건물 {len(pts)}동 · 전 {BEFORE} / 후 {after}')
    fig.tight_layout()
    fig.savefig(A / 'figures' / 's2_scatter.png', dpi=110, facecolor='white'); plt.close(fig)
    dump(A / 'figures' / 's2_scatter.json', dict(item='2-2', source='s2_buildings', buildings=len(pts), before=BEFORE, after=after, scientific_verdict=None))
    xy = g['xyz'][r3, :2]; tau3 = g['tau'][r3]
    fig, ax = plt.subplots(1, 2, figsize=(12, 6.4), sharex=True, sharey=True)
    for a, (label, run) in zip(ax, [(f'전: {BEFORE} (324장)', BEFORE), (f'후: {after} ({len(after_list)}장)', after)]):
        v = S[run][r3]
        ok = np.isfinite(v) & (np.abs(np.where(np.isfinite(v), v, 0)) <= tau3)
        col = np.where(~np.isfinite(v), '#999999', np.where(ok, '#f0f0f0', np.where(v < 0, '#2166ac', '#b2182b')))
        o = np.argsort(ok)[::-1]
        a.scatter(xy[o, 0], xy[o, 1], s=.3, c=col[o], rasterized=True)
        a.set_facecolor('#d9d9d9')
        a.set_title(f'{label}\n칸 3 τ 안 {100 * ok.mean():.1f} %'); a.set_aspect('equal')
    fig.suptitle('칸 3 참값 점(ALS) 위에서 본 τ 안/밖 · 흰색 τ 안 / 파랑 −τ보다 작음 / 빨강 +τ보다 큼 / 회색 면 없음')
    fig.tight_layout(rect=(0, 0, 1, .9))
    fig.savefig(A / 'figures' / 's2_cell3_map.png', dpi=110, facecolor='white'); plt.close(fig)
    dump(A / 'figures' / 's2_cell3_map.json', dict(item='2-4', runs=[BEFORE, after], rows=int(r3.sum()),
                                                  crs='EPSG:25832; local XY = EPSG:25832 - [690953, 5336071]', scientific_verdict=None))
    print('DONE', flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
