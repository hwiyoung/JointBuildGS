"""Request 11-24 16:15 (no training): target points × visible views (TARGETPATH 10 m rule) split by the GT depth buffer (TARGETPATH tp0) at the point's pixel:
  A hidden by GT : buffer nearer than the point by > 0.5 m; (D, counted apart: buffer farther than the point by > 0.5 m);  B visible by GT : |buffer − point depth| <= 0.5 m;  C no buffer.
B pairs: kind of the 판 9 (cell_ga) instruction (df19 rule: right target / other target in front / image depth / target behind / none).
Per point: number of B views (median) and share of B views with a right target (median), lost / kept at 판 0.
A pairs: share where the 판 9 pixel has a target (disc/cell owner, weight > 0) within 0.5 m of the GT buffer (a target on the occluding surface), over all A pairs and over A pairs with a target.
usage: df28_abc.py <stem>   writes docs/tables/abc_<stem>.csv/json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'
KN = ['맞는 목표', '앞의 다른 목표', '영상 깊이 지시', '뒤의 목표', '지시 없음']

def main(stem):
    site = stem.split('__')[0]; P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'normal', 'tau', 'case_id', 'target_ok']); R = loadz(O/'points_out'/f'res_{stem}.npz', ['p0_s0'])
    tgt = np.flatnonzero((P['case_id'] == 2) & P['target_ok']); kept = (R['p0_s0'][tgt] & 1).astype(bool)
    X = P['xyz'][tgt].astype('f8'); N = P['normal'][tgt].astype('f8'); tau = P['tau'][tgt]; n = len(tgt)
    idx = json.loads((O/'maps/base/cell_ga'/stem/'index.json').read_text())['views']
    cA = np.zeros(n, 'i4'); cB = np.zeros(n, 'i4'); cC = np.zeros(n, 'i4'); cD = np.zeros(n, 'i4'); bRight = np.zeros(n, 'i4'); kB = np.zeros((n, 5), 'i4'); aT = np.zeros(n, 'i4'); aOn = np.zeros(n, 'i4')
    for name, meta in idx.items():
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M); Pc = X@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'): u = np.floor(K[0, 0]*Pc[:, 0]/z + K[0, 2] + .5); v = np.floor(K[1, 1]*Pc[:, 1]/z + K[1, 2] + .5)
        ok = (z > .1) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741) & (((Cc[None] - X)*N).sum(1) > 0); ii = np.flatnonzero(ok)
        if not len(ii): continue
        uu, vv, zz = u[ii].astype(int), v[ii].astype(int), z[ii]
        mv = np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f'{name}.npy')[vv, uu]; vs = ~(np.isfinite(mv) & (mv > 0) & (mv < zz - 10.)); ii, uu, vv, zz = ii[vs], uu[vs], vv[vs], zz[vs]
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy')[vv, uu]; gv = np.isfinite(gt)
        A = gv & (gt < zz - .5); B = gv & ~A & (np.abs(gt - zz) <= .5); C = ~gv
        a = loadz(O/'maps/base/cell_ga'/stem/f'{name}.npz', ['depth', 'weight', 'owner']); o = a['owner'][vv, uu]; w = a['weight'][vv, uu]; d = a['depth'][vv, uu]; t = tau[ii]
        k = np.full(len(ii), 4); disc = (o >= 0) & (w > 0); img = (o < 0) & (w > 0)
        k[disc & (np.abs(d - zz) <= t)] = 0; k[disc & (d < zz - t)] = 1; k[img] = 2; k[disc & (d > zz + t)] = 3
        np.add.at(cA, ii[A], 1); np.add.at(cB, ii[B], 1); np.add.at(cC, ii[C], 1); np.add.at(cD, ii[gv & (gt > zz + .5)], 1); np.add.at(kB, (ii[B], k[B]), 1); np.add.at(bRight, ii[B & (k == 0)], 1)
        np.add.at(aT, ii[A & disc], 1); np.add.at(aOn, ii[A & disc & (np.abs(d - gt) <= .5)], 1)
    rows = []
    for g, gm in [('잃은 점(판 0)', ~kept), ('지킨 점(판 0)', kept)]:
        tA, tB, tC, tD = int(cA[gm].sum()), int(cB[gm].sum()), int(cC[gm].sum()), int(cD[gm].sum()); tot = tA + tB + tC + tD; kb = kB[gm].sum(0); hb = cB[gm] > 0
        r = dict(stem=STEM_KO[stem], group=g, points=int(gm.sum()), visible_pairs=tot, A_hidden_by_GT_pct=100*tA/tot if tot else None, B_visible_by_GT_pct=100*tB/tot if tot else None,
                 C_no_GT_buffer_pct=100*tC/tot if tot else None, D_buffer_behind_point_pct=100*tD/tot if tot else None, B_pairs=tB, **{f'B: {KN[j]} %': (100*float(kb[j]/tB) if tB else None) for j in range(5)},
                 B_views_per_point_median=float(np.median(cB[gm])) if gm.any() else None, points_with_B=int(hb.sum()),
                 B_right_share_per_point_median_pct=100*float(np.median(bRight[gm][hb]/cB[gm][hb])) if hb.any() else None,
                 A_target_on_occluder_pct_of_A=100*float(aOn[gm].sum()/tA) if tA else None, A_pairs_with_target=int(aT[gm].sum()),
                 A_target_on_occluder_pct_of_A_with_target=100*float(aOn[gm].sum()/max(1, aT[gm].sum())) if aT[gm].sum() else None)
        rows.append(r)
    table(f'abc_{stem}', rows); print('ABC', stem, json.dumps(rows, ensure_ascii=False)[:600], flush=True)

if __name__ == '__main__': main(sys.argv[1])
