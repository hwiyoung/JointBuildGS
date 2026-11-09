"""Expose both immutable ancestry and current attachment of actual contributors."""
from common import *
receipt=json.loads((D/'attribution_receipt.json').read_text())
if receipt['status']!='PASS_EXACT_SAVED_DEPTH_MAX_ALPHA_T':raise SystemExit(0)
z=loadz(O/'gaussians/attribution_30000.npz');pg=loadz(O/'work/patch_groups.npz');expected=pg['reference_owner'][z['reference_row_id']];full=z['max_contributor_full_gaussian'];valid=full>=0;snap=loadz(MODEL/'target_monitor/snapshot_30000.npz',['target_index','target_tag','patch_ids','init_id']);current=np.full(len(full),-1,'i8');attached=valid&(z['target_tag']==1);current[attached]=snap['patch_ids'][snap['target_index'][full[attached]]];init_id=np.full(len(full),-1,'i8');init_id[valid]=snap['init_id'][full[valid]]
initial_class=np.full(len(full),3,'i1');initial_class[valid&(z['origin']==0)]=2;prior=valid&(z['origin']==1);initial_class[prior]=np.where(z['initial_patch'][prior]==expected[prior],0,1);current_class=np.full(len(full),4,'i1');current_class[valid&(z['target_tag']==0)]=2;current_class[valid&(z['target_tag']==2)]=3;current_class[attached]=np.where(current[attached]==expected[attached],0,1)
z.update(reference_patch=expected,current_patch=current,init_id=init_id,initial_lineage_class=initial_class,current_binding_class=current_class);savez(O/'gaussians/attribution_30000.npz',**z)
initnames=['같은 패치 계보','다른 패치 계보','SfM 배경 계보','확인 불가'];currentnames=['같은 패치에 묶임','다른 패치에 묶임','배경','풀림','확인 불가'];groupnames=['기타 패치','틀린 판정 패치','보정 비교 패치'];rows=[]
for gp in [1,2]:
 for ic in range(4):
  for cc in range(5):
   for lineage_group in [0,1,2]:
    take=(z['group']==gp)&(initial_class==ic)&(current_class==cc)&(z['initial_patch_group']==lineage_group)
    if take.any():rows.append(dict(reference_group=gp,initial_lineage=initnames[ic],initial_patch_group=groupnames[lineage_group] if ic in [0,1] else '해당 없음',current_binding=currentnames[cc],reference_rows=int(take.sum()),fraction_of_group=float(take.sum()/(z['group']==gp).sum())))
table('actual_max_alpha_T_origin',rows)
receipt.update(attribution_export_sha256=sha(O/'gaussians/attribution_30000.npz'),lineage_table=str(D/'tables/actual_max_alpha_T_origin.csv'));dump(D/'attribution_receipt.json',receipt)
print('ATTRIBUTION_TABLE_READY',len(rows))
