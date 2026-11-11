"""Order 5.4 (optional): fixed-camera depth strip. Two training images x six key iterations: mesh-render surf_depth (same renders as
the meshes: SH0, RESCORE box) and difference to the original plate's 30,000 render (FINALTRAIN meshes/B173nb_b10__ALS/render). CPU."""
from frames import *

def depth_of(receipt_dir, name):
    rec = json.loads((receipt_dir/'receipt.json').read_text()); v = next(v for v in rec['views'] if v['name'] == name); return loadz(receipt_dir/v['file'], ['depth'])['depth']

def main():
    c = cfg(); its = c['figures']['strip']['iterations']; cams = [x['name'] for x in json.loads((D/'camera_choice.json').read_text())['chosen']]
    orig = FT/'meshes'/STEM/'render'; fig, axs = plt.subplots(4, len(its), figsize=(3.1*len(its), 9.2), facecolor='white'); recs = {}
    for r, cam in enumerate(cams):
        o = depth_of(orig, cam); m = o > 0; lo, hi = np.percentile(o[m], [1, 99])
        for j, it in enumerate(its):
            d = depth_of(O/'gtj/renders'/f'{STEM}__tl_{it}', cam); a = axs[2*r, j]; b = axs[2*r+1, j]
            a.imshow(np.where(d > 0, d, np.nan), cmap='viridis', vmin=lo, vmax=hi); diff = np.where((d > 0) & m, d-o, np.nan)
            b.imshow(diff, cmap='RdBu_r', vmin=-1, vmax=1)
            for x in (a, b): x.set_xticks([]); x.set_yticks([])
            if r == 0: a.set_title(f'{it:,}회', fontsize=12, color='#16263d')
            recs[f'{cam}_{it}'] = dict(median_abs_diff_m=float(np.nanmedian(np.abs(diff))) if np.isfinite(diff).any() else None, valid_pixels=int(np.isfinite(diff).sum()))
        axs[2*r, 0].set_ylabel(f'영상 {r+1} 깊이', fontsize=11); axs[2*r+1, 0].set_ylabel(f'영상 {r+1} − 원래 판 30,000회', fontsize=10)
    fig.colorbar(plt.cm.ScalarMappable(cmap='RdBu_r', norm=plt.Normalize(-1, 1)), ax=axs[:, -1], fraction=.03, label='깊이 차 (m)')
    out = O/'figures'; out.mkdir(exist_ok=True); fig.savefig(out/'strip_B173_고정카메라깊이_v1.png', dpi=200, facecolor='white'); plt.close(fig)
    dump(out/'strip_B173_고정카메라깊이_v1.json', dict(at=now(), iterations=its, cameras=cams, depth='mesh-render surf_depth (SH0, RESCORE box crop)', reference='original FINALTRAIN 30,000 render of the same view',
         colour=dict(depth='viridis, per-image 1-99 percentile of the original', difference='RdBu_r ±1 m'), values=recs, plate='새 판 (다시 돌린 판) 대 원래 판', scientific_verdict=None))
    print('DEPTHSTRIP', recs, flush=True)
if __name__ == '__main__': main()
