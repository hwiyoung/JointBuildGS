"""Check whether released V0 descendants have subsequently returned to bounds."""
import ast,sys
from types import SimpleNamespace
from scipy.spatial import cKDTree
from common import *
from stage1_prepare import eval_mask
class Array:
    def __init__(self,a):self.a=np.asarray(a)
    def detach(self):return self
    def double(self):return Array(self.a.astype('f8'))
    def cpu(self):return self
    def numpy(self):return self.a
    def __rmul__(self,v):return Array(v*self.a)
def main(site,prior):
    root=O/'stage1'/f'{site}__{prior}';g=loadz(root/'gaussians.npz');t=loadz(FT/'targets'/f'{site}__{prior}.npz')
    assert np.array_equal(eval_mask(t['centre'],site),t['in_eval']), 'Evaluation-box lineage differs from inherited target in_eval'
    valid=g['patch_ids'];c=SimpleNamespace(points=t['target'][valid].astype(float),valid_patch=valid,patch_normal=Array(t['normal'][valid].astype('f4')),patch_sigma=Array(t['sigma'][valid].astype('f4')))
    source=R/'src/phd/forks/GeoGS-conf-guided-v1-r23/jbgs_target_r7.py';node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='TargetR7');fn=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='candidates');env=dict(np=np,cKDTree=cKDTree)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),env)
    ii=np.flatnonzero(g['inside_eval']&(g['tag']==2));dist,ex,idx=env['candidates'](c,Array(g['xyz'][ii]));eligible=np.isfinite(dist)
    save=np.zeros(len(g['tag']),bool);save[ii]=eligible
    savez(root/'released_currently_eligible.npz',eligible=save)
    dump(root/'qualification.json',dict(site=site,prior=prior,eval_box_matches_inherited_in_eval=True,released_in_eval=len(ii),released_now_with_valid_candidate=int(eligible.sum()),source_sha256=sha(source),scientific_verdict=None))
    print('RELEASED_CURRENTLY_ELIGIBLE',site,prior,len(ii),int(eligible.sum()),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
