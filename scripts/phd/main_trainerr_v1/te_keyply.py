"""Key-iteration scene dump -> PLY with the unchanged GaussianModel.save_ply (mesh input). TRAINLOG lineage_key.to_ply / render_states.load.
argv: <model_dir (container path)> <name> [<name> ...]"""
from common import *
sys.path.insert(0, '/source')
import torch
from scene import GaussianModel
@torch.no_grad()
def main(model, *names):
    model = Path(model)
    for name in names:
        out = model.parent/'ply'/f'{name}.ply'; out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists(): continue
        d = torch.load(model/'trainlog/scene'/f'{name}.pt', map_location='cpu', weights_only=False); g = GaussianModel(3)
        for a, k in [('_xyz', 'xyz'), ('_features_dc', 'f_dc'), ('_features_rest', 'f_rest'), ('_opacity', 'opacity'), ('_scaling', 'scaling'), ('_rotation', 'rotation')]:
            setattr(g, a, torch.nn.Parameter(d[k].cuda().contiguous(), requires_grad=False))
        g.active_sh_degree = int(d['active_sh_degree']); g.save_ply(str(out))
        dump(out.with_suffix('.json'), dict(at=now(), name=name, iteration=int(d['iteration']), gaussians=len(d['xyz']), source=str(model/'trainlog/scene'/f'{name}.pt'), ply_sha256=sha(out),
             writer='GaussianModel.save_ply (r28 = r23 code)', scientific_verdict=None)); print('PLY', name, len(d['xyz']), flush=True)
if __name__ == '__main__': main(*sys.argv[1:])
