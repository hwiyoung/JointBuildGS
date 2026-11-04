"""Modify one saved PLY once using preselected tag/target-only masks."""
from common import *
import sys
from plyfile import PlyData,PlyElement
def main(site,prior,simulation):
    cfg();stem=f'{site}__{prior}';root=O/'stage1'/stem;b=json.loads((root/'binding.json').read_text());model=Path(b['model'])/'point_cloud/iteration_30000/point_cloud.ply'
    g=loadz(root/'gaussians.npz');mask=loadz(root/'simulation_masks.npz');t=loadz(FT/'targets'/f'{stem}.npz');ply=PlyData.read(model);vertex=ply['vertex'].data.copy();xyz=np.c_[vertex['x'],vertex['y'],vertex['z']];assert np.array_equal(xyz,g['xyz'])
    selected=mask[simulation];removed=0;moved=0;maxmove=0.
    if simulation.startswith('delete'):
        removed=int(selected.sum());vertex=vertex[~selected]
    else:
        idx=g['patch_ids'][mask['nearest_target_index'][selected]];anchor=t['target'][idx].astype('f4').astype(float);normal=t['normal'][idx].astype('f4').astype(float);width=(np.float32(1.96)*t['sigma'][idx].astype('f4')).astype(float)
        p=xyz[selected].astype(float);h=((p-anchor)*normal).sum(1);bounded=np.clip(h,-width,width);q=(p+((bounded-h)/(normal*normal).sum(1))[:,None]*normal).astype('f4')
        moved=int((q!=xyz[selected]).any(1).sum());maxmove=float(np.linalg.norm(q-p,axis=1).max()) if len(q) else 0
        for k,name in enumerate(['x','y','z']):vertex[name][selected]=q[:,k]
    key=stem+'__sim_'+simulation;dest=O/'simulations'/key/'point_cloud.ply';dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists()
    PlyData([PlyElement.describe(vertex,'vertex')],text=False).write(str(dest))
    views=json.loads((O/'views'/f'{site}.json').read_text());job=dict(site=site,prior=prior,family='FINALTRAIN_30000',key=key,views=len(views['views']),box=views['box'],ply=str(dest),cache=str(O/'renders'/key),scientific_verdict=None)
    dump(O/'jobs'/f'{key}.json',job);dump(dest.with_suffix('.json'),dict(source=str(model),source_sha256=sha(model),output_sha256=sha(dest),simulation=simulation,selected=int(selected.sum()),removed=removed,moved=moved,max_move_m=maxmove,GT_used=False,role='upper-bound diagnostic only, not trained performance',scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
