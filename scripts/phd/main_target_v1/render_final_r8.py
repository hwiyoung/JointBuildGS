"""Read-only stored-model inference at original training plus 16 virtual views."""
import sys,time
import numpy as np,torch
from argparse import ArgumentParser
from types import SimpleNamespace
from common import *
sys.path.insert(0,'/source');sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1')
import gpu_s1 as G
G.DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1' # inherited box input through existing read-only artifact mount
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.general_utils import safe_state
@torch.no_grad()
def main():
 key=sys.argv[1];cfg=json.loads((CFG/'scoring_r8.json').read_text());assert sha(CFG/'scoring_r8.json')==json.loads((CFG/'scoring_r8.lock.json').read_text())['config_sha256'];row=next(r for r in cfg['rows'] if r['key']==key);assert not row['existing_virtual'];root=OUT/'r8/meshes'/key/'render';root.mkdir(parents=True,exist_ok=False);start=time.monotonic()
 p=ArgumentParser();lp=ModelParams(p);pp=PipelineParams(p);args=p.parse_args(['-s',str(S0/'fork_inputs/s61'/row['site']/f"scene_{row['prior']}"),'-m',row['model'],'--eval','-r','1','--data_device','cpu']);safe_state(False);dataset=lp.extract(args);g=GaussianModel(args.sh_degree);scene=Scene(dataset,g,load_iteration=row['iteration'],shuffle=False);pipe=pp.extract(args);train=scene.getTrainCameras();centres=np.load(S1/'defs'/row['site']/'unseen.npz')['centre'];c=torch.tensor(centres,device='cuda').float();target=SimpleNamespace(completed_mask=torch.ones(len(c),device='cuda',dtype=torch.bool),get_xyz=c);virtual=G.create_virtual_cameras_for_completion(target,train,n_virtual_cams=8,distance_scale=1.5,elevation_angles=[.2,.5]);assert len(virtual)==16
 box=G.box_of(row['site']);xyz=g.get_xyz;inside=((xyz>=torch.tensor(box[0],device='cuda').float())&(xyz<=torch.tensor(box[1],device='cuda').float())).all(1);subset=G.subset(dataset,g,inside);subset.active_sh_degree=0;bg=torch.zeros(3,device='cuda');cams=train+virtual;intr=G.to_cam_open3d(cams);views=[]
 for i,(cam,co) in enumerate(zip(cams,intr)):
  a=G.render(cam,subset,pipe,bg);d=a['surf_depth'];mask=G.box_mask(cam,d,box);depth=d.squeeze().cpu().numpy().copy();depth[mask.squeeze().cpu().numpy()<.5]=0;rgb=(a['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1');path=root/f'{i:04d}.npz';np.savez_compressed(path,depth=depth,rgb=rgb);views.append(dict(index=i,name=cam.image_name,virtual=i>=len(train),K=co.intrinsic.intrinsic_matrix.tolist(),W2C=co.extrinsic.tolist(),width=cam.image_width,height=cam.image_height,file=path.name,sha256=sha(path)))
  if i%40==0:print('FINAL_RENDER',key,i+1,len(cams),flush=True)
 dump(root/'receipt.json',dict(status='PASS',at=stamp(),row=row,views=views,box=box.tolist(),gaussians=int(inside.sum()),model_sha256=sha(Path(row['model'])/f"point_cloud/iteration_{row['iteration']}/point_cloud.ply"),virtual_target_sha256=sha(S1/'defs'/row['site']/'unseen.npz'),source_sha256=sha(__file__),seconds=time.monotonic()-start,optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
