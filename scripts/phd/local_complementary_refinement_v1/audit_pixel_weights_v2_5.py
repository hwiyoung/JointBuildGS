"""Full-raster CPU checks of frozen LC weights on real targets, synthetic predictions."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
import traceback

import numpy as np
import torch
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save_csv(path, rows):
    with Path(path).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(set().union(*(r.keys() for r in rows))))
        writer.writeheader(); writer.writerows(rows)


def numeric_check(actual, expected, atol, rtol, name):
    a, b = np.asarray(actual), np.asarray(expected)
    require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), name+' shape/nonfinite')
    error = np.abs(a-b)
    require(np.all(error <= atol + rtol*np.abs(b)), name+' exceeds tolerance')
    return float(np.max(error)) if error.size else 0.


def independent_maps(prior, visual, tau0, tau1):
    vp, vi = np.isfinite(prior)&(prior>0), np.isfinite(visual)&(visual>0)
    both = vp&vi
    bp, bi = vp.astype(prior.dtype), vi.astype(prior.dtype)
    a = np.full(prior.shape, np.nan, dtype=prior.dtype)
    a[both] = np.clip((np.abs(prior[both]-visual[both])-tau0)/(tau1-tau0), 0, 1)
    bp[both], bi[both] = 1-a[both], a[both]
    return vp, vi, both, a, bp, bi


def prediction_map(prior, visual, vp, vi, mode, offset):
    pred = np.ones_like(prior)
    both = vp&vi
    if mode == 'midpoint':
        pred[both] = prior[both] + (visual[both]-prior[both])/2
    elif mode == 'above':
        pred[both] = np.maximum(prior[both], visual[both])+offset
    elif mode == 'below':
        pred[both] = np.minimum(prior[both], visual[both])-offset
    else:
        raise ValueError('Unknown synthetic prediction')
    sign = -1 if mode == 'below' else 1
    pred[vp&~vi] = prior[vp&~vi]+sign*offset
    pred[vi&~vp] = visual[vi&~vp]+sign*offset
    require(np.isfinite(pred).all(), 'Synthetic prediction became nonfinite')
    return pred


def plot_camera(output, region, camera, rgb, vp, vi, bp, bi, scenario_maps, cfg):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    sequential = LinearSegmentedColormap.from_list('weight_blue', ['#f7fbff','#2864a5'])
    sequential.set_bad(cfg['visuals']['missing_color'])
    signed = LinearSegmentedColormap.from_list('signed', ['#2864a5','#ffffff','#c66b24'])
    signed.set_bad(cfg['visuals']['missing_color'])
    fig, axes = plt.subplots(4,3,figsize=(15,15),layout='constrained')
    axes[0,0].imshow(rgb); axes[0,0].set_title('Sealed RGB: camera context only')
    for ax, values, valid, title in ((axes[0,1],bp,vp,'Prior multiplier bP'),(axes[0,2],bi,vi,'Visual multiplier bI')):
        im=ax.imshow(np.where(valid,values,np.nan),cmap=sequential,vmin=0,vmax=1,interpolation='nearest')
        ax.set_title(title+'; gray = source unavailable'); fig.colorbar(im,ax=ax,shrink=.7)
    strength_max=max(float(m['total_strength'].max()) for _,m in scenario_maps)*1e8
    gradient_max=max(float(np.max(np.abs(m['signed_gradient_sum']))) for _,m in scenario_maps)*1e8
    gradient_max=max(gradient_max,1e-12)
    for row,(coefficient,maps) in enumerate(scenario_maps,1):
        images=[(maps['final_image_share'],sequential,0,1,'Final image share; gray = undefined'),
                (np.where(vp|vi,maps['total_strength']*1e8,np.nan),sequential,0,strength_max,'Total depth strength × 1e8'),
                (np.where(vp|vi,maps['signed_gradient_sum']*1e8,np.nan),signed,-gradient_max,gradient_max,'Synthetic midpoint dL/dd × 1e8')]
        for col,(array,cmap,vmin,vmax,title) in enumerate(images):
            im=axes[row,col].imshow(array,cmap=cmap,vmin=vmin,vmax=vmax,interpolation='nearest')
            axes[row,col].set_title(f'lambdaP={coefficient:g}: '+title,fontsize=10)
            fig.colorbar(im,ax=axes[row,col],shrink=.7)
    for ax in axes.flat:
        ax.set_xlabel('Pixel column u'); ax.set_ylabel('Pixel row v'); ax.tick_params(labelsize=8)
    fig.suptitle(f'{region} / {camera}\nFull-raster CPU weight audit: real targets, SYNTHETIC prediction, no Gaussian update\n'
                 f'Nprior={int(vp.sum()):,}; Nvisual={int(vi.sum()):,}; lambdaI=.05 scenarios. Source counts are not assumed equal.',fontsize=12)
    fig.savefig(output/f'{region}_pixel_weight_maps.png',dpi=cfg['visuals']['dpi'])
    plt.close(fig)


def plot_table(output, rows, cfg):
    import matplotlib.pyplot as plt
    selected=[r for r in rows if r['dtype']=='float64' and r['prediction']=='midpoint']
    data=[]
    for r in selected:
        float32=next(x for x in rows if x['region']==r['region'] and x['lambda_prior']==r['lambda_prior'] and x['dtype']=='float32' and x['prediction']=='midpoint')
        data.append([r['region'],f"{r['lambda_prior']:g}",f"{r['prior_valid_count']:,}",f"{r['visual_valid_count']:,}",
            f"{r['local_prior_loss']:.5g}",f"{r['local_visual_loss']:.5g}",f"{r['scaled_depth_total']:.5g}",
            f"{r['gradient_sum_max_abs_error']:.2e}",f"{float32['gradient_sum_max_abs_error']:.2e}"])
    fig,ax=plt.subplots(figsize=(15,4)); ax.axis('off')
    table=ax.table(cellText=data,colLabels=['Region','lambdaP','Nprior','Nvisual','Local LP','Local LI','Scaled total','Grad err f64','Grad err f32'],loc='center',cellLoc='center')
    table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1,1.7)
    for (r,c),cell in table.get_celld().items():
        cell.set_edgecolor('#dddddd')
        if r==0: cell.set_facecolor('#e8eef6')
    ax.set_title('Real full target rasters / synthetic midpoint prediction / lambdaI=.05\nLoss and per-pixel gradient verification; no scene performance or Gaussian update measured',pad=18)
    fig.text(.5,.03,'Local LP/LI include spatial multipliers but exclude lambda. Errors are max absolute analytic-vs-autograd depth-gradient errors.',ha='center',fontsize=10)
    fig.savefig(output/'verification_table.png',dpi=cfg['visuals']['dpi'],bbox_inches='tight'); plt.close(fig)


def run(args, output, records):
    snapshots=output/'snapshots'; snapshots.mkdir()
    def bind(path, expected=None, snapshot=None):
        path=Path(path); digest=sha(path)
        require(expected is None or digest==expected, 'Input hash differs: '+str(path))
        records.append(dict(path=str(path),bytes=path.stat().st_size,sha256_before=digest,expected_sha256=expected))
        if snapshot:
            dest=snapshots/snapshot; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,dest)
        return path
    cfg=json.loads(bind(args.config,snapshot='pixel_weight_audit_v2_5.json').read_text())
    require(cfg['schema']=='JBGS_PIXEL_WEIGHT_AUDIT_v2_5' and cfg['scientific_verdict'] is None,'Audit config identity')
    main=json.loads(bind(args.main_config,cfg['expected_training_config_sha256'],'experiment_v2.json').read_text())
    binding=json.loads(bind(args.binding,cfg['expected_binding_sha256'],'input_binding.json').read_text())
    require(binding['config']['sha256']==sha(args.main_config),'Main config/binding differs')
    require(main['runtime']['image_id']==os.environ['JBGS_RUNTIME_IMAGE_ID'],'Runtime image differs')
    require(main['local_weight']['confidence_enabled'] is False,'This audit requires disabled confidence')
    tau0,tau1=binding['tau0_m'],binding['tau1_m']
    require((tau0,tau1)==(main['local_weight']['tau0_m'],main['local_weight']['tau1_m']),'Threshold binding differs')
    bind(__file__,snapshot='audit_pixel_weights_v2_5.py'); bind(args.launcher,snapshot='run_pixel_weight_audit_v2_5.sh')
    helper_path=bind(args.helper,snapshot='jbgs_local_depth.py')
    spec=importlib.util.spec_from_file_location('frozen_local_depth',helper_path)
    helper=importlib.util.module_from_spec(spec); sys.modules[spec.name]=helper; spec.loader.exec_module(helper)
    checks,gate_checks,case_stats=[],[],[]
    for case in cfg['cases']:
        region,camera=case['region'],case['camera']; stem=Path(camera).stem
        invocation=json.loads(bind(args.inputs/region/'train_invocation.json',snapshot=region+'/train_invocation.json').read_text())
        require(invocation['implementation_hashes']['jbgs_local_depth.py']==sha(helper_path),'Frozen helper differs from actual invocation')
        require(invocation['config_sha256']==sha(args.main_config) and invocation['input_binding']['sha256']==sha(args.binding),'Invocation binding differs')
        manifest=json.loads(bind(args.inputs/region/'input_manifest.json',binding['regions'][region]['manifest']['sha256'],region+'/input_manifest.json').read_text())
        seals={r['path']:r for r in manifest['files']}
        require(len(seals)==len(manifest['files']),'Duplicate manifest file paths')
        arrays={}
        for key,relative in [('prior','prior/raw_depth/'+stem+'.npy'),('visual','da3/raw_depth/'+stem+'.npy'),('rgb','scene/images/'+camera)]:
            path=bind(args.inputs/region/relative,seals[relative]['sha256'])
            require(path.stat().st_size==seals[relative]['bytes'],'Input size differs')
            if key=='rgb':
                arrays[key]=np.array(Image.open(path).convert('RGB')); shutil.copyfile(path,output/(region+'_sealed_RGB.JPG'))
            else: arrays[key]=np.load(path,allow_pickle=False)
        require(arrays['prior'].shape==arrays['visual'].shape==arrays['rgb'].shape[:2],'Full raster dimensions differ')
        require(arrays['prior'].ndim==2,'Expected 2D full target rasters')
        base=independent_maps(arrays['prior'].astype('float64'),arrays['visual'].astype('float64'),tau0,tau1)
        vp0,vi0,both0,a0,bp0,bi0=base
        stats=dict(region=region,camera=camera,height=arrays['prior'].shape[0],width=arrays['prior'].shape[1],
            pixels=arrays['prior'].size,prior_valid_count=int(vp0.sum()),visual_valid_count=int(vi0.sum()),
            both_valid_count=int(both0.sum()),prior_only_count=int((vp0&~vi0).sum()),visual_only_count=int((vi0&~vp0).sum()),
            neither_valid_count=int((~vp0&~vi0).sum()),a_zero_both_count=int((a0[both0]==0).sum()),a_one_both_count=int((a0[both0]==1).sum()),
            input_prior_dtype=str(arrays['prior'].dtype),input_visual_dtype=str(arrays['visual'].dtype))
        case_stats.append(stats)
        np.savez_compressed(output/(region+'_base_maps.npz'),prior_target=arrays['prior'],visual_target=arrays['visual'],prior_valid=vp0,visual_valid=vi0,
            both_valid=both0,disagreement_gate_both_only=a0,prior_multiplier=bp0,visual_multiplier=bi0)
        scenario_maps=[]
        for dtype_name in cfg['dtypes']:
            dtype=np.dtype(dtype_name); tol=cfg['tolerances'][dtype_name]
            prior,visual=arrays['prior'].astype(dtype),arrays['visual'].astype(dtype)
            vp,vi,both,a,bp,bi=independent_maps(prior,visual,tau0,tau1)
            np_,ni=int(vp.sum()),int(vi.sum())
            pt,vt=torch.from_numpy(prior),torch.from_numpy(visual)
            for lambda_p in cfg['lambda_prior_scenarios']:
                lambda_i=cfg['lambda_visual']
                kp=(dtype.type(lambda_p)*bp/dtype.type(np_)) if np_ else np.zeros_like(bp)
                ki=(dtype.type(lambda_i)*bi/dtype.type(ni)) if ni else np.zeros_like(bi)
                strength=kp+ki; share=np.full_like(strength,np.nan)
                np.divide(ki,strength,out=share,where=strength>0)
                for mode in cfg['synthetic_predictions']:
                    pred=prediction_map(prior,visual,vp,vi,mode,cfg['single_source_offset_m'])
                    t=torch.tensor(pred,requires_grad=True)
                    captured={}
                    if mode=='midpoint' and lambda_p==cfg['lambda_prior_scenarios'][0]:
                        def capture(frame,event,arg):
                            if event=='return' and frame.f_code.co_filename==str(helper_path) and frame.f_code.co_name=='complementary_depth_losses':
                                captured.update({k:frame.f_locals[k].detach().cpu().numpy().copy() for k in ('wp','wv')})
                        sys.setprofile(capture)
                    try: lp,li,local_stats=helper.complementary_depth_losses(t,pt,vt,tau0=tau0,tau1=tau1,collect_stats=True)
                    finally: sys.setprofile(None)
                    if captured:
                        gate_checks.append(dict(region=region,dtype=dtype_name,
                            prior_gate_max_abs_error=numeric_check(captured['wp'],bp,tol['gate_atol'],0,'prior gate'),
                            visual_gate_max_abs_error=numeric_check(captured['wv'],bi,tol['gate_atol'],0,'visual gate')))
                    require(local_stats['prior_denominator']==np_ and local_stats['visual_denominator']==ni,'Source denominators differ')
                    rp=np.zeros_like(pred); ri=np.zeros_like(pred)
                    rp[vp]=pred[vp]-prior[vp]; ri[vi]=pred[vi]-visual[vi]
                    independent_lp=np.mean(bp[vp]*np.abs(rp[vp]),dtype=dtype) if np_ else dtype.type(0)
                    independent_li=np.mean(bi[vi]*np.abs(ri[vi]),dtype=dtype) if ni else dtype.type(0)
                    sp,si=lambda_p*lp,lambda_i*li
                    gp=torch.autograd.grad(sp,t,retain_graph=True)[0].detach().numpy()
                    gi=torch.autograd.grad(si,t,retain_graph=True)[0].detach().numpy()
                    gs=torch.autograd.grad(sp+si,t)[0].detach().numpy()
                    ap,ai=kp*np.sign(rp),ki*np.sign(ri)
                    row=dict(region=region,camera=camera,dtype=dtype_name,prediction=mode,lambda_prior=lambda_p,lambda_visual=lambda_i,
                        prior_valid_count=np_,visual_valid_count=ni,local_prior_loss=float(lp.detach()),local_visual_loss=float(li.detach()),
                        scaled_prior_loss=float(sp.detach()),scaled_visual_loss=float(si.detach()),scaled_depth_total=float((sp+si).detach()),
                        prior_loss_abs_error=numeric_check(lp.detach().numpy(),independent_lp,tol['loss_atol'],tol['loss_rtol'],'prior loss'),
                        visual_loss_abs_error=numeric_check(li.detach().numpy(),independent_li,tol['loss_atol'],tol['loss_rtol'],'visual loss'),
                        scaled_total_abs_error=numeric_check((sp+si).detach().numpy(),np.sum(kp*np.abs(rp)+ki*np.abs(ri),dtype=dtype),tol['loss_atol'],tol['loss_rtol'],'scaled depth total'),
                        gradient_prior_max_abs_error=numeric_check(gp,ap,tol['gradient_atol'],tol['gradient_rtol'],'prior signed gradient'),
                        gradient_visual_max_abs_error=numeric_check(gi,ai,tol['gradient_atol'],tol['gradient_rtol'],'visual signed gradient'),
                        gradient_sum_max_abs_error=numeric_check(gs,ap+ai,tol['gradient_atol'],tol['gradient_rtol'],'sum signed gradient'),
                        gradient_composition_max_abs_error=numeric_check(gs,gp+gi,tol['gradient_atol'],tol['gradient_rtol'],'gradient decomposition'),status='PASS')
                    checks.append(row)
                    if dtype_name=='float64' and mode=='midpoint':
                        maps=dict(prior_effective_coefficient=kp,visual_effective_coefficient=ki,total_strength=strength,final_image_share=share,
                            synthetic_prediction=pred,signed_gradient_prior=gp,signed_gradient_visual=gi,signed_gradient_sum=gs)
                        np.savez_compressed(output/f'{region}_lambdaP_{lambda_p:g}_maps.npz',**maps)
                        scenario_maps.append((lambda_p,maps))
        plot_camera(output,region,camera,arrays['rgb'],vp0,vi0,bp0,bi0,scenario_maps,cfg)
    save_csv(output/'verification_checks.csv',checks); save_csv(output/'case_counts.csv',case_stats); save_csv(output/'gate_checks.csv',gate_checks)
    plot_table(output,checks,cfg)
    return dict(status='PASS',schema=cfg['schema'],scientific_verdict=None,scope=cfg['scope'],coefficient_scope=cfg['coefficient_scope'],
        cases=case_stats,full_raster_trials=len(checks),gate_checks=gate_checks,tolerances=cfg['tolerances'],tau0_m=tau0,tau1_m=tau1,
        actual_gaussian_gradient_or_update_measured=False,raw_gt_accessed=False,training_executed=False,cuda_executed=False,
        float32_gradient_max_abs_error=max(r['gradient_sum_max_abs_error'] for r in checks if r['dtype']=='float32'),
        float64_gradient_max_abs_error=max(r['gradient_sum_max_abs_error'] for r in checks if r['dtype']=='float64'),
        limitations=['Full observed target rasters; prediction is synthetic, not rendered from an Anchor or trained Gaussian.',
          'Lambda scenarios are diagnostic assumptions, not measured run-wide coefficients.',
          'CPU autograd loss routing is tested; renderer, Gaussian parameters, Adam and CUDA backward are not exercised.',
          'A gate follows target disagreement, not source truth. Correct implementation does not establish useful geometry.',
          'Maps retain separate source-valid masks; coefficient zero is distinct from absent source. Image share is NaN when total strength is zero.',
          'Display downsampling is visual only; numeric verification and NPZ arrays use all original raster pixels.',
          'Cameras inherit earlier contextual selection; this is not a representative performance sample.'])


def main():
    require(Path('/.dockerenv').exists(),'Docker required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','main-config','binding','helper','launcher','inputs','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    output=args.output/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir(parents=True,exist_ok=False)
    records=[]; started=time.time(); result={}; exit_code=1
    try:
        result=run(args,output,records); exit_code=0
    except Exception as error:
        result=dict(status='FAIL',scientific_verdict=None,exception_type=type(error).__name__,exception=str(error)); traceback.print_exc()
    finally:
        for record in records:
            record['sha256_after']=sha(record['path']); record['unchanged']=record['sha256_before']==record['sha256_after']
        if not all(r['unchanged'] for r in records): result['status']='FAIL_INPUT_MUTATION'; exit_code=1
        result.update(inputs=records,started_unix=started,finished_unix=time.time(),command=sys.argv,
            runtime_image_id=os.environ.get('JBGS_RUNTIME_IMAGE_ID'),python_version=sys.version,numpy_version=np.__version__,torch_version=torch.__version__,
            cgroup_cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),cgroup_memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
        result['outputs']=[dict(path=str(p.relative_to(output)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(output.rglob('*')) if p.is_file()]
        write_json(output/'receipt.json',result)
    print(json.dumps(dict(status=result['status'],output=str(output),full_raster_trials=result.get('full_raster_trials'),scientific_verdict=None)))
    sys.exit(exit_code)


if __name__=='__main__': main()
