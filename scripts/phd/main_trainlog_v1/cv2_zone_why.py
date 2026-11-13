"""Concept video v2 r6 side record (2026-11-13, user: 'is the changed roof all B173 can show?', 'why is zone 1 below the ALS surface?'). Read-only; writes
docs figures_concept_v2/zone1_find/zone_why.json only.
Unit = GTJUDGE GT rows of B173 x ALS (rows.npz) inside the r5 zones (static.json: band |offset| <= 0.5 m along the line, box) and inside the B173 scope
(footprint, z range). Completeness = |row_s| <= row_tau_m (normal_line.values). Families: this method tl_<n> (203 views, every saved iteration), image-only
2DGS cmp_2dgs_7000 / cmp_2dgs_30000_v203, judgment off (stage-3 r15 fork) cmp_nojudge_30000_v203, and the GTJUDGE distances of the image-depth mesh (mvs),
the ALS prior surface (prior) and GeoGS_30000.
Row situation: prior right (<= TAU) / mid / far (> 0.5 m) / absent; image depth (MVS) right / mid / wrong (> 0.5 m or absent).
Zone-1 band per judgment: each row takes the nearest FINALTRAIN target patch (centre within 0.5 m); target offset = (target - row xyz) . row normal (up +);
this method's completeness per saved iteration and the share below -tau / above +tau.
GT is used only to classify rows and to score. No pass criteria. scientific_verdict: null"""
from cv2_frames import *
from scipy.spatial import cKDTree
from shapely.geometry import shape
import importlib.util
OUTD = FIGD/'zone1_find'

