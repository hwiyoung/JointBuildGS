"""Saved scene state -> PLY with the unchanged GaussianModel.save_ply (TRAINERR te_keyply.py rule), written under addendum4/ply/<run>/.
argv: <model_dir (container path)> <run> <name> [<name> ...]"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
from common import *
sys.path.insert(0, '/source')
import torch
from scene import GaussianModel
@torch.no_grad()
def main(model, run, *names):
    model = Path(model)
    for name in names:
        out = O/'addendum4/ply'/run/f'{name}.ply'; out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists(): continue
        d = torch.load(model/'trainlog/scene'/f'{name}.pt', map_location='cpu', weights_only=False); g = GaussianModel(3)
        for a, k in [('_xyz', 'xyz'), ('_features_dc', 'f_dc'), ('_features_rest', 'f_rest'), ('_opacity', 'opacity'), ('_scaling', 'scaling'), ('_rotation', 'rotation')]:
            setattr(g, a, torch.nn.Parameter(d[k].cuda().contiguous(), requires_grad=False))
        g.active_sh_degree = int(d['active_sh_degree']); g.save_ply(str(out))
        dump(out.with_suffix('.json'), dict(at=now(), run=run, name=name, iteration=int(d['iteration']), gaussians=len(d['xyz']), source=str(model/'trainlog/scene'/f'{name}.pt'), ply_sha256=sha(out),
             writer='GaussianModel.save_ply (r31 = r30 = r23 code)', scientific_verdict=None)); print('PLY', name, len(d['xyz']), flush=True)
if __name__ == '__main__': main(*sys.argv[1:])
