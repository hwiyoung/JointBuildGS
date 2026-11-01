"""Actual baseline initializer and r8 target controller, no optimization or rendering."""
import sys
sys.path.insert(0,'/source')
from types import SimpleNamespace as NS
import numpy as np,torch
from plyfile import PlyData
from scene import GaussianModel
from utils.graphics_utils import BasicPointCloud
from utils.general_utils import safe_state
from simple_knn._C import distCUDA2
import jbgs_target
from common import *
@torch.no_grad()
def main():
    site,prior=sys.argv[1:3];root=OUT/'r8/verification/initial'/prior;root.mkdir(parents=True,exist_ok=False)
    source=S0/'fork_inputs/s61'/site/f'scene_{prior}/sparse/0/points3D.ply';v=PlyData.read(str(source))['vertex']
    xyz=np.c_[v['x'],v['y'],v['z']];rgb=np.c_[v['red'],v['green'],v['blue']]/255.
    safe_state(False);g=GaussianModel(3);g.create_from_pcd(BasicPointCloud(xyz,rgb,np.zeros_like(xyz)),1.)
    scales=g._scaling.clone();rot=g._rotation.clone();opacity=g._opacity.clone();features=g._features_dc.clone()
    targetdir=OUT/'r8/stage1'/f'{site}_{prior}';index=json.loads((targetdir/'maps/index.json').read_text());scene=NS(getTrainCameras=lambda:[NS(image_name=k) for k in index['views']])
    args=NS(jbgs_target='on',jbgs_target_rev='r8',jbgs_target_dir=str(targetdir),model_path=str(root/'model'),jbgs_target_lambda=.05,jbgs_judgment='off',jbgs_appearance='off',jbgs_mv_consistency='off')
    (root/'model').mkdir();c=jbgs_target.create(args,scene,g,None,None)
    with np.load(targetdir/'seeds.npz') as z:
        keep=torch.tensor(z['keep_original'],device='cuda');bg=torch.tensor(z['background_original'],device='cuda');n=len(keep)
        assert torch.equal(g._scaling[:n],scales[keep]);assert torch.equal(g._rotation[n:],rot[bg]);assert torch.equal(g._opacity[n:],opacity[bg]);assert torch.equal(g._features_dc[n:],features[bg])
        expected=torch.log(torch.sqrt(torch.clamp_min(distCUDA2(g._xyz),1e-7)))[n:,None].repeat(1,2);assert torch.equal(g._scaling[n:],expected)
    old=OUT/'r7/runs'/f'tg_{site}_{prior}_s0_r7/model/target_monitor/snapshot_0.npz'
    with np.load(old) as z:
        p=z['origin']==1
        for key,value in [('xyz',g._xyz[:n]),('scale',g.get_scaling[:n]),('opacity',g.get_opacity[:n,0]),('rotation',g.get_rotation[:n])]:assert z[key][p].tobytes()==value.cpu().numpy().tobytes(),key
    # The count guard must fire beyond 7000; reset grace must not mask count/memory checks.
    from jbgs_target_r8 import TargetR8
    c.n6000=max(1,len(g._xyz)//4);c.last_opacity_reset=9000
    try:c.observe(9000,g,torch.tensor(1.,device='cuda'),torch.tensor(1.),torch.tensor(0.),'unit_count')
    except RuntimeError as e:assert str(e)=='TARGET_STOP_count_gt_3x_6000'
    else:raise AssertionError('missing post7000 count stop')
    assert json.loads((c.mon/'STOP.json').read_text())['reason']=='count_gt_3x_6000'
    large=json.loads((c.mon/'initial_large_background.json').read_text());oldlarge=json.loads((old.parent/'initial_large_background.json').read_text())
    result=dict(at=stamp(),status='PASS_R8_INITIALIZATION',optimization_steps=0,baseline_background_rotation_opacity_color_identical=True,baseline_scale_rule_exact=True,
        actual_patch_initial_xyz_scale_opacity_rotation_byte_identical=True,post7000_count_stop_during_opacity_grace=True,initial_large_background_r8=large,initial_large_background_r7=oldlarge,scientific_verdict=None)
    dump(root/'result.json',result);dump(DOC/'tables'/f'r8_initial_{prior}.json',result);print(result['status'],prior,flush=True)
if __name__=='__main__':main()
