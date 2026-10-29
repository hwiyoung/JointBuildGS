"""All 203 saved-scene photos, exact colour adjoints and opacity gradients.

No optimizer step or new training. GT labels are reporting/gate inputs only.
"""
import gc
import hashlib
import json
import math
import random
import runpy
import sys
import time
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,'/source')
import jbgs_freespace as F
import jbgs_judgment as J
from freespace_training import install_median
install_median()
from gaussian_renderer import render
from utils.loss_utils import l1_loss,ssim

ROOT=Path('/out/freespace_v1');DOC=Path('/docs/freespace_v1')


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()


def photoloss(pkg,cam,opt):
    gt=cam.original_image.cuda()
    return (1-opt.lambda_dssim)*l1_loss(pkg['render'],gt)+opt.lambda_dssim*(1-ssim(pkg['render'],gt))


def relative(a,b):
    if a is None or b is None:return 0. if a is None and b is None else float('inf')
    return float((a-b).double().norm()/a.double().norm().clamp_min(1e-30))


def off_replay(j,opt,scene,g,pipe,bg):
    # Same seed/current RNG draw sequence as the first ten training iterations,
    # evaluated without stepping Adam (the user explicitly says no training).
    state=random.getstate();stack=scene.getTrainCameras().copy();rows=[]
    params=[g._xyz,g._scaling,g._rotation,g._opacity,g._features_dc,g._features_rest]
    names=['xyz','scaling','rotation','opacity','features_dc','features_rest']
    for iteration in range(1,11):
        cam=stack.pop(random.randint(0,len(stack)-1));j.cur_iter=iteration
        pkg=render(cam,g,pipe,bg);rgb=photoloss(pkg,cam,opt)
        m,p,_=j.losses(cam.image_name,pkg)
        total=rgb+j.lambda_mvs*m+j.lambda_prior*p
        off=F.add_loss(total,None,j,cam,g,pkg['fs_median_depth'],iteration)
        assert off is total
        a=torch.autograd.grad(total,params,retain_graph=True,allow_unused=True)
        b=torch.autograd.grad(off,params,retain_graph=True,allow_unused=True)
        # Third traversal is a baseline-vs-baseline negative control for CUDA
        # atomic accumulation noise. It cannot relax the user's tolerance.
        c=torch.autograd.grad(total,params,retain_graph=True,allow_unused=True)
        cancelled=torch.autograd.grad(off-total,params,allow_unused=True)
        diffs={name:relative(x,y) for name,x,y in zip(names,a,b)}
        control={name:relative(x,y) for name,x,y in zip(names,a,c)}
        exact_zero=all(x is None or int(torch.count_nonzero(x))==0 for x in cancelled)
        assert exact_zero
        rows.append(dict(iteration=iteration,view=cam.image_name,loss=float(total.detach()),
            loss_relative_difference=0.,gradient_relative_l2=diffs,baseline_repeat_relative_l2=control,
            same_graph_difference_gradient_exact_zero=exact_zero))
        del pkg,rgb,total,off,m,p,a,b,c,cancelled
    random.setstate(state)
    maximum=max(max(x['gradient_relative_l2'].values()) for x in rows)
    result=dict(status='PASS' if maximum<=1e-6 else 'FAIL_NUMERICAL_TOLERANCE',rows=rows,maximum_relative_difference=maximum,
        evaluation='First ten seed-drawn training cameras, initial model, two full backward traversals per loss. No Adam updates, density changes or training run.',
        off_same_tensor_identity=True,optimizer_steps=0,scientific_verdict=None)
    write(ROOT/'off_ten.json',result);write(DOC/'off_ten.json',result)
    print('OFF_TEN',result['status'],result['maximum_relative_difference'],flush=True)
    return result


