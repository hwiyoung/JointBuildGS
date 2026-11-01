"""Read saved baseline provenance and attribute existing first hits; no training or rescoring."""
import sys
sys.path.insert(0, '/source')
from argparse import ArgumentParser
import numpy as np
import torch
from arguments import ModelParams, PipelineParams
from scene import Scene, GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *


def loadz(path):
    with np.load(path) as z:
        return {k:z[k] for k in z.files}


@torch.no_grad()
def main():
    prior = sys.argv[1]
    binding = json.loads((CFG/'baseline_origin_r8.lock.json').read_text())
    for name, digest in binding['files'].items():
        assert sha(name) == digest, name
    row = binding['inputs'][prior]
    for name, digest in row.items():
        assert sha(name) == digest, name
    base = OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0'
    model = base/'model'
    dest = OUT/'r8/baseline_origin'/prior
    dest.mkdir(parents=True, exist_ok=False)
    (dest/'views').mkdir()
    parser = ArgumentParser(); lp = ModelParams(parser); pp = PipelineParams(parser)
    args = parser.parse_args(['-s', str(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{prior}'), '-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False)
    g = GaussianModel(args.sh_degree)
    scene = Scene(lp.extract(args), g, load_iteration=7000, shuffle=False)
    pipe = pp.extract(args); bg = torch.zeros(3, device='cuda')
    initial = np.load(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{prior}/sparse/0/origin.npy')
    ids = g.init_id.cpu().numpy(); origins = g.origin.cpu().numpy()
    assert ids.min() >= 0 and ids.max() < len(initial)
    assert np.array_equal(origins, initial[ids]) and set(np.unique(origins)) <= {0,1}
    labels = torch.zeros((len(ids),3),device='cuda')
    labels[:,0] = (g.origin == 0).float(); labels[:,2] = (g.origin == 1).float()
    e = loadz(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'B173nb_b10__{prior}/evaluation.npz')
    z = loadz(base/'post7000/patch_z.npz')
    eligible = e['in_eval'] & e['scoring_allowed']
    hit = e['centre'] + z['z'][:,None]*e['normal']
    selected = np.flatnonzero(eligible & ~z['no_surface'])
    sums = np.zeros((len(hit),3)); counts = np.zeros(len(hit),np.int32)
    cover = json.loads((model/'check7000/coverage.json').read_text())
    metas = {v['camera']:v for v in cover['views']}; views=[]
    cameras=sorted(scene.getTrainCameras(),key=lambda c:c.image_name)
    assert len(cameras)==203 and set(metas)=={c.image_name for c in cameras}
    for i, cam in enumerate(cameras):
        saved=loadz(model/'check7000/renders'/f'{cam.image_name}.npz')
        ordinary=render(cam,g,pipe,bg)
        depth=ordinary['surf_depth'].squeeze().cpu().numpy()
        assert np.array_equal(depth,saved['depth'],equal_nan=True),cam.image_name
        attribution=render(cam,g,pipe,bg,override_color=labels)
        alpha=attribution['rend_alpha'].squeeze().cpu().numpy()
        assert np.array_equal(alpha,saved['alpha'],equal_nan=True),cam.image_name
        assert np.array_equal(attribution['surf_depth'].squeeze().cpu().numpy(),depth,equal_nan=True)
        fraction=(attribution['render']/attribution['rend_alpha'].clamp_min(1e-8)).clamp(0,1).permute(1,2,0).cpu().numpy()
        meta=metas[cam.image_name]; M=np.asarray(meta['W2C']); K=np.asarray(meta['K'])
        q=hit[selected]@M[:3,:3].T+M[:3,3]; front=q[:,2]>0; goodids=selected[front];q=q[front]
        u=np.rint(K[0,0]*q[:,0]/q[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*q[:,1]/q[:,2]+K[1,2]).astype(int)
        ok=(u>=0)&(w>=0)&(u<depth.shape[1])&(w<depth.shape[0]);u,w,q,goodids=u[ok],w[ok],q[ok],goodids[ok]
        visible=np.isfinite(depth[w,u])&(depth[w,u]>0)&(abs(depth[w,u]-q[:,2])<=.25)&(alpha[w,u]>1e-5)
        ids2=goodids[visible]; values=fraction[w[visible],u[visible]]
        sums[ids2]+=values;counts[ids2]+=1
        path=dest/'views'/f'{cam.image_name}.npz'
        np.savez_compressed(path,patch_index=ids2,u=u[visible],v=w[visible],fraction=values)
        views.append(dict(camera=cam.image_name,matched=len(ids2),sha256=sha(path),depth_alpha_byte_equal=True))
        if i%40==0:print('BASELINE_ORIGIN',prior,i+1,203,flush=True)
    mean=np.divide(sums,counts[:,None],out=np.full_like(sums,np.nan),where=counts[:,None]>0)
    np.savez_compressed(dest/'origin_attribution.npz',hit_xyz=hit,mean_fraction=mean,views=counts,category=z['category'],in_eval=eligible,
                        background_dominant=(counts>0)&(mean[:,0]>=.5),released_dominant=np.zeros(len(hit),bool))
    dump(dest/'summary.json',dict(at=stamp(),status='PASS_BASELINE_PROVENANCE_REPLAY',prior=prior,iteration=7000,
         gaussians=len(ids),origin_counts={str(k):int((origins==k).sum()) for k in [0,1]},initial_origin_by_id_exact=True,
         views=views,matched=int((counts>0).sum()),channels=['SfM background','released not applicable','prior seed'],
         mapping='PLY origin=0 SfM; origin=1 prior; baseline has no release controller. Same alpha-normalized contribution and 0.25 m visibility rule as r8.',
         input_hashes=row,optimization_steps=0,geometry_rescored=False,scientific_verdict=None))
    print('BASELINE_ORIGIN_COMPLETE',prior,flush=True)


if __name__=='__main__':main()
