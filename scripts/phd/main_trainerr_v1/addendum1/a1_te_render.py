import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')  # addendum-1 copy of te_render.py: views/render under PH/.../addendum1/
"""Stage 2 (GPU): for every seen (point, view) pair of views/<name>.npz: the max alpha*T Gaussian at the pixel (TARGET r5 maxid rasterizer,
PROCFIG/TRAINLOG lineage rule), render depth (surf_depth, camera z) and render alpha of a 30000 model. Gaussians cropped to the mesh-render box,
SH degree 0 (RESCORE render_model rule). The speed renderer depth at the same pixels is recorded for the renderer check.
argv: <stem> <arm> [ply] [tag] [drop_file] [views_name]   (drop_file: npz with full_index of Gaussians removed = opacity 0, check 6 simulations)"""
import math, importlib.util
from types import SimpleNamespace
from common import *
sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
import torch
import diff_surfel_rasterization as raster
from scene import GaussianModel
from gaussian_renderer import render

def camera(W, H, K, W2C, name):  # TRAINLOG render_states.camera (unchanged)
    zn, zf = .01, 2000.
    P = np.zeros((4, 4), 'f4'); P[0, 0] = 2*K[0, 0]/W; P[1, 1] = 2*K[1, 1]/H; P[0, 2] = (2*K[0, 2]-(W-1))/W; P[1, 2] = (2*K[1, 2]-(H-1))/H; P[2, 2] = zf/(zf-zn); P[2, 3] = -zf*zn/(zf-zn); P[3, 2] = 1
    w = torch.tensor(np.asarray(W2C), device='cuda', dtype=torch.float32).T; p = torch.tensor(P, device='cuda').T
    return SimpleNamespace(image_width=W, image_height=H, image_name=name, FoVx=2*math.atan(W/(2*K[0, 0])), FoVy=2*math.atan(H/(2*K[1, 1])), znear=zn, zfar=zf,
                           world_view_transform=w, projection_matrix=p, full_proj_transform=w@p, camera_center=w.inverse()[3, :3])

def load_model(ply, box, drop=None):
    with Path(ply).open('rb') as f:
        names = []
        while True:
            line = f.readline().decode('ascii').strip()
            if line == 'end_header': break
            if line.startswith('property') and 'f_rest_' in line: names.append(line)
    g = GaussianModel(round(math.sqrt(len(names)/3+1)-1)); g.load_ply(str(ply))
    inside = ((g.get_xyz >= torch.tensor(box[0], device='cuda')) & (g.get_xyz <= torch.tensor(box[1], device='cuda'))).all(1)
    if drop is not None and len(drop): inside[torch.as_tensor(drop, device='cuda', dtype=torch.long)] = False
    full = torch.nonzero(inside).squeeze(1)
    for a in ['_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity']: setattr(g, a, torch.nn.Parameter(getattr(g, a).detach()[inside].clone(), requires_grad=False))
    g.active_sh_degree = 0; return g, full

@torch.no_grad()
def main(stem, arm, ply='', tag='', drop_file='', views_name=''):
    t = Timer(f'render_{stem}_{arm}{"_"+tag if tag else ""}'); site = stem.split('__')[0]; name = f'{stem}__{arm}' + (f'__{tag}' if tag else '')
    vj = json.loads((GT/'views'/f'{site}.json').read_text()); views = [v for v in vj['views'] if not v['virtual']]; box = np.array(vj['box'])
    ply = Path(ply) if ply else arm_paths(stem, arm)['model']/'point_cloud/iteration_30000/point_cloud.ply'
    pr = loadz((O/'addendum1')/'views'/f'{views_name or name}.npz', ['point', 'view', 'px', 'py'])
    drop = loadz(drop_file)['full_index'] if drop_file else None
    g, full = load_model(ply, box, drop); torch.cuda.set_per_process_memory_fraction(.3)
    pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
    spec = importlib.util.spec_from_file_location('jbgs_target_r5_maxid', MAXID); maxid = importlib.util.module_from_spec(spec); spec.loader.exec_module(maxid)
    from renderer import install
    speed = install()
    order = np.argsort(pr['view'], kind='stable'); vv = pr['view'][order]; bounds = np.searchsorted(vv, np.arange(len(views)+1))
    n = len(pr['view']); drawer = np.full(n, -1, np.int64); rdepth = np.full(n, np.nan, np.float32); ralpha = np.full(n, np.nan, np.float32); sdepth = np.full(n, np.nan, np.float32)
    keys = None
    for j, v in enumerate(views):
        sel = order[bounds[j]:bounds[j+1]]
        if not len(sel): continue
        cam = camera(v['width'], v['height'], np.asarray(v['K']), np.asarray(v['W2C']), v['name'])
        px = torch.as_tensor(pr['px'][sel].astype(np.int64), device='cuda'); py = torch.as_tensor(pr['py'][sel].astype(np.int64), device='cuda')
        raster._C = maxid; pkg = render(cam, g, pipe, bg); keys = keys or sorted(pkg)
        idx = torch.round(pkg['rend_dist'].squeeze()[py, px]).long()-1; ok = idx >= 0
        d = torch.full((len(sel),), -1, device='cuda', dtype=torch.long); d[ok] = full[idx[ok]]; drawer[sel] = d.cpu().numpy()
        rdepth[sel] = pkg['surf_depth'].squeeze()[py, px].cpu().numpy(); ralpha[sel] = pkg['rend_alpha'].squeeze()[py, px].cpu().numpy()
        raster._C = speed; sp = render(cam, g, pipe, bg); sdepth[sel] = sp['surf_depth'].squeeze()[py, px].cpu().numpy()
        if j % 60 == 0: print('RENDER', name, j, len(views), flush=True)
    diff = np.abs(rdepth-sdepth); fin = np.isfinite(diff)
    savez((O/'addendum1')/'render'/f'{name}.npz', drawer=drawer, rdepth=rdepth, ralpha=ralpha, sdepth=sdepth)
    dump((O/'addendum1')/'render'/f'{name}.json', dict(at=now(), stem=stem, arm=arm, ply=str(ply), ply_sha256=sha(ply), pairs=n, box=box.tolist(), cropped_gaussians=int(len(full)),
         dropped=0 if drop is None else int(len(drop)), drop_file=drop_file or None, render_keys=keys, maxid=str(MAXID), maxid_sha256=sha(MAXID),
         depth_maxid_vs_speed=dict(max_abs=float(diff[fin].max()) if fin.any() else None, p99=float(np.quantile(diff[fin], .99)) if fin.any() else None, pairs_over_1cm=int((diff[fin] > .01).sum())),
         seconds=t.done(), rule='TARGET r5 maxid id = round(rend_dist)-1 (max alpha*T), RESCORE render_model box crop and SH 0', scientific_verdict=None))
    print('RENDER_DONE', name, n, float(diff[fin].max()) if fin.any() else None, flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
