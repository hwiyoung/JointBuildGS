"""Request 11-24 14:30 (no training, 판 0 map, same target points and views as df22): the 'other target in front' pixels whose target does NOT match the GT depth there.
For those pixels (GT buffer present, |target − GT buffer| > τ of the owner kind):
  1. is the owner patch's target right on its own GT points (판 0 target-right definition: |GT point − patch target plane| <= τ, all eligible GT points of that patch,
     pts_<stem>.npz; the patch counts as right when at least half of its GT points are right; patches without GT points counted apart)
     -> right: 'a right target covering pixels beyond its own patch'; wrong: 'a wrong target';
  2. how far in front of the target point: point depth − target depth in (τ, 1] m, (1, 3], (3, 10], > 10 m.
R1 × LoD2 only, also: per target point, visible views minus the views whose front target matches the GT depth (counted as hidden) -> median for lost / kept points.
usage: df23_front_wrong.py <stem>   writes docs/tables/front_wrong_<stem>.csv/json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'
BINS = [(0, 1, '1 m 안'), (1, 3, '1~3 m'), (3, 10, '3~10 m'), (10, 1e9, '10 m 넘음')]

def main(stem, var='base', tag=''):
    site, prior = stem.split('__'); roof, wall = tau_of(site, prior)
    P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'normal', 'tau', 'case_id', 'target_ok', 'patch']); R = loadz(O/'points_out'/f'res_{stem}.npz', ['p0_s0'])
    # patch target right on its own GT points
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['kind']); NP = len(tb['kind']); pa = P['patch']; hp = pa >= 0
    n_all = np.bincount(pa[hp], minlength=NP); n_ok = np.bincount(pa[hp], weights=P['target_ok'][hp].astype(float), minlength=NP)
    p_state = np.where(n_all == 0, 2, np.where(n_ok*2 >= n_all, 0, 1))   # 0 right, 1 wrong, 2 no GT points
    ptau = np.where(tb['kind'] == 2, wall if prior == 'LoD2' else roof, roof)
    tgt = np.flatnonzero((P['case_id'] == 2) & P['target_ok']); kept = (R['p0_s0'][tgt] & 1).astype(bool)
    X = P['xyz'][tgt].astype('f8'); N = P['normal'][tgt].astype('f8'); tau = P['tau'][tgt]; n = len(tgt)
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']
    rec = dict(pt=[], st=[], gap=[]); vis = np.zeros(n, 'i4'); hid_gt = np.zeros(n, 'i4')
    for name, meta in idx.items():
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M); Pc = X@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'): u = np.floor(K[0, 0]*Pc[:, 0]/z + K[0, 2] + .5); v = np.floor(K[1, 1]*Pc[:, 1]/z + K[1, 2] + .5)
        ok = (z > .1) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741) & (((Cc[None] - X)*N).sum(1) > 0); ii = np.flatnonzero(ok)
        if not len(ii): continue
        uu, vv, zz = u[ii].astype(int), v[ii].astype(int), z[ii]
        mv = np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f'{name}.npy')[vv, uu]; vs = ~(np.isfinite(mv) & (mv > 0) & (mv < zz - 10.)); ii, uu, vv, zz = ii[vs], uu[vs], vv[vs], zz[vs]
        vis[ii] += 1
        a = loadz(O/'maps/base'/var/stem/f'{name}.npz', ['depth', 'weight', 'owner']); o = a['owner'][vv, uu]; w = a['weight'][vv, uu]; d = a['depth'][vv, uu]
        k2 = (o >= 0) & (w > 0) & (d < zz - tau[ii])
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy')[vv, uu]; gtv = np.isfinite(gt); right = gtv & (np.abs(d - gt) <= ptau[np.maximum(o, 0)])
        hid_gt[ii] += (k2 & right)
        wr = k2 & gtv & ~right
        rec['pt'].append(ii[wr]); rec['st'].append(p_state[o[wr]]); rec['gap'].append((zz - d)[wr])
    Rr = {k: np.concatenate(v) for k, v in rec.items()}; rows = []
    for g, gm in [('잃은 점(판 0)', ~kept), ('지킨 점(판 0)', kept)]:
        m = gm[Rr['pt']]; st = Rr['st'][m]; gap = Rr['gap'][m]; tot = int(m.sum())
        row = dict(stem=STEM_KO[stem], group=g, points=int(gm.sum()), front_not_gt_pairs=tot,
                   **{'맞는 목표가 제 패치 밖까지 덮음 %': 100*float((st == 0).mean()) if tot else None, '틀린 목표 %': 100*float((st == 1).mean()) if tot else None,
                      '그 패치에 참값 점 없음 %': 100*float((st == 2).mean()) if tot else None})
        for lo, hi, lab in BINS:
            mk = (gap > lo) & (gap <= hi); row[f'앞 {lab} %'] = 100*float(mk.mean()) if tot else None
            for s_, sl in [(0, '맞는 목표'), (1, '틀린 목표')]:
                row[f'앞 {lab} — {sl} %'] = 100*float((mk & (st == s_)).sum()/max(1, (st == s_).sum())) if tot else None
        if stem == 'R1rep_b10__LoD2':
            row['가려지지 않은 영상 중앙값(10 m 규칙)'] = float(np.median(vis[gm])); row['참값에 맞는 앞 목표 영상을 가려진 것으로 다시 센 뒤 중앙값'] = float(np.median((vis - hid_gt)[gm]))
            row['다시 센 뒤 0장인 점 %'] = 100*float(((vis - hid_gt)[gm] == 0).mean())
        rows.append(row)
    table(f'front_wrong_{stem}' + (f'_{tag}' if tag else ''), rows); print('FWRONG', stem, json.dumps(rows, ensure_ascii=False)[:600], flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
