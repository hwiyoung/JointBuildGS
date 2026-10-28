"""Source-faithful patch table, proven regional joins, explicit unavailable states."""
import argparse,gzip,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from patch_units import O,D,C,CACHE,W,locked,sha,dump,log,TYPE_NAMES,prepare
PH=Path('/ph');S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
PREP=PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1'
SITES={'B0_b10':'B0','B173nb_b10':'B173nb','B173_b0':'B173','R1rep_b10':'R1rep'}

def spatial_names(src,cfg):
    a=np.deg2rad(cfg['frame']['u_axis_angle_degrees_ccw_from_easting'])
    uv=src['centre'][:,:2]@np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]]).T
    boxes=json.loads((PREP/'step06/boxes_v1.json').read_text())['boxes'];ranges=json.loads((PREP/'step01/ranges.json').read_text())
    eval_names=np.full(len(uv),'',dtype='<U70');explore=np.full(len(uv),'',dtype='<U45')
    masks={}
    for site,b in SITES.items():
        q=boxes[b];m=(uv[:,0]>=q['eval_u'][0])&(uv[:,0]<=q['eval_u'][1])&(uv[:,1]>=q['eval_v'][0])&(uv[:,1]<=q['eval_v'][1]);masks[site]=m
        eval_names[m]=np.char.add(np.char.add(eval_names[m],np.where(eval_names[m]=='','',';')),site)
    for key in cfg['regions']['exploration_names']:
        q=ranges[key]
        if q['kind']=='uv_box':m=(uv[:,0]>=q['u_m'][0])&(uv[:,0]<=q['u_m'][1])&(uv[:,1]>=q['v_m'][0])&(uv[:,1]<=q['v_m'][1])
        else:
            x0,y0,x1,y1=q['xy_rect_local'];c=src['centre'];m=(c[:,0]>=x0)&(c[:,0]<=x1)&(c[:,1]>=y0)&(c[:,1]<=y1)
        explore[m]=np.char.add(np.char.add(explore[m],np.where(explore[m]=='','',';')),key)
    return eval_names,explore,masks

