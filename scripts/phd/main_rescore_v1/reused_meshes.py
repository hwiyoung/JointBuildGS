"""Copy already produced, matching training-view surfaces; never edit originals."""
import sys,shutil
from common import *

def main(site):
 cfg();start=time.monotonic();rows=[];copies={}
 for jp in sorted((O/'jobs').glob(site+'__*.json')):
  j=json.loads(jp.read_text())
  if 'model' not in j or j['key'].endswith('__freeze_views'):continue
  root=Path(j['model']).parent
  if j['family']=='r8':receipt=root/f"post{j['iteration']}/merged.json";source=receipt.with_name('merged.ply')
  else:receipt=root/'post/post.json';source=receipt.with_name('mesh_tsdf.ply')
  if not receipt.exists() or not source.exists():
   rows.append(dict(key=j['key'],status='REBUILD_REQUIRED',reason='matching saved training-view mesh not found'));continue
  r=json.loads(receipt.read_text());t=r['tsdf'];views=json.loads((O/'views'/f'{site}.json').read_text())['views'];ntrain=sum(not v['virtual'] for v in views)
  assert t['voxel_m']==.05 and t['sdf_trunc_m']==.25 and t['views']==ntrain
  assert r['site']==site and np.array_equal(r['box'],j['box'])
  if r.get('iteration') is not None:assert r['iteration']==j['iteration']
  out=O/'meshes'/j['key']/'train.ply';out.parent.mkdir(parents=True,exist_ok=True);digest=sha(source)
  if not out.exists():
   if digest in copies:os.link(copies[digest],out)
   else:shutil.copyfile(source,out)
  copies[digest]=out
  assert sha(out)==digest
  source_code=R/'scripts/phd/main_target_v1/post_r8.py' if j['family']=='r8' else R/'scripts/phd/main_fill_v1/cdgs/tsdf_tiled.py' if j['family']=='CDGS' else R/'scripts/phd/main_stage1_v1/gpu_s1.py'
  record=dict(status='PASS_REUSED_IDENTICAL_SETTINGS',key=j['key'],site=site,prior=j['prior'],family=j['family'],iteration=j['iteration'],source=str(source),source_sha256=digest,source_receipt=str(receipt),source_receipt_sha256=sha(receipt),source_code=str(source_code),source_code_sha256=sha(source_code),mesh_sha256=digest,voxel_m=.05,trunc_m=.25,views=ntrain,virtual_views=0,cluster_to_keep=None,eval_crop=False,model_sha256=sha(j['ply']),scientific_verdict=None)
  dump(out.with_suffix('.json'),record);rows.append(record)
 table('training_mesh_reuse_'+site,rows);timing('training_mesh_reuse_'+site,start)
if __name__=='__main__':main(sys.argv[1])
