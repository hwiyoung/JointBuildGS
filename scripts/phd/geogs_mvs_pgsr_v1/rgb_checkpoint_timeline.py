"""Audit saved states and render a bounded historical timeline without training."""
import gc
import json
import math
import os
from pathlib import Path
import time
import traceback
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw
import torch
import rgb_radius_probe as p


def original_model(condition):
    model = Path(condition['cfg_args']['path']).parent
    assert p.sha(model / 'cfg_args') == condition['cfg_args']['sha256']
    if condition['mode'] == 'mvs':
        receipt = p.read(model.parent / 'receipt.json')
        assert receipt['status'] == 'PASS' and receipt['job']['id'] == condition['run_id']
        model = p.TASK / receipt['job']['training_relative'] / 'model'
        assert p.sha(model / 'cfg_args') == condition['cfg_args']['sha256']
    return model


def inventory(manifest, experiment):
    rows = []
    for region in ['P1','P2','P3']:
        case = next(v for v in manifest['cases'] if v['id'] == region+'_train_1')
        for condition in case['conditions']:
            if condition['mode'] not in ['da3','mvs']:
                continue
            model = original_model(condition)
            checkpoints = []
            for receipt_path in sorted((model/'jbgs_complete').glob('iteration_*/receipt.json')):
                receipt = p.read(receipt_path)
                checkpoints.append({'iteration':receipt['iteration'], 'path':str(receipt_path.parent),
                    'checkpoint_present':(receipt_path.parent/'checkpoint.pth').exists(),
                    'ply_present':(receipt_path.parent/'point_cloud.ply').exists(),
                    'receipt_sha256':p.sha(receipt_path)})
            trace_path = model/'jbgs_trace.jsonl'
            trace = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
            rows.append({'region':region,'condition':condition['id'],'model':str(model),
                'checkpoints':checkpoints,'trace_path':str(trace_path),'trace_sha256':p.sha(trace_path),
                'trace_count':len(trace),'first_iteration':trace[0]['iteration'],'last_iteration':trace[-1]['iteration'],
                'trace_fields':sorted(trace[0]),'checkpoints_at_10000_or_15000':any(v['iteration'] in [10000,15000] for v in checkpoints),
                'count_samples':[{k:v[k] for k in ['iteration','gaussians','protected']} for v in trace if v['iteration'] in [100,8000,8100,10000,12000,15000,20000,30000]],
                'constant_count_from_15000':len({v['gaussians'] for v in trace if v['iteration']>=15000})==1})
    result={'scientific_verdict':None,'runs':rows,'common_anchors':experiment['anchors'],
        'limitations':'Counts are global and net; no clone/split/prune event or persistent Gaussian parent IDs. Separate preflight states are not main-run snapshots. Initial seed PLY is not a complete iteration0 Gaussian state.'}
    p.write(p.OUT/'inventory.json',result)
    return result


