"""PHD-MAIN-BASE151-v1 addendum 1, 가-2 check: render the expected depth (depth_ratio 0, the rule used for the meshes) and the median depth
(depth_ratio 1) and the alpha of a cell model at the views of a job file. Same camera() as RESCORE render_model.py; the whole cell model (no
box crop). Runs in the method image with /source = the method source (b151_post41.render_cmd mounts), GPU only for rendering.

  python b151_add1_render.py /gtjudge/add1/jobs/<key>.json  ->  /gtjudge/add1/renders/<key>/<view>.npz (expected, median, alpha; float32)
scientific_verdict: null
"""
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, '/source')
import torch  # noqa: E402
from gaussian_renderer import render  # noqa: E402
from scene import GaussianModel  # noqa: E402

sys.path.insert(0, '/repo/scripts/phd/main_rescore_v1')
from render_model import camera  # noqa: E402


@torch.no_grad()
def main(jobfile):
    t0 = time.monotonic()
    torch.cuda.set_per_process_memory_fraction(.6)
    job = json.loads(Path(jobfile).read_text())
    root = Path('/gtjudge/add1/renders') / job['key']
    root.mkdir(parents=True, exist_ok=True)
    names = []
    with open(job['ply'], 'rb') as f:
        while True:
            line = f.readline().decode('ascii').strip()
            if line == 'end_header':
                break
            if line.startswith('property') and 'f_rest_' in line:
                names.append(line)
    g = GaussianModel(round(math.sqrt(len(names) / 3 + 1) - 1))
    g.load_ply(job['ply'])
    g.active_sh_degree = 0
    bg = torch.zeros(3, device='cuda')
    out = []
    for v in job['views']:
        cam = camera(v)
        pk0 = render(cam, g, SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False), bg)
        pk1 = render(cam, g, SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=1., debug=False), bg)
        H, W = v['height'], v['width']
        p = root / f"{v['name']}.npz"
        np.savez_compressed(p, expected=pk0['surf_depth'].reshape(H, W).cpu().numpy().astype('f4'), median=pk1['surf_depth'].reshape(H, W).cpu().numpy().astype('f4'),
                            alpha=pk0['rend_alpha'].reshape(H, W).cpu().numpy().astype('f4'))
        out.append(dict(name=v['name'], file=p.name))
    (root / 'receipt.json').write_text(json.dumps(dict(status='PASS', job=job, views=out, seconds=time.monotonic() - t0,
                                                       rule='expected = surf_depth with depth_ratio 0 (alpha-normalised mean depth, the mesh rule); '
                                                            'median = surf_depth with depth_ratio 1; alpha = rend_alpha; whole cell model, no crop',
                                                       scientific_verdict=None), indent=1))
    print('RENDERED', job['key'], len(out), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
