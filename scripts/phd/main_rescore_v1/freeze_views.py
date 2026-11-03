"""Freeze inherited train+16 virtual cameras once per region, without training."""
import sys
from argparse import ArgumentParser
from types import SimpleNamespace
from common import *
import torch
sys.path.insert(0,'/source');sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1')
import gpu_s1 as G
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from utils.general_utils import safe_state
G.DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
@torch.no_grad()
def main(jobfile):
 cfg();start=time.monotonic();torch.cuda.set_per_process_memory_fraction(.25);j=json.loads(Path(jobfile).read_text());site=j['site'];path=O/'views'/f'{site}.json';assert not path.exists()
 p=ArgumentParser();lp=ModelParams(p);pp=PipelineParams(p);args=p.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f"scene_{j['prior']}"),'-m',j['model'],'--eval','-r','1','--data_device','cpu']);safe_state(False);dataset=lp.extract(args);g=GaussianModel(args.sh_degree);scene=Scene(dataset,g,load_iteration=j['iteration'],shuffle=False);train=scene.getTrainCameras();source=S1/'defs'/site/'unseen.npz';centres=loadz(source,['centre'])['centre'];c=torch.tensor(centres,device='cuda').float();target=SimpleNamespace(completed_mask=torch.ones(len(c),device='cuda',dtype=torch.bool),get_xyz=c);virtual=G.create_virtual_cameras_for_completion(target,train,n_virtual_cams=8,distance_scale=1.5,elevation_angles=[.2,.5]);assert len(virtual)==16
 cameras=train+virtual;views=[dict(index=i,name=cam.image_name,virtual=i>=len(train),K=co.intrinsic.intrinsic_matrix.tolist(),W2C=co.extrinsic.tolist(),width=cam.image_width,height=cam.image_height) for i,(cam,co) in enumerate(zip(cameras,G.to_cam_open3d(cameras)))]
 dump(path,dict(site=site,views=views,box=G.box_of(site).tolist(),virtual_target=str(source),virtual_target_sha256=sha(source),source_sha256=sha(__file__),method='unchanged TARGET train+16 virtual cameras',optimization_steps=0,scientific_verdict=None));timing('freeze_views_'+site,start)
if __name__=='__main__':main(sys.argv[1])
