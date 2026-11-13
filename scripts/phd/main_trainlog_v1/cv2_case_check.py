"""Concept video, another case (TL_CASE=B0_b10__LoD2, 2026-11-13): two read-only checks after the first cut, written to /docs/case_check_v1.json.
Measures outside the fixed numbers table (purpose stated, no pass line); rules of training, judgment, targets, meshes and scores unchanged.
  (a) zone target pixels of the video camera: the numbers-table column 'target within 10 cm' counts pixels of this camera whose target 3-D point is inside
      the zone box. Here: render depth - target depth (along the pixel ray, x rn as numbers()) for ours 7,000/30,000 and 2DGS 30,000.
      Purpose: zone 2 gave 0.0 % for every state; check whether the zone-2 wall is seen by this camera at all.
  (b) completeness (normal_line.values, row_tau_m, as the table) on subsets of GTJUDGE rows:
      story rows = wall rows with the prior right (<= TAU) and image depth absent or > 0.5 m off (the cv2_case_zones.py zone-1 rule), inside zone 1;
      cluster A = the dense part of those rows (4 m cells with >= 200 rows, cv2_site_look.py); wall / non-wall rows per zone; zone wall rows by height above
      ground (scope ground_z). Families: ours (tl_n), 2DGS 7,000/30,000 (case meshes) and GTJUDGE FINALTRAIN_30000 (the original run), baseline_30000
      (RESCORE judgment-off, other settings), mvs (image-depth mesh), prior (the LoD2 surface).
      Purpose: the zone box mixes the story rows with wall parts the photos see; report the story rows apart.
GT used only to score. scientific_verdict: null"""
from common import *
import cv2_frames as F
import importlib.util
assert TL_CASE == 'B0_b10__LoD2', TL_CASE
TAU = 0.211856
spec = importlib.util.spec_from_file_location('gtj_normal_line', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)

