"""Only B173 training views, followed by the already-validated shared cleanup."""
from common import *
import sys
from bounded_cleanup import cleanup
from score_mesh import score

def main(action,key):
 j=json.loads((O/'jobs'/f'{key}.json').read_text());assert j['site']=='B173nb_b10'
 root=O/'meshes'/key;root.mkdir(parents=True,exist_ok=True);out=root/'primary.ply'
 if action=='cleanup':
  raw=Path(j['raw_train_mesh']) if 'raw_train_mesh' in j else root/'train_work/merged.ply'
  if not out.exists():
   if 'raw_sha256' in j:assert sha(raw)==j['raw_sha256']
   # 2DGS is exactly the same raw mesh in both prior rows.
   other=O/'meshes'/key.replace('__LoD2__','__ALS__')/'primary.ply'
   same=key.endswith('__2DGS_30000') and j['prior']=='LoD2' and other.exists()
   if same:
    oj=json.loads((O/'jobs'/f'{key.replace("__LoD2__","__ALS__")}.json').read_text());assert oj['raw_sha256']==j['raw_sha256'];os.link(other,out);v=json.loads(other.with_suffix('.json').read_text());v.update(reused_identical_mesh=str(other));dump(out.with_suffix('.json'),v)
   else:cleanup(j['site'],raw,out)
   rec=json.loads(out.with_suffix('.json').read_text());rec.update(views=203,virtual_views=0,raw_mesh=str(raw),source_job=str(O/'jobs'/f'{key}.json'),source_job_sha256=sha(O/'jobs'/f'{key}.json'),role='primary training-view mesh',scientific_verdict=None);dump(out.with_suffix('.json'),rec)
 elif action=='score':
  if not (O/'scores'/key/'values.json').exists():score(j['site'],j['prior'],key,out)
 else:raise ValueError(action)
if __name__=='__main__':main(*sys.argv[1:])
