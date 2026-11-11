"""Render every saved state after training (order 3 '학습 중 렌더'), r27 renderer = FINALTRAIN rfix speed .so, inference only.
View camera: PROCFIG rank-1 direction (az 180, el 35), far perspective; building-scope Gaussians only.
Two training images: full scene, active SH degree, black background (as training); per-pixel max alpha*T id (TARGET r5 maxid .so)."""
import sys, math, time, importlib.util
from types import SimpleNamespace
from common import *
sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
import torch
import diff_surfel_rasterization as raster
from scene import GaussianModel
from gaussian_renderer import render
from PIL import Image
import matplotlib; matplotlib.use('Agg'); from matplotlib import cm
MAXID = PH/'main_target_v1/PHD-MAIN-TARGET-v1/r5/runtime/maxid_build/jbgs_target_r5_maxid.so'

def camera(W, H, K, W2C, name):
    zn, zf = .01, 2000.
    P = np.zeros((4, 4), 'f4'); P[0, 0] = 2*K[0, 0]/W; P[1, 1] = 2*K[1, 1]/H; P[0, 2] = (2*K[0, 2]-(W-1))/W; P[1, 2] = (2*K[1, 2]-(H-1))/H; P[2, 2] = zf/(zf-zn); P[2, 3] = -zf*zn/(zf-zn); P[3, 2] = 1
    w = torch.tensor(np.asarray(W2C), device='cuda', dtype=torch.float32).T; p = torch.tensor(P, device='cuda').T
    return SimpleNamespace(image_width=W, image_height=H, image_name=name, FoVx=2*math.atan(W/(2*K[0, 0])), FoVy=2*math.atan(H/(2*K[1, 1])), znear=zn, zfar=zf,
                           world_view_transform=w, projection_matrix=p, full_proj_transform=w@p, camera_center=w.inverse()[3, :3])

def view_camera(c):
    vc = c['renders']['view_camera']; up = np.array(c['coordinates']['up']); up /= np.linalg.norm(up)
    east = np.array([1., 0, 0]); east -= (east@up)*up; east /= np.linalg.norm(east); north = np.cross(up, east)
    a, e = np.radians(vc['azimuth_deg']), np.radians(vc['elevation_deg'])
    out = np.cos(e)*(np.cos(a)*east+np.sin(a)*north)+np.sin(e)*up; f = -out; r = np.cross(f, up); r /= np.linalg.norm(r); u = np.cross(r, f)
    g_ = c['scope']['buffered_footprint']; rings = g_['coordinates'] if g_['type'] == 'Polygon' else [r for poly in g_['coordinates'] for r in poly]
    xy = np.concatenate([np.asarray(r, float)[:, :2] for r in rings]); b = (xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()); z0, z1 = c['scope']['z_min'], c['scope']['z_max']
    corners = np.array([[x, y, z] for x in (b[0], b[2]) for y in (b[1], b[3]) for z in (z0, z1)]); ctr = corners.mean(0)
    W, H, D_ = vc['width'], vc['height'], 500.
    q = (corners-ctr)@np.stack([r, u]).T; width = max(np.ptp(q[:, 0]), np.ptp(q[:, 1])*W/H)*1.08
    fx = (W/2)/(width/2/D_); K = np.array([[fx, 0, W/2], [0, fx, H/2], [0, 0, 1]]); C = ctr-f*D_
    Rw = np.stack([r, -u, f]); t = -Rw@C; W2C = np.eye(4); W2C[:3, :3] = Rw; W2C[:3, 3] = t
    depth = (corners-C)@f
    return dict(W=W, H=H, K=K, W2C=W2C, basis=np.stack([r, u, f]).tolist(), center=ctr.tolist(), distance_m=D_, ortho_width_m=width, depth_range=[float(depth.min()), float(depth.max())])

def colour(x, lo, hi, cmap='viridis', mask=None):
    v = np.clip((x-lo)/(hi-lo), 0, 1); rgb = (getattr(cm, cmap)(v)[..., :3]*255).astype('u1')
    if mask is not None: rgb[~mask] = 255
    return rgb

def load(path, keep=None):
    d = torch.load(path, map_location='cpu', weights_only=False); g = GaussianModel(3)
    for name, key in [('_xyz', 'xyz'), ('_features_dc', 'f_dc'), ('_features_rest', 'f_rest'), ('_opacity', 'opacity'), ('_scaling', 'scaling'), ('_rotation', 'rotation')]:
        t = d[key] if keep is None else d[key][keep]
        setattr(g, name, torch.nn.Parameter(t.cuda().contiguous(), requires_grad=False))
    g.active_sh_degree = int(d['active_sh_degree']); return g, d

