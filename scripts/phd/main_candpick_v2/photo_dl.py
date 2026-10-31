"""CPU-only stored-curve replay with point DL; sealed rows never leave holdout."""
import time
from scipy import ndimage
from cp2_common import *
AC=module('cp2_inherited_analysis_core','/repo/scripts/phd/main_judgenum_v1/analysis_core.py')

def lookup(keys,query):
    order=np.argsort(keys);ss=keys[order];pos=np.searchsorted(ss,query)
    out=np.full(len(query),-1,np.int64)
    if not len(ss):return out
    good=pos<len(ss);good&=ss[np.minimum(pos,len(ss)-1)]==query
    out[good]=order[pos[good]];return out

def derive(p,bound):
    """Only the support interval changes. Preserve original range-independent peaks."""
    h=p['heights'];s=p['curve'].astype(np.float32);good=np.isfinite(h)&np.isfinite(s)
    inside=good&(np.abs(h)<=(bound+1e-8).astype(h.dtype)[:,None])
    outside=good&~inside&(p['peak_mask']|(np.abs(h)>(bound+.3).astype(h.dtype)[:,None]))
    outside&=np.isfinite(bound)[:,None]
    result={}
    for label,mask in [('in',inside),('out',outside)]:
        score=np.max(np.where(mask,s,-np.inf),axis=1)
        height=np.min(np.where(mask&(s==score[:,None]),h,np.inf),axis=1)
        score[~np.isfinite(score)]=np.nan;height[~np.isfinite(height)]=np.nan
        result['s_'+label]=score;result['h_'+label]=height
    difference=result['s_in']-result['s_out'];j=np.full((len(h),15),2,np.int8)
    for k,c in enumerate(config()['photo']['inherited_judgments']['candidates']):
        support=(difference>=c['delta'])&(result['s_in']>=c['s_min'])
        contradict=(difference<=-c['delta'])&(result['s_out']>=c['s_min'])
        j[support,k]=0;j[contradict,k]=1
        j[np.isfinite(p['texture'])&(p['texture']<5),k]=3
        j[p['selected_count']<3,k]=4
    result.update(difference=difference,judgment=j)
    return result

CORE_KEYS=['patch_id','kind','area','cell','centre','building','photo_judgments','judgment_after','d_mean_cm','DL_cm']

def process_file(corepath,sealed,manifest):
    tile,prior=corepath.stem.split('__');base=OUT/'holdout' if sealed else OUT/'photo_dl'
    dest=base/'core_points'/corepath.name
    if dest.exists():return arrays(dest)
    with np.load(corepath) as z:d={k:z[k] for k in CORE_KEYS}
    assert len(np.unique(d['patch_id']))==len(d['patch_id'])
    out=dict(d);out['old_photo_judgments']=d['photo_judgments'].copy()
    out['photo_judgments']=np.full_like(d['photo_judgments'],2)
    out['photo_point_id']=np.full(len(d['area']),'',dtype='<U100')
    out['point_DL_m']=np.full(len(d['area']),np.nan)
    out['photo_source_available']=np.zeros(len(d['area']),bool)
    out['old_range_replay']=np.full_like(d['photo_judgments'],2)
    manifest.append(bind(corepath))
    for kind,source in [(1,PC),(2,WP)]:
        if prior=='ALS' and kind==2:continue
        source=source/'holdout' if sealed else source
        pp=source/'points'/corepath.name;mp=source/'patches'/corepath.name
        if not pp.exists() or not mp.exists():continue
        with np.load(pp) as z:
            keys=['point_id','heights','curve','peak_mask','texture','selected_count','sigma','judgment','area','centre','normal','building','kind','holdout']
            p={k:z[k] for k in keys}
        assert bool(np.all(p['holdout'])) if sealed else not p['holdout'].any()
        with np.load(mp) as z:mapping={k:z[k] for k in ['patch_id','point_id']}
        coreidx=lookup(d['patch_id'],mapping['patch_id'])
        owners=lookup(p['point_id'],mapping['point_id']);assert (owners>=0).all()
        join=(coreidx>=0)
        assert np.all(d['kind'][coreidx[join]]==kind)
        core=coreidx[join];owner=owners[join]
        assert len(np.unique(core))==len(core),'multiple point owners'
        finite=np.isfinite(d['DL_cm'][core])
        count=np.bincount(owner[finite],minlength=len(p['point_id']))
        dl=np.full(len(p['point_id']),np.nan);has=np.flatnonzero(count)
        if len(has):dl[has]=ndimage.median(d['DL_cm'][core[finite]],labels=owner[finite]+1,index=has+1)/100.
        values=derive(p,dl);old=derive(p,3*p['sigma'])
        out['photo_judgments'][core]=values['judgment'][owner]
        out['photo_point_id'][core]=p['point_id'][owner]
        out['point_DL_m'][core]=dl[owner]
        out['photo_source_available'][core]=True
        out['old_range_replay'][core]=old['judgment'][owner]
        assert np.array_equal(d['photo_judgments'][core],p['judgment'][owner]),'inherited point-patch judgments mismatch'
        pdest=base/'points'/('roof' if kind==1 else 'wall')/corepath.name;pdest.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(pdest,point_id=p['point_id'],DL_m=dl,finite_DL_patch_count=count,
            total_joined_patch_count=np.bincount(owner,minlength=len(p['point_id'])),old_judgment=p['judgment'],old_range_replay=old['judgment'],
            **values)
        manifest.extend([bind(pp),bind(mp)])
    dest.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(dest,**out)
    if not sealed:print('photo',corepath.stem,len(d['area']),'patches',flush=True)
    return out

