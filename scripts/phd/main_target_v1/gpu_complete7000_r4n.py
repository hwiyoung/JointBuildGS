"""Complete interrupted readout from an immutable saved 7000 PLY, zero optimizer steps."""
import sys,zipfile
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state

@torch.no_grad()
def main():
    prior=sys.argv[1];site='B173nb_b10';run=OUT/'r4n/runs'/f'tg_{site}_{prior}_s0';model=run/'model';root=model/'check7000'
    assert (OUT/'r4n/STOP_BOTH.json').exists() and (run/'receipt.json').exists()
    assert not (root/'coverage.json').exists()
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False);pipe=pp.extract(args)
    with np.load(model/'target_monitor/snapshot_7000.npz') as z:
        assert np.array_equal(g._xyz.cpu().numpy(),z['xyz']) and np.array_equal(g.init_id.cpu().numpy(),z['init_id'])
        assert np.array_equal(g.origin.cpu().numpy(),z['origin'])
        big=torch.as_tensor(z['initial_large_background'],device='cuda')[g.init_id.long()]
    labels=torch.stack([(g.origin==0).float(),big.float(),(g.origin==1).float()],1);bg=torch.zeros(3,device='cuda')
    maps=OUT/'r2/stage1'/f'{site}_{prior}'/'maps';index=json.loads((maps/'index.json').read_text())
    rows=[];old=[];new=[];replays=[];broken=[]
    for cam in sorted(scene.getTrainCameras(),key=lambda c:c.image_name):
        dest=root/'renders'/f'{cam.image_name}.npz';valid=False
        if dest.exists():
            try:
                with np.load(dest) as z:depth=z['depth'];[z[k] for k in ['rgb','alpha','origin_fraction']]
                valid=True
            except (ValueError,EOFError,zipfile.BadZipFile):
                keep=dest.with_suffix('.npz.interrupted');assert not keep.exists();dest.rename(keep);broken.append(str(keep))
        if valid:
            old.append(cam.image_name)
            if len(replays)<4:
                replay=render(cam,g,pipe,bg)['surf_depth'].squeeze().cpu().numpy()
                assert np.array_equal(depth,replay,equal_nan=True),'SAVED_MODEL_REPLAY_MISMATCH'
                replays.append(cam.image_name)
        else:
            pkg=render(cam,g,pipe,bg);depth=pkg['surf_depth'].squeeze().cpu().numpy();a=render(cam,g,pipe,bg,override_color=labels)
            fraction=(a['render']/a['rend_alpha'].clamp_min(1e-8)).clamp(0,1).permute(1,2,0).cpu().numpy()
            np.savez_compressed(dest,depth=depth,rgb=(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1'),
                origin_fraction=fraction.astype('f4'),alpha=a['rend_alpha'].squeeze().cpu().numpy())
            new.append(cam.image_name)
        with np.load(maps/index['views'][cam.image_name]['file']) as z:target=z['depth'];sigma=z['sigma']
        good=np.isfinite(target)&(target>0)&np.isfinite(sigma)&(sigma>0)
        ok=good&np.isfinite(depth)&(depth>0)&(abs(depth-target)<=1.96*sigma)
        rows.append(dict(camera=cam.image_name,inside=int(ok.sum()),target_pixels=int(good.sum()),K=index['views'][cam.image_name]['K'],W2C=index['views'][cam.image_name]['W2C']))
    inside=sum(v['inside'] for v in rows);den=sum(v['target_pixels'] for v in rows);fraction=inside/den
    receipt=dict(at=stamp(),status='COMPLETED_SAVED_MODEL_READOUT',optimization_steps=0,preserved_views=len(old),new_views=len(new),
        byte_equal_depth_replay_views=replays,interrupted_files_preserved=broken,model_sha256=sha(model/'point_cloud/iteration_7000/point_cloud.ply'),
        scientific_verdict=None)
    dump(root/'completion_receipt.json',receipt)
    dump(root/'coverage.json',dict(iteration=7000,inside=inside,target_pixels=den,fraction=fraction,criterion=.8,status='PASS' if fraction>=.8 else 'FAIL',
        views=rows,origin_fraction_channels=['background','initial_background_over_1m_ancestry','prior'],
        attribution='alpha-normalized rendered contributions; diagnostics only',readout_completion=receipt,scientific_verdict=None))
    print('COMPLETE_SAVED_7000',prior,fraction,flush=True)

if __name__=='__main__':main()
