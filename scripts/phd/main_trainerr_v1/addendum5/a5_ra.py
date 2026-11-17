"""Work ra (order 6): which views remove the surface of the B0 visible wall. GPU (/source = r31).
Mesh rule (scripts/phd/main_rescore_v1/render_model.py 27, 33; src/phd/streamed_tsdf.py 4-21, 55-56): per training view the rendered surf_depth
(expected depth, depth_ratio 0) masked to the mesh box (depth 0 outside), Open3D ScalableTSDFVolume voxel 0.05 m, sdf_trunc 0.25 m, depth_trunc 300 m:
a voxel at camera depth z takes from a pixel with depth d nothing if d <= 0 or d - z <= -0.25 (ray ends > 0.25 m in front), else min(1, (d - z)/0.25).
  views <model> : every visible_low / visible_high GT point (2,000 sampled per place, rng 0) x every training view whose image contains it:
                  rendered depth d at the point pixel -> beyond (d > z + 0.25), stop (0 < d < z - 0.25), right (|d - z| <= 0.25), none (d = 0);
                  at beyond pixels the splat weights at the wall depth (z +- 0.25), behind it, accumulated opacity, and the wall-depth splats' opacity / angle
                  -> payload addendum5/ra/views_<model>.npz
  tables        : per model and place -> tables/ra_views.csv"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
RA5 = A5O/'ra'
TLCASE = TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model'; SA2 = A4O/'runs/B0_b10/sa2_B0_LoD2_occlmask/attempt1/model'
MODELS = {f'{k}_{it}': (m, str(it)) for k, m in [('record', TLCASE), ('sa2', SA2)] for it in (7000, 15000, 30000)}
BOX = TLC/'gtj/jobs/B0_b10__LoD2__tl_30000.json'
TRUNC = .25

def views(name):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_da as D4
    camera = D4.gpu_setup(); t0 = time.monotonic(); model, st = MODELS[name]; S = D4.load_pt(model, st); box = np.asarray(json.loads(BOX.read_text())['box'])
    places = {pl: place_points5(pl) for pl in ['visible_low', 'visible_high']}; rng = np.random.default_rng(0); pick = {}
    for pl, P in places.items(): pick[pl] = np.sort(rng.choice(len(P['xyz']), min(2000, len(P['xyz'])), replace=False))
    md, mi = D4.views_of('B0_b10__LoD2'); names = sorted(mi); rec = {pl: {k: [] for k in ['pt', 'view', 'z', 'd', 'w_wall', 'w_behind', 'acc', 'wall_op', 'wall_angle', 'wall_n']} for pl in places}
    with torch.no_grad():
        g = D4.gmodel(S); from gaussian_renderer import render; from types import SimpleNamespace; from utils.general_utils import build_rotation
        pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False)
        op_all = g.get_opacity[:, 0].cpu().numpy(); nrm_all = build_rotation(g.get_rotation)[:, :, 2].cpu().numpy()
        for j, nm in enumerate(names):
            mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C'])
            with np.load(md/mm['file']) as z: H, W = z['owner'].shape
            cam = camera(W, H, K, M, nm); rd = None
            for pl, P in places.items():
                X = P['xyz'][pick[pl]].astype('f8'); Xc = X@M[:3, :3].T+M[:3, 3]; zc = Xc[:, 2]; okz = zc > .2
                u = np.floor(K[0, 0]*Xc[:, 0]/np.where(okz, zc, 1)+K[0, 2]).astype('i8'); v = np.floor(K[1, 1]*Xc[:, 1]/np.where(okz, zc, 1)+K[1, 2]).astype('i8')
                ins = okz & (u >= 0) & (u < W) & (v >= 0) & (v < H)
                if not ins.any(): continue
                if rd is None:   # the mesh input depth of this view: surf_depth masked to the box (render_model.py 33)
                    pkg = render(cam, g, pipe, torch.zeros(3, device='cuda')); dep = pkg['surf_depth'].reshape(H, W)
                    yy, xx = torch.meshgrid(torch.arange(H, device='cuda'), torch.arange(W, device='cuda'), indexing='ij')
                    xyz = torch.stack([(xx-K[0, 2])*dep/K[0, 0], (yy-K[1, 2])*dep/K[1, 1], dep, torch.ones_like(dep)], -1); world = xyz@cam.world_view_transform.inverse()
                    bx = torch.tensor(box, device='cuda', dtype=world.dtype); mask = ((world[..., :3] >= bx[0]) & (world[..., :3] <= bx[1])).all(-1) & (dep > 0)
                    rd = torch.where(mask, dep, torch.zeros_like(dep)).cpu().numpy()
                q = np.flatnonzero(ins); d = rd[v[q], u[q]].astype('f8'); n = len(q)
                ww = np.full(n, np.nan); wb = np.full(n, np.nan); ac = np.full(n, np.nan); wo = np.full(n, np.nan); wa = np.full(n, np.nan); wn = np.zeros(n)
                be = np.flatnonzero(d > zc[q]+TRUNC)
                if len(be):
                    C = D4.contrib(g, cam, u[q][be], v[q][be])
                    if len(C):
                        p = C[:, 0].astype('i8'); rel = C[:, 3]-zc[q][be][p]; wall = np.abs(rel) <= TRUNC; beh = rel > TRUNC; gi = C[:, 1].astype('i8'); m_ = len(be)
                        ww[be] = np.bincount(p, C[:, 2]*wall, m_); wb[be] = np.bincount(p, C[:, 2]*beh, m_); ac[be] = np.bincount(p, C[:, 2], m_)
                        on = np.asarray(P['out'][pick[pl]][q][be][p], 'f8'); ang = np.degrees(np.arccos(np.clip(np.abs((nrm_all[gi]*on).sum(1)), 0, 1)))
                        sw = np.bincount(p, C[:, 2]*wall, m_); wo[be] = np.bincount(p, C[:, 2]*wall*op_all[gi], m_)/np.maximum(sw, 1e-12); wa[be] = np.bincount(p, C[:, 2]*wall*ang, m_)/np.maximum(sw, 1e-12)
                        wn[be] = np.bincount(p, wall.astype('f8'), m_)
                for k, val in [('pt', pick[pl][q]), ('view', np.full(n, j)), ('z', zc[q]), ('d', d), ('w_wall', ww), ('w_behind', wb), ('acc', ac), ('wall_op', wo), ('wall_angle', wa), ('wall_n', wn)]: rec[pl][k].append(val)
    RA5.mkdir(parents=True, exist_ok=True)
    savez(RA5/f'views_{name}.npz', **{f'{pl}__{k}': np.concatenate(v) if v else np.zeros(0) for pl, r in rec.items() for k, v in r.items()}, **{f'{pl}__xyz': places[pl]['xyz'][pick[pl]] for pl in places})
    print('RAVIEWS', name, {pl: len(np.concatenate(r['pt'])) for pl, r in rec.items()}, round(time.monotonic()-t0), flush=True)

def tables():
    rows = []
    for name in MODELS:
        p = RA5/f'views_{name}.npz'
        if not p.exists(): continue
        z = loadz(p)
        for pl in ['visible_low', 'visible_high']:
            pt = z[f'{pl}__pt']; d = z[f'{pl}__d']; zz = z[f'{pl}__z']
            cls = np.where(d <= 0, 3, np.where(d > zz+TRUNC, 0, np.where(d < zz-TRUNC, 1, 2)))
            npts = len(np.unique(pt)); r = dict(model=name, place=pl, place_ko=PLACE_KO[pl], points=npts, point_views=len(pt))
            per = {}
            for k, ko in enumerate(['지나쳐 봄', '앞에서 멈춤', '맞음', '깊이 없음(상자 밖·투명)']):
                r[f'{ko} %(점-영상)'] = pct(cls == k); cnt = np.bincount(pt, cls == k, pt.max()+1)[np.unique(pt)]; per[k] = cnt
                r[f'{ko} 점당 영상 수 q25/q50/q75'] = q4(cnt)
            tot = np.bincount(pt, None, pt.max()+1)[np.unique(pt)]; r['점당 영상 수 q25/q50/q75'] = q4(tot)
            r['점당 지나쳐 봄 비율 q25/q50/q75'] = q4(per[0]/np.maximum(tot, 1)); r['점당 맞음 비율 q25/q50/q75'] = q4(per[2]/np.maximum(tot, 1))
            be = cls == 0
            r['지나쳐 보는 화소: 벽 깊이(±0.25 m) 무게 q25/q50/q75'] = q4(z[f'{pl}__w_wall'][be]); r['지나쳐 보는 화소: 벽 뒤 무게 q25/q50/q75'] = q4(z[f'{pl}__w_behind'][be])
            r['지나쳐 보는 화소: 불투명도 합 q25/q50/q75'] = q4(z[f'{pl}__acc'][be]); r['지나쳐 보는 화소: 벽 깊이 가우시안 불투명도(무게 평균) 중앙값'] = med(z[f'{pl}__wall_op'][be])
            r['지나쳐 보는 화소: 벽 깊이 가우시안과 벽 법선 사이 각(무게 평균) 중앙값 °'] = med(z[f'{pl}__wall_angle'][be]); r['지나쳐 보는 화소: 벽 깊이 가우시안 없음 %'] = pct(z[f'{pl}__wall_n'][be] == 0) if be.any() else None
            rows.append(r)
    table5('ra_views', rows); print('RA TABLE', len(rows), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'views': lambda: views(a[1]), 'tables': tables}[a[0]]()
