"""Request 2 item 3 (pre-training): target depth maps of 판 1 (discs) and 판 9 (cells) side by side at the five site places, the same training view as the
site figures (case_<place>_<stem>_p0.json 'view'), crop around the section line. Panels: photo, 판 1 target depth, 판 9 target depth (pixels that 판 1 gives a disc
target but 판 9 gives image depth / a target behind it / nothing outlined). No GT. usage: df25_fig_cellmap.py   writes /docs/figures/cellmap_<place>.png/.pdf/.json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import df15_case as C15
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
PLACES = [('R1_floor_band', 'R1rep_b10__ALS'), ('R1_sawtooth_valley', 'R1rep_b10__LoD2'), ('R1_round_wall', 'R1rep_b10__LoD2'), ('B173_rooftop_structure', 'B173nb_b10__LoD2'), ('B173_wing', 'B173nb_b10__ALS')]

def main(va='ga', vb='cell_ga', la='판 1 목표 깊이 (원반)', lb='판 9 목표 깊이 (칸)', tag=''):
    c = cfg(False); out = []
    for place, stem in PLACES:
        site, prior = stem.split('__'); roof, wall = tau_of(site, prior)
        view = json.loads((D/'figures'/f'case_{place}_{stem}_p0.json').read_text())['view']
        tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['centre', 'normal', 'area', 'prior_height_m', 'mvs_mean_m', 'target', 'surface_exists', 'kind'])
        A, B = C15.line_of(place, stem, c, tb); h = np.r_[(B - A)/np.linalg.norm(B - A), 0]; e = np.cross([0, 0, 1.], h); o = np.r_[(A + B)/2, 0]; L = np.linalg.norm(B - A)
        rel = tb['centre'] - o; pids = np.flatnonzero((np.abs(rel@e) <= .25) & (np.abs(rel@h) <= L/2) & tb['surface_exists'])
        zl = np.nanmedian(tb['centre'][pids, 2]) if len(pids) else 0.
        meta = json.loads((O/'maps/base/ga'/stem/'index.json').read_text())['views'][view]; K = np.asarray(meta['K']); M = np.asarray(meta['W2C'])
        q = np.c_[np.r_[A[None], B[None]], np.full(2, zl)]@M[:3, :3].T + M[:3, 3]; uv = np.c_[K[0, 0]*q[:, 0]/q[:, 2] + K[0, 2], K[1, 1]*q[:, 1]/q[:, 2] + K[1, 2]]
        lo_, hi_ = uv.min(0) - 90, uv.max(0) + 90; x0, x1 = int(np.clip(lo_[0], 0, 1023)), int(np.clip(hi_[0], 1, 1024)); y0, y1 = int(np.clip(lo_[1], 0, 740)), int(np.clip(hi_[1], 1, 741)); sl = (slice(y0, y1), slice(x0, x1))
        g = loadz(O/'maps/base'/va/stem/f'{view}.npz', ['depth', 'owner', 'weight']); k = loadz(O/'maps/base'/vb/stem/f'{view}.npz', ['depth', 'owner', 'weight'])
        gh = (g['owner'] >= 0) & (g['weight'] > 0); kh = k['owner'] >= 0; ptau = np.where(tb['kind'] == 2, wall if prior == 'LoD2' else roof, roof)
        gap = gh & (~kh | (kh & (k['depth'] > g['depth'] + np.where(gh, ptau[np.maximum(g['owner'], 0)], 0))))
        img = np.asarray(Image.open(S0/'fork_inputs/s61'/site/f'scene_{prior}'/'images'/f'{view}.jpg').convert('RGB').resize((1024, 741)))
        d1 = np.where(g['owner'] >= 0, g['depth'], np.nan)[sl]; d9 = np.where(kh, k['depth'], np.nan)[sl]; vv = np.r_[d1[np.isfinite(d1)], d9[np.isfinite(d9)]]
        vmin, vmax = (np.percentile(vv, [2, 98]) if len(vv) else (0, 1))
        fig, ax = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
        ax[0].imshow(img[sl]); ax[0].plot(uv[:, 0] - x0, uv[:, 1] - y0, 'y-', lw=2); ax[0].set_title('사진 (노란 선 = 단면)')
        ax[1].imshow(d1, cmap='viridis', vmin=vmin, vmax=vmax); ax[1].set_title(la)
        im = ax[2].imshow(d9, cmap='viridis', vmin=vmin, vmax=vmax); ax[2].contour(gap[sl], levels=[.5], colors='m', linewidths=.5)
        ax[2].set_title(f'{lb} · 분홍 테두리 = 왼쪽 목표가 이 지도에서 빠지거나 뒤로 간 화소 ({int(gap[sl].sum()):,})', fontsize=9)
        fig.colorbar(im, ax=ax[1:], shrink=.8, label='깊이 (m)')
        for a_ in ax: a_.axis('off')
        fig.suptitle(f'{C15.LABEL[place]} ({STEM_KO[stem]}): 목표 깊이 지도'); p = D/'figures'/(f'cellmap_{place}' + (f'_{tag}' if tag else '')); fig.savefig(p.with_suffix('.png'), dpi=100); fig.savefig(p.with_suffix('.pdf')); plt.close(fig)
        r = dict(place=place, stem=stem, view=view, crop=[x0, y0, x1, y1], gap_pixels_crop=int(gap[sl].sum()), disc_target_pixels_crop=int(gh[sl].sum()), cell_target_pixels_crop=int(kh[sl].sum()), scientific_verdict=None)
        dump(p.with_suffix('.json'), r); out.append(r)
    print('CELLFIG', json.dumps(out, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
