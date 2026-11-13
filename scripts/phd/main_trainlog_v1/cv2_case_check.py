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

if __name__ == '__main__': main()
