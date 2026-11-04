"""Measure targets of outside-scope descendants that draw evaluated rows.
This measurement never changes the frozen, GT-free simulation masks.
"""
from common import *
import sys
sys.path.append('/repo/src/phd/forks/GeoGS-conf-guided-v1-r24')
from release_search import TangentTree
def main(site,prior):
 root=O/'stage1'/f'{site}__{prior}';a=loadz(root/'attribution.npz');g=loadz(root/'gaussians.npz');mask=(a['current_binding']==2)&~np.isfinite(a['released_target_tangent_m']);indices=np.unique(a['selected_gaussian'][mask]);indices=indices[indices>=0];assert (~g['inside_eval'][indices]).all();t=loadz(FT/'targets'/f'{site}__{prior}.npz');valid=g['patch_ids'];tree=TangentTree(t['target'][valid],t['normal'][valid].astype('f4').astype(float),(np.float32(1.96)*t['sigma'][valid].astype('f4')).astype(float),valid)
 tangent,excess,near=tree.query(g['xyz'][indices]);rows=np.flatnonzero(mask);lookup=np.searchsorted(indices,a['selected_gaussian'][rows]);a['released_target_tangent_m'][rows]=tangent[lookup];a['released_target_excess_m'][rows]=excess[lookup];savez(root/'attribution.npz',**a);savez(root/'outside_attributed_targets.npz',full_gaussian_index=indices,nearest_target_index=near,tangent_m=tangent,normal_excess_m=excess)
 dump(root/'outside_attributed_targets.json',dict(outside_gaussians_measured=len(indices),attributed_gt_rows=len(rows),selection_used_for='measurement only; GT never selects simulation or training actions',simulation_masks_sha256=sha(root/'simulation_masks.npz'),scientific_verdict=None));print('OUTSIDE_ATTRIBUTED',prior,len(indices),len(rows),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