def main():
    import time; t0 = time.monotonic(); S = F.Static(); st = loadz(F.STN); td = loadz(O/'concept/inputs.npz', ['target_depth'])['target_depth'].astype(float); out = dict(at=now(), rule=__doc__, camera=F.CAM, camera_file=F.CAM_FILE)
    rend = {'ours_7000': O/'gtj/renders'/f'{STEM}__tl_7000'/F.CAM_FILE, 'ours_30000': O/'gtj/renders'/f'{STEM}__tl_30000'/F.CAM_FILE, '2dgs_30000': F.V2/'gtj/renders'/f'{STEM}__cmp_2dgs_30000'/F.CAM_FILE}
    out['a_target_pixels'] = {}
    for k in (1, 2):
        m = st[f'zmask{k}']; rec = dict(pixels=int(m.sum()))
        for lab, p in rend.items():
            rd = loadz(p, ['depth'])['depth'].astype(float); ok = m & (rd > 0); d = ((rd-td)*st['rn'])[ok]
            rec[lab] = dict(n=int(ok.sum()), median_render_minus_target_m=float(np.median(d)), within_10cm_pct=float(100*np.mean(np.abs(d) <= .1)),
                            render_in_front_pct=float(100*np.mean(d < -.1)), render_behind_pct=float(100*np.mean(d > .1)))
        out['a_target_pixels'][str(k)] = rec
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'row_tau_m', 'wall', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence'])
    X = row['xyz'].astype(float); W = row['wall'].astype(bool); tau = row['row_tau_m']; ground = float(cfg()['scope']['ground_z']); h = X[:, 2]-ground
    pr = row['prior_presence'].astype(bool) & (row['prior_distance_m'] <= TAU); mp = row['mvs_presence'].astype(bool); absent = ~mp; wrong = mp & (row['mvs_distance_m'] > .5)
    story = W & pr & (absent | wrong); ci = np.flatnonzero(story); ij = np.floor(X[ci, :2]/4).astype(int); _, inv, cnt = np.unique(ij, axis=0, return_inverse=True, return_counts=True)
    A = np.zeros(len(X), bool); A[ci[cnt[inv.ravel()] >= 200]] = True
    fams = {**{f'ours_{n}': O/'gtj/scenes'/STEM/'distances'/f'tl_{n}.npz' for n in F.FRAMES if n != 'input'},
            '2dgs_7000': F.V2/'gtj/scenes'/STEM/'distances'/'cmp_2dgs_7000.npz', '2dgs_30000': F.V2/'gtj/scenes'/STEM/'distances'/'cmp_2dgs_30000.npz',
            **{f'gtjudge_{n}': GT/'scenes'/STEM/'distances'/f'{n}.npz' for n in ['FINALTRAIN_30000', 'baseline_30000', 'mvs', 'prior']}}
    Dz = {lab: loadz(p, ['row_s'])['row_s'] for lab, p in fams.items()}
    def pct(m): return dict(n=int(m.sum()), **{lab: round(float(nl.values(Dz[lab][m], tau[m])['within_pct']), 1) for lab in Dz})
    z = {k: F.in_zone(X, S.zones[k], S.zr) for k in (1, 2)}
    b = dict(ground_z=ground, story_rows_zone1=dict(rows=int((z[1] & story).sum()), image_depth_absent=int((z[1] & W & pr & absent).sum()), image_depth_wrong=int((z[1] & W & pr & wrong).sum()),
             height_above_ground_q10_q50_q90=np.quantile(h[z[1] & story], [.1, .5, .9]).round(2).tolist()))
    b['zone1_story_rows'] = pct(z[1] & story); b['zone1_wall_not_story'] = pct(z[1] & W & ~story); b['cluster_A'] = pct(A)
    for k in (1, 2):
        b[f'zone{k}_wall'] = pct(z[k] & W); b[f'zone{k}_non_wall'] = pct(z[k] & ~W)
        b[f'zone{k}_wall_by_height'] = {f'{lo}-{hi} m': pct(z[k] & W & (h >= lo) & (h < hi)) for lo, hi in [(0, 5), (5, 10), (10, 15), (15, 25)]}
    out['b_completeness'] = b; out['seconds'] = round(time.monotonic()-t0, 1); out['scientific_verdict'] = None
    dump(D/'case_check_v1.json', out); print('CHECK', json.dumps(out['a_target_pixels'], ensure_ascii=False)[:800], json.dumps(b['zone1_story_rows'])[:600], flush=True)

