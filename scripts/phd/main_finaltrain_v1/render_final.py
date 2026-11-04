"""Original training views plus the inherited sixteen virtual views; evaluation only."""
import ast,math,sys,time
from argparse import ArgumentParser
from types import SimpleNamespace
from common import *
import torch
sys.path.insert(0,'/source');sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1')
import gpu_s1 as G
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.general_utils import safe_state
from renderer import install
G.DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'

@torch.no_grad()
def main(site,prior):
    cfg();install();stem=f'{site}__{prior}';run=O/'runs'/site/f'ft_{prior}_s0';receipt=json.loads((run/'receipt.json').read_text())
    assert receipt['status']=='TRAINING_COMPLETE_30000';model=Path(receipt['attempts'][-1]['model']);root=O/'meshes'/stem/'render';root.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    p=ArgumentParser();lp=ModelParams(p);pp=PipelineParams(p);args=p.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);dataset=lp.extract(args);g=GaussianModel(args.sh_degree);scene=Scene(dataset,g,load_iteration=30000,shuffle=False);pipe=pp.extract(args);train=scene.getTrainCameras()
    source=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/defs'/site/'unseen.npz';centres=np.load(source)['centre'];c=torch.tensor(centres,device='cuda').float()
    target=SimpleNamespace(completed_mask=torch.ones(len(c),device='cuda',dtype=torch.bool),get_xyz=c)
    virtual=G.create_virtual_cameras_for_completion(target,train,n_virtual_cams=8,distance_scale=1.5,elevation_angles=[.2,.5]);assert len(virtual)==16
    box=G.box_of(site);xyz=g.get_xyz;inside=((xyz>=torch.tensor(box[0],device='cuda').float())&(xyz<=torch.tensor(box[1],device='cuda').float())).all(1)
    subset=G.subset(dataset,g,inside);subset.active_sh_degree=0;bg=torch.zeros(3,device='cuda');cams=train+virtual;intr=G.to_cam_open3d(cams);views=[]
    shared=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1/views'/f'{site}.json';shared_sha=None
    if shared.exists():
        fixed=json.loads(shared.read_text())['views'];assert len(fixed)==len(cams)
        source_camera=R/'scripts/phd/main_rescore_v1/render_model.py';node=next(x for x in ast.parse(source_camera.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='camera')
        env=dict(np=np,torch=torch,math=math,SimpleNamespace=SimpleNamespace)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source_camera),'exec'),env)
        cams=[env['camera'](v) for v in fixed]
        intr=[SimpleNamespace(intrinsic=SimpleNamespace(intrinsic_matrix=np.asarray(v['K'])),extrinsic=np.asarray(v['W2C'])) for v in fixed]
        shared_sha=sha(shared)
    for i,(cam,co) in enumerate(zip(cams,intr)):
        a=G.render(cam,subset,pipe,bg);depth=a['surf_depth'];mask=G.box_mask(cam,depth,box);d=depth.squeeze().cpu().numpy().copy();d[mask.squeeze().cpu().numpy()<.5]=0
        rgb=(a['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1');path=root/f'{i:04d}.npz';savez(path,depth=d,rgb=rgb)
        views.append(dict(index=i,name=cam.image_name,virtual=i>=len(train),K=co.intrinsic.intrinsic_matrix.tolist(),W2C=co.extrinsic.tolist(),width=cam.image_width,height=cam.image_height,file=path.name,sha256=sha(path),mask_fraction=float(mask.float().mean()),depth_fraction=float((d>0).mean())))
        if i%40==0:print('FINAL_RENDER',stem,i+1,len(cams),flush=True)
    dump(root/'receipt.json',dict(status='PASS',at=now(),views=views,box=box.tolist(),gaussians=int(inside.sum()),model_sha256=sha(model/'point_cloud/iteration_30000/point_cloud.ply'),
        virtual_target_sha256=sha(source),shared_rescore_views_sha256=shared_sha,source_sha256=sha(__file__),renderer=cfg()['renderer'],seconds=time.monotonic()-start,optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