def summarize(prior,data,sealed,choices=None):
    d={k:np.concatenate([x[k] for x in data]) for k in data[0]}
    after=d['judgment_after'];dist=d['d_mean_cm']/100.
    base=OUT/'holdout' if sealed else OUT/'photo_dl'
    result={};rows=[]
    oldchoices=json.loads((JN/'calibration.json').read_text())['values'][prior]['base']['photo_choices']
    for group,mask in [('roof',d['kind']==1),('wall',d['kind']==2),('combined',np.ones(len(after),bool))]:
        if not mask.any():continue
        if sealed:
            index=choices[group]['choice_index'];_,summary=AC.summaries(d,after,dist,index,mask)
            result[group]=dict(choice_index=index,summary=summary)
            continue
        selected=AC.select(d,after,dist,mask);index=selected['best']
        if prior=='ALS' and group=='wall':index=result['roof']['choice_index']
        _,summary=AC.summaries(d,after,dist,index,mask)
        original=dict(d,photo_judgments=d['old_photo_judgments'])
        oldindex=oldchoices['roof' if prior=='ALS' and group=='wall' else group]
        oldselect=AC.select(original,after,dist,mask)
        # Stored base choice must be reproduced before replacing photo judgments.
        if not (prior=='ALS' and group=='wall'):assert oldselect['best']==oldindex,(prior,group,oldselect['best'],oldindex)
        no_photo=dict(d,photo_judgments=np.full_like(d['photo_judgments'],2));none=AC.select(no_photo,after,dist,mask)
        oldsummary=AC.summaries(original,after,dist,oldindex,mask)[1]
        noreport=AC.summaries(no_photo,after,dist,none['best'],mask)[1]
        display=AC.summaries(original,after,dist,44,mask)[1]
        equalreport=AC.summaries(d,after,dist,selected['building_equal_best'],mask)[1]
        result[group]=dict(choice_index=index,building_equal_choice_index=selected['building_equal_best'],
            summary=summary,grid_wrong_area_m2=selected['errors'],grid_building_equal_errors=selected['building_equal_errors'],
            building_equal_summary=equalreport,leave_one_out=selected['leave_one_out'],old_choice_index=oldindex,
            old_selected=oldsummary,no_photo=noreport,old_display_photo=display)
        status='UNAVAILABLE_NO_ALS_WALL_CURVES' if prior=='ALS' and group=='wall' else 'COMPLETE'
        for label,idx,summ in [('new_selected',index,summary),('old_selected',oldindex,oldsummary),
                               ('no_photo',none['best'],noreport),('old_display_photo',44,display)]:
            rows.append(dict(prior=prior,group=group,setting=label,status=status,choice_index=idx,
                **{k:v for k,v in summ.items() if k not in ['cross','buildings']}))
        table(f'photo_{prior}_{group}_grid',[dict(choice_index=i,photo_index=i//9,threshold_index=i%9,
            wrong_area_m2=selected['errors'][i],building_equal_wrong_fraction=selected['building_equal_errors'][i]) for i in range(135)])
        table(f'photo_{prior}_{group}_leave_one_out',selected['leave_one_out'])
        table(f'photo_{prior}_{group}_buildings',summary['buildings'])
        table(f'photo_{prior}_{group}_cross',summary['cross'])
        if prior=='LoD2' and group=='roof':
            oldpi=oldindex//9
            target=mask&(after==1)&(d['cell']==1)&(d['old_photo_judgments'][:,oldpi]==0)
            assert abs(float(d['area'][target].sum())-834.4375)<1e-8
            changes=[]
            for rule,pi in [('old_selected_photo_parameters',oldpi),('new_selected_photo_parameters',index//9)]:
                values=np.minimum(d['photo_judgments'][:,pi],2)
                for j,label in enumerate(['support','contradict','unknown']):
                    q=target&(values==j);changes.append(dict(rule=rule,new_judgment=label,patches=int(q.sum()),area_m2=float(d['area'][q].sum())))
            table('photo_834_transition',changes,original_area_m2=float(d['area'][target].sum()))
            path=base/'target_834.npz'
            np.savez_compressed(path,**{k:d[k][target] for k in ['patch_id','centre','building','area','photo_point_id','point_DL_m','photo_judgments','old_photo_judgments']})
    save(base/f'{prior}_selection.json',dict(prior=prior,groups=result,source=SOURCE,scientific_verdict=None))
    if not sealed:
        table(f'photo_{prior}_comparison',rows)
        area_rows=[]
        for kind in [1,2]:
            mask=d['kind']==kind
            for pi in range(15):
                for j in range(5):
                    q=mask&(d['photo_judgments'][:,pi]==j)
                    area_rows.append(dict(prior=prior,kind=kind,photo_index=pi,judgment=j,patches=int(q.sum()),area_m2=float(d['area'][q].sum())))
        table(f'photo_{prior}_judgment_areas',area_rows)
        report=dict(prior=prior,patches=len(after),area_m2=float(d['area'].sum()),
            unavailable_DL_patches=int((~np.isfinite(d['point_DL_m'])&d['photo_source_available']).sum()),
            unavailable_DL_area_m2=float(d['area'][~np.isfinite(d['point_DL_m'])&d['photo_source_available']].sum()),
            missing_photo_source_patches=int((~d['photo_source_available']).sum()),
            old_range_precision_mismatches=int(((d['old_range_replay']!=d['old_photo_judgments'])&d['photo_source_available'][:,None]).sum()),
            old_range_precision_changed_patches=int(((d['old_range_replay']!=d['old_photo_judgments']).any(1)&d['photo_source_available']).sum()),
            old_range_precision_changed_area_m2=float(d['area'][(d['old_range_replay']!=d['old_photo_judgments']).any(1)&d['photo_source_available']].sum()))
        save(base/f'{prior}_replay.json',dict(**report,source=SOURCE,scientific_verdict=None))
    return result,dict(prior=prior,patches=len(after),area_m2=float(d['area'].sum()))

def main():
    cfg=config();start=time.monotonic();assert not Path('/dev/nvidia0').exists(),'CPU-only task'
    lock=dict(at=now(),config_sha256=sha(CFG/'candpick_v2.json'),implementation=bind(__file__),
        inherited_select=bind('/repo/scripts/phd/main_judgenum_v1/analysis_core.py'),source=SOURCE,scientific_verdict=None)
    save(CFG/'photo_implementation.lock.json',lock)
    manifests={False:[],True:[]};public=[];choices={}
    for sealed in [False,True]:
        source=JN/'holdout/core_points' if sealed else JN/'core_points'
        for prior in ['ALS','LoD2']:
            parts=[process_file(p,sealed,manifests[sealed]) for p in sorted(source.glob(f'*__{prior}.npz'))]
            if not parts:continue
            result,count=summarize(prior,parts,sealed,choices.get(prior))
            if not sealed:choices[prior]=result
            else:public.append(count)
            del parts
        base=OUT/'holdout' if sealed else OUT/'photo_dl'
        save(base/'inputs.json',dict(inputs=manifests[sealed],source=SOURCE,scientific_verdict=None))
    held=OUT/'holdout';hashes=[dict(file=str(p.relative_to(held)),sha256=sha(p)) for p in sorted(held.rglob('*')) if p.is_file()]
    save(DOC/'tables/holdout_counts_and_hashes.json',dict(counts=public,files=hashes,source=SOURCE,scientific_verdict=None))
    save(OUT/'photo_dl/complete.json',dict(status='COMPLETE_WITH_REPORTED_UNAVAILABLE',at=now(),seconds=time.monotonic()-start,
        new_images_processed=0,gpu_used=False,scientific_verdict=None))
    print('PHOTO_DL_COMPLETE',round(time.monotonic()-start,1),flush=True)

if __name__=='__main__':main()