def regions(prior,src,cfg,masks):
    n=len(src['cell']);out={};rows=[];validcodes=cfg['regions']['codes']
    combined=np.full(n,-1,np.int8);conflict=np.zeros(n,bool);matched_any=np.zeros(n,bool)
    for site in SITES:
        f=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz';r=dict(np.load(f))
        code=np.full(n,-1,np.int8);source_index=np.full(n,-1,np.int64);matched=np.zeros(n,bool)
        # ALS TINs are rebuilt by spatial crop and have different triangles; proximity is not identity.
        reason='different_ALS_TIN_patch_support' if prior=='ALS' else 'no_exact_source_patch'
        if prior=='LoD2':
            fstore=S0/'s61/box'/site/'LoD2/units.npz';st=dict(np.load(fstore))
            assert np.array_equal(st['loc_center'],r['centre'])
            table={int(x['ext']):x for x in json.loads((DR/'s02_box'/site/'lod2_surfaces.json').read_text())['surfaces']}
            bld=np.array([table[int(e)]['building'] for e in r['surf_ext']])
            sn=np.cross(st['loc_t1'],st['loc_t2']);sn/=np.maximum(np.linalg.norm(sn,axis=1,keepdims=True),1e-12)
            wall=r['kind']==2;sn[wall]=np.array([table[int(e)]['normal'] for e in r['surf_ext'][wall]])
            raw=r['centre']-r['frame_shift'];tr=cKDTree(raw)
            lo=raw[r['in_eval']].min(0)-1e-6;hi=raw[r['in_eval']].max(0)+1e-6
            # Work in chunks to keep a full-campus table bounded in memory.
            for start in range(0,n,100000):
                end=min(start+100000,n);p=src['raw_centre'][start:end]
                # Exact matches cannot lie beyond the source eval bounding box.
                cand=np.flatnonzero(((p>=lo)&(p<=hi)).all(1))+start
                if not len(cand):continue
                dist,ix=tr.query(src['raw_centre'][cand],distance_upper_bound=1e-6)
                finite=np.isfinite(dist);cand=cand[finite];ix=ix[finite];dist=dist[finite]
                ok=(dist<1e-6)&r['in_eval'][ix]&(src['kind'][cand]==r['kind'][ix])&(src['building'][cand]==bld[ix])
                ok &= np.isclose(src['area'][cand],r['area'][ix],rtol=1e-8,atol=1e-9)
                ok &= np.abs((src['normal'][cand]*sn[ix]).sum(1))>1-1e-6
                ii=cand[ok];jj=ix[ok];matched[ii]=True;source_index[ii]=jj
                good=np.isin(r['code_ext_v3'][jj],validcodes)&(src['gt_status'][ii]==0)&np.isfinite(src['gt_p'][ii])
                code[ii[good]]=r['code_ext_v3'][jj[good]]
            reason='unmatched_geometry_or_missing_GT_or_source_code'
        yes=code>=0;conflict |= yes&(combined>=0)&(combined!=code);combined[yes&(combined<0)]=code[yes&(combined<0)];matched_any |=matched
        out['region_code_'+site]=code;out['region_source_row_'+site]=source_index
        out['region_geometry_joined_'+site]=matched
        total=float(r['area'][r['in_eval']].sum());src_counts={str(k):float(r['area'][r['in_eval']&(r['code_ext_v3']==k)].sum()) for k in validcodes}
        dst_counts={str(k):float(src['area'][code==k].sum()) for k in validcodes}
        diffs={k:100*(dst_counts[k]-v)/total for k,v in src_counts.items()}
        allmatched=bool(np.all(np.abs(list(diffs.values()))<=.5))
        rows.append(dict(prior=prior,site=site,reference_area_m2=total,table_eval_area_m2=float(src['area'][masks[site]].sum()),
            matched_geometry_area_m2=float(src['area'][matched].sum()),assigned_area_m2=float(src['area'][yes].sum()),
            unavailable_eval_patches=int((masks[site]&~yes).sum()),unmatched_geometry_eval_patches=int((masks[site]&~matched).sum()),
            unmatched_geometry_eval_area_m2=float(src['area'][masks[site]&~matched].sum()),
            unavailable_eval_area_m2=float(src['area'][masks[site]&~yes].sum()),reference_by_code_m2=src_counts,table_by_code_m2=dst_counts,
            area_difference_pp_of_reference_eval=diffs,status='PASS' if allmatched else 'PARTIAL',reason=reason,reference_sha256=sha(f)))
    combined[conflict]=-1;out['region_code']=combined
    # Reason codes: no new visibility has been manufactured.
    why=np.full(n,1,np.int8);why[matched_any]=2;why[src['gt_status']!=0]=3;why[conflict]=4;why[combined>=0]=0
    out['region_unavailable_reason_code']=why
    ineval=np.logical_or.reduce(list(masks.values()))
    reason=np.full(n,'평가 지역 밖',dtype='<U32')
    reason[ineval]='격자가 다름' if prior=='ALS' else '평가 지역 넓이가 빠짐'
    reason[matched_any]='참값 또는 원본 영역 코드 없음'
    # Geometry failures keep their requested reason even when GT is also missing.
    reason[matched_any&(src['gt_status']!=0)]='참값 없음'
    reason[conflict]='겹친 평가 지역 코드가 다름'
    reason[combined>=0]=''
    out['region_unavailable_reason']=reason
    out['region_geometry_joined']=matched_any
    return out,rows

def csv_columns(table,start,end):
    cols={}
    for k,v in table.items():
        if v.ndim==1:cols[k]=v[start:end]
        else:
            for i,axis in enumerate('xyz'):cols[k+'_'+axis]=v[start:end,i]
    frame=pd.DataFrame(cols)
    for k in frame.columns:
        if k.startswith('region_code') or k.startswith('region_source_row') or k in ['mvs_face_id','mvs_face_type','mvs_mvsshape_id','mvs_mvsshape_type']:
            frame[k]=frame[k].mask(frame[k]<0).astype('Int64')
    return frame

