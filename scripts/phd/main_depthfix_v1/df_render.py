"""PHD-MAIN-DEPTHFIX-v1 render step: GTTARGET-v1 g3_render_model.py copied; only the variant names and the occlusion mask source changed
(variants base | occl10 | occlga, mask = /te/stage1x/<stem>/<variant>/<view>.npz 'occ', written by df5_occl.py). Original docstring: PHD-MAIN-GTTARGET-v1 order 7.1 (copied from TRAINERR addendum6 a6_ra_render.py; only the variant rules changed):
variants base | occl (no depth at the order-2 'occluded' pixels of order 4, gt/stage1/<stem>/occl) | median_depth | occl_median.
Original docstring: Work ra (order 6.1, diagnostic only): addendum3 a3_ra_render.py (the inherited RESCORE render_model render step used by GTJUDGE mesh_job 'render') with the
addendum6_c.json variants applied to the depth handed to the unchanged TSDF recipe. Runs in the gtj container (/gtjudge = addendum6 shadow, /source = r31).
argv: <stem> <family> <ply (container path)> <variant>   variants: base | occl_10 | median_depth | occl_10_median | target_only
Writes /gtjudge/jobs/<stem>__<family>.json and /gtjudge/renders/<stem>__<family>/NNNN.npz + receipt.json in the render_model layout."""
import sys, math, time
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import *
sys.path.insert(0, '/source')
import torch
from scene import GaussianModel
from gaussian_renderer import render
from types import SimpleNamespace
_ensure_views_inherited = ensure_views
def ensure_views(site):
    # issues 33: RESCORE meshes/B173nb_b10__ALS__r8_30000/final_work/inputs/meta.json (box source) was removed by another session's cleanup on 11-24;
    # this task's own views/<site>.json already holds the same box (written by the inherited ensure_views before), so read it first. Values unchanged.
    own = O/'views'/f'{site}.json'
    if own.exists():
        z = json.loads(own.read_text())
        if 'box' in z and 'views' in z: return z
    return _ensure_views_inherited(site)
STAGE1 = Path('/te/stage1'); MVS = Path('/art/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61')

@torch.no_grad()
def main(stem, fam, ply, variant):
    assert variant in ('base', 'occl10', 'occlga')
    cfg(); start = time.monotonic(); site, prior = stem.split('__'); key = f'{stem}__{fam}'; view = ensure_views(site); ply = Path(ply)
    jobp = O/'jobs'/f'{key}.json'
    if not jobp.exists(): dump(jobp, dict(key=key, site=site, prior=prior, family=fam, box=view['box'], ply=str(ply), variant=variant))
    job = json.loads(jobp.read_text()); rm = module('render_model'); module('renderer', 'main_finaltrain_v1').install()
    root = O/'renders'/key; root.mkdir(parents=True, exist_ok=True); views = json.loads((O/'views'/f'{site}.json').read_text())['views']; box = np.array(job['box'])
    mi = json.loads((STAGE1/stem/'maps/index.json').read_text())['views']
    names = []
    with ply.open('rb') as f:
        while True:
            line = f.readline().decode('ascii').strip()
            if line == 'end_header': break
            if line.startswith('property') and 'f_rest_' in line: names.append(line)
    g = GaussianModel(round(math.sqrt(len(names)/3+1)-1)); g.load_ply(str(ply)); inside = ((g.get_xyz >= torch.tensor(box[0], device='cuda')) & (g.get_xyz <= torch.tensor(box[1], device='cuda'))).all(1)
    for a in ['_xyz', '_features_dc', '_features_rest', '_scaling', '_rotation', '_opacity']: setattr(g, a, torch.nn.Parameter(getattr(g, a).detach()[inside].clone(), requires_grad=False))
    g.active_sh_degree = 0; pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
    records = []; removed = 0; kept = 0
    for i, v in enumerate(views):
        cam = rm.camera(v); pkg = render(cam, g, pipe, bg); depth = pkg['surf_depth'].reshape(v['height'], v['width'])
        H, W = depth.shape; K = np.array(v['K']); yy, xx = torch.meshgrid(torch.arange(H, device='cuda'), torch.arange(W, device='cuda'), indexing='ij')
        xyz = torch.stack([(xx-K[0, 2])*depth/K[0, 0], (yy-K[1, 2])*depth/K[1, 1], depth, torch.ones_like(depth)], -1); world = xyz@cam.world_view_transform.inverse()
        mask = ((world[..., :3] >= torch.tensor(box[0], device='cuda')) & (world[..., :3] <= torch.tensor(box[1], device='cuda'))).all(-1) & (depth > 0)   # inherited rule
        rule = torch.ones_like(mask)
        if variant in ('occl10', 'occlga'):
            with np.load(Path('/te/stage1x')/stem/variant/mi[v['name']]['file']) as z: occ = z['occ']
            assert occ.shape == (H, W), (v['name'], occ.shape, (H, W)); rule = torch.from_numpy(~occ).cuda()
        removed += int((mask & ~rule).sum()); kept += int((mask & rule).sum()); mask = mask & rule
        d = depth.cpu().numpy().copy(); d[~mask.cpu().numpy()] = 0
        rgb = (pkg['render'].permute(1, 2, 0).clamp(0, 1).cpu().numpy()*255).astype('u1'); p = root/f'{i:04d}.npz'; savez(p, depth=d, rgb=rgb); records.append(dict(v, file=p.name, sha256=sha(p)))
        if i % 40 == 0: print('RA6_RENDER', key, i+1, len(views), flush=True)
    dump(root/'receipt.json', dict(status='PASS', views=records, cached_views=0, box=box.tolist(), model_sha256=sha(ply), variant=variant, depth_ratio=pipe.depth_ratio,
         pixels_removed_by_rule=removed, pixels_kept=kept, inherited_source=str(R/'scripts/phd/main_trainerr_v1/addendum3/a3_ra_render.py'), renderer_sha256=sha('/source/gaussian_renderer/__init__.py'), job=job,
         seconds=time.monotonic()-start, rule='inherited render_model depth/box mask; then the variant rule (addendum6_c.json work_ra.variants)', scientific_verdict=None))
    print('RA6_RENDER_DONE', key, removed, kept, flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
