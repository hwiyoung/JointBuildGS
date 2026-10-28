"""Read-only saved-model renders, PSNR identity gate, and frozen source-photo choices."""
import argparse
import json
import math
import sys
from pathlib import Path
import numpy as np
import torch
from PIL import Image
sys.path.insert(0,'/source')
from arguments import ModelParams,PipelineParams
from scene import Scene
from scene.cameras import Camera
from gaussian_renderer import GaussianModel,render
from utils.image_utils import psnr
from utils.loss_utils import ssim
from common import *
from recount import load_eval

def load(site,prior,result,iteration):
    path=model_path(site,result)
    parser=argparse.ArgumentParser();mp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61'/site/f'scene_{prior}'),'-m',str(path),'--eval','-r','1','--data_device','cpu'])
    dataset=mp.extract(args);pipe=pp.extract(args);g=GaussianModel(dataset.sh_degree)
    scene=Scene(dataset,g,load_iteration=iteration,shuffle=False)
    return pipe,g,scene,path

def matrices(cam):
    H,W=cam.image_height,cam.image_width
    ext=cam.world_view_transform.T.detach().cpu().numpy()
    proj=cam.projection_matrix.T.detach().cpu().numpy()
    K=np.array([[proj[0,0]*W/2,0,proj[0,2]*W/2+(W-1)/2],
        [0,proj[1,1]*H/2,proj[1,2]*H/2+(H-1)/2],[0,0,1.]])
    return ext,K

def project(xyz,ext,K):
    cam=xyz@ext[:3,:3].T+ext[:3,3]
    q=cam@K.T
    return q[:,:2]/q[:,2,None],cam[:,2]

def compare_quality(site,result,prior,train_rows,eval_rows):
    root=(S3 if result.startswith('nojudge') else LT)/'runs'/site/result
    tpath=LT/'photo'/site/result/'train_quality.json' if result.startswith('nojudge') else root/'post/train_quality.json'
    qpath=root/'post/quality.json';comparisons=[]
    for group,path,rows in [('training',tpath,train_rows),('evaluation',qpath,eval_rows)]:
        if not path.exists():
            comparisons.append(dict(group=group,status='UNAVAILABLE',reason='LOSSTRAIN reference record absent',path=str(path)))
            continue
        reference=json.loads(path.read_text())
        old=reference['per_view'];lookup={r.get('view',r.get('name',r.get('camera'))):r for r in old}
        new={r['view']:r for r in rows}
        assert set(new)==set(lookup),(group,'image membership mismatch',list(old[0]))
        diffs=[dict(view=k,measured=new[k]['psnr_db'],reference=float(lookup[k].get('psnr_db',lookup[k].get('psnr'))),
            absolute_difference_db=abs(new[k]['psnr_db']-float(lookup[k].get('psnr_db',lookup[k].get('psnr'))))) for k in new]
        maximum=max(r['absolute_difference_db'] for r in diffs)
        comparisons.append(dict(group=group,path=str(path),sha256=sha(path),views=len(rows),
            maximum_per_view_difference_db=maximum,status='PASS' if maximum<=config()['stops']['psnr_tolerance_db'] else 'STOP',comparisons=diffs))
    return comparisons