def table(path,rows):
    import csv
    write(path.with_suffix('.json'),dict(rows=rows,scientific_verdict=None))
    if rows:
        with path.with_suffix('.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def rankprob(pressure,a,b):
    x=pressure[a];y=np.sort(pressure[b])
    if not len(x) or not len(y):return dict(strict=None,midrank=None,tie_fraction=None,n_a=len(x),n_b=len(y))
    left=np.searchsorted(y,x,side='left').sum(dtype=np.float64)
    right=np.searchsorted(y,x,side='right').sum(dtype=np.float64);pairs=len(x)*len(y)
    return dict(strict=float(left/pairs),midrank=float((left+right)/(2*pairs)),tie_fraction=float((right-left)/pairs),n_a=len(x),n_b=len(y))


def plot(cam,pkg,G,free,case,case_ids,e):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for p in Path('/fonts').glob('NotoSansCJK-Regular.ttc'):
        font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']='Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus']=False
    image=cam.original_image[:3].permute(1,2,0).cpu().numpy().clip(0,1)
    xyz=torch.as_tensor(e['centre'][case_ids],device='cuda',dtype=torch.float32)
    clip=torch.cat([xyz,torch.ones_like(xyz[:,:1])],1)@cam.full_proj_transform
    uv=((clip[:,:2]/clip[:,3:4]+1)*torch.tensor([cam.image_width,cam.image_height],device='cuda')/2-.5).cpu().numpy()
    finite=np.isfinite(uv).all(1)&(clip[:,3].cpu().numpy()>0)
    xy=uv[finite]
    if len(xy):
        lower=np.maximum(np.floor(xy.min(0)-50),0).astype(int)
        upper=np.minimum(np.ceil(xy.max(0)+50),[cam.image_width,cam.image_height]).astype(int)
    else:lower=np.array([0,0]);upper=np.array([cam.image_width,cam.image_height])
    x0,y0=lower;x1,y1=upper
    if x1<=x0 or y1<=y0:x0,y0,x1,y1=0,0,cam.image_width,cam.image_height
    fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    axes[0].imshow(image[y0:y1,x0:x1]);axes[0].set_title('학습 사진')
    for ax,data,title in [(axes[1],G,'모두 놓아줌 G'),(axes[2],free,'앞면 차지 비율 F')]:
        im=ax.imshow(data.detach().cpu().numpy()[y0:y1,x0:x1],vmin=0,vmax=1,cmap='magma')
        ax.set_title(title);fig.colorbar(im,ax=ax,fraction=.04)
    for ax in axes:ax.axis('off')
    fig.suptitle(case+' · '+cam.image_name+'\n판 4 저장 모델, 학습 없음')
    folder=DOC/'figures';folder.mkdir(exist_ok=True)
    fig.savefig(folder/(case+'.png'),dpi=170);plt.close(fig)
    np.savez_compressed(ROOT/(case+'_maps.npz'),G=G.detach().cpu().numpy()[y0:y1,x0:x1],F=free.detach().cpu().numpy()[y0:y1,x0:x1],crop=np.array([x0,y0,x1,y1]))


def probe(j,args,opt,scene,g,pipe,bg):
    start=time.monotonic();cfg=json.loads(Path('/config/farpull_v1_freespace_v1.json').read_text())
    assert digest('/config/farpull_v1_freespace_v1.json')==json.loads(Path('/config/farpull_v1_freespace_v1.lock.json').read_text())['sha256']
    off_check=off_replay(j,opt,scene,g,pipe,bg)
    unit=Path('/ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/runs/B173nb_b10/lt_dynnow_ALS_s0')
    attempt=json.loads((unit/'PASS.json').read_text())['attempt'];model=unit/f'attempt_{attempt}/model'
    checkpoint=model/'jbgs_complete/iteration_30000/checkpoint.pth'
    state=torch.load(checkpoint,map_location='cuda',weights_only=False);assert state['iteration']==30000
    g.restore(state['model'],opt)
    for attr in ['frozen_mask','density_mask','origin','init_id','completed_mask']:
        if attr in state:setattr(g,attr,state[attr].to('cuda') if state[attr] is not None else None)
    j.cur_iter=30000
    with np.load(model/'dump/iteration_30000/gaussians.npz') as z:
        assert np.array_equal(g.get_xyz.detach().cpu().numpy(),z['xyz'])
    support=Path('/out/evidence_prune_v1/B173nb_b10')
    for name,expected in cfg['support_sha256']['B173nb_b10'].items():assert digest(support/name)==expected,name
    with np.load(support/'diagnostic_labels.npz') as z:labels={k:z[k] for k in z.files}
    roof=labels['roof'];wall=labels['wall'];floating=labels['floating']&~roof&~wall
    assert int(floating.sum())==cfg['expected_floating']
    with np.load(support/'delete_mask.npz') as z:
        assert np.array_equal(g.frozen_mask.cpu().numpy(),z['protected'])
        inside=torch.as_tensor(z['inside_scope'],device='cuda')
    with np.load('/ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/B173nb_b10__ALS/evaluation.npz') as z:e={k:z[k] for k in ['cell','centre']}
    cases=json.loads(Path('/config/floatdiag_reference/cases_ALS.json').read_text())['cases']
    cases={c['id']:c for c in cases if c['site']=='B173nb_b10'}
    choices=json.loads(Path('/config/floatdiag_reference/photos_B173nb_b10_ALS.json').read_text())['cases']
    selected={r['case']:r['main']['view'] for r in choices if r['main'] and r['case'] in cases}
    quality=json.loads(Path('/ph/main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1/renders/B173nb_b10/lt_dynnow_ALS_s0/iteration_30000/quality.json').read_text())
    ref={r['view']:r['psnr_db'] for r in quality['train']}
    cams=scene.getTrainCameras();assert len(cams)==203 and {c.image_name for c in cams}==set(ref)
    N=len(g.get_xyz);pressure=np.zeros(N,np.float64);photo_abs=np.zeros(N,np.float64);free_abs=np.zeros(N,np.float64)
    photo_samples=np.zeros((203,int(floating.sum())),np.float32);free_samples=np.zeros_like(photo_samples)
    cell_num=np.zeros(7,np.int64);cell_den=np.zeros(7,np.int64);rows=[];max_psnr=0.
    cell_lookup=torch.as_tensor(e['cell'],device='cuda');del state;gc.collect();torch.cuda.empty_cache()
    for i,cam in enumerate(cams):
        pkg=render(cam,g,pipe,bg);photo=photoloss(pkg,cam,opt)
        photo_grad=torch.autograd.grad(photo,g._opacity)[0].detach().flatten()
        photo_abs+=photo_grad.abs().cpu().numpy().astype(np.float64)
        photo_samples[i]=photo_grad.abs().cpu().numpy()[floating]
        mse=(pkg['render'].detach().clamp(0,1)-cam.original_image[:3].cuda().clamp(0,1)).square().mean()
        psnr=float(-10*torch.log10(mse));max_psnr=max(max_psnr,abs(psnr-ref[cam.image_name]));assert max_psnr<=.1,(cam.image_name,max_psnr)
        sources,loc=F.sources_for(j,cam);G,margins,_=F.source_gate(pkg['fs_median_depth'].squeeze(0),sources)
        f=F.centre_flags(cam,g,sources,margins,inside);feature=f.clone().requires_grad_(True)
        free,_=F.feature_render(cam,g,feature)
        loss=(G*free).mean()
        df,do=torch.autograd.grad(loss,[feature,g._opacity]);do=do.detach().flatten()
        p=(df.detach()*f*G.numel()).cpu().numpy()
        assert np.isfinite(p).all() and p.min()>=-1e-7
        pressure+=np.maximum(p,0).astype(np.float64);free_abs+=do.abs().cpu().numpy().astype(np.float64)
        free_samples[i]=do.abs().cpu().numpy()[floating]
        has=(loc>=0)&(loc<len(cell_lookup));cells=torch.full_like(loc,-1);cells[has]=cell_lookup[loc[has]].long()
        counts=[]
        for cell in range(7):
            mask=cells==cell;den=int(mask.sum());num=int((mask&(G>.5)).sum());cell_num[cell]+=num;cell_den[cell]+=den
            counts.append(dict(cell=cell,pixels=den,G_gt_half=num,fraction=num/den if den else None))
        row=dict(index=i,view=cam.image_name,psnr_db=psnr,psnr_replay_abs_difference_db=abs(psnr-ref[cam.image_name]),
            L_free=float(loss.detach()),G_gt_half_fraction=float((G>.5).float().mean()),
            positive_f_gaussians=int((f>0).sum()),pressure_sum=float(p.sum()),cells=counts,
            floating_free_positive_gradient=int((do[torch.as_tensor(floating,device='cuda')]>0).sum()),
            floating_free_negative_gradient=int((do[torch.as_tensor(floating,device='cuda')]<0).sum()))
        rows.append(row)
        for case,name in selected.items():
            if cam.image_name==name:plot(cam,pkg,G,free,case,np.asarray(cases[case]['patch_indices']),e)
        write(ROOT/'live.json',dict(done=i+1,total=203,seconds=time.monotonic()-start,last_view=cam.image_name,optimizer_steps=0,scientific_verdict=None))
        if i%10==0 or i==202:print('FREESPACE_PREFLIGHT',i+1,203,'seconds',round(time.monotonic()-start),flush=True)
        del pkg,photo,photo_grad,free,loss,df,do,feature,f,G,margins,sources,loc,cells
    groups=dict(roof=roof,wall=wall,floating=floating,other=~(roof|wall|floating));group_rows=[]
    for name,mask in groups.items():
        q=np.quantile(pressure[mask],[.5,.9,.99]) if mask.any() else [None]*3
        group_rows.append(dict(group=name,count=int(mask.sum()),p50=q[0],p90=q[1],p99=q[2],positive_fraction=float((pressure[mask]>0).mean()) if mask.any() else None))
    ranks={name:rankprob(pressure,floating,mask) for name,mask in [('roof',roof),('wall',wall),('roof_or_wall',roof|wall)]}
    a=float(np.median(photo_abs[floating]/203));b=float(np.median(free_abs[floating]/203))
    calibration=dict(a=a,b=b,lambda1=a/b if b>0 else None,lambda4=4*a/b if b>0 else None,
        pooled_photo_gaussian_median=float(np.median(photo_samples)),pooled_free_gaussian_median=float(np.median(free_samples)),
        rule=cfg['calibration'],status='PASS' if b>0 and a>0 else 'UNAVAILABLE_ZERO_GRADIENT')
    rank=ranks['roof_or_wall']['strict'];gate=rank is not None and rank>=.8
    result=dict(status='PASS' if gate and calibration['status']=='PASS' and off_check['status']=='PASS' else 'STOP_PREFLIGHT_GATE',rank_pass=gate,
        off_check_status=off_check['status'],off_check_maximum_relative_difference=off_check['maximum_relative_difference'],
        ranks=ranks,calibration=calibration,groups=group_rows,views=203,gaussians=N,floating_count=int(floating.sum()),
        max_psnr_replay_difference_db=max_psnr,optimizer_steps=0,seconds=time.monotonic()-start,
        source_checkpoint_sha256=digest(checkpoint),diagnostic_labels_sha256=digest(support/'diagnostic_labels.npz'),
        all_photos_exact_membership=True,scope_reused_exact=True,depth='native median',scientific_verdict=None)
    np.savez_compressed(ROOT/'pressure_and_gradients.npz',pressure=pressure,photo_abs_mean=photo_abs/203,free_abs_mean=free_abs/203,
        roof=roof,wall=wall,floating=floating,photo_samples=photo_samples,free_samples=free_samples)
    cell_rows=[dict(cell=i,pixels=int(cell_den[i]),G_gt_half=int(cell_num[i]),fraction=float(cell_num[i]/cell_den[i]) if cell_den[i] else None) for i in range(7)]
    table(DOC/'pressure_groups',group_rows);table(DOC/'cells',cell_rows);write(ROOT/'views.json',dict(rows=rows,scientific_verdict=None))
    write(ROOT/'preflight.json',result);write(DOC/'preflight.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


original=J.Judgment.__init__
def init(self,args,opt,scene,g,*a,**kw):
    original(self,args,opt,scene,g,*a,**kw)
    probe(self,args,opt,scene,g,kw['pipe'],kw['background'])
    raise SystemExit(0)


if __name__=='__main__':
    J.Judgment.__init__=init
    sys.argv[0]='/source/train.py'
    runpy.run_path('/source/train.py',run_name='__main__')