def targets():
    """(c) 'targets' (2026-11-13, user '둘 다 진행' = the handoff to the analysis session): writes /docs/case_check_targets_v1.json (case_check_v1.json untouched).
    Same rows as (b). Each row takes the nearest FINALTRAIN target patch (FT/targets/<stem>.npz, valid patches, centre within 0.5 m; the cv2_zone_why.py rule);
    target offset = (target - row xyz) . row normal (GTJUDGE row normal as stored); target right = |offset| <= row_tau_m. Per zone, wall rows by height and the
    zone-1 story rows: judgment share of the nearest patch (agree 0 / correct 2 / keep 1 / missing 4 / no patch), target right %, and the completeness of
    ours at 7,000 and 30,000 per judgment. Purpose: split 'target already wrong' from 'worse during training' as the B173 zone-1 handoff did; no pass line."""
    import time; from scipy.spatial import cKDTree; t0 = time.monotonic(); S = F.Static()
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'normal', 'row_tau_m', 'wall', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence'])
    X = row['xyz'].astype(float); Nr = row['normal'].astype(float); W = row['wall'].astype(bool); tau = row['row_tau_m']; ground = float(cfg()['scope']['ground_z']); h = X[:, 2]-ground
    pr = row['prior_presence'].astype(bool) & (row['prior_distance_m'] <= TAU); mp = row['mvs_presence'].astype(bool); story = W & pr & (~mp | (mp & (row['mvs_distance_m'] > .5)))
    tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'sigma', 'judge_region', 'region', 'centre'])
    valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0) & np.isin(tg['judge_region'], [0, 1, 2, 4])
    iv = np.flatnonzero(valid); dd, kk = cKDTree(tg['centre'][iv]).query(X, k=1, distance_upper_bound=.5); hit = np.isfinite(dd)
    pi = np.full(len(X), -1); pi[hit] = iv[kk[hit]]; jr = np.full(len(X), -1); jr[hit] = tg['judge_region'][pi[hit]]
    toff = np.full(len(X), np.nan); toff[hit] = np.einsum('ij,ij->i', tg['target'][pi[hit]]-X[hit], Nr[hit]); tright = hit & (np.abs(np.nan_to_num(toff, nan=9.)) <= tau)
    ours = {n: loadz(O/'gtj/scenes'/STEM/'distances'/f'tl_{n}.npz', ['row_s'])['row_s'] for n in ('7000', '30000')}
    JN = {0: 'agree', 2: 'correct', 1: 'keep', 4: 'missing', -1: 'no_patch'}
    def block(m):
        r = dict(rows=int(m.sum()), target_right_pct=round(float(100*tright[m].mean()), 1) if m.any() else None, by_judgment={})
        for j, name in JN.items():
            mj = m & (jr == j)
            if not mj.any(): continue
            off = np.abs(toff[mj & hit & ~tright])
            r['by_judgment'][name] = dict(rows=int(mj.sum()), share_pct=round(float(100*mj.sum()/m.sum()), 1), target_right_pct=round(float(100*tright[mj].mean()), 1) if j >= 0 else None,
                                          target_wrong_median_abs_m=round(float(np.median(off)), 2) if len(off) else None,
                                          **{f'ours_{n}': round(float(nl.values(ours[n][mj], tau[mj])['within_pct']), 1) for n in ours})
        return r
    z = {k: F.in_zone(X, S.zones[k], S.zr) for k in (1, 2)}; out = dict(at=now(), rule=targets.__doc__, ground_z=ground, targets=str(FT/'targets'/f'{STEM}.npz'))
    out['zone1_story_rows'] = block(z[1] & story)
    for k in (1, 2): out[f'zone{k}_wall_by_height'] = {f'{lo}-{hi} m': block(z[k] & W & (h >= lo) & (h < hi)) for lo, hi in [(0, 5), (5, 10), (10, 15), (15, 25)]}
    out['seconds'] = round(time.monotonic()-t0, 1); out['scientific_verdict'] = None; dump(D/'case_check_targets_v1.json', out)
    print('TARGETS', json.dumps(out['zone1_story_rows'], ensure_ascii=False)[:700], flush=True)

