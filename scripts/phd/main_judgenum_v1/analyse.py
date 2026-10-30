"""Calibrate only development rows, with explicit unavailable states."""
import csv
import json
from pathlib import Path
import time
import zipfile
import numpy as np
from scipy.spatial import cKDTree
from analysis_core import radius_table,judgment,minimum_area,smooth,select,summaries,T2,choice
from cylinder_runtime import RADII
from selected_npz import selected
from lock_config import dump,sha,stamp
O=Path('/out');C=Path('/cfg');D=Path('/docs')
SCENARIOS=[('base',0,1.96,False),('confidence90',0,1.645,False),('confidence99',0,2.576,False),
           ('spacing050',0,1.96,True),('length3',1,1.96,False),('length10',2,1.96,False)]

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def save(name,rows,meta=None):
    obj={'rows':clean(rows),'source':'PHD-MAIN-JUDGENUM-v1; [이 발주에서 냄]',
         'config_sha256':sha(C/'judgenum_v1.json'),'scientific_verdict':None,**(meta or {})}
    dump(D/'tables'/f'{name}.json',obj)
    if rows and all(isinstance(r,dict) for r in rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (D/'tables'/f'{name}.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
            for r in clean(rows):w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
        lines=['| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']
        for row in clean(rows):lines.append('| '+' | '.join(str(row.get(k,'')).replace('|','/') for k in keys)+' |')
        (D/'tables'/f'{name}.md').write_text('\n'.join(lines)+'\n')

def load(prior):
    pieces=[];where=[];offset=0
    for p in sorted((O/'inputs').glob(f'*__{prior}.npz')):
        with np.load(p) as z:part={k:z[k] for k in z.files}
        tile=p.stem.split('__')[0];rec=json.loads((O/'cylinders'/f'{tile}.complete.json').read_text())
        r=next(r for r in rec['parts'] if r['file']==str(p));assert r['sha256']==sha(p)
        where.append({'tile':tile,'file':str(p),'offset':offset,'count':len(part['area']),
          'raw_start':r['start'],'raw_count':sum(q['count'] for q in rec['parts'])})
        offset+=len(part['area']);pieces.append(part)
    return {k:np.concatenate([p[k] for p in pieces]) for k in pieces[0]},where

def read_counts(where,h):
    vals=[]
    for w in where:
        m=np.memmap(O/'cylinders'/f"{w['tile']}.bin",dtype='<f8',mode='r',shape=(w['raw_count'],3,10,7))
        vals.append(np.array(m[w['raw_start']:w['raw_start']+w['count'],h,:,0]));del m
    return np.concatenate(vals)

def read_stats(where,h,kind,chosen):
    vals=[]
    for w in where:
        m=np.memmap(O/'cylinders'/f"{w['tile']}.bin",dtype='<f8',mode='r',shape=(w['raw_count'],3,10,7))
        k=kind[w['offset']:w['offset']+w['count']]
        r=np.where(k==1,chosen[1]['radius_index'],chosen[2]['radius_index'])
        vals.append(np.array(m[w['raw_start']+np.arange(w['count']),h,r,:]));del m
    return np.concatenate(vals)

def spaced(d,where,prior,cfg):
    groups=[]
    for w in where:
        ids=d['patch_id'][w['offset']:w['offset']+w['count']];k=d['kind'][w['offset']:w['offset']+w['count']]
        out=np.full(len(ids),'',dtype='<U100');look={p:i for i,p in enumerate(ids)}
        for kind,source in [(1,cfg['sources']['roof_photo']),(2,cfg['sources']['wall_photo'])]:
            if not np.any(k==kind):continue
            f=Path(source)/'patches'/f"{w['tile']}__{prior}.npz"
            with zipfile.ZipFile(f) as z:
                with z.open('patch_id.npy') as src:pid=np.lib.format.read_array(src,allow_pickle=False)
                mask=np.isin(pid,ids[k==kind]);gid=selected(z,'point_id',mask)
                for p,g in zip(pid[mask],gid):out[look[p]]=str(g)
        assert np.all(out!=''),'Missing inherited 50cm grouping'
        groups.append(out)
    group=np.concatenate(groups);_,inverse=np.unique(group,return_inverse=True)
    # Lexicographically first existing patch per exact inherited group.
    order=np.lexsort((d['patch_id'],inverse));codes=inverse[order]
    ix=order[np.r_[True,codes[1:]!=codes[:-1]]]
    weights=np.bincount(inverse,weights=d['area'])
    reduced={k:v[ix] for k,v in d.items()};reduced['area']=weights[inverse[ix]]
    return reduced,ix

def area_rows(d,j,after,DL,prior,name):
    rows=[]
    for kind in [1,2]:
        k=d['kind']==kind
        cuts=[('all',k)]+[(str(rt),k&(d['roof_type']==rt)) for rt in sorted(set(d['roof_type'][k]))]
        for roof,m in cuts:
            area=float(d['area'][m].sum())
            for stage,values in [('before',j),('after',after)]:
                row={'scenario':name,'prior':prior,'kind':kind,'roof_type':roof,'stage':stage,
                     'patch_count':int(m.sum()),'area_m2':area}
                for val,label in [(-1,'unavailable'),(0,'same'),(1,'different'),(2,'inherit')]:
                    row[label+'_area_m2']=float(d['area'][m&(values==val)].sum())
                    row[label+'_fraction']=row[label+'_area_m2']/area if area else None
                rows.append(row)
    return rows

def diagnostics(d,stats,DL,z,prior):
    rows=[];bias=[];bounds=[]
    n,dist=stats[:,0],stats[:,1]
    for kind in [1,2]:
        base=(d['kind']==kind)&(d['cell']==0);finite=base&np.isfinite(DL)&(DL>0)&np.isfinite(dist)
        masks=[('all',finite)]+[(str(rt),finite&(d['roof_type']==rt)) for rt in sorted(set(d['roof_type'][base]))]
        for label,m in masks:
            for lo,hi in [(None,None),(4,9),(10,19),(20,49),(50,None)]:
                q=m if lo is None else m&(n>=lo)&((n<=hi) if hi is not None else True)
                v=np.abs(dist[q])/DL[q]*z
                qs=np.quantile(v,[.683,.95,.99]) if len(v) else [None]*3
                rows.append({'prior':prior,'kind':kind,'roof_type':label,'n_min':lo,'n_max':hi,
                  'patch_count':len(v),'area_m2':float(d['area'][q].sum()),'q683':qs[0],'q95':qs[1],'q99':qs[2]})
        v=dist[finite];med=float(np.median(v)) if len(v) else None
        den=float(d['area'][base].sum())
        bias.append({'prior':prior,'kind':kind,'patch_count':len(v),'median_d_cm':med*100 if med is not None else None,
          'nmad_cm':float(1.4826*np.median(np.abs(v-med))*100) if len(v) else None,
          'cell0_area_m2':den,'false_fraction_after_diagnostic_subtraction':
              float(d['area'][finite&(np.abs(dist-med)>DL)].sum()/den) if den and med is not None else None})
        for cell in [1,2]:
            for length in [3.,5.,10.]:
                m=(d['kind']==kind)&(d['cell']==cell)
                exceeds=(np.abs(d['gt_p'])>length)|(np.abs(d['mvs_p'])>length)
                bounds.append({'prior':prior,'kind':kind,'cell':cell,'half_length_m':length,
                    'patch_count':int((m&exceeds).sum()),'area_m2':float(d['area'][m&exceeds].sum()),
                    'missing_mvs_p_area_m2':float(d['area'][m&~np.isfinite(d['mvs_p'])].sum())})
    return clean(rows),clean(bias),clean(bounds)

def main():
    t0=time.monotonic();cfg=json.loads((C/'judgenum_v1.json').read_text())
    assert (O/'census_complete.json').exists()
    out=O/'analysis';out.mkdir(exist_ok=True)
    all_radius=[];all_area=[];all_sensitivity=[];all_selected=[];all_losses=[];all_islands=[];all_old=[]
    calibration={};diag=[];bias=[];bounds=[];null_roofs=[];size_A=[];normal_checks=[]
    for prior in ['LoD2','ALS']:
        data,where=load(prior);base_choices={};baseline_saved=None
        for kind in [1,2]:
            for rt in sorted(set(data['roof_type'][data['kind']==kind])):
                m=(data['kind']==kind)&(data['roof_type']==rt)
                normal_checks.append({'prior':prior,'kind':kind,'roof_type':str(rt),'patch_count':int(m.sum()),
                  'area_m2':float(data['area'][m].sum()),'undefined_axis_count':int((m&~data['normal_defined']).sum()),
                  'undefined_axis_area_m2':float(data['area'][m&~data['normal_defined']].sum()),
                  'scale_25_check':'not_applicable_planar_face' if prior=='LoD2' else 'unavailable_TIN_normal_no_fit_neighbourhood',
                  'scale_25_fail_count':None,'scale_25_fail_area_m2':None})
        output={k:data[k] for k in data}
        for name,h,z,half in SCENARIOS:
            print('ANALYSE',prior,name,flush=True)
            d,subset=spaced(data,where,prior,cfg) if half else (data,np.arange(len(data['area'])))
            counts=read_counts(where,h);chosen,rrows=radius_table(counts[subset],d['kind'],prior,RADII)
            for row in rrows:row['scenario']=name
            all_radius+=rrows;stats=read_stats(where,h,data['kind'],chosen)[subset]
            j,DL=judgment(d,stats,z)
            tree=cKDTree(d['centre']);spacing=float(np.median(tree.query(d['centre'],k=2,workers=2)[0][:,1]));del tree
            radius=1.5*spacing if spacing<.18 or spacing>.36 else .36
            A,maxima,nullratios=minimum_area(d,j,radius)
            for kind in [1,2]:
                for bin_name in ['10~100','100~500','>500']:
                    vv=[r['largest_false_component_m2'] for r in maxima if r['kind']==kind and r['size_bin']==bin_name]
                    size_A.append({'prior':prior,'scenario':name,'kind':kind,'size_bin':bin_name,
                      'buildings':len(vv),'A_m2':float(np.quantile(vv,.95,method='higher')) if vv else None})
                for rt in sorted(set(d['roof_type'][d['kind']==kind])):
                    m=(d['kind']==kind)&(d['roof_type']==rt)&(d['cell']==0)
                    den=float(d['area'][m].sum());num=float(d['area'][m&(j==1)].sum())
                    null_roofs.append({'prior':prior,'scenario':name,'kind':kind,'roof_type':str(rt),
                      'patch_count':int(m.sum()),'area_m2':den,'different_area_m2':num,
                      'different_fraction':num/den if den else None,'unavailable_area_m2':float(d['area'][m&(j<0)].sum())})
            after,labels,components,loss,islands,mixed=smooth(d,j,A,radius)
            all_losses += [dict(prior=prior,scenario=name,**r) for r in loss]
            all_islands += [dict(prior=prior,scenario=name,**r) for r in islands]
            all_area+=area_rows(d,j,after,DL,prior,name)
            save(f'{prior}_{name}_null_buildings',maxima,{'radius_m':radius,'median_spacing_m':spacing})
            save(f'{prior}_{name}_null_rates',nullratios)
            group_results={};initial=np.full(len(j),9,np.int8)
            encoding=np.unique(d['building'],return_inverse=True)
            for group,mask in [('roof',d['kind']==1),('wall',d['kind']==2),('combined',np.ones(len(j),bool))]:
                if not mask.any():continue
                result=select(d,after,stats[:,1],mask,encoding)
                index=result['best']
                if prior=='ALS' and group=='wall':index=group_results['roof']['best']
                cc,report=summaries(d,after,stats[:,1],index,mask)
                group_results[group]=result
                if group!='combined':initial[mask]=cc[mask]
                row={'prior':prior,'scenario':name,'group':group,'choice_index':index,
                  'building_equal_choice_index':result['building_equal_best'],
                  'leave_one_out_changed':sum(q['changed'] for q in result['leave_one_out']),
                  'leave_one_out_buildings':len(result['leave_one_out']),
                  **{k:v for k,v in report.items() if k not in ['cross','buildings']}}
                all_selected.append(row)
                save(f'{prior}_{name}_{group}_grid',[{'photo_index':pi,'threshold2_m':None if ti==8 else T2[ti],
                  'threshold_index':ti,'wrong_area_m2':result['errors'][pi*9+ti],
                  'wrong_fraction':result['errors'][pi*9+ti]/result['denominator_m2'] if result['denominator_m2'] else None,
                  'building_equal_wrong_fraction':result['building_equal_errors'][pi*9+ti]} for pi in range(15) for ti in range(9)])
                save(f'{prior}_{name}_{group}_leave_one_out',result['leave_one_out'])
                save(f'{prior}_{name}_{group}_cross',report['cross'])
                save(f'{prior}_{name}_{group}_buildings',report['buildings'])
                if name=='base':base_choices[group]=index
                if group!='combined':
                    nullrow=next(r for r in nullratios if r['kind']==(1 if group=='roof' else 2))
                    area=float(d['area'][mask].sum());fixed=summaries(d,after,stats[:,1],base_choices[group],mask)[1]
                    all_sensitivity.append({'prior':prior,'scenario':name,'group':group,'area_m2':area,
                      'same_fraction':float(d['area'][mask&(after==0)].sum()/area),
                      'different_fraction':float(d['area'][mask&(after==1)].sum()/area),
                      'inherit_fraction':float(d['area'][mask&(after==2)].sum()/area),
                      'unavailable_fraction':float(d['area'][mask&(after<0)].sum()/area),
                      'false_different_fraction':nullrow['false_different_fraction'],
                      'minimum_area_m2':A[1 if group=='roof' else 2],'choice_index':index,
                      'same_choice_as_base':index==base_choices[group],
                      'wrong_area_m2':report['wrong_area_m2'],'wrong_fraction':report['wrong_fraction'],
                      'base_choice_wrong_area_m2':fixed['wrong_area_m2'],
                      'decided_photo_fraction':sum(report['photo_area_m2'][:2])/report['different_area_m2'] if report['different_area_m2'] else None})
            expanded=np.full(len(data['area']),-1,np.int8);expanded[subset]=after
            expanded_choice=np.full(len(data['area']),9,np.int8);expanded_choice[subset]=initial
            output[f'{name}_judgment_after']=expanded;output[f'{name}_initial_choice']=expanded_choice
            if half:
                output['spacing050_retained']=np.zeros(len(data['area']),bool);output['spacing050_retained'][subset]=True
                output['spacing050_area_m2']=np.zeros(len(data['area']));output['spacing050_area_m2'][subset]=d['area']
            calibration.setdefault(prior,{})[name]={'radius':chosen,'A':A,'components_radius_m':radius,
                'photo_choices':{k:v['best'] for k,v in group_results.items()}}
            if name=='base':
                output.update({'n':stats[:,0].astype(np.int64),'d_mean_cm':stats[:,1]*100,'d_median_cm':stats[:,2]*100,
                  's_cm':stats[:,3]*100,'s_nmad_cm':stats[:,4]*100,'DL_cm':DL*100,
                  'a_cm':d['mvs_a_a'].astype(float)*100,'sigma_p_cm':d['sigma_p']*100,
                  'a_missing':~np.isfinite(d['mvs_a_a']),'judgment_before':j,'judgment_after':after,
                  'component':labels,'initial_choice':initial,
                  'chosen_radius_m':np.where(d['kind']==1,chosen[1]['radius_m'] or np.nan,chosen[2]['radius_m'] or np.nan),
                  'als_normal_scale_check':np.full(len(j),-1,np.int8),'mixed_cutoff_unavailable':mixed})
                dd,bb,oo=diagnostics(d,stats,DL,z,prior);diag+=dd;bias+=bb;bounds+=oo
                tau=cfg['detection']['old_comparison_tau_m'][prior]
                old=j.copy();valid=j<2;valid&=j>=0
                old[valid]=(np.abs(stats[valid,1])>np.maximum(DL[valid],tau)).astype(np.int8)
                for kind in [1,2]:
                    m=(d['kind']==kind)&(old!=j)
                    all_old.append({'prior':prior,'kind':kind,'changed_patches':int(m.sum()),'changed_area_m2':float(d['area'][m].sum())})
                for group,mask in [('roof',d['kind']==1),('wall',d['kind']==2)]:
                    if not mask.any():continue
                    temp=dict(d);temp['photo_judgments']=np.full_like(d['photo_judgments'],2)
                    sel=select(temp,after,stats[:,1],mask,encoding)
                    for label,dd,index in [('no_photo',temp,sel['best']),('display_photo',d,44)]:
                        _,report=summaries(dd,after,stats[:,1],index,mask)
                        save(f'{prior}_base_{group}_{label}',[{k:v for k,v in report.items() if k not in ['cross','buildings']}])
                        save(f'{prior}_base_{group}_{label}_cross',report['cross'])
                        save(f'{prior}_base_{group}_{label}_buildings',report['buildings'])
            dump(out/f'{prior}_{name}.json',clean({'minimum_area':A,'chosen_radius':chosen,
              'component_spacing_m':spacing,'component_radius_m':radius,
              'mixed_cutoff_unavailable_count':int(mixed.sum()),'photo_choices':{k:v['best'] for k,v in group_results.items()},
              'scientific_verdict':None}))
            del components,counts,stats,j,DL,after,labels
        output['split']=np.full(len(data['area']),'development',dtype='<U11')
        output['prior']=np.full(len(data['area']),prior,dtype='<U4')
        core=O/'core_points';core.mkdir(exist_ok=True)
        for w in where:
            sl=slice(w['offset'],w['offset']+w['count'])
            np.savez_compressed(core/f"{w['tile']}__{prior}.npz",**{k:v[sl] for k,v in output.items()})
    for name,rows in [('radius_candidates',all_radius),('judgment_areas',all_area),('selected_values',all_selected),
      ('sensitivity',all_sensitivity),('lost_different_area',all_losses),('small_same_islands',all_islands),
      ('old_rule_comparison',all_old),('model_quantiles',diag),('bias_diagnostic',bias),('outside_cylinder',bounds),
      ('null_rates_by_roof_type',null_roofs),('minimum_area_by_building_size',size_A),('normal_checks',normal_checks)]:save(name,rows)
    dump(O/'calibration.json',clean({'values':calibration,'scientific_verdict':None,'at':stamp()}))
    dump(O/'analysis_complete.json',{'status':'COMPLETE_WITH_UNAVAILABLE_ROWS','seconds':time.monotonic()-t0,
      'at':stamp(),'scientific_verdict':None})
    print('ANALYSIS_COMPLETE',time.monotonic()-t0,flush=True)

if __name__=='__main__':main()
