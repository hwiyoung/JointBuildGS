"""Requested target/cell diagnostics; exact source_index join, no decision changes."""
from common import *
from geometry import context
from metrics import inherited_result_mask
from target_quality import REGIONS
import sys
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1';SITE='B173nb_b10'
def weighted(a,w):
 ok=np.isfinite(a);a=a[ok];w=w[ok]
 if not len(a):return dict(n=0,area_m2=0.,mean_m=None,p50_m=None,p90_m=None)
 order=np.argsort(a);cum=np.cumsum(w[order])/w.sum();q=np.interp([.5,.9],cum,a[order]);return dict(n=len(a),area_m2=float(w.sum()),mean_m=float(np.average(a,weights=w)),p50_m=float(q[0]),p90_m=float(q[1]))
def main(prior,mode='targets'):
 ctx=context(SITE,prior);c=ctx['core'];v=ctx['v2'];cell=v['cell_v2'];tau=v['tau_v2_m'];area=c['area'];src=FT/'targets'/f'{SITE}__{prior}.npz';t=loadz(src);ix=c['source_index'];assert np.array_equal(t['patch_id'][ix],c['patch_id']);assert np.array_equal(t['normal'][ix],c['normal'],equal_nan=True)
 region=t['judge_region'][ix];h=t['target_height_m'][ix];sigma=t['target_sigma_m'][ix];error=abs(h-c['gt_p']);valid=np.isfinite(error)&np.isfinite(tau);correct=valid&(error<=tau);rows=[]
 if mode=='targets':
  for r in [0,1,2,3,4,9]:
   for k in [0,1,2,4,3,5,6,9]:
    m=(region==r)&(cell==k);a=float(area[m].sum());den=float(area[m&valid].sum());ca=float(area[m&correct].sum());rows.append(dict(site=SITE,prior=prior,judgment_region=r,judgment_name=REGIONS[r],cell=k,patches=int(m.sum()),area_m2=a,valid_target_reference_area_m2=den,target_correct_area_m2=ca,target_correct_fraction=ca/den if den else None,target_correct_fraction_of_whole_cell=ca/a if a else None,target_unavailable_area_m2=float(area[m&~valid].sum()),target_source=str(src),target_sha256=sha(src),scientific_verdict=None))
  table('check_a_judgment_cell_'+prior,rows)
  rows=[]
  if prior=='LoD2':
   wrong=(region==0)&valid&~correct;ep=c['prior_height_m']-c['gt_p'];em=c['mvs_mean_m']-c['gt_p']
   for k in ['all',0,1,2,3,4,5,6,9]:
    m=wrong if k=='all' else wrong&(cell==k)
    rows.append(dict(site=SITE,prior=prior,cell=k,patches=int(m.sum()),area_m2=float(area[m].sum()),prior_abs_error=weighted(abs(ep[m]),area[m]),image_depth_abs_error=weighted(abs(em[m]),area[m]),prior_signed_error=weighted(ep[m],area[m]),image_depth_signed_error=weighted(em[m],area[m]),target_abs_error=weighted(error[m],area[m]),source=str(src),source_sha256=sha(src)))
   table('check_c_LoD2_agreement_wrong',rows);savez(O/'checks/check_c_LoD2.npz',patch_id=c['patch_id'][wrong],source_index=ix[wrong],cell=cell[wrong],area_m2=area[wrong],tau_m=tau[wrong],prior_error_m=ep[wrong],image_depth_error_m=em[wrong],target_error_m=error[wrong])
  print('TARGET_CHECKS',prior,flush=True);return
 key=f'{SITE}__{prior}__FINALTRAIN_30000';p=O/'scores'/key/'points.npz';z=loadz(p);own=z['row_owner'];ok=own>=0;cat=np.full(len(h),'target_wrong_outside_interval',dtype='<U40');cat[error<=1.96*sigma]='target_wrong_inside_interval';cat[correct]='target_correct';cat[~np.isfinite(sigma)&np.isfinite(h)]='sigma_unavailable';cat[~np.isfinite(h)]='no_target';cat[cell==5]='cell5_missing_image_wrong_prior';cat[cell==6]='cell6_no_reference';cat[cell==9]='invalid_prior_geometry';rows=[]
 for r in [0,2,1,4,3,9]:
  den=float(area[region==r].sum())
  for name in np.unique(cat[region==r]):
   m=(region==r)&(cat==name);gm=np.zeros(len(own),bool);gm[ok]=m[own[ok]];n=int(gm.sum());only=name in ['sigma_unavailable','cell5_missing_image_wrong_prior','cell6_no_reference','invalid_prior_geometry'];rows.append(dict(site=SITE,prior=prior,key=key,method='본 방법 FINALTRAIN 30,000회',judgment_region=r,judgment_name=REGIONS[r],category=str(name),patches=int(m.sum()),area_m2=float(area[m].sum()),region_area_m2=den,area_fraction=float(area[m].sum()/den) if den else None,n_gt=None if only else n,completeness=None if only or not n else float((z['row_distance_m'][gm]<=z['row_tau_m'][gm]).mean()),target_source=str(src),target_source_sha256=sha(src),provisional=False))
 table('target_quality_'+key,rows)
 if prior=='LoD2':
  own=z['sample_owner'];inside=own>=0;good=inherited_result_mask(z['sample_region_distance_m'],z['sample_region_lat_m']);m=inside&good&(z['sample_region_distance_m']>1);m[inside]&=cell[own[inside]]==1;ids=np.flatnonzero(m);reg=region[own[m]];rows=[]
  for r in [0,1,2,3,4,9]:rows.append(dict(judgment_region=r,judgment_name=REGIONS[r],points=int((reg==r).sum()),share=float((reg==r).mean()) if len(reg) else None,total_points=len(reg),threshold_m=1.,source=str(p),source_sha256=sha(p)))
  table('check_b_LoD2_far_point_regions',rows);savez(O/'checks/check_b_LoD2_far_points.npz',sample_index=ids,xyz=z['sample_xyz'][ids],distance_m=z['sample_region_distance_m'][ids],owner=own[ids],patch_id=c['patch_id'][own[ids]],source_index=ix[own[ids]],judge_region=reg)
  dump(O/'checks/check_b_selection.json',dict(points=len(ids),selection='cell_v2=1, column owner>=0, finite normal reference distance, lateral<=0.5 m, distance>1 m',score_sha256=sha(O/'scores'/key/'values.json'),excluded_reference_invalid_cell1=int((inside&~good&(np.where(inside,cell[np.maximum(own,0)],9)==1)).sum()),scientific_verdict=None))
 print('RESULT_CHECKS',prior,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
