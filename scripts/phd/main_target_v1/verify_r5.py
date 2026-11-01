"""Independent saved-depth and lineage recount; input-only strata invariants and source parity."""
import ast,sys
import numpy as np
from common import *
from scipy.spatial import cKDTree
from report_r5 import LABEL

def loadz(p,keys=None):
 with np.load(p) as z:return {k:z[k] for k in (z.files if keys is None else keys)}
def main():
 counts=[]
 for key in ['depth_ALS','depth_LoD2','image_2dgs']:
  root=OUT/'r5/baselines'/key;r=json.loads((root/'coverage.json').read_text());bind=json.loads((root/'binding.json').read_text())
  for p,h in bind.items():
   if p.startswith('/'):assert sha(Path(p))==h
  for prior,expected in r['strata'].items():
   t=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz',['kind','region','any_replaced']);maps=OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps';ix=json.loads((maps/'index.json').read_text());tot={k:np.zeros(3,np.int64) for k in expected}
   for view in r['views'][prior]:
    name=view['camera'];p=root/'renders'/f'{name}.npz';assert sha(p)==view['sha256'];depth=loadz(p,['depth'])['depth'];m=loadz(maps/ix['views'][name]['file'])
    valid=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0);good=np.isfinite(depth)&(depth>0);inside=abs(depth-m['depth'])<=np.float32(1.96)*m['sigma'];has=m['owner']>=0;j=np.maximum(m['owner'],0)
    labels={'all':valid,'prior':valid&has,'background':valid&~has,'prior_roof':valid&has&(t['kind'][j]==1),'prior_wall':valid&has&(t['kind'][j]==2)}
    labels.update({f'region_{k}':valid&has&(t['region'][j]==k) for k in range(4)})
    labels.update({'prior_original':valid&has&~t['any_replaced'][j],'prior_replaced':valid&has&t['any_replaced'][j]})
    for k,sel in labels.items():tot[k]+=np.array([sel.sum(),(sel&good&inside).sum(),(sel&~good).sum()])
   for k,v in tot.items():assert v.tolist()==[expected[k][f] for f in ['target_pixels','inside','missing']],(key,prior,k)
   counts.append(dict(method=key,prior=prior,views=203,status='PASS_EXACT_ALL_STRATA_RECOUNT'))
  print('VERIFIED_BASELINE',key,flush=True)
 for prior in ['ALS','LoD2']:
  root=OUT/'r5/failures'/prior;r=json.loads((root/'summary.json').read_text());s=loadz(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/model/target_monitor/snapshot_7000.npz',['init_id','origin']);seed=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}/seeds.npz',['patch']);patch=seed['patch'][s['init_id']];matrix=np.zeros((2,4),np.int64)
  for v in r['views']:
   name=v['camera'];p=loadz(root/'pixels'/f'{name}.npz');m=loadz(OUT/'r2/stage1'/f'B173nb_b10_{prior}/maps'/f'{name}.npz',['owner']);idx=p['max_gaussian'];valid=idx>=0;j=np.maximum(idx,0);lineage=np.full(idx.shape,3,np.int8);lineage[valid&(s['origin'][j]==0)]=2;pp=valid&(s['origin'][j]==1);lineage[pp]=np.where(patch[j][pp]==m['owner'][pp],0,1);assert np.array_equal(lineage,p['lineage'])
   for direction in range(2):
    for k in range(4):matrix[direction,k]+=np.count_nonzero((p['front_back']==direction)&(lineage==k))
  assert np.array_equal(matrix,r['cross_counts']) and len(r['byte_equal_depth_replay_views'])==203
  counts.append(dict(method='max_individual_contributor',prior=prior,views=203,status='PASS_ORIGIN_AND_PATCH_ID_RECOUNT'))
  print('VERIFIED_MAXID',prior,flush=True)
 # Verify extraction selected function bodies equal original, not a rewritten approximate classifier.
 extracted=ast.parse((REPO/'scripts/phd/main_target_v1/track_types_r5.py').read_text());ef={n.name:ast.dump(n,include_attributes=False) for n in extracted.body if isinstance(n,ast.FunctionDef)}
 for f,names in [('scripts/phd/main_meshpatch_v1/track_a/units_lib.py',['find','union_mask']),('scripts/phd/main_meshpatch_v1/track_a/planeseg.py',['plane_from_sums','rg_plane','csr','finish']),('scripts/phd/main_meshpatch_v1/patch_units.py',['units','types'])]:
  tree=ast.parse((REPO/f).read_text());sf={n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
  for name in names:assert ef[name]==sf[name],name
 # Every place table partitions its source area and its truth/decision cells; no detailed holdout export.
 place_rows=0
 for sf in sorted((DOC/'tables').glob('places_r5_*.json')):
  r=json.loads(sf.read_text());sealed=r['split']=='holdout';site=r['site'];prior=r['prior'];root=(OUT/'holdout/r5/places'/f'holdout_{prior}' if sealed else OUT/'r5/places'/(f'development_{prior}' if r['split']=='development' else f'{site}_{prior}'))
  d=loadz(root/'strata.npz');place=np.full(len(d['area']),3,np.int8);place[~d['photo_available']]=4;place[(d['photo_available']&(d['photo']==3))|d['manual_glass']]=2;place[d['mvs_edge_band']]=1;place[d['mvs_face_type']==3]=0;assert np.array_equal(place,d['place'])
  scopes={'all':np.ones(len(place),bool)}
  if r['split']=='experiment':
   inp=loadz(OUT/'r2/targets'/f'{site}_{prior}.npz',['in_eval','region','area']);assert np.array_equal(inp['region'],d['region']) and np.array_equal(inp['area'],d['area']);scopes={'evaluation':inp['in_eval'],'band':~inp['in_eval']}
  for row in r['rows']:
   m=scopes[row['scope']]&(d['kind']==row['kind'])&(place==list(LABEL).index(row['stratum']))
   if row['replacement']!='all':m&=d['any_replaced'] if row['replacement']=='replaced' else ~d['any_replaced']
   assert int(m.sum())==row['patches'] and abs(d['area'][m].sum()-row['area_m2'])<1e-8
   region=d['region'].copy();sig=np.isin(region,[2,3])
   if row['variant']=='prior_only':region[sig]=2
   elif row['variant']=='mvs_only':region[sig]=3
   for field,sel in [('cell2_area_m2',m&(d['cell']==2)),('cell2_corrected_area_m2',m&(d['cell']==2)&(region==3)),('cell1_area_m2',m&(d['cell']==1)),('cell1_preserved_area_m2',m&(d['cell']==1)&(region==2))]:assert abs(d['area'][sel].sum()-row[field])<1e-8
   if row['variant']=='main':assert abs(row['cell2_corrected_T2_area_m2']+row['cell2_corrected_photo_only_area_m2']-row['cell2_corrected_area_m2'])<1e-8
   place_rows+=1
  for scope,mask in scopes.items():
   for kind in [1,2]:
    a=sum(x['area_m2'] for x in r['rows'] if x['kind']==kind and x['scope']==scope and x['variant']=='main' and x['replacement']=='all');assert abs(a-d['area'][mask&(d['kind']==kind)].sum())<1e-7
 # Verify the skylight place is an input-only face mask, not the reference-filtered case.
 SL=PH/'main_fill_v1/PHD-MAIN-FILL-v1';defs=json.loads((SL/'prep/undecidable/definitions.json').read_text());faces=defs['cases']['skylight']['place_faces_LoD2_ext'];lod=loadz(OUT/'r2/targets/B173nb_b10_LoD2.npz',['surf','in_eval','centre']);mask=np.isin(lod['surf'],faces)
 assert np.array_equal(mask&lod['in_eval'],loadz(SL/'work/undecidable/regions_B173nb_b10_LoD2.npz',['place_skylight'])['place_skylight'])
 als=loadz(OUT/'r2/targets/B173nb_b10_ALS.npz',['centre','in_eval']);dist,_=cKDTree(lod['centre'][mask,:2]).query(als['centre'][:,:2]);assert np.array_equal((dist<=.5)&als['in_eval'],loadz(SL/'work/undecidable/regions_B173nb_b10_ALS.npz',['place_skylight'])['place_skylight'])
 for prior in ['ALS','LoD2']:
  r=json.loads((OUT/'r5'/f'resume_audit_{prior}.json').read_text());assert r['status']=='NOT_RUN_NO_OPTIMIZER_STATE'
 record=dict(at=stamp(),status='PASS_R5_INDEPENDENT_RECOUNT',rows=counts,place_rows_checked=place_rows,track_a_ast_identity=True,manual_skylight_input_face_mask_replay=True,scientific_verdict=None);dump(DOC/'tables/verification_r5.json',record);dump(OUT/'r5/verification.json',record);print('VERIFY_R5_PASS',flush=True)
if __name__=='__main__':main()
