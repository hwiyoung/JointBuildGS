"""Question ② (11-24): R1 × LoD2 pixels removed by the 10 m rule although their 판 0 target was right — what the image depth sees there.
Pixel set = 판 1 map 10 m rule (image depth nearer than the target depth by > 10 m) & 판 0 disc target & |target depth − GT depth buffer| <= τ (owner kind).
Examples = the four training views with the most such pixels; crop = 220 × 160 px window with the most such pixels. Panels: photo, image depth, target depth (removed pixels outlined).
Stats over all such pixels of the scene: target − image depth, image-depth 3D point height above the target point, distance from the image-depth 3D point to the nearest GT point
(GTJUDGE dense, view box), and image-depth confidence. GT used only to pick 'target right' and for these checks.
usage: df18_front10_fig.py [stem]   writes /docs/figures/front10_examples_<stem>.png/.pdf/.json, /docs/tables/front10_pixels_<stem>.csv/json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image
from scipy.ndimage import uniform_filter, binary_dilation
from scipy.spatial import cKDTree
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = font_manager.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'; GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'

def main(stem='R1rep_b10__LoD2'):
    site, prior = stem.split('__'); roof, wall = tau_of(site, prior)
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['kind', 'target']); ptau = np.where(tb['kind'] == 2, wall, roof)
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']; mroot = S0/'fork_inputs/s61'/site/'maps'
    G = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz']; box = np.array(json.loads((GT/'views'/f'{site}.json').read_text())['box']); G = G[((G >= box[0]) & (G <= box[1])).all(1)]
    tree = cKDTree(G[::4]); per = []; S = dict(diff=[], up=[], gtd=[], conf=[], n=0)
    for name, meta in idx.items():
        a = loadz(O/'maps/base/base'/stem/f'{name}.npz', ['depth', 'owner']); f10 = loadz(O/'maps/base/ga'/stem/f'{name}.npz', ['front_rule'])['front_rule']
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy'); own = a['owner']; has = own >= 0
        m = f10 & has & np.isfinite(gt) & (np.abs(a['depth'] - gt) <= np.where(has, ptau[np.maximum(own, 0)], 0))
        k = int(m.sum())
        if not k: continue
        per.append((k, name)); mvs = np.load(mroot/'mvs'/f'{name}.npy'); conf = np.load(mroot/'conf'/f'{name}.npy')
        ys, xs = np.nonzero(m); sel = np.random.default_rng(0).choice(len(ys), min(len(ys), 3000), replace=False); ys, xs = ys[sel], xs[sel]
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Rw = M[:3, :3].T; Cc = cam_centre(M)
        def world(d): return (np.c_[(xs - K[0, 2])/K[0, 0]*d, (ys - K[1, 2])/K[1, 1]*d, d] - M[:3, 3])@Rw.T
        Xm = world(mvs[ys, xs]); Xt = world(a['depth'][ys, xs])
        S['diff'].append(a['depth'][ys, xs] - mvs[ys, xs]); S['up'].append(Xm[:, 2] - Xt[:, 2]); S['gtd'].append(tree.query(Xm, workers=16)[0]); S['conf'].append(conf[ys, xs]); S['n'] += k
    per.sort(reverse=True); ex = [n for _, n in per[:4]]
    D_, U_, GD, CF = (np.concatenate(S[k]) for k in ['diff', 'up', 'gtd', 'conf'])
    q = lambda x, p: float(np.quantile(x, p))
    rows = [dict(stem=STEM_KO[stem], pixels=S['n'], views_with_pixels=len(per), sampled=len(D_),
                 target_minus_image_depth_m_q10_q50_q90=[q(D_, .1), q(D_, .5), q(D_, .9)], image_point_above_target_m_q10_q50_q90=[q(U_, .1), q(U_, .5), q(U_, .9)],
                 image_point_to_nearest_gt_m_q10_q50_q90=[q(GD, .1), q(GD, .5), q(GD, .9)], image_point_within_0p5m_of_gt_pct=100*float((GD <= .5).mean()),
                 image_point_within_2m_of_gt_pct=100*float((GD <= 2).mean()), confidence_q10_q50_q90=[q(CF, .1), q(CF, .5), q(CF, .9)],
                 rule=__doc__.split('\n')[1])]
    table(f'front10_pixels_{stem}', rows)
    fig, ax = plt.subplots(len(ex), 3, figsize=(13, 3.3*len(ex)), constrained_layout=True, squeeze=False); meta_out = []
    for r_, name in enumerate(ex):
        a = loadz(O/'maps/base/base'/stem/f'{name}.npz', ['depth', 'owner']); f10 = loadz(O/'maps/base/ga'/stem/f'{name}.npz', ['front_rule'])['front_rule']
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy'); own = a['owner']; has = own >= 0
        m = f10 & has & np.isfinite(gt) & (np.abs(a['depth'] - gt) <= np.where(has, ptau[np.maximum(own, 0)], 0))
        dens = uniform_filter(m.astype('f4'), size=(160, 220)); cy, cx = np.unravel_index(np.argmax(dens), dens.shape)
        y0, x0 = int(np.clip(cy - 80, 0, 741 - 160)), int(np.clip(cx - 110, 0, 1024 - 220)); sl = (slice(y0, y0 + 160), slice(x0, x0 + 220))
        img = np.asarray(Image.open(S0/'fork_inputs/s61'/site/f'scene_{prior}'/'images'/f'{name}.jpg').convert('RGB').resize((1024, 741)))
        mvs = np.load(mroot/'mvs'/f'{name}.npy'); dt = np.where(has, a['depth'], np.nan); edge = binary_dilation(m[sl], iterations=1) & ~m[sl]
        lo_, hi_ = np.nanpercentile(np.r_[dt[sl][np.isfinite(dt[sl])], mvs[sl][np.isfinite(mvs[sl]) & (mvs[sl] > 0)]], [2, 98])
        ov = np.zeros(m[sl].shape + (4,)); ov[m[sl]] = [1, 0, 1, .45]
        ax[r_, 0].imshow(img[sl]); ax[r_, 0].imshow(ov); ax[r_, 0].set_title(f'사진 (분홍 = 맞는 목표가 10 m 규칙으로 빠진 화소)', fontsize=9)
        ax[r_, 1].imshow(np.where(mvs[sl] > 0, mvs[sl], np.nan), cmap='viridis', vmin=lo_, vmax=hi_); ax[r_, 1].set_title('영상 깊이', fontsize=9)
        im = ax[r_, 2].imshow(dt[sl], cmap='viridis', vmin=lo_, vmax=hi_); ax[r_, 2].contour(m[sl], levels=[.5], colors='m', linewidths=.6); ax[r_, 2].set_title('판 0 목표 깊이 (분홍 테두리 = 빠진 화소)', fontsize=9)
        fig.colorbar(im, ax=ax[r_, 1:], shrink=.8, label='깊이 (m)')
        for c_ in range(3): ax[r_, c_].axis('off')
        meta_out.append(dict(view=name, crop_xy=[x0, y0, 220, 160], removed_right_pixels_view=int(m.sum()), removed_right_pixels_crop=int(m[sl].sum())))
    fig.suptitle(f'{STEM_KO[stem]}: 10 m 규칙으로 빠진, 목표가 맞던 화소'); p = D/'figures'/f'front10_examples_{stem}'; fig.savefig(p.with_suffix('.png'), dpi=110); fig.savefig(p.with_suffix('.pdf')); plt.close(fig)
    dump(p.with_suffix('.json'), dict(stem=stem, examples=meta_out, stats=rows[0], rule=__doc__, scientific_verdict=None)); print('FRONT10', json.dumps(rows[0], ensure_ascii=False)[:900], flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
