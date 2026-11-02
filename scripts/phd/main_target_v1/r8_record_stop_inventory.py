"""CPU tables for the state saved at the recording guard, with unchanged spatial bins."""
import gc
import numpy as np
import torch
from plyfile import PlyData
from scipy.special import expit
from common import *
from cause_r8_spatial import bins,writecsv
ROOT=OUT/'r8_recorded_continue'
NAMES=['배경','패치','풀림: 100회 자손','풀림: 그 밖']
def grouping(xyz,tag,released,b):
    x,h=bins(xyz,b);t=tag.copy();t[(tag==2)&(released!=100)]=3
    return t.astype('i4')*16+x*4+h
def main():
    for p,h in json.loads((CFG/'r8_record_diagnostics.lock.json').read_text())['files'].items():assert sha(p)==h,p
    stop=json.loads((ROOT/'STOP_LoD2.json').read_text());src=Path(stop['stop_dir']);dest=ROOT/'stop_diagnostic';dest.mkdir(exist_ok=False)
    cfg=json.loads((CFG/'r8_record_continue.json').read_text());b=json.loads(Path(cfg['boundaries']).read_text())
    assert sha(cfg['boundaries'])==cfg['boundary_sha256'];assert sha(src/'checkpoint.pth')==stop['checkpoint_sha256'];assert sha(src/'point_cloud.ply')==stop['ply_sha256']
    v=PlyData.read(src/'point_cloud.ply')['vertex'].data;xyz=np.column_stack([v[k] for k in ['x','y','z']]);ids=v['init_id'].astype('i8')
    with np.load(src/f'snapshot_{stop["attempted_iteration"]}.npz') as snap:
        assert np.array_equal(xyz,snap['xyz']) and np.array_equal(ids,snap['init_id'])
        tag=snap['target_tag'].copy();released=snap['target_released_at'].copy()
    scale=np.exp(np.column_stack([v['scale_0'],v['scale_1']])).max(1);opacity=expit(v['opacity']);group=grouping(xyz,tag,released,b)
    np.savez_compressed(dest/'arrays.npz',xyz=xyz,init_id=ids,tag=tag,released_at=released,longest_axis=scale,opacity=opacity,group=group)
    rows=[]
    for j in range(64):
        mask=group==j;n=int(mask.sum());rows.append(dict(state='r8_LoD2_stop_'+str(stop['attempted_iteration']),provenance=NAMES[j//16],tag=j//16,xy_bin=j%16//4,height_bin=j%4,count=n,
            longest_axis_median_m=float(np.median(scale[mask])) if n else None,opacity_median=float(np.median(opacity[mask])) if n else None))
    assert sum(r['count'] for r in rows)==stop['gaussians'];dump(dest/'counts.json',dict(rows=rows,scientific_verdict=None));writecsv(dest/'counts.csv',rows)
    gradients=[];paths=sorted((Path(cfg['model'])/'recording/pre_densification').glob('iteration_*/gradient.npz'))+[src/'gradient.npz']
    for path in paths:
        a=dict(np.load(path));it=int(path.parent.name.split('_')[-1]);gg=grouping(a['xyz'],a['target_tag'],a['target_released_at'],b)
        ply=src/'point_cloud.ply' if path==src/'gradient.npz' else Path(cfg['model'])/f'point_cloud/iteration_{it}/point_cloud.ply'
        pv=PlyData.read(ply)['vertex'].data
        assert np.array_equal(np.column_stack([pv[k] for k in ['x','y','z']]),a['xyz'])
        assert np.array_equal(pv['init_id'].astype('i8'),a['init_id']);del pv
        accum=a['accum'].reshape(-1);denom=a['denom'].reshape(-1)
        with np.errstate(divide='ignore',invalid='ignore'):gr=accum/denom
        gr[np.isnan(gr)]=0;above=gr>=cfg['densify_grad_threshold']
        for j in range(64):
            mask=gg==j;n=int(mask.sum());nabove=int((mask&above).sum());gradients.append(dict(iteration=it,population='saved_stop_state' if path==src/'gradient.npz' else 'immediately_before_densification',
                provenance=NAMES[j//16],tag=j//16,xy_bin=j%16//4,height_bin=j%4,count=n,denom_positive=int((mask&(denom>0)).sum()),above=nabove,fraction=nabove/n if n else None,threshold=cfg['densify_grad_threshold']))
        print('GRADIENT_TABLE',it,len(gg),int(above.sum()),flush=True);del a,gg,gr,above;gc.collect()
    dump(dest/'gradient.json',dict(rows=gradients,scientific_verdict=None));writecsv(dest/'gradient.csv',gradients)
    cp=torch.load(src/'checkpoint.pth',map_location='cpu');m=cp['model'];assert np.array_equal(xyz,m[1].detach().numpy());assert np.array_equal(ids,cp['init_id'].numpy())
    assert np.array_equal(tag,cp['target_r6']['meta']['target_tag'].numpy());assert np.array_equal(released,cp['target_r6']['meta']['target_released_at'].numpy())
    assert cp['iteration']==stop['completed_iteration'] and len(m[10]['state'])>0
    audit=dict(at=stamp(),status='PASS_SAVED_STOP_STATE',ply_checkpoint_xyz_init_id_and_tags_equal=True,optimizer_groups=len(m[10]['param_groups']),optimizer_states=len(m[10]['state']),
        saved_iteration=cp['iteration'],attempted_iteration=stop['attempted_iteration'],train_cameras=len(cp['train_order']),rng_keys=list(cp['rng']),
        ordinary_resume_ready=stop['ordinary_resume_ready'],original_checkpoint_unchanged=sha(cfg['checkpoint'])==cfg['checkpoint_sha256'],files={str(p):sha(p) for p in paths+[src/'point_cloud.ply',src/'checkpoint.pth']},scientific_verdict=None)
    assert audit['original_checkpoint_unchanged'];dump(dest/'audit.json',audit);dump(dest/'boundaries.json',b)
    print('STOP_INVENTORY_COMPLETE',stop['gaussians'],flush=True)
if __name__=='__main__':main()
