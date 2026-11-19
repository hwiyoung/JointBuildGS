"""Order 5 pre-training checks per scene (CPU). usage: g1_check.py <stem> | g1_check.py table
 - target depth: eval GT rows projected to every training view where they are visible (no GT point nearer than the row's tau at that pixel);
   on order-1 pixels |target depth - row depth| <= tau share (>= 99 %)
 - occlusion: order-1 pixels with image depth > 10 m nearer than the target (must be 0)
 - coverage: order 1-4 pixel shares next to the method's prior pixel share (no threshold)
 - seeds: GT patches, seeds, seedless valid patches (must be 0)
 - target mesh: O/meshes/<stem>__gtt_target/score.json completeness (>= 99 %)
 - figure: one view (most order-2 pixels among the median third by order 1): photo | target depth | order map"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from scipy.ndimage import minimum_filter
GAP = 0.03  # m, GT point spacing used for the visibility splat (median spacing 0.024 m, receipt)

def depth_check(stem):
    site, prior = stem.split('__'); root = O/'stage1'/stem; idx = json.loads((root/'maps/index.json').read_text())
    r = loadz(GT/'scenes'/stem/'rows.npz', ['xyz', 'row_tau_m']); X = r['xyz'].astype('f8'); tau = r['row_tau_m']
    a = loadz(GT/'reference'/site/'dense.npz', ['xyz']); b = loadz(GT/'reference'/site/'normal_points.npz', ['xyz']); G = np.r_[a['xyz'], b['xyz'].astype('f8')]
    box = view_box(site); G = G[((G >= box[0]) & (G <= box[1])).all(1)]
    n_vis = n_o1 = n_ok = 0; n_viol = 0; n_beh = n_fr = 0; per = []
    for name, v in idx['views'].items():
        K = np.asarray(v['K']); M = np.asarray(v['W2C']); m = loadz(root/'maps'/v['file']); oc = loadz(root/'occl'/v['file'], ['code']); H, W = m['depth'].shape
        Pc = G@M[:3, :3].T+M[:3, 3]; z = Pc[:, 2]; ok = z > .1; u = np.floor(K[0, 0]*Pc[ok, 0]/z[ok]+K[0, 2]+.5).astype(int); vv = np.floor(K[1, 1]*Pc[ok, 1]/z[ok]+K[1, 2]+.5).astype(int)
        inn = (u >= 0) & (u < W) & (vv >= 0) & (vv < H); zz = z[ok][inn]; uu = u[inn]; vw = vv[inn]
        # depth-adaptive splat: a GT point covers a square of its spacing (gap_m) on the image, so near surfaces have no holes between points
        buf = np.full((H, W), np.inf, 'f4'); half = np.ceil(GAP*K[0, 0]/zz/2).astype(int)
        for h in np.unique(half):
            sel = half == h; b1 = np.full(H*W, np.inf, 'f4'); np.minimum.at(b1, vw[sel]*W+uu[sel], zz[sel].astype('f4')); b1 = b1.reshape(H, W)
            if h > 0: b1 = minimum_filter(b1, size=2*int(min(h, 25))+1, mode='nearest')
            buf = np.minimum(buf, b1)
        buf = buf.ravel()
        Q = X@M[:3, :3].T+M[:3, 3]; zq = Q[:, 2]; okq = zq > .1; uq = np.full(len(X), -1); vq = np.full(len(X), -1)
        uq[okq] = np.floor(K[0, 0]*Q[okq, 0]/zq[okq]+K[0, 2]+.5); vq[okq] = np.floor(K[1, 1]*Q[okq, 1]/zq[okq]+K[1, 2]+.5)
        inq = okq & (uq >= 0) & (uq < W) & (vq >= 0) & (vq < H); j = np.flatnonzero(inq); pix = vq[j]*W+uq[j]
        vis = zq[j]-buf[pix] <= tau[j]; j = j[vis]; pix = pix[vis]; code = oc['code'].ravel()[pix]; o1 = code == 1
        d = m['depth'].ravel()[pix[o1]]; dd = d-zq[j[o1]]; good = np.abs(dd) <= tau[j[o1]]; behind = dd > tau[j[o1]]; front = dd < -tau[j[o1]]
        mv = np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f'{name}.npy'); viol = int(((oc['code'] == 1) & np.isfinite(mv) & (mv > 0) & (mv < m['depth']-10)).sum())
        n_vis += len(j); n_o1 += int(o1.sum()); n_ok += int(good.sum()); n_viol += viol; n_beh += int(behind.sum()); n_fr += int(front.sum())
        per.append(dict(view=name, visible=len(j), order1=int(o1.sum()), within=int(good.sum()), target_behind=int(behind.sum()), target_in_front=int(front.sum()), mvs_violations=viol))
    return dict(rows_visible_pairs=n_vis, order1_pairs=n_o1, within_tau=n_ok, within_tau_pct=100*n_ok/max(n_o1, 1), target_behind_pct=100*n_beh/max(n_o1, 1), target_in_front_pct=100*n_fr/max(n_o1, 1), visibility=f'GT point splat {GAP} m', order1_mvs_10m_violations=n_viol), per

def figure(stem):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    from matplotlib.colors import ListedColormap
    from PIL import Image
    site, prior = stem.split('__'); root = O/'stage1'/stem; idx = json.loads((root/'maps/index.json').read_text()); names = list(idx['views'])
    o1 = np.array([idx['views'][n]['order_pixels'][0] for n in names]); o2 = np.array([idx['views'][n]['order_pixels'][1] for n in names])
    mid = np.argsort(o1)[len(o1)//3: 2*len(o1)//3]; k = mid[np.argmax(o2[mid])]; name = names[k]
    m = loadz(root/'maps'/f'{name}.npz'); oc = loadz(root/'occl'/f'{name}.npz'); img = Image.open(S0/'fork_inputs/s61'/site/f'scene_{prior}/images'/f'{name}.jpg').convert('RGB').resize((1024, 741))
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.4), constrained_layout=True)
    ax[0].imshow(img); ax[0].set_title('사진')
    Dm = np.where(oc['code'] == 1, m['depth'], np.nan); im = ax[1].imshow(Dm, cmap='viridis'); ax[1].set_title('목표 깊이(차례 1, m)'); fig.colorbar(im, ax=ax[1], shrink=.8)
    cm = ListedColormap(['#2b83ba', '#d7191c', '#bbbbbb', '#ffffff']); ax[2].imshow(oc['code'].astype(int)-1, cmap=cm, vmin=0, vmax=3, interpolation='nearest')
    ax[2].set_title('차례: 파랑 1 참값, 빨강 2 가려짐, 회색 3 영상 깊이, 흰 4 없음')
    for a in ax: a.set_axis_off()
    fig.suptitle(f'{TITLE} · {stem} · {name} · 가려진 화소는 깊이 감독을 걸지 않는다', fontsize=12)
    out = D/'figures'/f'stage1_check_{stem}.png'; out.parent.mkdir(parents=True, exist_ok=True); fig.savefig(out, dpi=110); plt.close(fig); return str(out), name

def main(stem):
    c = cfg(1); t0 = time.monotonic(); site, prior = stem.split('__'); root = O/'stage1'/stem
    dep, per = depth_check(stem); sr = json.loads((root/'seed_receipt.json').read_text()); rd = json.loads((root/'ready.json').read_text()); tot = rd['totals']
    sp = O/'meshes'/f'{stem}__gtt_target'/'score.json'; mesh = None
    if sp.exists():
        rows = json.loads(sp.read_text())['rows']; a = next(r for r in rows if r['surface'] == 'all' and str(r.get('case_id')) == 'all')
        mesh = dict(completeness_pct=a['completeness_pct'], accuracy_pct=a.get('accuracy_pct'), rows=a['n_gt'])
    fig, view = figure(stem)
    rec = dict(at=now(), stem=stem, title=TITLE, target_mesh=mesh, target_depth=dep, coverage=dict(
        order_pct={f'order{k}': 100*tot[f'order{k}']/tot['pixels'] for k in (1, 2, 3, 4)}, method_prior_pixel_pct=100*tot['ft_prior_pixels']/tot['pixels'],
        method_background_pixel_pct=100*tot['ft_background_pixels']/tot['pixels'], order2_reasons=dict(backface=tot['order2_backface'], gt_points=tot['order2_gt_points'], mvs_10m=tot['order2_mvs_10m'])),
        seeds=dict(gt_patches=sr['gt_seeds'], seeds=sr['seeds_total'], gt_seeds=sr['gt_seeds'], background_seeds=sr['background_seeds'], seedless_valid_patches=sr['seedless_valid_patches'],
                   background_within_0p3m=sr['background_within_0p3m_of_gt_patch'], background_within_0p3m_fraction=sr['background_within_0p3m_fraction']),
        figure=fig, figure_view=view, seconds=time.monotonic()-t0, scientific_verdict=None)
    pc = c['precheck']; rec['pass'] = dict(target_mesh=None if mesh is None else mesh['completeness_pct'] >= pc['target_mesh_within_tau_min_pct'],
        target_depth=dep['within_tau_pct'] >= pc['target_depth_within_tau_min_pct'], occlusion=dep['order1_mvs_10m_violations'] <= pc['occlusion_violations_max'],
        seeds=sr['seedless_valid_patches'] == 0)
    dump(O/'checks'/f'{stem}.json', rec); table(f'stage1/check_views_{stem}', per); print('CHECK', stem, json.dumps(rec['pass']), json.dumps(dep), flush=True)

def summary():
    rows = []
    for stem in STEMS:
        p = O/'checks'/f'{stem}.json'
        if not p.exists(): continue
        r = json.loads(p.read_text()); cv = r['coverage']
        rows.append(dict(stem=stem, title=TITLE, target_mesh_completeness_pct=(r['target_mesh'] or {}).get('completeness_pct'), target_mesh_accuracy_pct=(r['target_mesh'] or {}).get('accuracy_pct'),
            target_depth_within_tau_pct=r['target_depth']['within_tau_pct'], target_depth_pairs=r['target_depth']['order1_pairs'], target_behind_pct=r['target_depth']['target_behind_pct'], target_in_front_pct=r['target_depth']['target_in_front_pct'],
            order1_mvs_10m_violations=r['target_depth']['order1_mvs_10m_violations'], **{f'{k}_pct': v for k, v in cv['order_pct'].items()},
            method_prior_pixel_pct=cv['method_prior_pixel_pct'], method_background_pixel_pct=cv['method_background_pixel_pct'],
            order2_backface=cv['order2_reasons']['backface'], order2_gt_points=cv['order2_reasons']['gt_points'], order2_mvs_10m=cv['order2_reasons']['mvs_10m'],
            gt_patches=r['seeds']['gt_patches'], seeds=r['seeds']['seeds'], background_seeds=r['seeds']['background_seeds'], seedless_valid_patches=r['seeds']['seedless_valid_patches'],
            background_within_0p3m=r['seeds']['background_within_0p3m'], background_within_0p3m_pct=100*r['seeds']['background_within_0p3m_fraction'],
            pass_all=all(v is not False for v in r['pass'].values()) and r['pass']['target_mesh'] is not None, figure=Path(r['figure']).name))
    table('stage1_checks', rows); print('SUMMARY', json.dumps(rows, ensure_ascii=False, default=str))

if __name__ == '__main__':
    summary() if sys.argv[1] == 'table' else main(sys.argv[1])
