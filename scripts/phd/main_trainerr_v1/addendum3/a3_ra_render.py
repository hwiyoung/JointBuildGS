"""Work ra (order 6, diagnostic only): the inherited mesh render step (RESCORE render_model.py, used by GTJUDGE mesh_job 'render') with one pixel rule
added before the depth is handed to the unchanged TSDF recipe. Runs in the gtj container (/gtjudge = addendum3 shadow, /source = r30, speed renderer installed).
argv: <stem> <variant>   variants (addendum3.json work_ra.variants): base | opacity_0.5 | opacity_0.8 | discontinuity_0.5 | median_depth
Writes /gtjudge/jobs/<stem>__ra_<variant>.json and /gtjudge/renders/<stem>__ra_<variant>/NNNN.npz + receipt.json in the render_model layout."""
import sys, importlib.util, math, time
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import *
sys.path.insert(0, '/source')
import torch
from scene import GaussianModel
from gaussian_renderer import render
from types import SimpleNamespace
FT_RUNS = Path('/art/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs')

@torch.no_grad()
def main(stem, variant):
    assert variant in ('base', 'opacity_0.5', 'opacity_0.8', 'discontinuity_0.5', 'median_depth')
    cfg(); start = time.monotonic(); site, prior = stem.split('__'); fam = f'ra_{variant}'; key = f'{stem}__{fam}'; view = ensure_views(site)
    ply = FT_RUNS/site/f'ft_{prior}_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply'
    jobp = O/'jobs'/f'{key}.json'
    if not jobp.exists(): dump(jobp, dict(key=key, site=site, prior=prior, family=fam, box=view['box'], ply=str(ply), variant=variant))
    job = json.loads(jobp.read_text()); rm = module('render_model'); module('renderer', 'main_finaltrain_v1').install()
    root = O/'renders'/key; root.mkdir(parents=True, exist_ok=True); views = json.loads((O/'views'/f'{site}.json').read_text())['views']; box = np.array(job['box'])
    names = []
    with ply.open('rb') as f:
        while True:
            line = f.readline().decode('ascii').strip()
            if line == 'end_header': break
            if line.startswith('property') and 'f_rest_' in line: names.append(line)
    g = GaussianModel(round(math.sqrt(len(names)/3+1)-1)); g.load_ply(str(ply)); inside = ((g.get_xyz >= torch.tensor(box[0], device='cuda')) & (g.get_xyz <= torch.tensor(box[1], device='cuda'))).all(1)
    for a in ['_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity']: setattr(g, a, torch.nn.Parameter(getattr(g, a).detach()[inside].clone(), requires_grad=False))
    g.active_sh_degree = 0; pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=1. if variant == 'median_depth' else 0., debug=False); bg = torch.zeros(3, device='cuda')
    records = []; removed = 0; kept = 0
    for i, v in enumerate(views):
        cam = rm.camera(v); pkg = render(cam, g, pipe, bg); depth = pkg['surf_depth'].reshape(v['height'], v['width']); alpha = pkg['rend_alpha'].reshape(v['height'], v['width'])
        H, W = depth.shape; K = np.array(v['K']); yy, xx = torch.meshgrid(torch.arange(H, device='cuda'), torch.arange(W, device='cuda'), indexing='ij')
        xyz = torch.stack([(xx-K[0, 2])*depth/K[0, 0], (yy-K[1, 2])*depth/K[1, 1], depth, torch.ones_like(depth)], -1); world = xyz@cam.world_view_transform.inverse()
        mask = ((world[..., :3] >= torch.tensor(box[0], device='cuda')) & (world[..., :3] <= torch.tensor(box[1], device='cuda'))).all(-1) & (depth > 0)   # inherited rule
        rule = torch.ones_like(mask)
        if variant.startswith('opacity'): rule = alpha >= float(variant.split('_')[1])
        elif variant == 'discontinuity_0.5':
            jump = torch.zeros_like(mask)
            jump[:, 1:] |= (depth[:, 1:]-depth[:, :-1]).abs() > .5; jump[:, :-1] |= (depth[:, :-1]-depth[:, 1:]).abs() > .5
            jump[1:, :] |= (depth[1:, :]-depth[:-1, :]).abs() > .5; jump[:-1, :] |= (depth[:-1, :]-depth[1:, :]).abs() > .5; rule = ~jump
        removed += int((mask & ~rule).sum()); kept += int((mask & rule).sum()); mask = mask & rule
        d = depth.cpu().numpy().copy(); d[~mask.cpu().numpy()] = 0
        rgb = (pkg['render'].permute(1, 2, 0).clamp(0, 1).cpu().numpy()*255).astype('u1'); p = root/f'{i:04d}.npz'; savez(p, depth=d, rgb=rgb); records.append(dict(v, file=p.name, sha256=sha(p)))
        if i % 40 == 0: print('RA_RENDER', key, i+1, len(views), flush=True)
    dump(root/'receipt.json', dict(status='PASS', views=records, cached_views=0, box=box.tolist(), model_sha256=sha(ply), variant=variant, depth_ratio=pipe.depth_ratio,
         pixels_removed_by_rule=removed, pixels_kept=kept, inherited_source=str(R/'scripts/phd/main_rescore_v1/render_model.py'), renderer_sha256=sha('/source/gaussian_renderer/__init__.py'), job=job,
         seconds=time.monotonic()-start, rule='inherited render_model depth/box mask; then the variant rule (addendum3.json work_ra.variants)', scientific_verdict=None))
    print('RA_RENDER_DONE', key, removed, kept, flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
