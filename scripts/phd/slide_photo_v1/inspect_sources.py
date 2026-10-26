from common import *
import zipfile
def schema(p):
    print(str(p))
    with np.load(p) as z:print({k:(str(z[k].dtype),z[k].shape) for k in z.files if k in ['centre','normal','surf','loc_center','loc_surface','surf_ext','loc_area','in_eval','gt_p','mvs_a_p','mvs_a_status','xyz','points','means','scales','quats','rotations']})
for p in [U/'patch_values/B0_b10__LoD2__R1.5.npz',S0/'s61/box/B0_b10/LoD2/units.npz']:schema(p)
print('stage1',list((S1/'stage1/B0_b10/prop_LoD2_s0').iterdir()))
gp=S1/'stage1/B0_b10/prop_LoD2_s0/model/dump/iteration_30000/gaussians.npz'
with np.load(gp) as z:print('gaussian_schema',{k:(str(z[k].dtype),z[k].shape) for k in z.files})
places=load(REPO/'configs/phd/main_photofig_v1/photofig_v1.json')['places']
for key in ['fig3','fig3b','fig3_extra']:
    print('wall',key,{k:(v if not isinstance(v,list) or len(v)<10 else ['length',len(v)]) for k,v in places[key].items() if k not in ['photo_candidates']})
print('raw split',list(load(W/'image_split.json')))
print('tiles',len(load(W/'inputs/tiles.json')))
