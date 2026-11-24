"""Request 11-24 14:00 item 4 (no training): which patch gives the 'other target in front' (kind 2 of df19), 판 0 map only (CPU, read only).
Target points, views and the kind rule = df19_kinds.py (visible outward views, TARGETPATH kinds). For every (point, view) pixel of kind 2 (disc owner, weight > 0,
target depth < point depth − τ):
  - 판 0 target type of the owner patch (가중 평균 / 영상 깊이 / 되돌림 / 결측);
  - is that target right at that pixel: |target depth − GT depth buffer| <= τ of the owner patch kind (GT buffer = TARGETPATH tp0, scene-box GT only, issues 23;
    pixels without GT buffer counted apart);
  - is the owner the point's own patch / a touching patch (centre distance <= r_owner + r_point + 0.05 m, r = sqrt(area/π)) / farther.
Shares per scene and group (lost / kept at 판 0), pooled over pairs; also the median over points of the per-point share. usage: df22_front.py <stem>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'

def main(stem, var='base', tag=''):
    site, prior = stem.split('__'); roof, wall = tau_of(site, prior)
    P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'normal', 'tau', 'case_id', 'target_ok', 'patch']); R = loadz(O/'points_out'/f'res_{stem}.npz', ['p0_s0'])
    tgt = np.flatnonzero((P['case_id'] == 2) & P['target_ok']); kept = (R['p0_s0'][tgt] & 1).astype(bool)
    X = P['xyz'][tgt].astype('f8'); N = P['normal'][tgt].astype('f8'); tau = P['tau'][tgt]; pp = P['patch'][tgt]; n = len(tgt)
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['centre', 'area', 'kind']); typ = loadz(O/'patchinfo'/f'{stem}.npz', ['type'])['type']
    rad = np.sqrt(tb['area']/np.pi); ptau = np.where(tb['kind'] == 2, wall if prior == 'LoD2' else roof, roof)
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']
    rec = dict(pt=[], typ=[], right=[], gtv=[], rel=[])
    for name, meta in idx.items():
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M); Pc = X@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'): u = np.floor(K[0, 0]*Pc[:, 0]/z + K[0, 2] + .5); v = np.floor(K[1, 1]*Pc[:, 1]/z + K[1, 2] + .5)
        ok = (z > .1) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741) & (((Cc[None] - X)*N).sum(1) > 0); ii = np.flatnonzero(ok)
        if not len(ii): continue
        uu, vv, zz = u[ii].astype(int), v[ii].astype(int), z[ii]
        mv = np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f'{name}.npy')[vv, uu]; vs = ~(np.isfinite(mv) & (mv > 0) & (mv < zz - 10.)); ii, uu, vv, zz = ii[vs], uu[vs], vv[vs], zz[vs]
        a = loadz(O/'maps/base'/var/stem/f'{name}.npz', ['depth', 'weight', 'owner']); o = a['owner'][vv, uu]; w = a['weight'][vv, uu]; d = a['depth'][vv, uu]
        k2 = (o >= 0) & (w > 0) & (d < zz - tau[ii])
        if not k2.any(): continue
        ii, uu, vv, o, d = ii[k2], uu[k2], vv[k2], o[k2], d[k2]
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy')[vv, uu]; gtv = np.isfinite(gt); right = gtv & (np.abs(d - gt) <= ptau[o])
        own = pp[ii]; dist = np.linalg.norm(tb['centre'][o] - tb['centre'][np.maximum(own, 0)], axis=1)
        rel = np.where(o == own, 0, np.where((own >= 0) & (dist <= rad[o] + rad[np.maximum(own, 0)] + .05), 1, 2))
        rec['pt'].append(ii); rec['typ'].append(typ[o]); rec['right'].append(right); rec['gtv'].append(gtv); rec['rel'].append(rel)
    Rr = {k: np.concatenate(v) for k, v in rec.items()}; rows = []
    for g, gm in [('잃은 점(판 0)', ~kept), ('지킨 점(판 0)', kept)]:
        m = gm[Rr['pt']]; t = Rr['typ'][m]; r_ = Rr['right'][m]; gv = Rr['gtv'][m]; rl = Rr['rel'][m]; ptid = Rr['pt'][m]; tot = int(m.sum())
        row = dict(stem=STEM_KO[stem], group=g, points=int(gm.sum()), front_pairs=tot, points_with_front=int(len(np.unique(ptid))))
        for k in [0, 1, 2, 3]: row[f'목표 종류 {TYPE_KO[k]} %'] = 100*float((t == k).mean()) if tot else None
        row['참값 버퍼 있음 %'] = 100*float(gv.mean()) if tot else None
        row['참값 깊이에 맞음 % (버퍼 있는 쌍 가운데)'] = 100*float(r_[gv].mean()) if gv.any() else None
        for k in [0, 1, 2, 3]:
            mk = (t == k) & gv; row[f'맞음 % — {TYPE_KO[k]}'] = 100*float(r_[mk].mean()) if mk.sum() >= 100 else None
        for k, lab in [(0, '같은 패치'), (1, '맞닿은 패치'), (2, '떨어진 패치')]: row[f'{lab} %'] = 100*float((rl == k).mean()) if tot else None
        if tot:
            u_, inv = np.unique(ptid, return_inverse=True); cnt = np.bincount(inv); adj = np.bincount(inv, weights=(rl <= 1)); rgt = np.bincount(inv, weights=r_.astype(float))
            row['점마다: 맞닿거나 같은 패치 몫 중앙값 %'] = 100*float(np.median(adj/cnt)); row['점마다: 참값에 맞는 몫 중앙값 %'] = 100*float(np.median(rgt/cnt))
        rows.append(row)
    table(f'front_owner_{stem}' + (f'_{tag}' if tag else ''), rows); print('FRONT', stem, json.dumps(rows, ensure_ascii=False)[:700], flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
