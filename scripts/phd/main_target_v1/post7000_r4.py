"""CPU-only cached-render TSDF and unchanged first-hit score for the 7000 pilot."""
import sys,subprocess
import numpy as np
from common import *
sys.path.insert(0,'/repo/src/phd')
import streamed_tsdf as T

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def prepare(site,prior,wd):
    root=OUT/'r4/runs'/f'tg_{site}_{prior}_s0/model/check7000';cover=json.loads((root/'coverage.json').read_text())
    folder=wd/'inputs';folder.mkdir(parents=True,exist_ok=False)
    dr=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
    poly=np.asarray(json.loads((dr/'s02_box'/site/'range.json').read_text())['polygon_local'])
    gt=loadz(dr/'s52/box_gt'/site/'gt_points.npz')['xyz'][:,2].astype(float)
    box=np.array([[poly[:,0].min()-2,poly[:,1].min()-2,np.percentile(gt,5)-5],
                  [poly[:,0].max()+2,poly[:,1].max()+2,gt.max()+5]])
    views=cover['views'];first=loadz(root/'renders'/f"{views[0]['camera']}.npz");H,W=first['depth'].shape
    depth=np.lib.format.open_memmap(folder/'depth_masked.npy',mode='w+',dtype='f4',shape=(len(views),H,W))
    rgb=np.lib.format.open_memmap(folder/'rgb.npy',mode='w+',dtype='u1',shape=(len(views),H,W,3))
    vv,uu=np.indices((H,W),dtype=np.float32);intr=[];extr=[];kept=[]
    for i,v in enumerate(views):
        a=loadz(root/'renders'/f"{v['camera']}.npz");d=a['depth'];K=np.asarray(v['K'],np.float32);M=np.asarray(v['W2C'],np.float32)
        inv=np.linalg.inv(M).astype(np.float32);cam=np.stack([(uu-K[0,2])/K[0,0]*d,(vv-K[1,2])/K[1,1]*d,d,np.ones_like(d)],-1)
        world=(cam.reshape(-1,4)@inv.T)[:,:3].reshape(H,W,3)
        valid=np.isfinite(d)&(d>0)&(world>=box[0].astype('f4')).all(2)&(world<=box[1].astype('f4')).all(2)
        depth[i]=np.where(valid,d,0);rgb[i]=a['rgb'];kept.append(float(valid.mean()))
        intr.append([K[0,0],K[1,1],K[0,2],K[1,2]]);extr.append(M)
    depth.flush();rgb.flush();del depth,rgb
    np.savez(folder/'cams.npz',names=np.array([v['camera'] for v in views]),intr=np.asarray(intr),wh=np.tile([W,H],(len(views),1)),extrinsic=np.asarray(extr))
    dump(folder/'meta.json',dict(site=site,result=f'tg_{site}_{prior}_s0',prior_scene=prior,box=box.tolist(),views=len(views),width=W,height=H,
        mean_share_of_pixels_in_box=float(np.mean(kept)),depth_dir=str(folder),views_without_depth=[],
        rgb='cached trained SH RGB; geometry independent of RGB',box_mask='same float32 pixel unprojection and unchanged box, evaluated on CPU',scientific_verdict=None))
    dump(folder/'binding.json',dict(files={p.name:sha(p) for p in folder.iterdir() if p.is_file()},
        source_coverage_sha256=sha(root/'coverage.json'),scientific_verdict=None))

