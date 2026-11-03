"""Table 7.7: owned GT rows grouped by target quality, with missing data explicit."""
from common import *
from geometry import context
import sys
REGIONS={0:'일치',1:'보존',2:'보정',3:'보정(빈 공간)',4:'결측',9:'미판정'}
def main(site,prior,family,key):
 ctx=context(site,prior);core=ctx['core'];v=ctx['v2'];cell=v['cell_v2'];tau=v['tau_v2_m'];area=core['area'];source=TG/'r8/targets'/f'{site}_{prior}.npz' if family=='r8' else O/'targets_v2'/f'{site}__{prior}.npz';t=loadz(source)
 if family=='r8':
  ix=core['source_index'];oldnormal=t['normal'][ix];h=t['h'][ix];sigma=t['sigma'][ix];normaldot=np.einsum('ij,ij->i',core['normal'],oldnormal);error=abs(h-core['gt_p']*normaldot);region=np.full(len(h),9,np.int8)
  for old,new in [(0,4),(1,0),(2,1),(3,2),(5,3)]:region[t['region'][ix]==old]=new
  target_note='r8 h and sigma; JA GT position centre+gt_p*normal projected onto original target normal before height comparison'
 else:
  assert np.array_equal(t['patch_id'],core['patch_id']);h=t['target_height_m'];sigma=t['target_sigma_m'];region=t['region'];error=abs(h-core['gt_p']);target_note='targets_v2 target_height_m and target_sigma_m'
 z=loadz(O/'scores'/key/'points.npz',['row_distance_m','row_owner']);own=z['row_owner'];dist=z['row_distance_m'];valid=own>=0;rowtau=np.full(len(own),np.nan);rowtau[valid]=tau[own[valid]];rows=[]
 categories=np.full(len(h),'target_wrong_outside_interval',dtype='<U40');categories[error<=1.96*sigma]='target_wrong_inside_interval';categories[error<=tau]='target_correct';categories[~np.isfinite(sigma)&np.isfinite(h)]='sigma_unavailable';categories[~np.isfinite(h)]='no_target';categories[cell==5]='cell5_missing_image_wrong_prior';categories[cell==6]='cell6_no_reference';categories[cell==9]='invalid_prior_geometry'
 for r in [0,2,1,4,3,9]:
  den=float(area[region==r].sum())
  for category in np.unique(categories[region==r]):
   pm=(region==r)&(categories==category);m=np.zeros(len(dist),bool);m[valid]=pm[own[valid]];n=int(m.sum());area_only=category in ['sigma_unavailable','cell5_missing_image_wrong_prior','cell6_no_reference','invalid_prior_geometry'];rows.append(dict(site=site,prior=prior,key=key,judgment_region=r,judgment_name=REGIONS[r],category=str(category),patches=int(pm.sum()),area_m2=float(area[pm].sum()),region_area_m2=den,area_fraction=float(area[pm].sum()/den) if den else None,n_gt=None if area_only else n,completeness=None if area_only or not n else float((dist[m]<=rowtau[m]).mean()),target_source=str(source),target_source_sha256=sha(source),target_fields=target_note,source_tag='[이 발주에서 냄]'))
 for row in rows:row.update(method='r8 본 방법 · 옛 판단으로 학습한 임시값' if family=='r8' else '판단으로 조합한 메시',provisional=family=='r8')
 table('target_quality_'+key,rows)
if __name__=='__main__':main(*sys.argv[1:])