@torch.no_grad()
def main():
    started=time.time()
    torch.set_num_threads(2)
    cfg=p.read('/config.json')
    diagnostic=p.TASK/'viewer_rgb_v1/rgb_diagnostic_v1'/cfg['diagnostic_attempt']
    assert p.sha(diagnostic/'manifest.json')==cfg['diagnostic_manifest_sha256']
    manifest=p.read(diagnostic/'manifest.json')
    experiment=p.read(p.TASK/'inputs_v2/experiment.json')
    inv=inventory(manifest,experiment)
    case=next(v for v in manifest['cases'] if v['id']==cfg['case'])
    assert p.sha(diagnostic/case['photo_full_url'])==case['photo_full_sha256']
    photo=p.rgb(diagnostic/case['photo_full_url'])
    k=np.asarray(case['K'])
    camera=p.Camera(colmap_id=case['camera_id'],R=np.asarray(case['R']).T,T=np.asarray(case['t']),
        FoVx=2*math.atan(case['full_width']/(2*k[0,0])),FoVy=2*math.atan(case['full_height']/(2*k[1,1])),
        image=p.image_tensor(photo),gt_alpha_mask=None,image_name=Path(case['name']).stem,uid=case['index'])
    p.apply_projection(camera,{'K':case['K'],'width':case['full_width'],'height':case['full_height']})
    pipe=SimpleNamespace(compute_cov3D_python=False,convert_SHs_python=False,depth_ratio=0.)
    black=torch.zeros(3,device='cuda')
    x0,y0,x1,y1=case['bbox']; sl=np.s_[y0:y1,x0:x1]
    tiles=[('Original photo',photo[sl])]
    records=[]
    for stage in cfg['stages']:
        tick=time.time()
        if stage['id']=='common_anchor_8000':
            root=p.BASE/experiment['anchors']['P1']['relative']
            model=root.parents[1]
        else:
            condition=next(v for v in case['conditions'] if v['id']==stage['condition'])
            model=original_model(condition)
            root=model/'jbgs_complete'/f"iteration_{stage['iteration']}"
        receipt=p.read(root/'receipt.json')
        assert receipt['iteration']==stage['iteration'] and receipt['scientific_verdict'] is None
        assert p.sha(root/'point_cloud.ply')==receipt['ply_sha256']
        assert p.sha(root/'checkpoint.pth')==receipt['checkpoint_sha256']
        if stage['id']=='common_anchor_8000':
            assert receipt['checkpoint_sha256']==experiment['anchors']['P1']['sha256']
        state=torch.load(str(root/'checkpoint.pth'),map_location='cpu',mmap=True)
        assert state['schema']==receipt['schema'] and state['iteration']==stage['iteration']
        pc=p.GaussianModel(3); pc.load_ply(str(root/'point_cloud.ply'))
        for key,index in [('_xyz',1),('_features_dc',2),('_features_rest',3),('_scaling',4),('_rotation',5),('_opacity',6)]:
            assert torch.equal(getattr(pc,key).cpu(),state['model'][index]), key
        pc.active_sh_degree=int(state['model'][0])
        protected=state['frozen_mask'].bool().cuda()
        assert protected.shape==(pc._xyz.shape[0],)
        bg=torch.full((3,),1. if state['args']['white_background'] else 0.,device='cuda')
        del state
        gc.collect()
        package=p.render(camera,pc,pipe,bg)
        render=p.u8(package['render'])
        alpha=package['rend_alpha'].squeeze().cpu().numpy()[sl]
        large=package['radii']>cfg['large_radius_px']
        flags=torch.stack([protected,protected&large,(~protected)&large],dim=1).float()
        selected=p.render(camera,pc,pipe,black,override_color=flags)
        mass=selected['render'].cpu().numpy()[:,y0:y1,x0:x1]
        assert float((selected['rend_alpha']-package['rend_alpha']).abs().max())==0
        assert (mass>=-1e-6).all() and (mass<=alpha[None]+1e-5).all()
        assert (mass[1]<=mass[0]+1e-5).all() and (mass[1]+mass[2]<=alpha+1e-5).all()
        target=p.OUT/stage['id']; target.mkdir()
        Image.fromarray(render[sl]).save(target/'rgb.png')
        np.savez_compressed(target/'contribution.npz',alpha=alpha,protected=mass[0],protected_large=mass[1],unprotected_large=mass[2])
        support=alpha>=.95
        def fraction(array):
            return float((array[support]/alpha[support]).mean()) if support.any() else None
        parity=None
        if stage['iteration']==30000:
            saved=p.rgb(diagnostic/condition['render_full_url'])
            assert p.sha(diagnostic/condition['render_full_url'])==condition['render_full_sha256']
            parity=int(np.abs(render.astype(np.int16)-saved.astype(np.int16)).max())
            assert parity<=1
        row={'stage':stage,'root':str(root),'checkpoint_sha256':receipt['checkpoint_sha256'],
            'ply_sha256':receipt['ply_sha256'],'active_sh_degree':pc.active_sh_degree,'gaussians':len(protected),
            'protected_count':int(protected.sum()),'visible_large_count':int(large.sum()),
            'protected_roi_mass_mean':float(mass[0].mean()),'protected_large_roi_mass_mean':float(mass[1].mean()),
            'unprotected_large_roi_mass_mean':float(mass[2].mean()),'all_large_roi_mass_mean':float((mass[1]+mass[2]).mean()),
            'supported_roi_protected_fraction':fraction(mass[0]),'supported_roi_protected_large_fraction':fraction(mass[1]),
            'supported_roi_unprotected_large_fraction':fraction(mass[2]),'final_saved_png_max_u8_delta':parity,
            **p.metrics(photo[sl],render[sl],alpha),'wall_seconds':time.time()-tick}
        p.write(target/'result.json',row); records.append(row)
        tiles.append((stage['id'],render[sl]))
        print(json.dumps(row),flush=True)
        del pc,protected,package,large,flags,selected
        gc.collect(); torch.cuda.empty_cache()
    h,w=photo[sl].shape[:2]
    canvas=Image.new('RGB',(4*w,2*(h+32)),'#eeeeee'); draw=ImageDraw.Draw(canvas)
    for i,(label,array) in enumerate(tiles):
        x,y=(i%4)*w,(i//4)*(h+32)
        draw.text((x+6,y+8),label,fill='black');canvas.paste(Image.fromarray(array),(x,y+32))
    canvas.save(p.OUT/'timeline.png')
    p.write(p.OUT/'receipt.json',{'status':'PASS_SAVED_CHECKPOINT_TIMELINE','scientific_verdict':None,
        'config':cfg,'case':case['id'],'bbox':case['bbox'],'results':records,'inventory':inv,
        'new_training_steps':0,'wall_seconds':time.time()-started,'runtime_image_id':os.environ['DIAGNOSTIC_IMAGE_ID'],
        'operator_head':(p.OUT/'operator_head.txt').read_text().strip(),'torch_version':torch.__version__,
        'script_sha256':{v.name:p.sha(v) for v in p.OUT.glob('*.py')},'config_sha256':p.sha('/config.json'),
        'scope':'Saved states only; no missing intermediate model reconstruction, no optimizer, no parent-ID claims. Protection membership uses exact same-state tensors/PLY equality.'})


if __name__=='__main__':
    try:
        main()
    except Exception:
        p.write(p.OUT/'failure.json',{'status':'FAIL','scientific_verdict':None,'traceback':traceback.format_exc()})
        raise
