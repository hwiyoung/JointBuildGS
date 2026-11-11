"""Video v5 / spot strips (user decision 2026-11-11): the three B173 places are the thesis figure places, taken as already defined (no new choice):
  1 wing   = stage-1 scene 1 'B173 남쪽 날개' (sections_v1 B173_wing): window of the section length x 8 m around the section line
  2 wall   = stage-1 scene 3 'B173의 가려진 긴 벽' (S1/defs/fig_views_v1.json unseen_face, surf_ext 53; unseen.npz patch centres)
  3 glass  = stage-1 scene 5 'B173 유리 채광창' (sections_v1 B173_sawtooth): same window rule
(places_v1.npz b173_wing__ALS spans the whole old gable roof, 115-164 x 75-150 m, so the stage-1 section geometry is used instead)
Fixed camera for v5: elevation 35, the azimuth (0..315 step 45) that maximises the smallest visible share of the three places
(visible = not behind the 30,000 mesh +0.5 m from that camera, and for the wall facing the camera). CPU, no training."""
import sys
from video_v2 import *
SP = O/'analysis/spots_v5'; SP.mkdir(parents=True, exist_ok=True)
SEC = json.loads(Path('/repo/configs/phd/main_stage1_v1/sections_v1.json').read_text())['sections']

def places(S):
    t = loadz(FT/'targets'/f'{STEM}.npz', ['centre', 'normal', 'prior_height_m', 'mvs_mean_m', 'target']); 
    def pts(idx): c, n = t['centre'][idx], t['normal'][idx]; pr = c+n*t['prior_height_m'][idx][:, None]; mv = c+n*np.nan_to_num(t['mvs_mean_m'][idx])[:, None]; return np.r_[pr, mv[np.isfinite(t['mvs_mean_m'][idx])]], n
    out = {}; tc = t['centre']; HALF_W = 4.0
    for key, sec in [('wing', 'B173_wing'), ('glass', 'B173_sawtooth')]:
        s = SEC[sec]; c = np.array(s['centre'][:2]); tt = np.array(s['t'], float); tt /= np.linalg.norm(tt); nn = np.array([-tt[1], tt[0]])
        win = (np.abs((tc[:, :2]-c)@tt) <= s['L']/2) & (np.abs((tc[:, :2]-c)@nn) <= HALF_W); idx = np.flatnonzero(win); P, n = pts(idx)
        out[key] = dict(patches=idx, points=P, normal=n, section=dict(centre=s['centre'], t=s['t'], L=s['L'], half_width_m=s['half_width_m'], window_half_width_m=HALF_W),
                        section_centre_xy=s['centre'][:2], source=f'sections_v1 {sec}: window L x 2*{HALF_W} m around the section line; FT target patches whose centre is inside')
    uf = json.loads((S1/'defs/fig_views_v1.json').read_text())['sites'][SITE]['unseen_face']; u = loadz(S1/'defs'/SITE/'unseen.npz', ['centre', 'normal', 'surf_ext']); w = u['surf_ext'] == uf['surf_ext']
    out['wall'] = dict(patches=np.flatnonzero(w), points=u['centre'][w].astype(float), normal=u['normal'][w].astype(float), face=uf, centroid_xy=u['centre'][w][:, :2].mean(0).tolist(), source='S1/defs/fig_views_v1.json unseen_face; unseen.npz surf_ext 53')
    for k in out:
        f = np.isfinite(out[k]['points']).all(1); out[k]['n_nonfinite_dropped'] = int((~f).sum()); out[k]['points'] = out[k]['points'][f]
        if len(out[k]['normal']) == len(f): out[k]['normal'] = out[k]['normal'][f]
        out[k]['centroid_xy'] = out[k]['points'][:, :2].mean(0).tolist()
    return out

def main():
    S = Ctx(); P = places(S); vis = {}
    for az in range(0, 360, 45):
        B = S.view(az); _, dep = S.raster(S.m30, B, 700); out = -B[2]; row = {}
        for k, p in P.items():
            v, _, _ = S.visible(p['points'], B, dep, .5)
            if k == 'wall': v &= (p['normal']@out) > .1
            row[k] = float(v.mean())
        vis[az] = row; print('AZ', az, row, flush=True)
    best = max(vis, key=lambda a: (min(vis[a].values()), -abs(((a-180+180) % 360)-180)))
    for k, p in P.items(): savez(SP/f'{k}.npz', patches=p['patches'], points=p['points'])
    dump(SP/'spots_v5.json', dict(at=now(), places={k: dict(source=p['source'], n_points=len(p['points']), n_nonfinite_dropped=p['n_nonfinite_dropped'], centroid_xy=p['centroid_xy'], section_centre_xy=p.get('section_centre_xy'),
         section=p.get('section'), face=p.get('face')) for k, p in P.items()}, visible_share_by_azimuth=vis, chosen_azimuth=best, elevation=35,
         rule='azimuth with the largest smallest-visible-share over the three places; ties -> nearest to 180 (the earlier videos)', scientific_verdict=None))
    print('BEST', best, vis[best], flush=True)

if __name__ == '__main__': main()
