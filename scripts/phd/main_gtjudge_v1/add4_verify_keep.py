"""Verify completed diagnostic outputs against the frozen prior and saved rows."""
from add4_common import *
def main():
 checks=[]
 for site in SITES:
  for prior in PRIORS:
   stem=f'{site}__{prior}';source=JA/'core_points'/f'{stem}.npz';core=loadz(source,['patch_id','prior_height_m']);targetpath=AW/'keep_targets'/f'{stem}.npz';target=loadz(targetpath)
   assert np.array_equal(core['patch_id'],target['patch_id']);assert np.array_equal(core['prior_height_m'],target['target_height_m'],equal_nan=True)
   features=loadz(AW/'features'/f'{stem}.npz');old=loadz(O/'scenes'/stem/'preservation_features.npz');assert np.array_equal(features['quadrant'][old['preservation']],old['quadrant'][old['preservation']])
   render=json.loads((O/'renders'/(stem+'__always_keep_mesh')/'receipt.json').read_text());assert render['GT_read'] is False
   for family,trunc in [('always_keep_mesh',.25),('always_keep_mesh_t010',.10)]:
    root=O/'meshes'/(stem+'__'+family);meta=json.loads((root/'final.json').read_text());scoremeta=json.loads((AW/'keep_scores'/stem/f'{family}.json').read_text());assert meta['voxel_m']==.05 and meta['trunc_m']==trunc and meta['GT_used_to_build_surface'] is False
    meshhash=proof(root/'final.ply')['sha256'];assert meshhash==meta['mesh_sha256']==scoremeta['mesh']['sha256']
    checks.append(dict(scene=stem,method=family,prior_values_exact=True,preservation_subdivisions_exact=True,mesh_sha256=meshhash,voxel_m=.05,trunc_m=trunc,reference_used_in_mesh=False))
 table=json.loads((AT/'always_keep.json').read_text());assert len(table['rows'])==1260
 for source in table['sources']:assert proof(source['path'])['sha256']==source['sha256']
 for r in table['rows']:
  assert r['n_gt']==r['n_within_tau']+r['n_far_hit']+r['n_no_surface']
  if r['n_gt']:assert abs(r['completeness_pct']+r['far_hit_pct']+r['no_surface_pct']-100)<1e-8
 dump(D/'verification/addendum4_keep.json',dict(at=now(),status='PASS_SOURCE_TARGET_MESH_AND_COUNT_CHECKS',checks=checks,table_rows=1260,scientific_verdict=None))
 print('ADD4_KEEP_VERIFIED',len(checks),1260,flush=True)
if __name__=='__main__':main()
