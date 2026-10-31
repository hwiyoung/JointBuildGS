"""Score all completed arms and six frozen v1 baselines using locked pixel views."""
import argparse
import gc
import time
import torch
from scipy import ndimage
from engine import Scene,photo
from depth_rule import expected_depth
from cp2_common import *

def run(unit,variant,start):
    cfg=config();baseline=variant=='v1'
    arm=f'cp_{start}_sh3_{unit}' if baseline else f'cp2_{variant}_{start}_{unit}'
    source=(CP1 if baseline else OUT)/'runs'/arm
    dest=OUT/'depth'/arm;dest.mkdir(parents=True,exist_ok=True)
    if (dest/'complete.json').exists():return
    if not (source/'complete.json').exists():
        save(dest/'unavailable.json',dict(arm=arm,status='UNAVAILABLE_NO_COMPLETE_TRAINING',scientific_verdict=None),replace=True);return
    end=3000 if baseline else cfg['arms'][variant]['iterations']
    assert sha(source/f'candidate_{end}.npz')==json.loads((source/'complete.json').read_text())['final_candidate_sha256']
    begin=time.monotonic();scene=Scene(unit,variant,start);scene.load_snapshot(source/f'candidate_{end}.npz',baseline=baseline)
    view=arrays(OUT/'depth_views'/unit/'selected_pixels.npz');d=scene.d
    pindex=view['point_index'];vindex=view['view_index'];pixel=view['pixel_index'];height=np.full(len(pixel),np.nan)
    checks=[];reps=[r for r in cfg['representatives'] if r['unit']==unit and r['selection']]
    for j in sorted(set(vindex)):
        cam=scene.cams[j];obs=np.flatnonzero(vindex==j);pixels=torch.as_tensor(np.unique(pixel[obs]),device='cuda',dtype=torch.long)
        with torch.no_grad():
            r=scene.render(cam,depth=True);depth,check=expected_depth(r[-1],pixels)
            dep=depth[pixel[obs]].cpu().numpy()
            ids=check.get('pixel_ids')
            ce=float((r[0][0,...,-1].reshape(-1)[ids]-check['center_expected']).abs().max()) if ids is not None else None
            ae=float((r[1][0,...,0].reshape(-1)[ids]-check['alpha']).abs().max()) if ids is not None else None
            # Small accumulation differences are measured, not confused with a scene result.
            checks.append(dict(view=cam['name'],pixel_observations=len(obs),invalid_depth=int((~np.isfinite(dep)|(dep<=0)).sum()),
                center_depth_max_error_m=ce,alpha_max_error=ae,
                below_near_contributors=check.get('below_geogs_near_count',0),nonfinite_ray_contributors=check.get('nonfinite_ray_depth',0)))
            uv=np.column_stack([pixel[obs]%cam['width']+.5,pixel[obs]//cam['width']+.5,np.ones(len(obs))])
            ray=uv@np.linalg.inv(cam['K']).T
            world=(ray*dep[:,None]-cam['E'][:3,3])@cam['E'][:3,:3]
            hi=np.sum((world-d['centre'][pindex[obs]])*d['normal'][pindex[obs]],1)
            hi[(~np.isfinite(dep))|(dep<=0)]=np.nan;height[obs]=hi
            if start=='right':
                for rep in reps:
                    if rep['render_view']['view_index']!=j:continue
                    x0,y0,x1,y1=rep['render_view']['crop'];sl=np.s_[y0:y1,x0:x1]
                    pi=np.flatnonzero(np.isin(d['point_id'],rep['selection']['point_ids']));q=np.isin(pindex[obs],pi)
                    rp=pixel[obs][q];hh=hi[q];finite=np.isfinite(hh)
                    hmap=np.full(cam['height']*cam['width'],np.nan,np.float32)
                    occupied=np.unique(rp[finite])
                    if len(occupied):hmap[occupied]=ndimage.median(hh[finite],labels=rp[finite]+1,index=occupied+1)
                    folder=OUT/'renders'/rep['id'];folder.mkdir(parents=True,exist_ok=True)
                    np.savez_compressed(folder/(arm+'.npz'),rgb=r[0][0,...,:3].cpu().numpy()[sl],
                        photo=photo(cam)[sl],height_map=hmap.reshape(cam['height'],cam['width'])[sl],
                        crop=np.array([x0,y0,x1,y1]),point_index=pindex[obs][q],pixel_index=rp,point_pixel_h_m=hh)
            del r,depth,check
        if len(checks)%20==0:print('DEPTH',arm,len(checks),'views',flush=True)
    n=len(d['point_id']);valid=np.isfinite(height);counts=np.bincount(pindex[valid],minlength=n)
    values=np.full(n,np.nan);ix=np.flatnonzero(counts)
    if len(ix):values[ix]=ndimage.median(height[valid],labels=pindex[valid]+1,index=ix+1)
    # Frozen request uses three views; absent complete support is not scored as zero.
    pairs=np.unique(pindex[valid].astype(np.int64)*len(scene.cams)+vindex[valid])
    valid_views=np.bincount(pairs//len(scene.cams),minlength=n)
    available=(view['chosen_view_index']>=0).all(1)&(valid_views>=3)&np.isfinite(values)
    ri=(d['right']=='image').astype(int);right=np.where(ri==1,d['mvs_p'],0.);wrong=np.where(ri==0,d['mvs_p'],0.)
    tau=cfg['depth']['tau_m'][unit.split('_')[1]]
    correct=available&(np.abs(values-right)<=tau);incorrect=available&(np.abs(values-wrong)<=tau)
    assert not (correct&incorrect).any(),'overlapping right/wrong windows'
    state=np.full(n,'unavailable',dtype='<U16');state[available]='between_outside';state[correct]='right';state[incorrect]='wrong'
    np.savez_compressed(dest/'points.npz',point_id=d['point_id'],h_m=values,outcome=state,valid_pixel_count=counts,valid_view_count=valid_views,
        total_pixel_count=np.bincount(pindex,minlength=n),right_height_m=right,wrong_height_m=wrong)
    rows=[]
    for group in ['a','b','c']:
        for side in ['all','front','back']:
            m=d['group']==group
            if side!='all':m&=d['side']==side
            area=float(d['area'][m].sum());row=dict(arm=arm,unit=unit,variant=variant,start=start,group=group,side=side,area_m2=area,points=int(m.sum()))
            for label in ['right','wrong','between_outside','unavailable']:
                a=float(d['area'][m&(state==label)].sum());row[label+'_area_m2']=a;row[label+'_fraction']=a/area if area else None
            rows.append(row)
    save(dest/'complete.json',dict(arm=arm,status='COMPLETE',at=now(),seconds=time.monotonic()-begin,
        commit=os.environ.get('CANDPICK_COMMIT'),docker_image=os.environ.get('CANDPICK_IMAGE'),
        config_sha256=sha(CFG/'candpick_v2.json'),gsplat_version=cfg['gsplat_version'],
        rows=rows,views=checks,point_values=bind(dest/'points.npz'),source=SOURCE,scientific_verdict=None))
    print('DEPTH_COMPLETE',arm,round(time.monotonic()-begin,1),flush=True)
    del scene;gc.collect();torch.cuda.empty_cache()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('lane',type=int,choices=[0,1]);a=p.parse_args()
    implementation=dict(at=now(),script=bind(__file__),depth_rule=bind(Path(__file__).with_name('depth_rule.py')),
        commit=os.environ.get('CANDPICK_COMMIT'),docker_image=os.environ.get('CANDPICK_IMAGE'),
        config_sha256=sha(CFG/'candpick_v2.json'),scientific_verdict=None)
    lock=CFG/f'depth_implementation_lane{a.lane}.lock.json'
    if not lock.exists():save(lock,implementation)
    else:
        saved=json.loads(lock.read_text());assert saved['script']['sha256']==implementation['script']['sha256']
        assert saved['depth_rule']['sha256']==implementation['depth_rule']['sha256']
    jobs=[(u,v,s) for v in ['v1','a','b','c','d'] for u in UNITS for s in ['equal','right']]
    for u,v,s in jobs[a.lane::2]:run(u,v,s)
