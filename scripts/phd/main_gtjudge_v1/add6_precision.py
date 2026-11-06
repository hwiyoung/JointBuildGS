"""Locate errors using stored sample scores; keep original and addendum2 denominators explicit."""
from add6_common import *
from add2_scores import normal_z

def main():
 records=[];checks=[];binding=[]
 for key in ['c1','c4']:
  c=case(key);root=root_of(c);row=loadz(root/'rows.npz');labels=loadz(root/'stage1_cells.npz')['case_id'];tree=cKDTree(row['xyz']);fp=AW/'features'/f"{c['site']}__{c['prior']}.npz";features=loadz(fp,['quadrant']);lgdm=loadz(root/'distances/fusion.npz',['row_s'])['row_s'];sources=[root/'rows.npz',root/'stage1_cells.npz',fp,root/'distances/fusion.npz',Path(__file__)]
  for method in ['FINALTRAIN_30000','fusion']:
   dp=root/'distances'/f'{method}.npz';z=loadz(dp,['sample_s','sample_tau','sample_eligible','sample_reference_row']);mp=dp.with_suffix('.json');meta=json.loads(mp.read_text());sp=Path(meta['accuracy_sample_source']);P=loadz(sp,['sample_xyz'])['sample_xyz'];assigned=z['sample_reference_row'];owned=assigned>=0;case_mask=np.zeros(len(P),bool);case_mask[owned]=labels[assigned[owned]]==c['case_id'];eligible0=case_mask&z['sample_eligible'];ids=np.flatnonzero(eligible0);nearest=tree.query(P[ids],workers=2)[1];absence=~np.isfinite(lgdm[nearest]);quadrant=features['quadrant'][nearest];bad=(~np.isfinite(z['sample_s'][ids]))|(abs(z['sample_s'][ids])>z['sample_tau'][ids]);steep=abs(normal_z(c['site'],c['prior'],method)[ids])<.5
   for version,keep,tablepath in [('stage1_original',np.ones(len(ids),bool),D/'tables/stage1'/f"{c['site']}__{c['prior']}_metrics.csv"),('addendum2_steep_excluded',~steep,D/'tables/addendum2/stage1'/f"{c['site']}__{c['prior']}.csv")]:
    total=int(keep.sum());nbad=int((keep&bad).sum());accuracy=100*(total-nbad)/total
    with tablepath.open() as f:source=next(r for r in csv.DictReader(f) if r['method']==method and r['case_id']==str(c['case_id']) and r.get('surface','all')=='all')
    assert abs(accuracy-float(source['accuracy_pct']))<1e-9
    checks.append(dict(case=c['id'],method=method,version=version,eligible_n=total,bad_n=nbad,accuracy_pct=accuracy,table_accuracy_pct=float(source['accuracy_pct']),source=proof(tablepath)))
    masks=[('all','all',np.ones(len(ids),bool)),('LGDM_absence','LGDM_none',absence),('LGDM_absence','LGDM_hit',~absence)]
    levels=[(1,'textureless_only'),(2,'edge_only'),(3,'textureless_and_edge'),(0,'other'),(-2,'unavailable')]
    masks += [('stage2_quadrant',name,quadrant==n) for n,name in levels]
    masks += [('LGDM_absence_x_stage2',a+'__'+name,am&(quadrant==n)) for a,am in [('LGDM_none',absence),('LGDM_hit',~absence)] for n,name in levels]
    for dimension,group,mask in masks:
     member=keep&mask;error=member&bad;n=int(error.sum());den=int(member.sum());far=error&np.isfinite(z['sample_s'][ids]);none=error&~np.isfinite(z['sample_s'][ids])
     records.append(dict(case=c['id'],case_id=c['case_id'],method=method,accuracy_version=version,dimension=dimension,group=group,eligible_total_n=total,bad_total_n=nbad,group_eligible_n=den,group_bad_n=n,group_far_n=int(far.sum()),group_none_n=int(none.sum()),pct_of_all_bad=100*n/nbad if nbad else None,bad_pct_in_group=100*n/den if den else None,nearest_rule='global nearest 3D saved scoring reference row; case population retains inherited same-owner assignment'))
    for dimension in ['LGDM_absence','stage2_quadrant','LGDM_absence_x_stage2']:
     rr=[r for r in records if r['case']==c['id'] and r['method']==method and r['accuracy_version']==version and r['dimension']==dimension];assert sum(r['group_bad_n'] for r in rr)==nbad;assert sum(r['group_eligible_n'] for r in rr)==total
   sources.extend([dp,mp,sp]);binding.append(dict(case=c['id'],method=method,reference_assignment_differs_from_global_nearest=int((assigned[ids]!=nearest).sum()),eligible_original_n=len(ids),feature_unavailable_n=int((quadrant==-2).sum())))
   if method=='FINALTRAIN_30000':
    op,ort,bounds=ortho(c['site']);im=orthocrop(ort,bounds);q=pixels(xyuv(P[ids]),bounds,im.size);inside=((q>=0)&(q<im.size)).all(1);state=np.where(~np.isfinite(z['sample_s'][ids]),2,np.where(abs(z['sample_s'][ids])>z['sample_tau'][ids],1,0));draw=ImageDraw.Draw(im);radius=max(.6,.05*im.width/(bounds[1]-bounds[0]));counts={}
    for k,col in [(0,'#8C95A3'),(1,'#D83730'),(2,'#EB6834')]:
     take=inside&(state==k);counts[str(k)]=int(take.sum())
     for x,y in q[take]:draw.ellipse([x-radius,y-radius,x+radius,y+radius],fill=col)
    png(im,c['id']+'_precision_map',dict(case=c['id'],method=method,accuracy_version='stage1_original',metric_population='eligible result samples assigned to requested case by original stage1 owner-preserving assignment',bounds_uv=bounds,state_colors={'in':'#8C95A3','far':'#D83730','none':'#EB6834'},state_draw_order=['in','far','none'],points_in_view_by_state=counts,points_outside_view=int((~inside).sum()),A_px=None,Aprime_px=None,box_corners_px=None,line_drawn=False),sources+[op])
   del P,z;gc.collect()
 table6('precision_where',records)
 source_code=[R/'scripts/phd/main_release_v1/stage0.py',R/'scripts/phd/main_gtjudge_v1/stage0.py',R/'scripts/phd/main_gtjudge_v1/collect.py',R/'scripts/phd/main_gtjudge_v1/add2_scores.py']
 dump(D/'verification/addendum6_precision.json',dict(at=now(),status='PASS_SAVED_ACCURACY_REPRODUCTION_AND_PARTITIONS',checks=checks,bindings=binding,
  original_assignment='RELEASE stage0.py 56-65: nearest 3D reference row restricted to the existing sample_owner; no owned-row match gives -1. GTJUDGE stage0.py 58-62 reuses it; collect.py 30-38 applies stage1 case_id to the assigned row and sample_eligible to the denominator.',
  addendum2='add2_scores.py 18-25 retains assignment and additionally excludes ALS result normals with abs(n_z)<0.5; both versions are separately reproduced, not pooled.',
  sources=[proof(p) for p in source_code],scientific_verdict=None));print('ADD6_PRECISION_DONE',len(records),json.dumps(checks,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