def v3check():
    """(d) 'v3' (2026-11-13, user '진행하자' = zone 2 slid off the inner corner): writes /docs/case_check_v3.json (earlier files untouched). No pass line.
    Row kinds in a zone box (GTJUDGE wall flag and row normal against the zone wall's outward normal): chosen wall (|n.out| > .9), perpendicular wall
    (|n.along| > .9, along = up x out), other wall, non-wall. Zones: zone 1 (unchanged), zone 2 v1 (case_zones.json) and zone 2 v3 (case_zones_v3.json).
    Per zone: kind counts; chosen-wall rows by height (0-5, 5-10, 10-15, 15-25 m): target right % (nearest FINALTRAIN patch, cv2_zone_why rule) and
    completeness of ours 7,000 / 10,000 / 15,000 / 30,000, the original run (GTJUDGE FINALTRAIN_30000), image-only 2DGS 30,000, the image-depth mesh, LoD2.
    Corner table: the zone-2 v1 wall rows below 10 m within 1 m of the wall plane by distance from the inner corner (corner = along -1.1 m from the v1 foot).
    Purpose: the v1 zone-2 numbers mixed the corner wall in; this keeps the corrected numbers (the correction note and the v3 report) reproducible."""
    import time; from scipy.spatial import cKDTree; from shapely.geometry import Polygon; t0 = time.monotonic(); c = cfg(); S = F.Static()
    up = np.asarray(c['coordinates']['up'], float); up /= np.linalg.norm(up); g = float(c['scope']['ground_z'])
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'normal', 'wall', 'row_tau_m']); X = row['xyz'].astype(float); N = row['normal'].astype(float); W = row['wall'].astype(bool); tau = row['row_tau_m']; h = X[:, 2]-g
    tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'sigma', 'judge_region', 'region', 'centre'])
    valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0) & np.isin(tg['judge_region'], [0, 1, 2, 4])
    iv = np.flatnonzero(valid); dd, kk = cKDTree(tg['centre'][iv]).query(X, k=1, distance_upper_bound=.5); hit = np.isfinite(dd); pi = np.full(len(X), -1); pi[hit] = iv[kk[hit]]
    toff = np.full(len(X), np.nan); toff[hit] = np.einsum('ij,ij->i', tg['target'][pi[hit]]-X[hit], N[hit]); tright = hit & (np.abs(np.nan_to_num(toff, nan=9.)) <= tau)
    fams = {**{f'ours_{n}': O/'gtj/scenes'/STEM/'distances'/f'tl_{n}.npz' for n in ('7000', '10000', '15000', '30000')}, 'original_30000': GT/'scenes'/STEM/'distances/FINALTRAIN_30000.npz',
            '2dgs_30000': F.V2/'gtj/scenes'/STEM/'distances/cmp_2dgs_30000.npz', 'image_depth_mesh': GT/'scenes'/STEM/'distances/mvs.npz', 'lod2': GT/'scenes'/STEM/'distances/prior.npz'}
    Dz = {k: loadz(p, ['row_s'])['row_s'] for k, p in fams.items()}
    def comp(m): return dict(rows=int(m.sum()), target_right_pct=round(float(100*tright[m].mean()), 1) if m.any() else None, **{k: round(float(nl.values(v[m], tau[m])['within_pct']), 1) if m.sum() >= 20 else None for k, v in Dz.items()})
    v1 = json.loads((O/'concept_v2'/'case_zones.json').read_text())['zones']; v3 = json.loads((O/'concept_v2'/'case_zones_v3.json').read_text())['zones']
    out = dict(at=now(), rule=v3check.__doc__, ground_z=g, zones={}, scientific_verdict=None)
    for name, z in (('zone1', v1['1']), ('zone2_v1', v1['2']), ('zone2_v3', v3['2'])):
        o = np.r_[z['wall_normal_out_xy'], 0.]; al = np.cross(up, o); al /= np.linalg.norm(al); zz = dict(poly=Polygon(z['box_polygon_xy']))
        rin = F.in_zone(X, zz, S.zr); fac = W & (np.abs(N@o) > .9); per = W & (np.abs(N@al) > .9)
        r = dict(kinds=dict(chosen_wall=int((rin & fac).sum()), perpendicular_wall=int((rin & per).sum()), other_wall=int((rin & W & ~fac & ~per).sum()), non_wall=int((rin & ~W).sum())),
                 chosen_wall_all=comp(rin & fac), chosen_wall_below_10m=comp(rin & fac & (h < 10)),
                 chosen_wall_by_height={f'{lo}-{hi} m': comp(rin & fac & (h >= lo) & (h < hi)) for lo, hi in [(0, 5), (5, 10), (10, 15), (15, 25)]})
        if name == 'zone2_v1':
            rel = X-np.r_[z['wall_foot_xy'], g]; xa, yo = rel@al, rel@o; m0 = fac & (np.abs(yo) < 1.) & (h < 10)
            r['corner_distance_below_10m'] = {f'{lo}-{hi} m': comp(m0 & (xa+1.1 >= lo) & (xa+1.1 < hi)) for lo, hi in [(0, 2), (2, 4), (4, 6), (6, 8)]}
        out['zones'][name] = r
    out['seconds'] = round(time.monotonic()-t0, 1); dump(D/'case_check_v3.json', out)
    print('V3CHECK', json.dumps({k: (v['kinds'], v['chosen_wall_below_10m']) for k, v in out['zones'].items()}, ensure_ascii=False)[:1500], flush=True)

if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['targets']: targets()
    elif sys.argv[1:] == ['v3']: v3check()
    else: main()
