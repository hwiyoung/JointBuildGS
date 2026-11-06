"""Reuse exactly the R1 preservation descriptors and saved scores, first output."""
from add9_common import *
MS=['prior','mvs','judgment_mesh','gt_judgment_mesh','always_keep_mesh','fusion','GeoGS_30000','FINALTRAIN_30000'];NAMES={1:'무늬 없음만',2:'높이가 꺾이는 곳만',3:'둘 다',0:'둘 다 아님',-2:'무늬 확인 불가'}
def main():
 for key in ['c3','c1']:
  c=case(key);root=root_of(c);row,lab=data(c);f=loadz(root/'preservation_features.npz');meta=json.loads((root/'preservation_features.json').read_text());sc=scores(c,MS);target=lab==2;assert np.array_equal(f['preservation'],target);rows=[]
  for k in [1,2,3,0]+([-2] if np.any(target&(f['quadrant']==-2)) else []):
   take=target&(f['quadrant']==k);n=int(take.sum());r=dict(site=c['site'],prior=c['prior'],division_id=k,division=NAMES[k],n_gt=n,small='적음' if n<1000 else '',percent=100*n/int(target.sum()))
   for m,z in sc.items():
    v=values(z[take],row['row_tau_m'][take]);r.update({m+'_completeness_pct':v['within_pct'],m+'_n_in':int((np.isfinite(z[take])&(abs(z[take])<=row['row_tau_m'][take])).sum()),m+'_n_far':int((np.isfinite(z[take])&(abs(z[take])>row['row_tau_m'][take])).sum()),m+'_n_none':int((~np.isfinite(z[take])).sum())})
   rows.append(r)
  assert sum(r['n_gt'] for r in rows)==int(target.sum());csv9(key+'_case2_split',rows);dump(T9/(key+'_case2_split.json'),record(key,dict(rows=rows,n_case2=int(target.sum()),definitions={k:meta[k] for k in ['threshold','texture_rule','edge_rule','unavailable_no_near_nadir']},features_reused=True),[root/'preservation_features.npz',root/'preservation_features.json',root/'rows.npz',root/'stage1_cells.npz']+[scorepath(c,m) for m in MS]))
  print('ADD9_SPLIT',key,json.dumps([{k:r[k] for k in ['division','n_gt','percent']} for r in rows],ensure_ascii=False),flush=True)
  if key=='c3':
   old=json.loads((F6/f"{c['id']}_top_crop_noline_v2.json").read_text());path,z,extent=ortho(c['site']);from add9_photos import building_support
   support,_=building_support(c);q=np.concatenate([xyuv(support),xyuv(row['xyz'][target])]);bounds=aspect_bounds(q.min(0)-1,q.max(0)+1,1.25);im=orthocrop(z,bounds);px=pixels(xyuv(row['xyz'][target]),bounds,im.size);im=circles(im,px,f['quadrant'][target],A9['split_colors'],[0,1,2,3],radius=3,alpha=.8);save9(im,'c3_case2_split_top',dict(bounds_uv=bounds,split_colors=A9['split_colors'],division_counts=rows,n_case2=int(target.sum()),points_inside_image=int(((px[:,0]>=0)&(px[:,0]<im.width)&(px[:,1]>=0)&(px[:,1]<im.height)).sum()),ortho_source_matches_addendum6=True,extent_rule='whole building support and all scene case2 points plus 1m margin'),[path,root/'rows.npz',root/'stage1_cells.npz',root/'preservation_features.npz'])
   line=line9('c3');take=section_mask(row['xyz'],line['section'])&target;counts={NAMES[k]:int((take&(f['quadrant']==k)).sum()) for k in [1,2,3,0,-2]};dump(W9/'current_c3_split.json',dict(n=int(take.sum()),counts=counts,line=line,stated_49_matches=int(take.sum())==49));print('ADD9_CURRENT',int(take.sum()),counts,flush=True)
 for key in ['c1','c2','c3','c4']:
  c=case(key);row,lab=data(c);rec=selected(c);print('INSPECT',key,'rows',len(lab),'keys',list(row),'building',rec['selection']['building_identity'],'case2',int((lab==2).sum()),flush=True)
if __name__=='__main__':main()