def score(site,prior,wd):
    import open3d as o3d
    sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
    import mesh_worker as MW,mesh_common as MC
    lt=PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'{site}__{prior}'
    e=loadz(lt/'evaluation.npz');v=loadz(lt/'values.npz');task=loadz(OUT/'r2/stage0/evaluation'/f'{site}_{prior}.npz')
    target=loadz(OUT/'r2/targets'/f'{site}_{prior}.npz')
    assert e['centre'].shape==task['centre'].shape and np.allclose(e['centre'],task['centre'],rtol=0,atol=1e-8)
    eligible=e['in_eval']&e['scoring_allowed']
    assert np.allclose(e['normal'][eligible],task['normal'][eligible],rtol=0,atol=1e-6,equal_nan=True)
    alignment=dict(centre_max_difference_m=float(np.max(abs(e['centre']-task['centre']))),
        scored_normal_max_difference=float(np.max(abs(e['normal'][eligible]-task['normal'][eligible]))),
        unscored_normal_mismatches=int(((np.max(abs(e['normal']-task['normal']),axis=1)>1e-6)&~eligible).sum()),
        p_gt_source='unchanged LOSSTRAIN direct_stage1_v2 evaluation used by MESHPATCH first-hit scoring',
        stage0_gt_med_is_a_separate_measurement=True)
    e['cell']=task['cell'];mesh=o3d.io.read_triangle_mesh(str(wd/'merged.ply'));z=MW.first_hit(mesh,e,v);cat=MC.classes(e,z)
    np.savez_compressed(wd/'patch_z.npz',**z,category=cat,cell=e['cell'],region=target['region'],any_replaced=target['any_replaced'])
    rows=MC.summarize(e,z);allcells=next(r for r in rows if r['cell']=='0~3')
    frac=allcells['floating_pct']/100 if allcells['floating_pct'] is not None else None
    eligible=e['in_eval']&e['scoring_allowed'];strata=[]
    for label,mask in [('all',eligible),('original',eligible&~target['any_replaced']),('replaced',eligible&target['any_replaced'])]:
        for region in range(4):
            sel=mask&(target['region']==region);area=float(e['area'][sel].sum())
            strata.append(dict(replacement=label,region=region,patches=int(sel.sum()),area_m2=area,
                result_within_tau_fraction=float(e['area'][sel&(cat==0)].sum()/area) if area else None,
                target_within_tau_fraction=float(e['area'][sel&(abs(target['h']-e['p_gt'])<=e['tau'])].sum()/area) if area else None))
    record=dict(at=stamp(),site=site,prior=prior,iteration=7000,status='PASS' if frac is not None and frac<=.05 else 'FAIL',
        floating_fraction_cells_0_3=frac,criterion=.05,rows=rows,result_vs_target=strata,mesh_sha256=sha(wd/'merged.ply'),
        mesh_vertices=len(mesh.vertices),mesh_faces=len(mesh.triangles),cell_source='r2 exact S1 code mapping',
        scorer_sources={str(Path(MW.__file__).relative_to(REPO)):sha(MW.__file__),str(Path(MC.__file__).relative_to(REPO)):sha(MC.__file__)},scientific_verdict=None)
    record['alignment']=alignment
    dump(wd/'score.json',record)
    if record['status']!='PASS':
        stop=OUT/'r4/STOP_BOTH.json'
        if not stop.exists():dump(stop,dict(at=stamp(),reason='floating_fraction_cells_0_3_gt_0.05',site=site,prior=prior,fraction=frac,scientific_verdict=None))
    # Associate visible first-hit points with saved rendered origin contributions.
    cover=json.loads((wd.parent/'model/check7000/coverage.json').read_text());hit=e['centre']+z['z'][:,None]*e['normal']
    sums=np.zeros((len(hit),3));counts=np.zeros(len(hit),np.int32);ids=np.flatnonzero(eligible&~z['no_surface'])
    for view in cover['views']:
        a=loadz(wd.parent/'model/check7000/renders'/f"{view['camera']}.npz");M=np.asarray(view['W2C']);K=np.asarray(view['K'])
        q=hit[ids]@M[:3,:3].T+M[:3,3];front=q[:,2]>0;goodids=ids[front];q=q[front]
        u=np.rint(K[0,0]*q[:,0]/q[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*q[:,1]/q[:,2]+K[1,2]).astype(int)
        ok=(u>=0)&(w>=0)&(u<a['depth'].shape[1])&(w<a['depth'].shape[0]);u,w,q,goodids=u[ok],w[ok],q[ok],goodids[ok]
        visible=np.isfinite(a['depth'][w,u])&(a['depth'][w,u]>0)&(abs(a['depth'][w,u]-q[:,2])<=.25)&(a['alpha'][w,u]>1e-5)
        ids2=goodids[visible];sums[ids2]+=a['origin_fraction'][w[visible],u[visible]];counts[ids2]+=1
    mean=np.divide(sums,counts[:,None],out=np.full_like(sums,np.nan),where=counts[:,None]>0)
    np.savez_compressed(wd/'origin_attribution.npz',hit_xyz=hit,mean_fraction=mean,views=counts,category=cat,in_eval=eligible,
        background_dominant=(counts>0)&(mean[:,0]>=.5),large_background_dominant=(counts>0)&(mean[:,1]>=.5))
    dump(wd/'origin_attribution.json',dict(at=stamp(),matched=int((counts>0).sum()),unmatched=int((eligible&(counts==0)).sum()),
        floating_background_dominant=int(((cat==1)&eligible&(counts>0)&(mean[:,0]>=.5)).sum()),
        floating_large_background_dominant=int(((cat==1)&eligible&(counts>0)&(mean[:,1]>=.5)).sum()),
        interpretation='rendered contribution association; not causal proof',stop_criterion=False,scientific_verdict=None))
    print('SCORE_7000',site,prior,record['status'],frac,flush=True)

def main():
    mode,site,prior=sys.argv[1:4];cfg=CFG/'post7000_r4.json';assert sha(cfg)==json.loads((CFG/'post7000_r4.lock.json').read_text())['sha256']
    wd=OUT/'r4/runs'/f'tg_{site}_{prior}_s0/post7000'
    if mode=='run':
        wd.mkdir(exist_ok=False);prepare(site,prior,wd)
        for command in [['plan','auto:16'],['order']]:
            with (wd/(command[0]+'.log')).open('x') as f:subprocess.run([sys.executable,__file__,command[0],site,prior,*command[1:]],stdout=f,stderr=subprocess.STDOUT,check=True)
        for tile in json.loads((wd/'plan/layout.json').read_text())['tiles']:
            with (wd/f'tile_{tile["k"]}.log').open('x') as f:subprocess.run([sys.executable,__file__,'tile',site,prior,str(tile['k'])],stdout=f,stderr=subprocess.STDOUT,check=True)
        for step in ['merge','score']:
            with (wd/(step+'.log')).open('x') as f:subprocess.run([sys.executable,__file__,step,site,prior],stdout=f,stderr=subprocess.STDOUT,check=True)
    elif mode=='plan':T.plan(wd,sys.argv[4])
    elif mode=='order':T.order(wd)
    elif mode=='tile':T.tile(wd,int(sys.argv[4]))
    elif mode=='merge':T.merge(wd,wd/'merged.ply',wd/'merged.json')
    elif mode=='score':score(site,prior,wd)

if __name__=='__main__':main()
