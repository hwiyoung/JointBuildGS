"""Sections 6 and 7, exact counts and unrounded area-weighted evaluation."""
import json,csv,sys
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz
from photo_judgment_reply2 import weighted_quantile,PHOTO_LABELS
from judgment_reply2 import VARIANTS,ARMS,GROUPS
from export_reply2 import CORE_STACKED
BASE=O/'r2';EX=dict(label='실험 지역과 사진 점을 공유해 뺀 핵심점',count=73,area_m2=5.442552935831812)
def val(v):
    if isinstance(v,np.generic):v=v.item()
    if isinstance(v,float) and not np.isfinite(v):return None
    if isinstance(v,dict):return {k:val(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [val(x) for x in v]
    return v

def main(group):
    prior,kind=GROUPS[group];name=f'{prior}_{kind}';core_files=sorted((BASE/'core_points').glob(f'*__{prior}__{kind}.npz'));parts=[loadz(p) for p in core_files];g={k:np.concatenate([p[k] for p in parts],axis=1 if k in CORE_STACKED else 0) for k in parts[0]};del parts
    source_files=core_files+sorted((BASE/'photo_points').glob(f'*__{prior}__{kind}.npz'))
    provenance=dict(source_tag='[이 발주에서 냄]',input_sha256={str(p):sha(p) for p in source_files},calculation_source_sha256=sha(Path(__file__)),config_sha256=sha(C/'judgecheck_v1.json'),photo_scope='Section 6 corrected-photo diagnostics use original targets 1 or 2 only; type-3-only scores are reserved for the section-7 geometry-oracle arm. Original target-2 membership is preserved at overlaps.')
    a=g['area'];cell=g['cell'];geom=g['geometry'];N=len(a);prior_valid=np.isfinite(g['prior_height_m'])&np.isfinite(g['normal']).all(1);total=float(a[prior_valid].sum());valid=np.isin(cell,range(6));eligible=valid&(geom!=9);outside=geom==1;tables={}
    def row(mask,den=None,**labels):
        area=float(a[mask].sum());d=float(a[den].sum()) if den is not None else None
        return dict(**labels,count=int(mask.sum()),area_m2=area,denominator_area_m2=d,fraction=area/d if d else None)
    rows=[]
    for vi in [0,2]:
        for panel in ['geometry','judgment']:
            if panel=='geometry':categories=[('한계 안',geom==0),('한계 밖',outside),('영상 깊이 없음',geom==2)]
            else:
                reg=g['region'][vi];why=g['reason'][vi];categories=[('일치',reg==0),('보존(사진 지지)',(reg==1)&(why==0)),('보존(기본 방향)',(reg==1)&(why==2)),('보정(사진 반박)',(reg==2)&(why==1)),('보정(기본 방향)',(reg==2)&(why==2)),('보정(빈 공간)',reg==3),('결측',reg==4)]
            for label,m in categories:
                for cc in range(6):rows.append(row(eligible&m&(cell==cc),eligible,variant=VARIANTS[vi],panel=panel,label=label,cell=cc))
            rows.append(row(cell==6,variant=VARIANTS[vi],panel=panel,label='참값 없음',cell=6));rows.append(row(valid&~eligible,variant=VARIANTS[vi],panel=panel,label='기하 확인 불가',cell=9));rows.append(row(cell==9,variant=VARIANTS[vi],panel=panel,label='사전 정보 높이/법선 없음',cell=9))
    tables['6_1_cross']=rows
    rows=[];building_rows=[]
    for vi,variant in enumerate(VARIANTS):
        c=g['old_cell'] if vi==3 else cell;den=(np.isin(g['old_region_source'],[2,3]) if vi==3 else outside)&np.isin(c,[0,1,2])&(g['region'][vi]!=9)
        correct=np.isin(g['region'][vi],[2,3]);wrong=den&(((c==1)&~correct)|((c==2)&correct))
        splits=[('all',np.ones(N,bool))]
        if prior=='ALS':splits.extend([('normal_fallback',~g['normal_rule_met']),('normal_rule_met',g['normal_rule_met'])])
        for label,m in splits:rows.append(dict(**row(wrong&m,den&m,variant=variant,stratum=label),whole_roof_fraction=float(a[wrong&m].sum()/total),denominator_kind='old rule outside and old cells' if vi==3 else 'new outside and new cells'))
        for b in np.unique(g['building']):
            m=g['building']==b;bd=float(a[m&prior_valid].sum());building_rows.append(dict(**row(wrong&m,den&m,variant=variant,building=str(b)),building_area_m2=bd,whole_building_fraction=float(a[wrong&m].sum()/bd) if bd else None))
    tables['6_2_accuracy']=rows;tables['6_2_buildings']=building_rows
    rows=[];primary_photo=sample_mask(g,prior,kind,bits=3)
    for vi in range(3):
        photo=g['photo_code'][vi];den=outside&np.isin(cell,[0,1,2]);variant=VARIANTS[vi]
        for reason,m in [('사진이 틀리게 지지',(cell==1)&(photo==0)),('사진이 틀리게 반박',(cell==2)&(photo==1))]:rows.append(row(den&m,den,variant=variant,reason=reason))
        for code in range(2,10):rows.append(row(den&(cell==(1 if prior=='ALS' else 2))&(photo==code),den,variant=variant,reason='기본 방향:'+PHOTO_LABELS[code]))
        rows.append(row((g['region'][vi]==3)&(cell==4),valid&(g['n']<4),variant=variant,reason='빈 공간 보정이 틀림(6.2 분모 밖)'))
        rows.append(row(outside&(cell==3),outside,variant=variant,reason='한계 밖 둘 다 틀림'))
        refuted=(geom==0)&(photo==1)&(primary_photo if vi<2 else np.ones(N,bool))
        rows.append(row(refuted,geom==0,variant=variant,reason='한계 안 사진 반박(전체 한계 안 분모)'))
        rows.append(row(refuted,(geom==0)&primary_photo if vi<2 else geom==0,variant=variant,reason='한계 안 사진 반박(사진 계산 부분 분모)'))
    tables['6_3_causes']=rows
    rows=[];sample2=sample_mask(g,prior,kind)
    for vi in range(3):
        photo=g['photo_code'][vi]
        for label,mask in [('일치 표본 한계 안 칸0',(geom==0)&(cell==0)),('한계 밖 칸1',outside&(cell==1)),('한계 밖 칸2',outside&(cell==2)),('한계 밖 칸3',outside&(cell==3))]:
            # All corrected-photo target types are computed, but the baseline row
            # must use only unchanged type-2 agreement sample, mapped below.
            if label.startswith('일치'):mask=mask&sample2
            for code in range(10):rows.append(row(mask&(photo==code),mask,variant=VARIANTS[vi],stratum=label,photo=PHOTO_LABELS[code]))
    tables['6_4_photos']=rows
    photo_scope=g['photo_computed']&primary_photo
    angles=g['mvs_normal_angle_deg'];am=np.isfinite(angles)&photo_scope;_,ui=np.unique(g['photo_point_id'][am],return_index=True);unique_angles=angles[am][ui]
    tables['6_4_planes']=[row(photo_scope&~g['mvs_plane_available'],photo_scope,metric='MVS 면 없음')]+[dict(metric='angle_core_area_weighted_quantile',q=q,value_deg=weighted_quantile(angles[am],a[am],q),count=int(am.sum()),area_m2=float(a[am].sum())) for q in [.1,.25,.5,.75,.9]]+[dict(metric='angle_photo_point_quantile',q=q,value_deg=float(np.quantile(unique_angles,q)) if len(unique_angles) else None,count=len(unique_angles)) for q in [.1,.25,.5,.75,.9]]
    rows=[]
    for old in range(7):
        for new in list(range(7))+[9]:rows.append(row((g['old_cell']==old)&(cell==new),np.ones(N,bool),old_cell=old,new_cell=new))
    tables['6_5_cell_cross']=rows
    rows=[]
    for z in [1.645,1.96,2.576]:
        limit=z*(np.sqrt(g['u_mvs']**2+g['sigma_P_m']**2+g['sigma_W_m']**2)+abs(g['r_m']));den=(cell==0)&np.isfinite(limit)
        rows.append(row(den&(abs(g['d_m'])>limit),den,metric='five_percent_check',z=z,reference_only=(prior=='LoD2' and kind==1)))
    finite_limit=np.isfinite(g['L_m'])&prior_valid
    for q in [.25,.5,.75]:rows.append(dict(metric='limit_quantile',q=q,value_m=float(np.quantile(g['L_m'][finite_limit],q)) if finite_limit.any() else None,count=int(finite_limit.sum())))
    rows.append(dict(metric='r_reference_cell0_median',value_m=np.median(g['d_m'][(cell==0)&np.isfinite(g['d_m'])]) if ((cell==0)&np.isfinite(g['d_m'])).any() else None))
    for nn,free in [('5','free5'),('10','free10')]:
        n=g['n5'] if nn=='5' else g['n'];ok=np.isfinite(g['prior_height_m'])&np.isfinite(g['normal']).all(1)
        rows.append(row(ok&(n<4),ok,metric='missing_before_sight',half_length_m=int(nn)));rows.append(row(ok&(n<4)&g[free],ok,metric='free_space',half_length_m=int(nn)));rows.append(row(ok&(n<4)&~g[free],ok,metric='missing_after_sight',half_length_m=int(nn)))
    rows.append(row(g['sight_unavailable'],np.ones(N,bool),metric='sight_unavailable_no_original_u_donors'))
    if prior=='ALS':
        for r in [.5,.75,1,1.5,2]:rows.append(dict(**row(g['normal_radius_m']==r,np.ones(N,bool),metric='normal_radius',radius_m=r),denominator_core_count=N,core_fraction=float(np.count_nonzero(g['normal_radius_m']==r)/N)))
        rows.append(row(~g['normal_rule_met'],np.ones(N,bool),metric='normal_fallback'))
        rows.append(row(~np.isfinite(g['prior_height_m']),np.ones(N,bool),metric='prior_height_missing'))
        for q in [.1,.25,.5,.75,.9]:rows.append(dict(metric='TIN_to_new_axis_height_quantile',q=q,value_m=weighted_quantile(g['prior_height_m'],a,q)))
    tables['6_5_geometry']=rows
    rows=[];truth=(g['gt_status']==0)&np.isfinite(g['gt_p']);sigmaM=np.hypot(g['u_mvs'],g['sigma_W_m'])
    for label,h,sigma,m in [('MVS',g['mvs_mean_m'],sigmaM,g['n']>=4),('prior_sigmaP',g['prior_height_m'],g['sigma_P_m'],np.ones(N,bool))]+([('prior_sigmaP_plus_sigmaW',g['prior_height_m'],np.hypot(g['sigma_P_m'],g['sigma_W_m']),np.ones(N,bool))] if prior=='ALS' else []):
        splits=[('all',np.ones(N,bool))] if prior=='ALS' or label=='MVS' or kind==2 else [(str(v),g['roof_type']==v) for v in np.unique(g['roof_type'])]
        for subtype,ss in splits:
            keep=truth&m&ss&np.isfinite(h)&np.isfinite(sigma)&(sigma>0)&np.isfinite(g['prior_height_m']);v=(h[keep]-g['gt_p'][keep])/sigma[keep];median=float(np.median(v)) if len(v) else np.nan
            rows.append(dict(**row(keep),source=label,roof_type=subtype,normalized_median=median,normalized_centered_NMAD=1.4826*float(np.median(abs(v-median))) if len(v) else None))
    tables['6_5_precision']=rows
    rows=[];tau=.1266 if prior=='ALS' else .2
    for cc in ['all']+list(range(6)):
        scope=valid if cc=='all' else cell==cc
        for ai,arm in enumerate(ARMS):
            h=g['arm_height_m'][ai];reg=g['arm_region'][ai];known=scope&((np.isfinite(h))|(reg==3))&(reg!=9);err=abs(h-g['gt_p']);finite=known&np.isfinite(err);right=known&(reg!=3)&(err<=tau)
            den=float(a[known].sum());rowval=dict(arm=arm,cell=cc,reference_area_m2=float(a[scope].sum()),scored_area_m2=den,uncountable_area_m2=float(a[scope&~known].sum()),correct_area_m2=float(a[right].sum()),within_tau_fraction=float(a[right].sum()/den) if den else None,
                mean_abs_error_m=float(np.average(err[finite],weights=a[finite])) if finite.any() else None,median_abs_error_m=weighted_quantile(err[finite],a[finite],.5),finite_error_area_m2=float(a[finite].sum()),no_face_area_m2=float(a[known&(reg==3)].sum()),count=int(known.sum()))
            rows.append(rowval)
    base={r['cell']:r for r in rows if r['arm']=='main'}
    for r in rows:
        b=base[r['cell']];r['within_tau_difference_pp']=(r['within_tau_fraction']-b['within_tau_fraction'])*100 if r['within_tau_fraction'] is not None and b['within_tau_fraction'] is not None else None
    tables['7_ablation']=rows
    for table,rows in tables.items():
        rows=val(rows);dest=D/'tables'/f'{name}_{table}';dump(dest.with_suffix('.json'),dict(at=now(),group=name,table=table,rows=rows,provenance=provenance,excluded_shared_cores=EX,scientific_verdict=None))
        fields=list(dict.fromkeys(k for r in rows for k in r));fields+=['excluded_shared_count','excluded_shared_area_m2']
        with dest.with_suffix('.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows);w.writerow(dict(excluded_shared_count=73,excluded_shared_area_m2=EX['area_m2']))
    result=val(dict(at=now(),group=name,core_count=N,area_m2=float(a.sum()),prior_height_valid_count=int(prior_valid.sum()),prior_height_valid_area_m2=total,whole_area_accuracy_denominator='retained area after missing prior height/normal exclusion',accuracy=tables['6_2_accuracy'],ablation=[r for r in tables['7_ablation'] if r['cell']=='all'],top15=sorted([r for r in building_rows if r['variant']=='new_clipped'],key=lambda r:-r['area_m2'])[:15],excluded_shared_cores=EX,scientific_verdict=None))
    dump(BASE/'metrics'/f'{name}.json',result);print('METRICS_COMPLETE',name,flush=True)

def sample_mask(g,prior,kind,bits=2):
    ids=set()
    for p in (BASE/'photo_points').glob(f'*__{prior}__{kind}.npz'):
        with np.load(p) as z:ids.update(z['point_id'][(z['target_type_bits']&bits)>0])
    return np.isin(g['photo_point_id'],list(ids))
if __name__=='__main__':main(int(sys.argv[1]))