@torch.no_grad()
def main(only=None):
    c = cfg(); torch.cuda.set_per_process_memory_fraction(.6)
    run = RUNM/'trainlog'; saves = [json.loads(l) for l in (run/'saves.jsonl').read_text().splitlines()]
    choice = json.loads((D/'camera_choice.json').read_text())['chosen']; views = {v['name']: v for v in json.loads((RS/'views'/f'{SITE}.json').read_text())['views']}
    trains = [views[x['name']] for x in choice]; vc = view_camera(c); light = np.array(c['renders']['light']); light /= np.linalg.norm(light)
    from renderer import install
    install(); rfix = raster._C; spec =importlib.util.spec_from_file_location('jbgs_target_r5_maxid', MAXID); maxid = importlib.util.module_from_spec(spec); spec.loader.exec_module(maxid)
    pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
    photos = {v['name']: np.asarray(Image.open(f'/p/fork_inputs/s61/{SITE}/scene_{PRIOR}/images/{v["name"]}.jpg').convert('RGB'), np.float32)/255. for v in trains}
    dump(O/'renders/cameras.json', dict(view=dict({k: (v.tolist() if hasattr(v, 'tolist') else v) for k, v in vc.items()}, azimuth_deg=180, elevation_deg=35, scope_only=True),
         training=[dict(name=v['name'], K=v['K'], W2C=v['W2C'], width=v['width'], height=v['height']) for v in trains], scientific_verdict=None))
    for sv in saves:
        name = sv['name']
        if only and name not in only: continue
        root = O/'renders'/name
        if (root/'render.json').exists(): continue
        root.mkdir(parents=True, exist_ok=True); t0 = time.monotonic()
        g, d = load(run/'scene'/f'{name}.pt'); inside = d['inside'].cuda(); rec = dict(name=name, iteration=sv['iteration'], gaussians=len(d['xyz']))
        arrays = {}
        # view camera: building-scope Gaussians only
        gv = GaussianModel(3)
        for a in ['_xyz', '_features_dc', '_features_rest', '_opacity', '_scaling', '_rotation']: setattr(gv, a, torch.nn.Parameter(getattr(g, a)[inside].contiguous(), requires_grad=False))
        gv.active_sh_degree = g.active_sh_degree
        cams = [('view', camera(vc['W'], vc['H'], vc['K'], vc['W2C'], 'view'), gv)] + [(f'train{i+1}', camera(v['width'], v['height'], np.asarray(v['K']), np.asarray(v['W2C']), v['name']), g) for i, v in enumerate(trains)]
        for key, cam, model in cams:
            raster._C = rfix; pkg = render(cam, model, pipe, bg)
            rgb = pkg['render'].permute(1, 2, 0).clamp(0, 1).cpu().numpy(); depth = pkg['surf_depth'].squeeze().cpu().numpy(); alpha = pkg['rend_alpha'].squeeze().cpu().numpy()
            normal = pkg['rend_normal'].permute(1, 2, 0).cpu().numpy(); nn_ = normal/np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-8)
            shade = (.55+.45*np.abs(nn_@light)); m = alpha > .5
            Image.fromarray((rgb*255).astype('u1')).save(root/f'{key}_rgb.png')
            Image.fromarray(((nn_*.5+.5).clip(0, 1)*255).astype('u1')*m[..., None]+255*(~m[..., None]).astype('u1')).save(root/f'{key}_normal.png')
            Image.fromarray(np.where(m, shade*235, 255).astype('u1')).save(root/f'{key}_shade.png')
            lo, hi = (vc['depth_range'] if key == 'view' else (float(np.percentile(depth[m], 1)) if m.any() else 0., float(np.percentile(depth[m], 99)) if m.any() else 1.))
            if key != 'view':
                if 'train_depth_range' not in rec: rec['train_depth_range'] = {}
            Image.fromarray(colour(depth, lo, hi, mask=m)).save(root/f'{key}_depth.png')
            Image.fromarray((alpha.clip(0, 1)*255).astype('u1')).save(root/f'{key}_alpha.png')
            arrays[f'{key}_depth'] = depth.astype('f4'); arrays[f'{key}_alpha'] = alpha.astype('f2'); arrays[f'{key}_normal'] = normal.astype('f2')
            if key != 'view':
                ph = photos[cam.image_name]; diff = np.abs(rgb-ph).mean(2); mse = float(((rgb-ph)**2).mean()); rec[f'{key}_psnr'] = float(10*np.log10(1/mse)); rec[f'{key}_camera'] = cam.image_name
                Image.fromarray(colour(diff, 0, .5, 'magma')).save(root/f'{key}_diff.png')
                raster._C = maxid; pk = render(cam, model, pipe, bg); idx = np.rint(pk['rend_dist'].squeeze().cpu().numpy()).astype('i8')-1
                same = float(np.abs(pk['surf_depth'].squeeze().cpu().numpy()-depth)[alpha > 0].max()) if (alpha > 0).any() else 0.
                uid = np.where(idx >= 0, d['uid'].numpy()[idx.clip(0)], -1); arrays[f'{key}_maxid_full'] = idx.astype('i4'); arrays[f'{key}_maxid_uid'] = uid
                rec[f'{key}_maxid_depth_max_abs_diff_m'] = same; rec[f'{key}_maxid_pixels'] = int((idx >= 0).sum())
        raster._C = rfix; savez(root/'data.npz', **arrays); rec['seconds'] = time.monotonic()-t0; rec['scientific_verdict'] = None; dump(root/'render.json', rec)
        print('RENDERED', name, round(rec['seconds'], 1), rec.get('train1_psnr'), rec.get('train2_psnr'), flush=True)
        del g, gv, d; torch.cuda.empty_cache()
if __name__ == '__main__': main(sys.argv[1:] or None)