def export(prior):
    cfg=locked();t=time.monotonic();src=prepare(prior,cfg);u=dict(np.load(CACHE/f'{prior}_units.npz'))
    rt=dict(np.load(CACHE/f'{prior}_roofer_def_types.npz'));mt=dict(np.load(CACHE/f'{prior}_mvsshape_10_types.npz'))
    n=len(src['cell']);hm=(src['mvs_a_status']==0)&np.isfinite(src['signed_difference_over_uncertainty'])&np.isfinite(src['mvs_a_nx'])
    fields=cfg['patches']['preserve']+['raw_centre','tile','tau','gt_status','mvs_a_status']
    table={k:src[k] for k in fields};en,ex,masks=spatial_names(src,cfg);table.update(eval_region=en,exploration_region=ex)
    reg,rows=regions(prior,src,cfg,masks);table.update(reg)
    check=json.loads((D/'tables'/f'patch_{prior}_tracka_check.json').read_text());verified=check['checks']['roofer_def']['status']=='PASS'
    gt=(src['gt_status']==0)&np.isfinite(src['gt_p'])
    prior_ok=gt&(np.abs(src['gt_p'].astype(np.float64))<=src['tau'].astype(np.float64))
    table.update(mvs_absent=~np.isfinite(src['mvs_p']),prior_within_tau=np.where(gt,np.where(prior_ok,'맞음','틀림'),'확인 불가'),
        prior_within_tau_code=np.where(gt,prior_ok.astype(np.int8),-1).astype(np.int8),
        mvs_p=src['mvs_p'],gt_p=src['gt_p'],
        mvs_face_id=np.where(hm,u['roofer_def'],-1),mvs_face_type=np.where(hm,rt['pt'],-1).astype(np.int8),mvs_edge_band=rt['edge']&hm,
        analysis_unit_roofer=u['roofer_def'],mvs_mvsshape_id=np.where(hm,u['mvsshape_10'],-1),mvs_mvsshape_type=np.where(hm,mt['pt'],-1).astype(np.int8),
        mvs_mvsshape_edge_band=mt['edge']&hm,mvs_face_benchmark_passed=np.full(n,verified,bool))
    target=O/'patch_table';target.mkdir(exist_ok=True)
    dest=target/f'{prior}_patch_table.npz';assert not dest.exists(),dest
    log(prior,'export_npz',rows=n);np.savez_compressed(dest,**table)
    cpath=target/f'{prior}_patch_table.csv.gz';assert not cpath.exists(),cpath
    with gzip.open(cpath,'wt',encoding='utf-8',newline='',compresslevel=6) as f:
        for start in range(0,n,100000):
            csv_columns(table,start,min(start+100000,n)).to_csv(f,index=False,header=start==0,float_format='%.17g')
            log(prior,'export_csv',completed_rows=min(start+100000,n),rows=n)
    counts=[]
    wc=json.loads(Path('/repo/configs/phd/main_widen0_v2/widen0_v2.json').read_text());cells=wc['cells']['order']
    for k,name in enumerate(cells):
        m=src['cell']==k;counts.append(dict(cell=k,name=name,patches=int(m.sum()),area_m2=float(src['area'][m].sum())))
    summary=dict(prior=prior,status='PASS' if verified and all(r['status']=='PASS' for r in rows) else 'PARTIAL',patches=n,area_m2=float(src['area'].sum()),
        original_columns_unchanged='pending_independent_validation',unique_patch_ids='pending_independent_validation',holdout_count=int(src['holdout'].sum()),
        wall_like_patches=int((~src['roof_like']).sum()),no_mvs_patches=int((~hm).sum()),no_mvs_area_m2=float(src['area'][~hm].sum()),
        region_unavailable_patches=int((table['region_code']<0).sum()),region_unavailable_area_m2=float(src['area'][table['region_code']<0].sum()),region_rows=rows,cells=counts,
        mvs_absent_by_mvs_p_patches=int(table['mvs_absent'].sum()),mvs_absent_by_mvs_p_area_m2=float(src['area'][table['mvs_absent']].sum()),
        prior_correct_patches=int(prior_ok.sum()),prior_correct_area_m2=float(src['area'][prior_ok].sum()),
        files=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in [dest,cpath]],seconds=time.monotonic()-t,scientific_verdict=None,provenance='[이 발주에서 냄]')
    dump(D/'tables'/f'patch_{prior}_table.json',summary)
    text=[f'# {prior} 패치 표','', '[이 발주에서 냄]', '',f"패치 {n:,}개, 넓이 {summary['area_m2']:.6f} m². 상태: {summary['status']}.",'','| 칸 | 이름 | 패치 수 | 넓이 m² |','|---:|---|---:|---:|']
    text +=[f"| {r['cell']} | {r['name']} | {r['patches']} | {r['area_m2']:.6f} |" for r in counts]
    text+=['','| 평가 지역 | v3 넓이 m² | 코드 부여 넓이 m² | 연결 안 된 패치 수 | 연결 안 된 넓이 m² | 상태 |','|---|---:|---:|---:|---:|---|']
    text += [f"| {r['site']} | {r['reference_area_m2']:.6f} | {r['assigned_area_m2']:.6f} | {r['unmatched_geometry_eval_patches']} | {r['unmatched_geometry_eval_area_m2']:.6f} | {r['status']} |" for r in rows]
    text +=['','ALS는 지역별 TIN의 패치가 달라 기존 코드의 동일성 연결을 확정하지 않았다. LoD2는 원래 중심·면적·건물·법선이 일치하는 패치만 연결했다. 참값이 없거나 코드가 겹쳐 충돌하면 비웠다.','',f"영역 코드 확인 불가 넓이: {summary['region_unavailable_area_m2']:.6f} m². 새 가시성 계산은 하지 않았다."]
    (D/'tables'/f'patch_{prior}_table.md').write_text('\n'.join(text)+'\n')
    log(prior,'table_complete',rows=n,status=summary['status'],seconds=time.monotonic()-t)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('prior',choices=['ALS','LoD2']);export(p.parse_args().prior)
