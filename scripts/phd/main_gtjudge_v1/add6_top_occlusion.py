"""Use the inherited MVS visibility convention for orthographic annotation metadata."""
from add6_common import *

def main():
 for site in ['B173nb_b10','B0_b10','R1rep_b10']:
  cases=[c for c in AC['cases'] if c['site']==site];p=meshpath(cases[0],'mvs');V,F=read_surface(p);sc=MeshScene(V,F);top=float(V[:,2].max()+10)
  for c in cases:
   line=np.array(selected(c)['annotation_xyz']);orig=line.copy();orig[:,2]=top;di=np.tile([0.,0.,-1.],(len(line),1));hit=sc.cast(orig,di);occluded=np.isfinite(hit)&(top-hit>line[:,2]+.15)
   for path in F6.glob(c['id']+'_top_crop_noline*.json'):
    j=json.loads(path.read_text());j['line_occluded']=occluded.tolist();j['occlusion_rule']='vertical MVS rays, more than 0.15m above annotation; proxy visibility following inherited MVS visibility convention';j['original_ortho_depth_available']=False;j['line_occlusion_source']='MVS proxy; source ortho stores RGB without per-pixel Z';j['sources'].extend([proof(p),proof(Path(__file__))]);dump(path,j)
  del V,F,sc;gc.collect()
 print('ADD6_TOP_OCCLUSION_MVS_PROXY',flush=True)
if __name__=='__main__':main()
