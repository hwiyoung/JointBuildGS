"""CPU audit of recorded checkpoint pairs, pre-density gradients, and method invariants."""
import ast,gc,sys
import numpy as np
import torch
from plyfile import PlyData
from common import *
def main():
    for p in Path(__file__).parent.glob('r8_record*.py'):ast.parse(p.read_text(),filename=str(p))
    iteration=int(sys.argv[1]);root=OUT/'r8_recorded_continue';cfg=json.loads((CFG/'r8_record_continue.json').read_text());model=Path(cfg['model'])
    receipt=json.loads((model/f'jbgs_complete/iteration_{iteration}/receipt.json').read_text())
    cp=model/f'jbgs_complete/iteration_{iteration}/checkpoint.pth';assert sha(cp)==receipt['checkpoint_sha256']
    saved=torch.load(cp,map_location='cpu');original=torch.load(cfg['checkpoint'],map_location='cpu')
    assert saved['optimization']==original['optimization'] and saved['implementation_hashes']==original['implementation_hashes']
    allowed={'model_path','save_iterations','jbgs_capture_iterations','jbgs_resume_full'}
    differences=[]
    for k,v in original['args'].items():
        w=saved['args'][k]
        if isinstance(v,float) and isinstance(w,float) and np.isnan(v) and np.isnan(w):continue
        if v!=w:differences.append(k);assert k in allowed,k
    for key in ['seed_sha256','maps_index_sha256','target_sha256','n6000']:
        assert saved['target_r6'][key]==original['target_r6'][key],key
    assert saved['train_order']==original['train_order'] and saved['test_order']==original['test_order']
    full=PlyData.read(model/f'jbgs_complete/iteration_{iteration}/point_cloud.ply')['vertex'].data
    xyz=np.column_stack([full[k] for k in ['x','y','z']]);assert np.array_equal(xyz,saved['model'][1].detach().numpy())
    assert np.array_equal(full['init_id'].astype('i8'),saved['init_id'].numpy())
    n=len(xyz)
    for a in saved['target_r6']['meta'].values():assert len(a)==n
    assert saved['iteration']==iteration and receipt['gaussians']==n
    assert len(saved['model'][10]['state'])==6
    for group in saved['model'][10]['param_groups']:
        entry=saved['model'][10]['state'][group['params'][0]]
        assert entry['exp_avg'].shape[0]==n and entry['exp_avg_sq'].shape[0]==n
    del original,saved,full,xyz;gc.collect()
    pre=PlyData.read(model/f'point_cloud/iteration_{iteration}/point_cloud.ply')['vertex'].data
    with np.load(model/f'recording/pre_densification/iteration_{iteration}/gradient.npz') as a:
        assert np.array_equal(np.column_stack([pre[k] for k in ['x','y','z']]),a['xyz'])
        assert np.array_equal(pre['init_id'].astype('i8'),a['init_id'])
        with np.errstate(divide='ignore',invalid='ignore'):gradient=a['accum']/a['denom']
        gradient[np.isnan(gradient)]=0
        assert np.array_equal(gradient,a['normalized']) and np.array_equal(gradient>=cfg['densify_grad_threshold'],a['above'])
        positive=int((a['denom']>0).sum());above=int(a['above'].sum())
    result=dict(at=stamp(),status='PASS',iteration=iteration,full_gaussians=n,pre_densification_gaussians=len(pre),denom_positive=positive,gradient_above=above,
        original_method_optimization_inputs_camera_membership_equal=True,allowed_argument_differences=differences,full_checkpoint_ply_meta_adam_equal=True,
        pre_densification_ply_gradient_population_equal=True,syntax_all_record_scripts='PASS',scientific_verdict=None)
    dump(root/f'verification/checkpoint_{iteration}.json',result);print('RECORD_CHECKPOINT_AUDIT',json.dumps(result),flush=True)
if __name__=='__main__':main()
