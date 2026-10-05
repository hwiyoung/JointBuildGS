"""Fresh source-assembled stock-gsplat 2DGS; paired bounded optimization arms."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
import sys
import time
import traceback

import numpy as np
from PIL import Image
import torch
from src.phd.source_selected_2dgs_v1 import optimization as opt


EXPECTED_KERNELS={'rasterize_to_pixels_2dgs_fwd.cu':'c5e7b0350a332c4885ed22f2642eaa7364011a658bead35193cb33748c100505',
                  'rasterize_to_pixels_2dgs_bwd.cu':'a7e591d3b427c876f173a99d6c737f941063cf96c869c805187a66d8d869f311'}
MASKS=('photo_mask','target_mask','surrounding_mask','outside_mask','authority_mask','projection_abstain_mask','depth_valid','normal_valid')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,np.integer):return int(value)
    if isinstance(value,np.bool_):return bool(value)
    if isinstance(value,(np.floating,float)):return float(value) if np.isfinite(value) else None
    return value


def write(path,obj):
    with Path(path).open('x') as f:json.dump(clean(obj),f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def load_npz(path):
    with np.load(path,allow_pickle=False) as f:return {k:f[k] for k in f.files}


def runtime():
    import gsplat
    root=Path(gsplat.__file__).parent
    kernels={key:sha(root/'cuda/csrc'/key) for key in EXPECTED_KERNELS}
    if gsplat.__version__!='1.4.0' or kernels!=EXPECTED_KERNELS:raise ValueError('Unmodified gsplat1.4 kernel identity required')
    if os.environ.get('JBGS_GSPLAT_MEDIAN_IS_SURFACE_SUM'):raise ValueError('Legacy renderer overlays prohibited')
    return dict(torch=torch.__version__,cuda=torch.version.cuda,gsplat=gsplat.__version__,
        kernel_sha256=kernels,image_id=os.environ.get('JBGS_CONTAINER_IMAGE_ID',os.environ.get('JBGS_RUNTIME_IMAGE_ID')),
        gpu=torch.cuda.get_device_name(0),python=sys.version,torch_extensions_dir=os.environ.get('TORCH_EXTENSIONS_DIR'),
        renderer='stock gsplat.rasterization_2dgs',depth='alpha-weighted Gaussian center camera-Z',
        pixel_adapter='original integer rays; gsplat K principal point +0.5, no RGB/depth resampling')


def fixture(cfg,output,config_path):
    """Actual stock CUDA forward/backward and original integer pixel-ray check."""
    points=dict(xyz=np.array([[0.,0.,5.],[.08,.05,5.3]],np.float32),normal=np.array([[0,0,1.],[0,.1,1.]],np.float32),
        rgb=np.array([[.7,.3,.2],[.2,.5,.8]],np.float32),scale=np.array([.05,.06],np.float32),
        source_kind=np.array([0,1]),stable_source_id=np.array([1,2]),trainable_geometry=np.array([True,True]))
    model=opt.SourceGaussians(points,cfg)
    view=dict(K=[[100.,0,31.],[0,100.,35.],[0,0,1.]],R=np.eye(3).tolist(),t=[0.,0.,0.],width=64,height=64)
    first=opt.render(model,view)
    projected=first['meta']['means2d'][0,0].detach().cpu().numpy()
    if not np.allclose(projected,[31.5,35.5],atol=2e-5,rtol=0):raise ValueError('Integer pixel projection fixture differs')
    # A single primitive isolates the raster peak from the overlapping second.
    single={k:v[:1] for k,v in points.items()};one=opt.SourceGaussians(single,cfg)
    alone=opt.render(one,view);peak=np.unravel_index(int(alone['alpha'].argmax()),(64,64))
    if peak!=(35,31):raise ValueError('Expected original integer pixel center peak not recovered')
    yy,xx=torch.meshgrid(torch.arange(64,device='cuda'),torch.arange(64,device='cuda'),indexing='ij')
    pattern=(xx.float()/64+.3*yy.float()/64)
    loss=(first['rgb'][...,0]*pattern).mean()+.03*first['depth'].mean()+.1*first['alpha'].mean()+.001*first['distortion'].mean()
    loss.backward()
    gradients={name:dict(finite=bool(torch.isfinite(p.grad).all()) if p.grad is not None else False,
        max_abs=float(p.grad.abs().max()) if p.grad is not None else None) for name,p in model.named_parameters()}
    if not all(v['finite'] and v['max_abs']>0 for v in gradients.values()):raise ValueError('Fixture requires finite nonzero gradients for every optimized primitive attribute')
    if first['normal_from_depth'] is None or first['normal_from_depth'].shape!=(64,64,3):raise ValueError('Depth normal contract differs')
    for key in ('rgb','depth','alpha','normal','normal_from_depth','distortion'):
        if not bool(torch.isfinite(first[key]).all()):raise ValueError('Nonfinite fixture field: '+key)
    optimizer=model.optimizer(cfg);optimizer.step();model.constrain();inv=model.invariants()
    np.savez_compressed(output/'fixture_arrays.npz',**opt.snapshot_cpu(first))
    result=dict(status='PASS_GSPLAT_GPU_PREFLIGHT',scientific_verdict=None,original_pixel=[31,35],
        stock_means2d=projected,rendered_peak_yx=peak,gradients=gradients,invariants=inv,runtime=runtime(),
        config_sha256=sha(config_path),driver_sha256=sha(__file__),optimization_sha256=sha(opt.__file__),
        outputs={'fixture_arrays.npz':sha(output/'fixture_arrays.npz')})
    write(output/'receipt.json',result);return result


def check_shapes(view,arrays):
    shape=(int(view['height']),int(view['width']))
    for key in ('prior_depth','selected_depth','prior_normal','selected_normal',*MASKS):
        expected=shape+(3,) if key.endswith('_normal') else shape
        if key not in arrays or arrays[key].shape!=expected:raise ValueError('Prepared view array shape differs: '+key)
    for key in MASKS:
        if arrays[key].dtype!=bool:raise ValueError('Fixed support masks must be explicit bool: '+key)
    if not arrays['photo_mask'].any():raise ValueError('No frozen photometric support')
    if np.any(arrays['depth_valid']&arrays['projection_abstain_mask']) or np.any(arrays['normal_valid']&arrays['projection_abstain_mask']):raise ValueError('Projected ambiguity cannot supervise depth/normal')
    if np.any(arrays['target_mask']&arrays['surrounding_mask']):raise ValueError('Target and surrounding windows overlap')
    expected=arrays['photo_mask']&~(arrays['target_mask']|arrays['surrounding_mask'])
    if not np.array_equal(expected,arrays['outside_mask']):raise ValueError('Outside must be remaining fixed regional support')
    both=np.isfinite(arrays['prior_depth'])&(arrays['prior_depth']>0)&np.isfinite(arrays['selected_depth'])&(arrays['selected_depth']>0)
    if np.any(arrays['depth_valid']&~both):raise ValueError('Paired depth domain must be valid for both arms')


def train(args,cfg,output):
    started=time.time();tcfg=cfg['training'];seed=int(tcfg['seed']);random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True,warn_only=True)
    manifest_path=args.prepared/args.region/'manifest.json';manifest=json.loads(manifest_path.read_text());root=manifest_path.parent
    if manifest.get('scientific_verdict') is not None:raise ValueError('Null scientific verdict required')
    arm_path=root/manifest['arms'][args.arm]
    expected=manifest.get('arm_sha256',{}).get(args.arm)
    if expected is None:raise ValueError('Prepared arm SHA256 required')
    if sha(arm_path)!=expected:raise ValueError('Source assembly bytes differ')
    points=load_npz(arm_path);model=opt.SourceGaussians(points,tcfg);optimizer=model.optimizer(tcfg)
    inputs=[dict(path=str(path),sha256=sha(path)) for path in (manifest_path,arm_path,args.config,Path(__file__),Path(opt.__file__))]
    views={};gpu={};order=[]
    for view in manifest['views']:
        vid=str(view['id'])
        if '/' in vid or vid in views:raise ValueError('Unique path-safe view ID required')
        path=Path(view['rgb_path']);path=path if path.is_absolute() else root/path
        if sha(path)!=view['rgb_sha256']:raise ValueError('RGB hash differs')
        arrays_path=root/view['arrays_path']
        if sha(arrays_path)!=view['arrays_sha256']:raise ValueError('View depth/mask bytes differ')
        arrays=load_npz(arrays_path);check_shapes(view,arrays)
        photo=np.asarray(Image.open(path).convert('RGB'),np.float32)/255
        if photo.shape!=(view['height'],view['width'],3):raise ValueError('RGB grid differs')
        views[vid]=dict(view=view,arrays=arrays,photo=photo)
        gpu[vid]=dict(photo=torch.from_numpy(photo).cuda(),arrays={k:torch.from_numpy(v).cuda() for k,v in arrays.items() if v.dtype.kind in 'bifu'})
        if view.get('split','train')=='train':order.append(vid)
        inputs.extend([dict(path=str(path),sha256=view['rgb_sha256']),dict(path=str(arrays_path),sha256=view['arrays_sha256'])])
    if not order:raise ValueError('No fixed train cameras')
    random.Random(seed).shuffle(order)
    steps=int(tcfg['iterations']);checkpoints=sorted(set(map(int,tcfg['checkpoints'])))
    if checkpoints[0]!=0 or checkpoints[-1]!=steps:raise ValueError('Iteration0 and final snapshot required')
    if tcfg.get('densification') or tcfg.get('pruning'):raise ValueError('This bounded identity-preserving probe has no densification/pruning')
    rt=runtime()
    if rt['image_id']!=cfg['resources']['image']:raise ValueError('Pinned Docker image identity environment differs')
    shutil.copy2(args.config,output/'config_snapshot.json');shutil.copy2(manifest_path,output/'manifest_snapshot.json')
    write(output/'invocation.json',dict(task_id=cfg['task_id'],region=args.region,arm=args.arm,
        scientific_verdict=None,manifest_sha256=sha(manifest_path),config_sha256=sha(args.config),
        driver_sha256=sha(__file__),optimization_sha256=sha(opt.__file__),inputs=inputs,runtime=rt,
        training=tcfg,camera_order=order,source_points=len(points['xyz']),geometry_trainable=int(np.asarray(points['trainable_geometry']).sum()),
        standard_renderer_bounded_optimizer=True,complete_vanilla_2dgs=False,seed=seed,started_unix=started))
    initial_renders={};checkpoint_rows=[];no_op={}
    def snapshot(iteration):
        inv=model.invariants();arrays=model.arrays(points)
        cp=f'checkpoint_{iteration:06d}'
        np.savez_compressed(output/(cp+'.npz'),**arrays)
        torch.save(dict(schema='jbgs.source_selected_2dgs.state.v1',scientific_verdict=None,iteration=iteration,
            arm=args.arm,region=args.region,model=model.state_dict(),optimizer=optimizer.state_dict(),
            random_state=random.getstate(),numpy_state=np.random.get_state(),torch_state=torch.get_rng_state(),
            cuda_state=torch.cuda.get_rng_state_all(),camera_order=order,next_camera_index=iteration%len(order),
            config_sha256=sha(args.config),manifest_sha256=sha(manifest_path)),output/(cp+'.pth'))
        parent=output/'renders'/f'iteration_{iteration:06d}';parent.mkdir(parents=True)
        rows=[]
        with torch.no_grad():
            for vid,item in views.items():
                view=item['view'];rendered=opt.render(model,view,distloss=False);raw=opt.snapshot_cpu(rendered)
                if not all(np.isfinite(x).all() for x in raw.values()):raise ValueError('Nonfinite checkpoint render')
                if iteration==0:
                    initial_renders[vid]=raw
                    if not no_op:
                        repeat=opt.snapshot_cpu(opt.render(model,view,distloss=False))
                        no_op.update({key:float(np.max(np.abs(raw[key]-repeat[key]))) for key in ('rgb','depth','alpha','normal')})
                        no_op['view_id']=vid
                        if any(no_op[key]>1e-6 for key in ('rgb','depth','alpha','normal')):raise ValueError('Actual regional iteration0 repeat render exceeds1e-6')
                masks={k.replace('_mask',''):item['arrays'][k] for k in ('target_mask','surrounding_mask','outside_mask')}
                metrics=opt.comparison_metrics(item['photo'],initial_renders[vid],raw,masks)
                folder=parent/vid;folder.mkdir()
                payload=dict(raw,photo=item['photo'],**{k:item['arrays'][k] for k in MASKS})
                np.savez_compressed(folder/'raw.npz',**payload)
                Image.fromarray(np.round(np.clip(raw['rgb'],0,1)*255).astype(np.uint8)).save(folder/'rgb.png')
                Image.fromarray(np.round(np.clip(raw['alpha'],0,1)*255).astype(np.uint8)).save(folder/'alpha.png')
                Image.fromarray(np.round(np.clip(raw['normal']*.5+.5,0,1)*255).astype(np.uint8)).save(folder/'normal.png')
                valid=(initial_renders[vid]['alpha']>=.5)&(initial_renders[vid]['depth']>0)
                limit=float(np.percentile(initial_renders[vid]['depth'][valid],99)) if valid.any() else 1.
                Image.fromarray(np.round(np.clip(raw['depth']/max(limit,1e-6),0,1)*255).astype(np.uint8)).save(folder/'depth.png')
                record=dict(view_id=vid,iteration=iteration,camera=view,metrics=metrics,depth_display_range_m=[0,limit],
                    renderer_depth=rt['depth'],camera_adapter=rt['pixel_adapter'],
                    excluded_frame_pixels=int(view['height']*view['width']-item['arrays']['photo_mask'].sum()))
                write(folder/'metrics.json',record);rows.append(record)
        checkpoint_rows.append(dict(iteration=iteration,invariants=inv,views=rows))
        print(json.dumps(dict(event='checkpoint',region=args.region,arm=args.arm,iteration=iteration,views=len(rows))),flush=True)
    snapshot(0)
    with (output/'loss_trace.jsonl').open('x') as log:
        for iteration in range(1,steps+1):
            tick=time.time();vid=order[(iteration-1)%len(order)];item=views[vid];data=gpu[vid]
            optimizer.zero_grad(set_to_none=True);rendered=opt.render(model,item['view'],distloss=True)
            loss,terms,counts=opt.objective(rendered,data['photo'],data['arrays'],args.arm,tcfg)
            loss.backward()
            gradient={name:dict(finite=p.grad is not None and bool(torch.isfinite(p.grad).all()),max_abs=float(p.grad.abs().max()) if p.grad is not None else None) for name,p in model.named_parameters()}
            if not all(v['finite'] for v in gradient.values()):raise ValueError('Nonfinite or missing parameter gradient')
            optimizer.step();model.constrain()
            row=dict(iteration=iteration,view_id=vid,terms={k:float(v.detach()) for k,v in terms.items()},counts=counts,gradient=gradient,seconds=time.time()-tick)
            log.write(json.dumps(clean(row),allow_nan=False)+'\n');log.flush()
            if iteration%50==0:print(json.dumps(dict(event='training',region=args.region,arm=args.arm,iteration=iteration,loss=row['terms']['total'])),flush=True)
            if iteration in checkpoints:snapshot(iteration)
    final=model.invariants();write(output/'checkpoint_summary.json',checkpoint_rows)
    for item in inputs:
        if sha(item['path'])!=item['sha256']:raise ValueError('Frozen input changed during training')
    outputs={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    receipt=dict(task_id=cfg['task_id'],status='PASS_SOURCE_SELECTED_2DGS_TRAIN',scientific_verdict=None,
        arm=args.arm,region=args.region,manifest_sha256=sha(manifest_path),config_sha256=sha(args.config),
        iterations=steps,checkpoints=checkpoints,camera_order=order,camera_order_sha256=hashlib.sha256(json.dumps(order).encode()).hexdigest(),
        source_points=len(points['xyz']),geometry_trainable=int(np.asarray(points['trainable_geometry']).sum()),
        final_invariants=final,outputs=outputs,runtime=rt,input_hashes_unchanged=True,iteration0_repeat_max_abs=no_op,
        wall_seconds=time.time()-started,peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    write(output/'receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('status','region','arm','wall_seconds')}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--region',choices=('P1','P2','P3'))
    p.add_argument('--arm',choices=('prior_only','source_selected'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--preflight',action='store_true');a=p.parse_args()
    if not Path('/.dockerenv').exists() or not torch.cuda.is_available():raise RuntimeError('Explicitly queued GPU Docker required')
    if Path('/reference').exists():raise RuntimeError('Evaluation reference must not be mounted for training')
    if a.output.exists():raise FileExistsError(a.output)
    a.output.mkdir(parents=True);cfg=json.loads(a.config.read_text())
    if cfg.get('scientific_verdict') is not None:raise ValueError('Null scientific verdict required')
    torch.set_num_threads(4)
    try:
        if a.preflight:
            result=fixture(cfg['training'],a.output,a.config);print(json.dumps(clean(result)),flush=True)
        else:
            if not all((a.prepared,a.region,a.arm)):raise ValueError('Prepared root, region and arm required')
            train(a,cfg,a.output)
    except Exception as error:
        write(a.output/'failure.json',dict(status='FAIL',scientific_verdict=None,error=repr(error),traceback=traceback.format_exc(),partial_outputs_preserved=True))
        raise


if __name__=='__main__':main()
