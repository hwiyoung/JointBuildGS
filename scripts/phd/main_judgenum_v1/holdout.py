"""Fixed development values applied to sealed holdout. Public output is counts and hashes only."""
import concurrent.futures
import json
from pathlib import Path
import time
import zipfile
import numpy as np
from lock_config import dump,sha,stamp
from cylinder_runtime import run
from selected_npz import selected
from analysis_core import judgment,smooth,choice,T2
import analyse as analysis
O=Path('/out');H=O/'holdout';C=Path('/cfg');D=Path('/docs')

def prepare(cfg):
    W=Path(cfg['sources']['widen']);held=set(json.loads((H/'scope_membership.json').read_text())['buildings'])
    (H/'inputs').mkdir(exist_ok=True);receipts=[]
    keys=['normal','tangent1','tangent2','surf','roof_type','source_extra','normal_defined','u_prior','mvs_a_a',
          'mvs_p','gt_p','patch_id','kind','area','cell','centre','building']
    for src in sorted((W/'holdout/patch_values').glob('*.npz')):
        tile,prior,_=src.stem.split('__')
        with np.load(src) as z:data={k:z[k] for k in keys}
        N=len(data['area'])
        if not N:continue
        assert set(data['building'])<=held
        judgments=np.full((N,15),2,np.int8);missing=np.ones(N,bool)
        look={p:i for i,p in enumerate(data['patch_id'])}
        for kind,source in [(1,cfg['sources']['roof_photo']),(2,cfg['sources']['wall_photo'])]:
            mask=data['kind']==kind
            if not mask.any() or (prior=='ALS' and kind==2):continue
            file=Path(source)/'holdout/patches'/f'{tile}__{prior}.npz'
            assert file.exists(),'Missing sealed photo input; stop'
            with zipfile.ZipFile(file) as z:
                with z.open('patch_id.npy') as f:ids=np.lib.format.read_array(f,allow_pickle=False)
                m=np.isin(ids,data['patch_id'][mask]);vals=selected(z,'judgment',m)
            positions=np.array([look[p] for p in ids[m]],np.int64)
            judgments[positions]=vals;missing[positions]=False
        data['photo_judgments']=judgments;data['photo_missing']=missing
        sigma=np.sqrt(data['u_prior'].astype(float)**2+.0275**2)
        if prior=='LoD2':
            sigma=np.array([cfg['detection']['prior_sigma']['LoD2_roof'].get(str(rt),.11) for rt in data['roof_type']])
            sigma[data['kind']==2]=.144
        data['sigma_p']=sigma
        p=H/'inputs'/f'{tile}__{prior}.npz';np.savez_compressed(p,**data)
        receipts.append({'source':str(src),'sha256':sha(src),'destination':str(p),'destination_sha256':sha(p)})
    dump(H/'input_join.json',{'status':'COMPLETE','sources':receipts,'scientific_verdict':None})

def tile_run(tile,cfg):
    dest=H/'cylinders'/f'{tile}.bin'
    if dest.with_suffix('.complete.json').exists():return
    parts=[];centres=[];normals=[];offset=0
    for p in sorted((H/'inputs').glob(tile+'__*.npz')):
        with np.load(p) as z:centres.append(z['centre']);normals.append(z['normal']);N=len(z['area'])
        parts.append({'file':str(p),'sha256':sha(p),'start':offset,'count':N});offset+=N
    pointfile=Path(cfg['sources']['mvs_points'].replace('<tile>',tile))
    seconds=run(pointfile,np.concatenate(centres),np.concatenate(normals),dest,O/'tmp/cylinders')
    dump(dest.with_suffix('.complete.json'),{'parts':parts,'seconds':seconds,'status':'COMPLETE','scientific_verdict':None})

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());cal=json.loads((O/'calibration.json').read_text())['values']
    t0=time.monotonic();prepare(cfg)
    tiles=sorted({p.stem.split('__')[0] for p in (H/'inputs').glob('*.npz')})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda t:tile_run(t,cfg),tiles))
    analysis.O=H;sealed_cfg=json.loads(json.dumps(cfg))
    for key in ['roof_photo','wall_photo']:sealed_cfg['sources'][key]+='/holdout'
    public=[]
    for prior in ['LoD2','ALS']:
        data,where=analysis.load(prior);output=dict(data)
        for name,h,z,half in analysis.SCENARIOS:
            settings=cal[prior][name];chosen={int(k):v for k,v in settings['radius'].items()};A={int(k):v for k,v in settings['A'].items()}
            d,subset=analysis.spaced(data,where,prior,sealed_cfg) if half else (data,np.arange(len(data['area'])))
            stats=analysis.read_stats(where,h,data['kind'],chosen)[subset];j,DL=judgment(d,stats,z)
            after,labels,_,_,_,mixed=smooth(d,j,A,settings['components_radius_m'])
            initial=np.full(len(after),9,np.int8)
            for kind,group in [(1,'roof'),(2,'wall')]:
                m=(d['kind']==kind)&(after==1)
                if not m.any():continue
                key='roof' if prior=='ALS' else group
                index=settings['photo_choices'][key];pi,ti=divmod(index,9)
                initial[m]=choice(d['photo_judgments'][m,pi],np.abs(stats[m,1]),T2[ti])
            jj=np.full(len(data['area']),-1,np.int8);jj[subset]=after
            cc=np.full(len(data['area']),9,np.int8);cc[subset]=initial
            output[f'{name}_judgment_after']=jj;output[f'{name}_initial_choice']=cc
            if half:
                output['spacing050_retained']=np.zeros(len(data['area']),bool);output['spacing050_retained'][subset]=True
                output['spacing050_area_m2']=np.zeros(len(data['area']));output['spacing050_area_m2'][subset]=d['area']
            if name=='base':
                output.update({'n':stats[:,0].astype(np.int64),'d_mean_cm':stats[:,1]*100,'d_median_cm':stats[:,2]*100,
                  's_cm':stats[:,3]*100,'s_nmad_cm':stats[:,4]*100,'DL_cm':DL*100,
                  'a_cm':d['mvs_a_a'].astype(float)*100,'sigma_p_cm':d['sigma_p']*100,'a_missing':~np.isfinite(d['mvs_a_a']),
                  'judgment_before':j,'judgment_after':after,'component':labels,'initial_choice':initial,
                  'chosen_radius_m':np.where(d['kind']==1,chosen[1]['radius_m'] or np.nan,chosen[2]['radius_m'] or np.nan),
                  'als_normal_scale_check':np.full(len(j),-1,np.int8),'mixed_cutoff_unavailable':mixed})
        output['split']=np.full(len(data['area']),'holdout',dtype='<U11');output['prior']=np.full(len(data['area']),prior,dtype='<U4')
        dest=H/'core_points';dest.mkdir(exist_ok=True);files=[]
        for w in where:
            sl=slice(w['offset'],w['offset']+w['count']);p=dest/f"{w['tile']}__{prior}.npz"
            np.savez_compressed(p,**{k:v[sl] for k,v in output.items()})
            files.append({'file':str(p.relative_to(H)),'sha256':sha(p)})
        public.append({'prior':prior,'building_count':len(set(data['building'])),
          'core_point_count':len(data['area']),'area_m2':float(data['area'].sum()),'files':files})
    dump(H/'complete.json',{'status':'COMPLETE','at':stamp(),'seconds':time.monotonic()-t0,'scientific_verdict':None})
    dump(D/'tables/holdout_counts_and_hashes.json',{'rows':public,'scientific_verdict':None})
    print('SEALED_HOLDOUT_COMPLETE')

if __name__=='__main__':main()
