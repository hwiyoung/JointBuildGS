"""Concept figure checks (2026-11-12) before writing captions, same camera as concept_prep.py. CPU, no training; GT only for counting.
  1 what the small red squares in row 3 of figure A are: per state, inside CROP_A, the render-minus-target depth split by the target owner
    (owner >= 0 = a prior patch disc of the TARGET map, -1 = MVS background), and for patch pixels whether the target lies on the ALS prior surface
    (the stage-1 prior mesh S1/defs/<site>/prior_ALS.npz ray-cast from the same camera, |target - prior depth| <= 0.3 m) and on the render of 30,000.
  2 what the red (above GT by more than TAU) mesh pixels of figure B are: per method inside CROP_B, the share lying on the ALS prior surface
    (|mesh depth - prior depth| <= 0.3 m) and their height above GT.
scientific_verdict: null"""
from common import *
from concept_mesh import cast
import concept_fig as CF
OUTC = O/'concept'

def main():
    zi = loadz(OUTC/'inputs.npz'); K, W2C, W, H = zi['K'].astype(float), zi['W2C'].astype(float), int(zi['W']), int(zi['H']); tgt = zi['target_depth'].astype(float); tw = zi['target_weight'].astype(float); own = zi['target_owner']
    p = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); ph, pd, _, _ = cast(p['V'].astype(float), p['F'].astype('i8'), K, W2C, W, H); pd = pd.astype(float)
    rec = dict(at=now(), rule=__doc__, prior_hit_pixels=int(ph.sum()), scientific_verdict=None, A={}, B={})
    ca, cb = CF.CROP_A, CF.CROP_B; crop = CF.crop; vt = np.isfinite(tgt) & (tgt > 0) & (tw > 0)
    on_prior = vt & ph & (np.abs(tgt-np.nan_to_num(pd, nan=-1e9)) <= .3)
    for n in CF.STATES:
        dz = loadz(O/'renders'/n/'data.npz', ['train1_depth', 'train1_alpha']); rd = dz['train1_depth'].astype(float); ok = vt & (dz['train1_alpha'].astype(float) > .5) & np.isfinite(rd) & (rd > 0); dd = rd-tgt
        row = {}
        for k, m in [('patch', own >= 0), ('mvs', own < 0)]:
            mm = crop(ok & m, ca); d = crop(dd, ca)[mm]
            row[k] = dict(pixels=int(mm.sum()), median_m=float(np.median(d)) if len(d) else None, within_10cm_pct=float((np.abs(d) <= .1).mean()*100) if len(d) else None,
                          red_gt_0p5m_pct=float((d > .5).mean()*100) if len(d) else None)
        mm = crop(ok & (own >= 0) & (dd > .5), ca); row['patch_red_on_prior_pct'] = float(crop(on_prior, ca)[mm].mean()*100) if mm.any() else None
        row['patch_red_render_vs_prior_m_median'] = float(np.median((rd-pd)[ca[1]:ca[3], ca[0]:ca[2]][mm])) if mm.any() else None
        rec['A'][n] = row; print('A', n, row, flush=True)
    for key in ['imgonly_2dgs', 'geogs_als', 'ours_30000']:
        mz = loadz(OUTC/f'mesh_{key}.npz'); e = mz['error_m'].astype(float); hit = mz['hit']; md = mz['depth'].astype(float)
        red = crop(hit & np.isfinite(e) & (e > CF.TAU), cb); onp = crop(hit & ph & (np.abs(md-np.nan_to_num(pd, nan=-1e9)) <= .3), cb); ee = crop(e, cb)[red]
        rec['B'][key] = dict(mesh_pixels=int(crop(hit, cb).sum()), red_pixels=int(red.sum()), red_pct_of_mesh=float(red.sum()/max(crop(hit, cb).sum(), 1)*100),
                             red_on_prior_pct=float(onp[red].mean()*100) if red.any() else None, red_height_above_gt_m_p50_p90=[float(np.percentile(ee, 50)), float(np.percentile(ee, 90))] if red.any() else None,
                             all_on_prior_pct=float(onp[crop(hit, cb)].mean()*100))
        print('B', key, rec['B'][key], flush=True)
    dump(OUTC/'concept_check.json', rec); print('DONE', flush=True)

if __name__ == '__main__': main()
