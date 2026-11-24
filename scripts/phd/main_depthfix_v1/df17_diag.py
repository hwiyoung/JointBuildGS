"""Question ① (11-24): why the right-target views of the target points drop from 판 0 to 판 1 (CPU, read only).
Target points = case 2 (image depth wrong) & 판 0 target right; lost / kept by 판 0 seed 0 base extraction.
For every (point, outward in-frame view) where the 판 0 map gives a right target (disc owner, weight > 0, |depth − point depth| <= τ), classify the 판 1 map pixel:
  still right | owner disc back-facing in this view (not drawn) -> then: other disc owns / image depth / nothing | 10 m rule weight 0 |
  same owner, other change (should be 0) | other disc owns without back-facing (should be 0).
Also per point: right views in 판 0 and 판 1, outward views. Same pixel rule as df12 (floor(K x + 0.5)), outward = GT normal faces the camera.
Visible view = TARGETPATH 10 m rule: image depth at the point's pixel not nearer than the point by > 10 m (point not hidden).
usage: df17_diag.py <stem>   writes /docs/tables/diag_ga_views_<stem>.csv/json and /df/points/diag_ga_<stem>.npz"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *

def main(stem):
    P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'normal', 'tau', 'case_id', 'target_ok']); R = loadz(O/'points_out'/f'res_{stem}.npz', ['p0_s0'])
    tgt = np.flatnonzero((P['case_id'] == 2) & P['target_ok']); kept = (R['p0_s0'][tgt] & 1).astype(bool)
    X = P['xyz'][tgt].astype('f8'); N = P['normal'][tgt].astype('f8'); tau = P['tau'][tgt]; n = len(tgt)
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['target', 'normal', 'surface_exists']); ids = np.flatnonzero(tb['surface_exists'])
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']
    C = {k: np.zeros(n, 'i4') for k in ['outward', 'vis', 'right0_vis', 'right1_vis', 'right0', 'right1', 'still', 'back_other_right', 'back_other_wrong', 'back_image', 'back_none', 'front10', 'same_owner_other', 'other_no_back']}
    for name, meta in idx.items():
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M); Pc = X@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'): u = np.floor(K[0, 0]*Pc[:, 0]/z + K[0, 2] + .5); v = np.floor(K[1, 1]*Pc[:, 1]/z + K[1, 2] + .5)
        ok = (z > .1) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741) & (((Cc[None] - X)*N).sum(1) > 0); ii = np.flatnonzero(ok)
        if not len(ii): continue
        uu, vv, zz = u[ii].astype(int), v[ii].astype(int), z[ii]; C['outward'][ii] += 1
        a = loadz(O/'maps/base/base'/stem/f'{name}.npz', ['depth', 'weight', 'owner']); b = loadz(O/'maps/base/ga'/stem/f'{name}.npz', ['depth', 'weight', 'owner', 'front_rule'])
        o0, o1 = a['owner'][vv, uu], b['owner'][vv, uu]; d0, d1 = a['depth'][vv, uu], b['depth'][vv, uu]; w0, w1 = a['weight'][vv, uu], b['weight'][vv, uu]
        r0 = (o0 >= 0) & (w0 > 0) & (np.abs(d0 - zz) <= tau[ii]); r1 = (o1 >= 0) & (w1 > 0) & (np.abs(d1 - zz) <= tau[ii])
        mv = np.load(S0/'fork_inputs/s61'/stem.split('__')[0]/'maps/mvs'/f'{name}.npy')[vv, uu]; vis = ~(np.isfinite(mv) & (mv > 0) & (mv < zz - 10.))   # TARGETPATH 10 m rule: point not hidden
        C['vis'][ii] += vis; C['right0_vis'][ii] += r0 & vis; C['right1_vis'][ii] += r1 & vis
        front = np.zeros(len(tb['target']), bool); front[ids] = ((Cc[None] - tb['target'][ids])*tb['normal'][ids]).sum(1) > 0
        back = (o0 >= 0) & ~front[np.maximum(o0, 0)]; f10 = b['front_rule'][vv, uu]
        C['right0'][ii] += r0; C['right1'][ii] += r1
        m = r0
        C['still'][ii] += m & r1
        C['back_other_right'][ii] += m & back & (o1 >= 0) & r1
        C['back_other_wrong'][ii] += m & back & (o1 >= 0) & ~r1
        C['back_image'][ii] += m & back & (o1 < 0) & (w1 > 0)
        C['back_none'][ii] += m & back & (o1 < 0) & (w1 == 0)
        C['front10'][ii] += m & ~back & f10
        C['same_owner_other'][ii] += m & ~back & ~f10 & (o1 == o0) & ~r1
        C['other_no_back'][ii] += m & ~back & ~f10 & (o1 != o0)
    savez(O/'points'/f'diag_ga_{stem}.npz', point=tgt, kept=kept, **C)
    rows = []
    for g, mk in [('잃은 점(판 0)', ~kept), ('지킨 점(판 0)', kept)]:
        r = dict(stem=STEM_KO[stem], group=g, points=int(mk.sum()), outward_views_median=float(np.median(C['outward'][mk])) if mk.any() else None,
                 right_views_p0_median=float(np.median(C['right0'][mk])) if mk.any() else None, right_views_p1_median=float(np.median(C['right1'][mk])) if mk.any() else None,
                 right_half_p0_pct=100*float((C['right0'][mk]*2 > C['outward'][mk]).mean()) if mk.any() else None, right_half_p1_pct=100*float((C['right1'][mk]*2 > C['outward'][mk]).mean()) if mk.any() else None,
                 visible_views_median=float(np.median(C['vis'][mk])) if mk.any() else None, right_vis_p0_median=float(np.median(C['right0_vis'][mk])) if mk.any() else None, right_vis_p1_median=float(np.median(C['right1_vis'][mk])) if mk.any() else None,
                 right_half_visible_p0_pct=100*float((C['right0_vis'][mk]*2 > C['vis'][mk]).mean()) if mk.any() else None, right_half_visible_p1_pct=100*float((C['right1_vis'][mk]*2 > C['vis'][mk]).mean()) if mk.any() else None,
                 removed_pairs_in_hidden_views_pct=100*float(((C['right0'] - C['right0_vis']) - (C['right1'] - C['right1_vis']))[mk].sum()/max(1, (C['right0'] - C['right1'])[mk].sum())) if mk.any() else None)
        tot = int(C['right0'][mk].sum()); r['p0_right_pairs'] = tot
        for k in ['still', 'back_other_right', 'back_other_wrong', 'back_image', 'back_none', 'front10', 'same_owner_other', 'other_no_back']: r[f'{k}_pct'] = 100*float(C[k][mk].sum()/tot) if tot else None
        rows.append(r)
    table(f'diag_ga_views_{stem}', rows); print('DIAG', json.dumps(rows, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(sys.argv[1])
