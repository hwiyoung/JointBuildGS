"""Refresh line metadata while retaining completed, line-free render pixels."""
from add6_render import *

for key in ['c1','c2','c4']:
 c=case(key);cam=camera(c)
 for method in ['FINALTRAIN_30000','fusion','GeoGS_30000']:
  p=F6/f"{c['id']}_result_dist_{method}.json";meta=json.loads(p.read_text());V,F=read_surface(meshpath(c,method));scene=MeshScene(V,F);meta.update(annotation(c,cam,scene));meta['config_sha256']=sha(C/'addendum6.json');meta['at']=now();meta['sources']=[proof(x['path']) for x in meta['sources']];meta['sources'].append(proof(Path(__file__)));meta['pixels_reused_from_completed_unmarked_render']=True;dump(p,meta);del scene,V,F;gc.collect()
 unmarked(key)
unmarked('c3')
