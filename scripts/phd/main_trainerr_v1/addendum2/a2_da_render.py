"""Addendum 2 work 다 render (GPU container, fork r28 renderer): arm 30000 model RGB at each crop pinhole camera of addendum2/da/selection.json -> addendum2/da/render_<arm>_<group>.png."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
from te_render import *
from types import SimpleNamespace
from PIL import Image
STEM, SITE = 'B0_b10__ALS', 'B0_b10'
def model_dir(arm):
    if arm == 'own': return FT/'runs'/SITE/'ft_ALS_s0/attempt1/model'
    for a in ['attempt2', 'attempt1']:
        p = GT/'runs'/SITE/'gt_ALS_s0'/a/'model'
        if (p/'point_cloud/iteration_30000/point_cloud.ply').exists() and (p/'target_monitor/snapshot_30000.npz').exists(): return p
@torch.no_grad()
def main():
    from renderer import install; install()
    A2O = O/'addendum2'; sel = json.loads((A2O/'da/selection.json').read_text())['selection']; box = np.array(json.loads((GT/'views'/f'{SITE}.json').read_text())['box'])
    pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda'); out = {}
    for arm in ARMS:
        ply = model_dir(arm)/'point_cloud/iteration_30000/point_cloud.ply'; g, _ = load_model(ply, box)
        for grp, s in sel.items():
            W, H = s['size']; pkg = render(camera(W, H, np.asarray(s['K_crop']), np.asarray(s['W2C']), s['image']), g, pipe, bg)
            img = (pkg['render'].clamp(0, 1).permute(1, 2, 0).cpu().numpy()*255+.5).astype('u1'); p = A2O/'da'/f'render_{arm}_{grp}.png'; Image.fromarray(img).save(p)
            out[f'{arm}_{grp}'] = dict(file=str(p), model=str(ply), alpha_mean=float(pkg['rend_alpha'].mean()))
        del g; torch.cuda.empty_cache()
    dump(A2O/'da/render.json', dict(at=now(), renders=out, model_box=box.tolist(), background='black', sh='degree 0 (te_render.load_model)', scientific_verdict=None)); print('DA_RENDER', list(out), flush=True)
if __name__ == '__main__': main()
