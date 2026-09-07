"""P3 source-conditioned gsplat experiment, deliberately separate from native Wu-Vallet.

Run in an isolated Docker image with the audited C4/C8 plane-surface adapter.
No evaluation reference is accepted or read by this module.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback
import cv2
import numpy as np
from scipy.spatial import cKDTree
import torch
from src.phd.p2_ab_v2.reconstruction import View, prepare_geometry, extract_surface
from src.phd.p2_ab_v3.appearance_sh import render_view
from src.phd.p2_ab_v6.surface_budget import SurfaceGaussians
from scripts.phd.p2_ab_v2.b_run import initialize_texture_and_support, readout_validity


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def load_views(common, cfg):
    views=[]
    for row in json.loads((common/'views.json').read_text())['views']:
        if row['role'] not in ('train','appearance_eval','eval'): continue
        path=Path(row['path'])
        if sha(path)!=row['sha256']: raise ValueError('Image hash mismatch '+str(path))
        rgb=cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
        h,w=rgb.shape[:2]
        if (w,h)!=(row['width'],row['height']): raise ValueError('Camera image dimensions mismatch')
        factor=min(1.,cfg['maximum_view_dimension_px']/max(h,w))
        nw,nh=round(w*factor),round(h*factor)
        rgb=cv2.resize(rgb,(nw,nh),interpolation=cv2.INTER_AREA)
        K=np.asarray(row['K'],np.float32).copy(); K[0]*=nw/w; K[1]*=nh/h
        V=np.eye(4,dtype=np.float32); V[:3,:3]=row['R']; V[:3,3]=row['t']
        device='cuda'; role='train' if row['role']=='train' else 'eval'
        v=View(row['image_id'],role,torch.tensor(rgb,device=device,dtype=torch.float32)/255,
               torch.ones((nh,nw),device=device,dtype=torch.bool),torch.tensor(K,device=device),
               torch.tensor(V,device=device),nw,nh,dict(row,resized_shape_hw=[nh,nw],
               source_K=row['K'],source_width=w,source_height=h,K=K.tolist(),width=nw,height=nh))
        v.context_depth=torch.zeros((nh,nw),device=device)
        views.append(v)
    if not any(v.role=='train' for v in views) or not any(v.role=='eval' for v in views):
        raise ValueError('Disjoint train/evaluation roles required')
    return views


def seeds(native,source,cfg):
    parts=[]
    for s in ('mvs','als') if source=='union' else (source,):
        xyz=native[s+'_xyz']; rows=native[s+'_tile_rows']
        # Select native observations first; normal estimation cannot create observations.
        _,ii=np.unique(np.floor(xyz/cfg['seed_voxel_m']).astype(np.int64),axis=0,return_index=True)
        ii=np.sort(ii); p=xyz[ii].astype(np.float32)
        if s+'_normals' in native:
            normal=native[s+'_normals'][ii].copy().astype(np.float32)
        else: normal=np.zeros_like(p)
        bad=~np.isfinite(normal).all(1)|(np.linalg.norm(normal,axis=1)<1e-5)
        if bad.any():
            tree=cKDTree(p); _,near=tree.query(p[bad],k=min(12,len(p)),workers=2)
            local=p[near]; local-=local.mean(1,keepdims=True)
            _,vectors=np.linalg.eigh(np.einsum('nki,nkj->nij',local,local))
            normal[bad]=vectors[:,:,0]
        patch=native.get(s+'_patch_id',np.zeros(len(xyz),np.int64))[ii].astype(np.int64)
        patch=np.maximum(patch,0)+(0 if s=='mvs' else 10_000_000)
        unit=((np.floor((p[:,0]+60)/.5).astype(int))*108+np.floor((p[:,1]+42)/.5).astype(int))
        parts.append((p,normal,patch,rows[ii],unit,np.full(len(p),0 if s=='mvs' else 1,np.uint8)))
    arrays=[np.concatenate([p[i] for p in parts]) for i in range(6)]
    seed=prepare_geometry(*arrays[:5],dict(cfg,seed_voxel_m=0))
    seed['source_id']=arrays[5][seed['seed_id']]
    return seed


@torch.no_grad()
def save_eval(model, views, seed, dest, masks, initial=None):
    dest.mkdir(exist_ok=False); rows=[]; surfaces=[]; renders={}
    for v in views:
        out=render_view(model,v); readout_validity(out)
        rgb=out['rgb'].clamp(0,1); target=v.image
        cpu={k:out[k].cpu().numpy().astype(np.float32) for k in ('depth','geometry_mass','alpha','normal_render')}
        r={'image_id':v.image_id,'masks':{}}
        error=rgb-target
        for key in ('union','intersection'):
            mask=masks[v.image_id][key]; n=int(mask.sum())
            r['masks'][key]={'pixels':n,'absolute_sum':float(error[mask].abs().sum()),'squared_sum':float(error[mask].square().sum()),
                'mae':float(error[mask].abs().mean()) if n else None,
                'psnr_db':float(-10*torch.log10(error[mask].square().mean().clamp_min(1e-15))) if n else None,
                'geometry_missing_pixels':int((mask&(out['geometry_mass']<.5)).sum())}
        if initial is not None:
            old=initial[v.image_id]; retained=(old['geometry_mass']>=.5)&(cpu['geometry_mass']>=.5)
            d=np.abs(old['depth']-cpu['depth'])
            r['surface_change']={'retained_pixels':int(retained.sum()),'removed_pixels':int(((old['geometry_mass']>=.5)&(cpu['geometry_mass']<.5)).sum()),
                'depth_abs_p90_m':float(np.quantile(d[retained],.9)) if retained.any() else None,
                'depth_exact':bool(np.array_equal(old['depth'],cpu['depth'])),'mass_exact':bool(np.array_equal(old['geometry_mass'],cpu['geometry_mass']))}
        cv2.imwrite(str(dest/f'rgb_{v.image_id}.png'),cv2.cvtColor(np.round(rgb.cpu().numpy()*255).astype(np.uint8),cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(dest/f'target_{v.image_id}.png'),cv2.cvtColor(np.round(target.cpu().numpy()*255).astype(np.uint8),cv2.COLOR_RGB2BGR))
        for key,a in cpu.items(): np.save(dest/f'{key}_{v.image_id}.npy',a)
        surfaces.append(extract_surface(out,v,seed,stride=2)); rows.append(r); renders[v.image_id]=cpu
    np.savez_compressed(dest/'extracted_surface.npz',**{k:np.concatenate([s[k] for s in surfaces]) for k in surfaces[0]})
    totals={}
    for key in ('union','intersection'):
        n=sum(r['masks'][key]['pixels'] for r in rows)
        a=sum(r['masks'][key]['absolute_sum'] for r in rows); s=sum(r['masks'][key]['squared_sum'] for r in rows)
        totals[key]={'pixels':n,'mae':a/(3*n) if n else None,'psnr_db':float(-10*np.log10(max(s/(3*n),1e-15))) if n else None,
                     'geometry_missing_pixels':sum(r['masks'][key]['geometry_missing_pixels'] for r in rows)}
    result={'views':rows,'aggregate':totals}; write(dest/'appearance.json',result)
    return result,renders


def main(config_path,output):
    output.mkdir(parents=True,exist_ok=False); start=time.monotonic()
    write(output/'STARTED.json',{'scientific_verdict':None})
    try:
        cfg=json.loads(Path(config_path).read_text()); write(output/'config.json',cfg)
        adapter_root=Path(os.environ['JBGS_GEOMETRY_ADAPTER_SNAPSHOT'])
        adapter_doc=json.loads((adapter_root/'adapter_manifest.json').read_text())
        for name,expected in adapter_doc['output_hashes'].items():
            actual_path=Path('/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc')/Path(name).name
            if sha(actual_path)!=expected: raise ValueError('Audited geometry adapter hash mismatch '+str(actual_path))
        torch.set_num_threads(2); cv2.setNumThreads(1); torch.manual_seed(cfg['seed'])
        common=Path(cfg['common_root']); native_path=common/'native.npz'
        inputs={str(p):sha(p) for p in (native_path,common/'views.json',Path(config_path))}
        native=dict(np.load(native_path,allow_pickle=False)); views=load_views(common,cfg)
        train=[v for v in views if v.role=='train']; ev=[v for v in views if v.role=='eval']
        frozen={}; masks={v.image_id:[] for v in ev}; init_info={}; source_view_support={}
        for source in sorted({a['source'] for a in cfg['arms']}):
            seed=seeds(native,source,cfg); np.savez_compressed(output/f'{source}_seeds.npz',**seed)
            model=SurfaceGaussians(seed,cfg); init_info[source]=initialize_texture_and_support(model,views)
            source_view_support[source]={v.image_id:dict(pixels=int(v.mask.sum()),
                sha256=hashlib.sha256(v.mask.cpu().numpy().tobytes()).hexdigest(),
                details=v.provenance['conditional_observation_mask']) for v in views}
            frozen[source]={'seed':seed,'state':{k:v.detach().cpu().clone() for k,v in model.state_dict().items()},
                'train_masks':{v.image_id:v.mask.clone() for v in train}}
            with torch.no_grad():
                for v in ev:
                    out=render_view(model,v); masks[v.image_id].append(out['geometry_mass']>=.5)
            del model; torch.cuda.empty_cache()
        for v in ev:
            stack=torch.stack(masks[v.image_id]); masks[v.image_id]={'union':stack.any(0),'intersection':stack.all(0)}
            for key,mask in masks[v.image_id].items(): cv2.imwrite(str(output/f'{key}_support_{v.image_id}.png'),mask.cpu().numpy().astype(np.uint8)*255)
        write(output/'views.json',{'views':[v.provenance for v in views],'initialization':init_info,
            'source_view_support':source_view_support,
            'visibility':'source-conditioned self visibility; no independent current-use claim',
            'evaluation_masks':'frozen union and intersection of all source initial plane-geometry supports; missing output remains in denominator'})
        # Freeze the exact view schedule before optimizing any arm.
        schedule=[train[i%len(train)].image_id for i in range(cfg['steps'])]
        write(output/'schedule.json',{'image_ids':schedule,'steps':cfg['steps']})
        results=[]
        for arm in cfg['arms']:
            source=arm['source']; spec=frozen[source]; seed=spec['seed']; dest=output/arm['name']; dest.mkdir()
            model=SurfaceGaussians(seed,cfg); model.load_state_dict(spec['state']); model.trainable(arm['geometry'])
            initial,initial_renders=save_eval(model,ev,seed,dest/'initial',masks)
            initial_state=model.state_arrays(seed); np.savez_compressed(dest/'gaussians_initial.npz',**initial_state,source_id=seed['source_id'])
            opt=[{'params':[model.sh0],'lr':cfg['color_lr']},{'params':[model.sh_rest],'lr':cfg['color_lr']*.05}]
            if arm['geometry']: opt.append({'params':[model.normal_offset],'lr':cfg['normal_lr']})
            optimizer=torch.optim.Adam(opt,eps=1e-15); arm_start=time.monotonic()
            for step in range(cfg['steps']):
                v=train[step%len(train)]; mask=spec['train_masks'][v.image_id]
                if int(mask.sum())==0: raise ValueError('Empty preregistered source training mask')
                optimizer.zero_grad(set_to_none=True); out=render_view(model,v)
                photo=(out['rgb']-v.image).abs()[mask].mean()
                loss=photo
                if arm['geometry']: loss=loss+cfg['normal_anchor_weight']*(model.normal_offset/cfg['normal_limit_m']).square().mean()
                if not bool(torch.isfinite(loss)): raise FloatingPointError('Nonfinite loss')
                loss.backward()
                parameters=[p for p in model.parameters() if p.requires_grad]
                if any(p.grad is not None and not bool(torch.isfinite(p.grad).all()) for p in parameters): raise FloatingPointError('Nonfinite gradient')
                torch.nn.utils.clip_grad_norm_(parameters,10.); optimizer.step()
                with torch.no_grad():
                    model.sh0.clamp_(-.5/.28209479177387814,.5/.28209479177387814)
                    model.normal_offset.clamp_(-cfg['normal_limit_m'],cfg['normal_limit_m'])
                    model.normal_offset.mul_(model.observable)
                row={'step':step+1,'image_id':v.image_id,'photo_l1':float(photo),'loss':float(loss),'pixels':int(mask.sum())}
                with (dest/'training.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
                if (step+1)%64==0: print(arm['name'],step+1,float(loss),flush=True)
            final,_=save_eval(model,ev,seed,dest/'final',masks,initial_renders)
            state=model.state_arrays(seed); np.savez_compressed(dest/'gaussians_final.npz',**state,source_id=seed['source_id'])
            shutil.copy2(dest/'final/extracted_surface.npz',dest/'extracted_surface.npz')
            geometry_keys=('xyz','quats','scales','opacity')
            unchanged=all(np.array_equal(initial_state[k],state[k]) for k in geometry_keys)
            if not arm['geometry'] and not unchanged: raise ValueError('Fixed geometry changed')
            if not arm['geometry'] and not all(r['surface_change']['depth_exact'] and r['surface_change']['mass_exact'] for r in final['views']):
                raise ValueError('Fixed actual rendered surface changed')
            result={'arm':arm['name'],'source':source,'geometry_active':arm['geometry'],'seed_count':len(seed['xyz']),
                'initial':initial,'final':final,'geometry_parameters_exact':unchanged,
                'offset_max_m':float(np.max(np.abs(state['normal_offset_m']))),'runtime_seconds':time.monotonic()-arm_start}
            write(dest/'result.json',result); results.append(result); del model; torch.cuda.empty_cache()
        if any(sha(p)!=h for p,h in inputs.items()): raise ValueError('Inputs changed during run')
        adapter={str(p):sha(p) for p in Path('/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc').glob('rasterize_to_pixels_2dgs_*.cu')}
        result={'status':'COMPLETED_SOURCE_CONDITIONED_DEVELOPMENT','task_id':cfg['task_id'],'scientific_verdict':None,'arms':results,
                'input_hashes':inputs,'source_snapshot_manifest':os.environ.get('JBGS_SOURCE_SNAPSHOT_MANIFEST'),
                'versions':{'torch':torch.__version__,'gsplat':__import__('gsplat').__version__,'cuda':torch.version.cuda,
                    'image_id':os.environ.get('JBGS_CONTAINER_IMAGE_ID'),'git_head':os.environ.get('JBGS_SOURCE_GIT_HEAD')},
                'geometry_adapter_hashes':adapter,'runtime_seconds':time.monotonic()-start,'limits':cfg['limits'],
                'wu_vallet_original_reproduced':False,'actual_A_decision_consumed':False,'evaluation_reference_accessed':False}
        write(output/'result.json',result); print(result['status'],flush=True)
    except Exception as exc:
        write(output/'FAILED.json',{'error':repr(exc),'traceback':traceback.format_exc(),'scientific_verdict':None}); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); main(args.config,args.output)
