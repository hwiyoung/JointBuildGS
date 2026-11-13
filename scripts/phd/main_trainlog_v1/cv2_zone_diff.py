"""Concept video v2 side check (2026-11-13, user: 'is the changed roof the only thing B173 can show? a wall instead?'). Read-only; writes docs
figures_concept_v2/zone1_find/zone_diff.json and zone_diff_map.png only.
Unit = GTJUDGE GT rows of B173 x ALS (rows.npz: xyz, row_tau_m, prior_distance_m / prior_presence, mvs_distance_m / mvs_presence, wall).
Row situation: prior right = present and distance <= TAU; prior wrong = absent or distance > 0.5 m; likewise for the image depth (MVS); else 'mid'.
Completeness of the 30,000 meshes per row = |row_s| <= row_tau_m (normal_line.values), this method (tl_30000), judgment off (cmp_nojudge_30000_v203),
image-only 2DGS (cmp_2dgs_30000_v203); all 203-view rule.
  table: completeness by roof/wall x prior state x image state;
  map: 4 m xy cells with >= 150 rows, ours - judgment off (and ours - 2DGS), the top cells each way with their row situation mix.
No pass criteria. scientific_verdict: null"""
from cv2_frames import *
from shapely.geometry import shape
import importlib.util
OUTD = FIGD/'zone1_find'

def main():
    t0 = time.monotonic(); S = Static(); c = cfg(); sj = json.loads((V2/'static.json').read_text())
    spec = importlib.util.spec_from_file_location('nl', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'row_tau_m', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence', 'wall'])
    X = row['xyz'].astype(float); tau = row['row_tau_m']; wall = row['wall'].astype(bool)
    def state(pres, d):
        pres = pres.astype(bool); d = np.where(pres, d, np.inf); return np.where(pres & (d <= TAU), 'right', np.where(~pres | (d > .5), 'wrong', 'mid'))
    ps = state(row['prior_presence'], row['prior_distance_m']); ms = state(row['mvs_presence'], row['mvs_distance_m'])
    fams = dict(ours=(O/'gtj/scenes'/STEM/'distances', 'tl_30000'), nojudge=(V2/'gtj/scenes'/STEM/'distances', 'cmp_nojudge_30000_v203'), img2dgs=(V2/'gtj/scenes'/STEM/'distances', 'cmp_2dgs_30000_v203'))
    rs = {k: loadz(r/f'{f}.npz', ['row_s'])['row_s'] for k, (r, f) in fams.items()}
    comp = lambda m: {k: (round(float(nl.values(v[m], tau[m])['within_pct']), 1) if m.any() else None) for k, v in rs.items()}
    rec = dict(at=now(), rule=__doc__, scientific_verdict=None, rows=int(len(X)), overall=comp(np.ones(len(X), bool)), table=[])
    for kind, km in (('roof', ~wall), ('wall', wall)):
        rec['table'].append(dict(kind=kind, prior='all', image='all', n=int(km.sum()), completeness_pct=comp(km)))
        for p in ('right', 'mid', 'wrong'):
            for q in ('right', 'mid', 'wrong'):
                m = km & (ps == p) & (ms == q)
                if m.sum() >= 200: rec['table'].append(dict(kind=kind, prior=p, image=q, n=int(m.sum()), completeness_pct=comp(m)))
    for r in rec['table']: print('TAB', json.dumps(r, ensure_ascii=False), flush=True)
    # cells
    ij = np.floor(X[:, :2]/4).astype(int); keys, inv = np.unique(ij, axis=0, return_inverse=True); inv = inv.ravel(); cells = []
    for ci in range(len(keys)):
        m = inv == ci
        if m.sum() < 150: continue
        cc = comp(m); mix = {f'{p}/{q}': int((m & (ps == p) & (ms == q)).sum()) for p in ('right', 'wrong') for q in ('right', 'wrong')}
        cells.append(dict(cell=keys[ci].tolist(), centre_xy=((keys[ci]+.5)*4).tolist(), n=int(m.sum()), wall_share_pct=round(float(100*wall[m].mean()), 1), height_median_m=round(float(np.median(X[m, 2]-S.ground)), 2),
                          completeness_pct=cc, ours_minus_nojudge=round(cc['ours']-cc['nojudge'], 1), ours_minus_2dgs=round(cc['ours']-cc['img2dgs'], 1), prior_image_mix=mix))
    cells.sort(key=lambda d: -d['ours_minus_nojudge']); rec['cells'] = cells
    rec['top_ours_over_nojudge'] = cells[:8]; rec['top_nojudge_over_ours'] = cells[-5:][::-1]
    for d in rec['top_ours_over_nojudge']: print('TOP+', json.dumps(d, ensure_ascii=False), flush=True)
    for d in rec['top_nojudge_over_ours']: print('TOP-', json.dumps(d, ensure_ascii=False), flush=True)
    # map
    fig, axs = plt.subplots(1, 2, figsize=(14, 8), dpi=100); fp = shape(c['scope']['footprint'])
    for ax, key, title in ((axs[0], 'ours_minus_nojudge', '본 방법 − 판단 끔 (완전성 %p, 30,000회)'), (axs[1], 'ours_minus_2dgs', '본 방법 − 사진만 쓴 2DGS (완전성 %p)')):
        for d in cells:
            v = d[key]; col = plt.get_cmap('RdBu')(.5+np.clip(v, -30, 30)/60); x0, y0 = d['cell'][0]*4, d['cell'][1]*4
            ax.add_patch(plt.Rectangle((x0, y0), 4, 4, color=col, lw=0))
        x, y = fp.exterior.xy; ax.plot(x, y, color=NAVY, lw=1)
        for k in (1, 2):
            b = np.asarray(sj['zones'][str(k)]['box_polygon_xy']); ax.plot(np.r_[b[:, 0], b[:1, 0]], np.r_[b[:, 1], b[:1, 1]], color='k', lw=1.2, ls='--'); ax.text(b[:, 0].mean(), b[:, 1].mean(), str(k), fontsize=12, ha='center', va='center', fontweight='bold')
        ax.set_aspect('equal'); ax.set_title(title, fontsize=11); ax.set_xlabel('x m (동 →)'); ax.set_ylabel('y m (북 →)')
    sm = plt.cm.ScalarMappable(cmap='RdBu', norm=plt.Normalize(-30, 30)); fig.colorbar(sm, ax=axs, shrink=.6, label='%p (파랑 = 본 방법이 높음)')
    OUTD.mkdir(parents=True, exist_ok=True); fig.savefig(OUTD/'zone_diff_map.png', bbox_inches='tight', facecolor='white'); plt.close(fig)
    rec['seconds'] = round(time.monotonic()-t0, 1); dump(OUTD/'zone_diff.json', rec); print('DONE', rec['overall'], rec['seconds'], flush=True)

if __name__ == '__main__': main()
