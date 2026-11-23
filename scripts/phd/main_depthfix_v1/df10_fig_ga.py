"""Order 7 (판 1 figure): one training view's target depth map, 판 0 beside 판 1, with the pixels whose instruction switch 가 removes coloured per rule.
R1 × LoD2: the view that sees most of the round-building wall place; R1 × 항공 LiDAR: the view that sees most floor-band points (outward, in frame).
No GT, no result used to pick the view. usage: df10_fig_ga.py   writes /docs/figures/ga_map_<stem>.png/.pdf/.json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = font_manager.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'

def pick_view(stem, pids):
    """the training view whose 판 0 target map has the most pixels owned by the place's patches (no GT, no result)."""
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']; best = None; mask = np.zeros(10**7, bool); mask[pids] = True
    for name in idx:
        own = loadz(O/'maps/base/base'/stem/f'{name}.npz', ['owner'])['owner']; n = int(mask[own[own >= 0]].sum())
        if best is None or n > best[1]: best = (name, n)
    return best

def main():
    c = cfg(False); out = []
    tb = {s: loadz(O/'families/base/targets'/f'{s}.npz', ['centre', 'kind', 'in_eval', 'surface_exists', 'target', 'normal']) for s in ['R1rep_b10__LoD2', 'R1rep_b10__ALS']}
    rw = c['places']['R1_round_wall']; t = tb['R1rep_b10__LoD2']; ce = np.asarray(rw['centre_xy'])
    m = (t['kind'] == 2) & t['in_eval'] & (np.abs(t['centre'][:, :2] - ce).max(1) <= rw['half_m']); wall_ids = np.flatnonzero(m)
    from scipy.spatial import cKDTree
    fb = loadz(TE/'addendum4/places/floor_band.npz'); fbp = fb[[k for k in fb if 'xyz' in k][0]].astype('f8'); ta = tb['R1rep_b10__ALS']
    d_, j_ = cKDTree(ta['centre']).query(fbp, distance_upper_bound=.5); fb_ids = np.unique(j_[np.isfinite(d_)])
    for stem, pids, place in [('R1rep_b10__LoD2', wall_ids, '둥근 건물 벽'), ('R1rep_b10__ALS', fb_ids, '바닥 띠')]:
        name, n = pick_view(stem, pids); site = stem.split('__')[0]
        zb = loadz(O/'maps/base/base'/stem/f'{name}.npz'); zg = loadz(O/'maps/base/ga'/stem/f'{name}.npz'); meta = json.loads((O/'maps/base/ga'/stem/'index.json').read_text())['views'][name]
        tt = tb[stem]; ids = np.flatnonzero(tt['surface_exists']); Cc = cam_centre(np.asarray(meta['W2C'])); front = np.zeros(len(tt['centre']), bool)
        front[ids] = ((Cc[None] - tt['target'][ids])*tt['normal'][ids]).sum(1) > 0
        hb = zb['owner'] >= 0; back = hb & ~front[np.maximum(zb['owner'], 0)]; f10 = zg['front_rule']
        img = Image.open(S0/'fork_inputs/s61'/site/f'scene_{stem.split("__")[1]}'/'images'/f'{name}.jpg').convert('RGB').resize((1024, 741))
        fig, ax = plt.subplots(1, 3, figsize=(15, 4.2), constrained_layout=True)
        ax[0].imshow(img); ax[0].set_title(f'사진 ({place}이 보이는 영상)')
        dm = np.where(hb, zb['depth'], np.nan); lo_, hi_ = np.nanpercentile(dm, [2, 98])
        for a_, d_, title in [(ax[1], np.where(hb, zb['depth'], np.nan), '판 0 목표 깊이'), (ax[2], np.where(zg['owner'] >= 0, zg['depth'], np.nan), '판 1 목표 깊이')]:
            im = a_.imshow(d_, cmap='viridis', vmin=lo_, vmax=hi_); a_.set_title(title)
        ov = np.zeros((741, 1024, 4)); ov[back] = [1, .5, 0, .9]; ov[f10] = [.9, 0, .9, .9]; ax[2].imshow(ov)
        fig.colorbar(im, ax=ax[1:], shrink=.8, label='깊이 (m)')
        from matplotlib.patches import Patch
        ax[2].legend(handles=[Patch(color=(1, .5, 0), label=f'뒷면으로 빠짐 ({int(back.sum()):,})'), Patch(color=(.9, 0, .9), label=f'10 m로 무게 0 ({int(f10.sum()):,})')], loc='lower right', fontsize=8)
        for a_ in ax: a_.axis('off')
        p = D/'figures'/f'ga_map_{stem}'; p.parent.mkdir(exist_ok=True); fig.savefig(p.with_suffix('.png'), dpi=110); fig.savefig(p.with_suffix('.pdf')); plt.close(fig)
        rec = dict(stem=stem, view=name, place=place, place_owner_pixels=n, back_removed_pixels=int(back.sum()), front10_pixels=int(f10.sum()), target_pixels_p0=int(hb.sum()),
                   rule='영상 = 판 0 목표 지도에서 자리의 패치(둥근 벽: 설정 places R1_round_wall 상자의 LoD2 벽 패치, 바닥 띠: TRAINERR 덧붙임 4 floor_band 점에서 0.5 m 안의 패치)가 가진 화소가 가장 많은 학습 영상', scientific_verdict=None)
        dump(p.with_suffix('.json'), rec); out.append(rec)
    print('FIG_GA', json.dumps(out, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