def run(site,result,prior,iteration,virtual_only=False):
    cfg=config();dest=OUT/'renders'/site/result/f'iteration_{iteration}';dest.mkdir(parents=True,exist_ok=True)
    pipe,g,scene,model=load(site,prior,result,iteration);bg=torch.zeros(3,device='cuda')
    e,_=load_eval(site,prior)
    cases=[c for c in json.loads((CFG/f'cases_{prior}.json').read_text())['cases'] if c['site']==site]
    photo_choices={c['id']:[] for c in cases}
    if not virtual_only:
        assert not (dest/'quality.json').exists(),'refuse duplicate rendering pass'
        tr,ev=[],[]
        with torch.no_grad():
            for group,cams,rows in [('train',scene.getTrainCameras(),tr),('eval',scene.getTestCameras(),ev)]:
                for i,cam in enumerate(cams):
                    pkg=render(cam,g,pipe,bg);colour=pkg['render'].clamp(0,1);photo=cam.original_image[:3].cuda().clamp(0,1)
                    p=float(psnr(colour[None],photo[None]).mean());s=float(ssim(colour,photo))
                    ext,K=matrices(cam)
                    row=dict(view=cam.image_name,psnr_db=p,ssim=s,width=cam.image_width,height=cam.image_height,
                        world_to_camera=ext.tolist(),intrinsic=K.tolist(),camera_center=cam.camera_center.detach().cpu().numpy().tolist())
                    rows.append(row)
                    if group=='train':
                        folder=dest/'train';folder.mkdir(exist_ok=True)
                        depth=pkg['surf_depth'].squeeze(0).cpu().numpy()
                        np.savez_compressed(folder/(cam.image_name+'.npz'),depth=depth,
                            alpha=pkg['rend_alpha'].squeeze(0).cpu().numpy(),
                            rgb_l1=(colour-photo).abs().mean(0).cpu().numpy())
                        Image.fromarray((colour.permute(1,2,0).cpu().numpy()*255).astype(np.uint8)).save(folder/(cam.image_name+'.png'))
                        photos=OUT/'photos'/site;photos.mkdir(parents=True,exist_ok=True)
                        if not (photos/(cam.image_name+'.png')).exists():
                            Image.fromarray((photo.permute(1,2,0).cpu().numpy()*255).astype(np.uint8)).save(photos/(cam.image_name+'.png'))
                        if result.startswith('nojudge'):
                            for c in cases:
                                ids=np.asarray(c['patch_indices'],int)
                                xyz=e['centre'][ids]
                                uv,dc=project(xyz,ext,K);xy=np.rint(np.nan_to_num(uv,nan=-1e6)).astype(int)
                                on=(dc>0)&np.isfinite(uv).all(1)&(xy[:,0]>=0)&(xy[:,0]<cam.image_width)&(xy[:,1]>=0)&(xy[:,1]<cam.image_height)
                                visible=np.zeros(len(ids),bool);valid=np.flatnonzero(on)
                                dd=depth[xy[valid,1],xy[valid,0]]
                                visible[valid]=np.isfinite(dd)&(dd>0)&(dc[valid]<=dd+.25)
                                area=e['area'][ids];fraction=float(area[visible].sum()/area.sum()) if area.sum() else 0.
                                angle=float(np.rad2deg(np.arccos(np.clip(abs(ext[2,2]),0,1))))
                                photo_choices[c['id']].append(dict(view=cam.image_name,coverage=fraction,angle_from_vertical_deg=angle,
                                    visible_patches=int(visible.sum()),total_patches=len(ids)))
                    if i%10==0:print(site,result,group,i+1,'/',len(cams),flush=True)
                    del pkg,colour,photo
        checks=compare_quality(site,result,prior,tr,ev) if iteration==30000 else []
        record=dict(at=now(),site=site,result=result,iteration=iteration,train=tr,evaluation=ev,
            train_psnr_db=float(np.mean([x['psnr_db'] for x in tr])),eval_psnr_db=float(np.mean([x['psnr_db'] for x in ev])),
            source_model=str(model),model_sha256=sha(model/f'point_cloud/iteration_{iteration}/point_cloud.ply'),
            checks=checks,optimizer_steps=0,scientific_verdict=None)
        save(dest/'quality.json',record)
        save(DOC/'provenance'/f'psnr_{site}_{result}_{iteration}.json',dict(at=now(),checks=checks,scientific_verdict=None))
        if any(x['status']=='STOP' for x in checks):raise SystemExit('STOP: saved-model PSNR differs by >0.1 dB')
        if result.startswith('nojudge'):
            selected=[]
            for case in cases:
                candidates=photo_choices[case['id']]
                main=sorted([x for x in candidates if x['coverage']>.9],key=lambda x:(x['angle_from_vertical_deg'],x['view']))
                oblique=sorted([x for x in candidates if x['coverage']>.5],key=lambda x:(-x['angle_from_vertical_deg'],x['view']))
                selected.append(dict(case=case['id'],main=main[0] if main else None,oblique=oblique[0] if oblique else None,
                    candidates=candidates,unavailable_reason=None if main and oblique else 'No camera passes the locked visible-area threshold'))
            save(CFG/f'photos_{site}_{prior}.json',dict(frozen_at=now(),visibility_result=result,iteration=iteration,cases=selected,
                rule='area-weighted original stage-1 patch centres; baseline rendered camera-depth visibility; ties by filename; no GT in camera selection',scientific_verdict=None))
    gp=CFG/f'geometry_{site}_{prior}.json'
    if gp.exists():
        with torch.no_grad():
            for case in json.loads(gp.read_text())['cases']:
                folder=DOC/'3d'/case['id']/result;folder.mkdir(parents=True,exist_ok=True)
                crop=GaussianModel(g.max_sh_degree);crop.active_sh_degree=g.active_sh_degree
                lower=torch.as_tensor(case['crop_min'],device='cuda');upper=torch.as_tensor(case['crop_max'],device='cuda')
                keep=((g.get_xyz>=lower)&(g.get_xyz<=upper)).all(1)
                for attr in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity']:
                    setattr(crop,attr,torch.nn.Parameter(getattr(g,attr).detach()[keep],requires_grad=False))
                for i,c in enumerate(case['cameras']):
                    right=np.array(c['right']);up=np.array(c['up']);direction=np.array(c['direction']);eye=np.array(c['eye'])
                    rotation=np.stack([right,-up,-direction]);translation=-rotation@eye
                    fovx=np.deg2rad(c['fov_x_deg']);fovy=2*np.arctan(np.tan(fovx/2)*c['height']/c['width'])
                    cam=Camera(0,rotation.T,translation,fovx,fovy,torch.zeros((3,c['height'],c['width'])),None,'virtual',0,data_device='cpu')
                    cam.zfar=1000.
                    pkg=render(cam,crop,pipe,bg);colour=pkg['render'].clamp(0,1)
                    Image.fromarray((colour.permute(1,2,0).cpu().numpy()*255).astype(np.uint8)).save(folder/f'gaussian_{i}.png')
                    del pkg,colour
                save(folder/'gaussian_captures.json',dict(case=case['id'],result=result,crop_gaussians=int(keep.sum()),
                    model=str(model),camera_config_sha256=sha(gp),opacity_cutoff_applied=False,
                    note='Same fixed crop and perspective cameras as mesh; every retained Gaussian keeps trained colour, shape and opacity. Views without training photographs may appear blurred.',scientific_verdict=None))
                del crop
        print('virtual Gaussian capture PASS',site,result,flush=True)
    else:print('virtual capture pending: geometry cameras not frozen yet',site,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site',required=True);p.add_argument('--result',required=True)
    p.add_argument('--prior',default='ALS');p.add_argument('--iteration',type=int,default=30000);p.add_argument('--virtual-only',action='store_true');a=p.parse_args()
    run(a.site,a.result,a.prior,a.iteration,a.virtual_only)
