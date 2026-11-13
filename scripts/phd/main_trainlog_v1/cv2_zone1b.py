"""Concept video v2 test of a moved zone 1 (2026-11-13, user: '시험 장면 만들어' = move zone 1 to the skylight cells where judgment makes the largest
difference, one test scene first). Read-only selection; writes concept_v2/zone1b_line.json and docs figures_concept_v2/zone1_find/zone1b_select.json only.
Kept from the r5 zone 1: direction = the B173_sawtooth axis (the skylight long axis, static.json zones.1 line_unit_xy), line length 12 m, band |offset| <= 0.5 m,
box = line x +-4 m, comparison = judgment off (cmp_nojudge_30000_v203).
Moved: the line origin. Candidates = r5 origin + a t + b n, a in -4..12 m (0.5 m steps), b in -6..6 m (0.25 m steps). For each candidate, the GTJUDGE GT rows
(rows.npz) in its band (|v| <= 0.5, 0 <= s <= L, z within the scope z range) score the 30,000 meshes by completeness (|row_s| <= row_tau_m, normal_line.values):
this method (tl_30000), judgment off, image-only 2DGS (both 203 views). Chosen = the largest band difference this method - judgment off among candidates with
>= MIN_ROWS band rows. This is a choice BY SCORE (the place where the judgment shows the most, not a representative place); the record keeps the r5 zone 1
values and the top candidates. Also recorded for the chosen band and box: row situation mix (prior / image depth right <= TAU, wrong > 0.5 m or absent, else mid)
and medians of prior and image-depth distance, and the box pixels in the camera crop.
No pass criteria. scientific_verdict: null"""
from cv2_frames import *
from shapely.geometry import Polygon
import importlib.util
MIN_ROWS = 400; OUTD = FIGD/'zone1_find'; LINE = V2/'zone1b_line.json'

def main():
    t0 = time.monotonic(); S = Static(); sj = json.loads((V2/'static.json').read_text()); z1 = sj['zones']['1']
    spec = importlib.util.spec_from_file_location('nl', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'row_tau_m', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence'])
    X = row['xyz'].astype(float); tau = row['row_tau_m']; zok = (X[:, 2] >= S.zr[0]) & (X[:, 2] <= S.zr[1])
    fams = dict(ours=(O/'gtj/scenes'/STEM/'distances', 'tl_30000'), nojudge=(V2/'gtj/scenes'/STEM/'distances', 'cmp_nojudge_30000_v203'), img2dgs=(V2/'gtj/scenes'/STEM/'distances', 'cmp_2dgs_30000_v203'))
    rs = {k: loadz(r/f'{f}.npz', ['row_s'])['row_s'] for k, (r, f) in fams.items()}
    comp = lambda m: {k: (round(float(nl.values(v[m], tau[m])['within_pct']), 1) if m.any() else None) for k, v in rs.items()}
    def state(pres, d):
        pres = pres.astype(bool); d = np.where(pres, d, np.inf); return np.where(pres & (d <= TAU), 'right', np.where(~pres | (d > .5), 'wrong', 'mid'))
    ps = state(row['prior_presence'], row['prior_distance_m']); ms = state(row['mvs_presence'], row['mvs_distance_m'])
    o0, t, n = line_frame(z1['line_origin_xy'], z1['line_unit_xy']); L = float(z1['line_length_m'])
    q = X[:, :2]-o0; s0, v0 = q@t, q@n; cands = []
    for a in np.arange(-4, 12.01, .5):
        for b in np.arange(-6, 6.01, .25):
            m = zok & (np.abs(v0-b) <= BAND) & (s0-a >= 0) & (s0-a <= L)
            if m.sum() < MIN_ROWS: continue
            c = comp(m); cands.append(dict(a=float(a), b=float(b), band_rows=int(m.sum()), band_completeness_pct=c, band_ours_minus_nojudge=round(c['ours']-c['nojudge'], 1)))
    cands.sort(key=lambda d: -d['band_ours_minus_nojudge']); best = cands[0]
    def describe(o):
        q = X[:, :2]-o; s, v = q@t, q@n; band = zok & (np.abs(v) <= BAND) & (s >= 0) & (s <= L); box = zok & (np.abs(v) <= 4) & (s >= 0) & (s <= L)
        poly = Polygon([o+aa*t+bb*n for aa, bb in [(0, -4), (L, -4), (L, 4), (0, 4)]]); ring = np.asarray(poly.exterior.coords)[:-1]
        u, w, _ = S.pix(np.c_[ring, np.full(len(ring), float(np.median(X[box, 2])))]); u0, v0_, u1, v1 = sj['camera']['crop_u0v0u1v1']
        out = dict(line_origin_xy=o.tolist(), line_end_xy=(o+L*t).tolist(), box_polygon_xy=ring.tolist(), box_corners_in_camera_crop=int(((u >= u0) & (u <= u1) & (w >= v0_) & (w <= v1)).sum()))
        for nm, m in (('band', band), ('box', box)):
            cc = comp(m); out[nm] = dict(rows=int(m.sum()), completeness_pct=cc, ours_minus_nojudge=round(cc['ours']-cc['nojudge'], 1), height_median_m=round(float(np.median(X[m, 2]-S.ground)), 2),
                                        situation={f'{p}/{qq}': int((m & (ps == p) & (ms == qq)).sum()) for p in ('right', 'mid', 'wrong') for qq in ('right', 'mid', 'wrong') if (m & (ps == p) & (ms == qq)).any()},
                                        prior_distance_median_m=round(float(np.nanmedian(np.where(row['prior_presence'][m].astype(bool), row['prior_distance_m'][m], np.nan))), 3),
                                        image_distance_median_m=round(float(np.nanmedian(np.where(row['mvs_presence'][m].astype(bool), row['mvs_distance_m'][m], np.nan))), 3))
        return out
    ob = o0+best['a']*t+best['b']*n
    rec = dict(at=now(), rule=__doc__, scientific_verdict=None, min_rows=MIN_ROWS, candidates_n=len(cands), direction_unit_xy=t.tolist(), line_length_m=L,
               r5_zone1=describe(o0), chosen=dict(shift_along_m=best['a'], shift_lateral_m=best['b'], **describe(ob)), top_candidates=cands[:12], worst_candidates=cands[-3:])
    print('R5', json.dumps(rec['r5_zone1'], ensure_ascii=False), flush=True); print('CHOSEN', json.dumps(rec['chosen'], ensure_ascii=False), flush=True)
    for d in cands[:12]: print('TOP', json.dumps(d), flush=True)
    rule = (f'zone 1 test (z1b): the r5 zone-1 line (B173_sawtooth direction, 12 m, box +-4 m) moved by {best["a"]:+.1f} m along and {best["b"]:+.2f} m across to the '
            'band (|offset| <= 0.5 m) where the 30,000 mesh completeness of this method minus judgment off is largest (chosen by score, cv2_zone1b.py)')
    dump(LINE, dict(at=now(), rule=rule, line_origin_xy=ob.tolist(), line_unit_xy=t.tolist(), line_length_m=L, selection=str(OUTD/'zone1b_select.json'), scientific_verdict=None))
    rec['seconds'] = round(time.monotonic()-t0, 1); OUTD.mkdir(parents=True, exist_ok=True); dump(OUTD/'zone1b_select.json', rec); print('DONE', rec['seconds'], flush=True)

if __name__ == '__main__': main()