def main():
    t0 = time.monotonic(); S = Static(); sj = json.loads((V2/'static.json').read_text()); c = cfg()
    spec = importlib.util.spec_from_file_location('nl', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'normal', 'row_tau_m', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence'])
    X = row['xyz'].astype(float); Nr = row['normal'].astype(float); Nr *= np.where(Nr[:, 2:3] < 0, -1, 1); tau = row['row_tau_m']
    zok = (X[:, 2] >= S.zr[0]) & (X[:, 2] <= S.zr[1]); scope = zok & shapely.contains_xy(shape(c['scope']['footprint']), X[:, 0], X[:, 1])
    pp = row['prior_presence'].astype(bool); pd_ = row['prior_distance_m']; mp = row['mvs_presence'].astype(bool); md = row['mvs_distance_m']
    P = np.where(~pp, 'absent', np.where(pd_ <= TAU, 'right', np.where(pd_ > .5, 'far', 'mid'))); M = np.where(mp & (md <= TAU), 'right', np.where(~mp | (md > .5), 'wrong', 'mid'))
    dist = O/'gtj/scenes'/STEM/'distances'; cd = V2/'gtj/scenes'/STEM/'distances'; gd = GT/'scenes'/STEM/'distances'
    its = sorted(int(f[3:-4]) for f in os.listdir(dist) if f.startswith('tl_') and f.endswith('.npz') and f[3:-4].isdigit())
    fam = {'ours_30000': dist/'tl_30000.npz', '2dgs_7000': cd/'cmp_2dgs_7000.npz', '2dgs_30000': cd/'cmp_2dgs_30000_v203.npz', 'nojudge_r15_30000': cd/'cmp_nojudge_30000_v203.npz',
           'image_depth_mesh': gd/'mvs.npz', 'prior_surface': gd/'prior.npz', 'GeoGS_30000': gd/'GeoGS_30000.npz'}
    rs = {k: loadz(p, ['row_s'])['row_s'] for k, p in fam.items()}; ours = {n: loadz(dist/f'tl_{n}.npz', ['row_s'])['row_s'] for n in its}
    comp = lambda a, m: round(float(nl.values(a[m], tau[m])['within_pct']), 1) if m.any() else None
    def side(a, m):
        f = np.isfinite(a[m]); s = np.nan_to_num(a[m]); return dict(within_pct=comp(a, m), below_pct=round(float(100*np.mean(f & (s < -tau[m]))), 1), above_pct=round(float(100*np.mean(f & (s > tau[m]))), 1))
    rec = dict(at=now(), rule=__doc__, scientific_verdict=None, families={k: str(p) for k, p in fam.items()}, iterations=its)
    rec['scope'] = dict(rows=int(scope.sum()), completeness_pct={k: comp(a, scope) for k, a in rs.items()},
                        situation=[dict(prior=a, image=b, rows=int(m.sum()), completeness_pct={k: comp(v, m) for k, v in rs.items()})
                                   for a in ('right', 'mid', 'far', 'absent') for b in ('right', 'mid', 'wrong') for m in [scope & (P == a) & (M == b)] if m.sum() >= 100])
    # nearest target patch
    tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'sigma', 'judge_region', 'region', 'centre'])
    valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0) & np.isin(tg['judge_region'], [0, 1, 2, 4])
    iv = np.flatnonzero(valid); dd, kk = cKDTree(tg['centre'][iv]).query(X, k=1, distance_upper_bound=.5); hit = np.isfinite(dd)
    pi = np.full(len(X), -1); pi[hit] = iv[kk[hit]]; jr = np.full(len(X), -1); jr[hit] = tg['judge_region'][pi[hit]]
    toff = np.full(len(X), np.nan); toff[hit] = np.einsum('ij,ij->i', tg['target'][pi[hit]]-X[hit], Nr[hit])
    rec['zones'] = {}
    for k in (1, 2):
        z = sj['zones'][str(k)]; o, t, n = line_frame(z['line_origin_xy'], z['line_unit_xy']); L = float(z['line_length_m']); q = X[:, :2]-o; s, v = q@t, q@n
        band = zok & (np.abs(v) <= BAND) & (s >= 0) & (s <= L); box = zok & shapely.contains_xy(shapely.Polygon(z['box_polygon_xy']), X[:, 0], X[:, 1]); zr = {}
        for nm, m in (('band', band), ('box', box)):
            zr[nm] = dict(rows=int(m.sum()), completeness_pct={kk_: comp(a, m) for kk_, a in rs.items()},
                          situation={f'{a}/{b}': int((m & (P == a) & (M == b)).sum()) for a in ('right', 'mid', 'far', 'absent') for b in ('right', 'mid', 'wrong') if (m & (P == a) & (M == b)).any()})
        if k == 1:
            f = np.isfinite(toff[band]); tt = toff[band]; ta = tau[band]
            zr['band_target'] = dict(within_pct=round(float(100*np.mean(f & (np.abs(np.nan_to_num(tt, nan=9)) <= ta))), 1), above_pct=round(float(100*np.mean(f & (np.nan_to_num(tt) > ta))), 1),
                                     below_pct=round(float(100*np.mean(f & (np.nan_to_num(tt) < -ta))), 1), no_patch_pct=round(float(100*np.mean(~f)), 1))
            zr['band_ours_by_iteration'] = {str(nn): side(a, band) for nn, a in ours.items()}
            zr['band_by_judgment'] = {}
            for j, name in ((0, '일치'), (1, '보존'), (2, '보정'), (4, '결측'), (-1, 'none')):
                m = band & (jr == j)
                if not m.any(): continue
                up = m & (toff > tau)
                zr['band_by_judgment'][name] = dict(rows=int(m.sum()), target_within_pct=round(float(100*np.mean(np.abs(np.nan_to_num(toff[m], nan=9)) <= tau[m])), 1),
                                                     target_above_rows=int(up.sum()), target_above_median_m=round(float(np.median(toff[up])), 2) if up.any() else None,
                                                     ours_by_iteration={str(nn): side(a, m) for nn, a in ours.items()},
                                                     image_depth_mesh_pct=comp(rs['image_depth_mesh'], m), prior_surface_pct=comp(rs['prior_surface'], m), twodgs_30000_pct=comp(rs['2dgs_30000'], m))
        rec['zones'][str(k)] = zr; print('ZONE', k, json.dumps({kk_: zr[kk_] for kk_ in ('band', 'box')}, ensure_ascii=False), flush=True)
    print('BAND1_JUDGMENT', json.dumps({k: {kk_: v[kk_] for kk_ in ('rows', 'target_within_pct', 'target_above_rows', 'target_above_median_m')} for k, v in rec['zones']['1']['band_by_judgment'].items()}, ensure_ascii=False), flush=True)
    print('BAND1_ITER', json.dumps(rec['zones']['1']['band_ours_by_iteration']), flush=True)
    rec['seconds'] = round(time.monotonic()-t0, 1); OUTD.mkdir(parents=True, exist_ok=True); dump(OUTD/'zone_why.json', rec); print('DONE', rec['seconds'], flush=True)

if __name__ == '__main__': main()
