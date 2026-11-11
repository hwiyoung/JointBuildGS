"""Is the 30,000 end-of-iteration scene dump identical to point_cloud/iteration_30000/point_cloud.ply (scene.save)?"""
import sys
from common import *
sys.path.insert(0, '/source')
import torch
from scene import GaussianModel
from render_states import load
def main():
    g, d = load(RUNM/'trainlog/scene/30000.pt'); p = GaussianModel(3); p.load_ply(str(RUNM/'point_cloud/iteration_30000/point_cloud.ply')); res = {}
    for a in ['_xyz', '_features_dc', '_features_rest', '_opacity', '_scaling', '_rotation']:
        x, y = getattr(g, a).detach(), getattr(p, a).detach(); res[a] = dict(shape_equal=x.shape == y.shape, bytes_equal=bool(x.shape == y.shape and torch.equal(x, y)), max_abs=float((x-y).abs().max()) if x.shape == y.shape else None)
    dump(O/'verification/dump30000_vs_ply.json', dict(at=now(), result=res, identical=all(v['bytes_equal'] for v in res.values()), scientific_verdict=None)); print(res, flush=True)
if __name__ == '__main__': main()
