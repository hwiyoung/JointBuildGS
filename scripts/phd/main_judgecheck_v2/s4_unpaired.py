"""'판정 없음' (발주 2.5) 의 수를 건물에 딸린 참값 점으로만 센다: 범위 건물의 LoD2 GroundSurface 윤곽 안의 지붕·땅 점, 윤곽 1 m 안의 벽 점.
(s4_truth_rest 는 구역 중심의 모든 점 가운데 짝이 없는 점을 셌기에 길·땅이 섞였다.) 짝짓기·솎기·분류는 s4_truth_rest 와 같은 함수.
  s4_unpaired.py <tile> -> truth/unpaired/<tile>.json"""
from common import *
from shapely import contains_xy
from shapely.ops import unary_union
import s4_truth_rest as TR
from s7_clusters import footprints
def main(tile):
    cfg(); dest = O/'truth/unpaired'/f'{tile}.json'
    if dest.exists(): return
    B = {r['building'] for r in json.loads((O/'stage0/buildings.json').read_text())['rows'] if r['in_scope']}
    FP = footprints(); fp = unary_union([g for b, g in FP.items() if b in B]); fpw = fp.buffer(1.0)
    t = next(x for x in json.loads((W/'inputs/tiles.json').read_text()) if x['id'] == tile)
    e0, n0, e1, n1 = t['core_global']; lo = np.array([e0-690953, n0-5336071]); hi = np.array([e1-690953, n1-5336071])
    X = np.load(WI/'points'/tile/'gt_xyz.npy').astype(np.float64); core = ((X[:, :2] >= lo) & (X[:, :2] < hi)).all(1) if len(X) else np.zeros(0, bool)
    out = dict(at=now(), tile=tile, gt_points=int(len(X)), scientific_verdict=None, rule='building-related = non-wall inside in-scope LoD2 GroundSurface footprints, wall within 1 m; 0.1 m thinning as s4_truth_rest')
    if not len(X) or not core.any(): out['priors'] = {}; dump(dest, out); return
    uv = X[:, :2] @ TR.BASIS.T; inbox = np.zeros(len(X), bool)
    for (u, v) in TR.BOXES.values(): inbox |= (uv[:, 0] >= u[0]) & (uv[:, 0] <= u[1]) & (uv[:, 1] >= v[0]) & (uv[:, 1] <= v[1])
    vert = TR.vertical_points(X); sel = np.flatnonzero(core & ~inbox)
    wall = vert[sel]; inside = np.where(wall, contains_xy(fpw, X[sel, 0], X[sel, 1]), contains_xy(fp, X[sel, 0], X[sel, 1]))
    res = {}
    for prior in ['LoD2', 'ALS']:
        P = []
        for q in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            z = loadz(q, ['patch_id', 'centre', 'normal', 'tangent1', 'tangent2', 'kind', 'prior_height_m'])
            m = ((z['centre'][:, :2] >= lo - 12) & (z['centre'][:, :2] <= hi + 12)).all(1)
            if m.any(): P.append({k: v[m] for k, v in z.items()})
        if not P: continue
        p = {k: np.concatenate([x[k] for x in P]) for k in P[0]}; n = p['normal'].astype(float); a = p['tangent1'].astype(float); b = p['tangent2'].astype(float)
        if prior == 'ALS':
            for i in np.flatnonzero(np.isfinite(n).all(1)):
                e = np.array([1., 0., 0.]) if abs(n[i, 0]) < .9 else np.array([0., 1., 0.]); e = e - n[i]*(e@n[i]); e /= np.linalg.norm(e); a[i] = e; b[i] = np.cross(n[i], e)
        c = p['centre'] + np.nan_to_num(p['prior_height_m'])[:, None]*n; length = np.where(p['kind'] == 1, 10., 5.); owner = np.full(len(sel), -1, np.int64)
        for kind, gm in [(1, ~wall), (2, wall)]:
            pm = np.flatnonzero(p['kind'] == kind); qi = np.flatnonzero(gm)
            if not len(pm) or not len(qi): continue
            o, h = TR.prism(X[sel[qi]], c[pm], a[pm], b[pm], n[pm], length[pm], O/'tmp'/f'prism_unp_{tile}_{prior}_{kind}')
            owner[qi[o >= 0]] = pm[o[o >= 0]]
        # 패치마다 기둥 안 참값 점 수 (평가 상자 안 점도 넣음, 종류 맞춤, 솎기 전): '참값이 없는 패치'를 정하는 데 씀
        allc = np.flatnonzero(core); wall_all = vert[allc]; hits = np.zeros(len(p['kind']), np.int64)
        for kind, gm in [(1, ~wall_all), (2, wall_all)]:
            pm = np.flatnonzero(p['kind'] == kind); qi = np.flatnonzero(gm)
            if not len(pm) or not len(qi): continue
            o, h = TR.prism(X[allc[qi]], c[pm], a[pm], b[pm], n[pm], length[pm], O/'tmp'/f'prism_hit_{tile}_{prior}_{kind}')
            hits += np.bincount(pm[o[o >= 0]], minlength=len(p['kind']))
        savez(O/'truth/unpaired'/f'{tile}__{prior}_patchhits.npz', patch_id=p['patch_id'], hits=hits)
        un = np.flatnonzero((owner < 0) & inside); ku = np.zeros(len(un), bool); nw = ~wall[un]
        if nw.any(): ku[nw] = TR.thin.keep_nearest(X[sel[un[nw]], :2], 0.1)
        if (~nw).any():
            qq = np.floor(X[sel[un[~nw]]]/0.1).astype(np.int64); _, first = np.unique(qq, axis=0, return_index=True); kw = np.zeros(int((~nw).sum()), bool); kw[first] = True; ku[~nw] = kw
        gk = np.where(wall[un], 2, 1)
        res[prior] = dict(unpaired_building_related_thinned=int(ku.sum()), roof_or_ground=int((ku & (gk == 1)).sum()), wall=int((ku & (gk == 2)).sum()), before_thinning=int(len(un)))
    out['priors'] = res; dump(dest, out); print('UNPAIRED', tile, json.dumps(res), flush=True)
if __name__ == '__main__': main(sys.argv[1])
