"""Audit masked-ray influence and spatial support of the published sample metric."""
import json
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image


def read(p): return json.loads(Path(p).read_text())
def summary(a):
    a=np.asarray(a)
    return dict(n=int(a.size), median=float(np.median(a)),mean=float(a.mean()),
                p10=float(np.quantile(a,.1)),p90=float(np.quantile(a,.9))) if a.size else dict(n=0)


cfg=read('/out/config.json');root=Path('/art')/cfg['attempt_relative'];analysis=root/cfg['analysis'];out=Path('/out')
run=read(root/'config.json');legacy=Path('/art')/run['r1_run_relative'];overrides=read(root/'execution/artifact_overrides.json')
result=dict(scientific_verdict=None,source_metric='fixed input point to closest native TSDF triangle',regions={})
for region in ['R1','R2','R5']:
    sample=np.load(analysis/(region+'_paired_samples.npz'));sel=(sample['source']==0)&(sample['judgment']==2)
    p=sample['xyz'][sel];byzone={str(z):int((sample['zone'][sel]==z).sum()) for z in np.unique(sample['zone'][sel])}
    r=dict(correction_n=len(p),zones=byzone,xyz_min=p.min(0).tolist(),xyz_max=p.max(0).tolist(),branches={})
    theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]]);uv=p[:,:2]@basis.T
    r['uv_min']=uv.min(0).tolist();r['uv_max']=uv.max(0).tolist()
    for b in ['mvs','da3','local_prior0']:
        d=sample['distance_'+b][sel];closest=sample['closest_'+b][sel];delta=closest-p
        r['branches'][b]=dict(distance=summary(d),closest_z_minus_sample_z=summary(delta[:,2]),
                              closest_xy_distance=summary(np.linalg.norm(delta[:,:2],axis=1)))
    if region=='R5':
        r['points']=[dict(xyz=p[i].tolist(),zone=int(sample['zone'][sel][i]),
                    distance={b:float(sample['distance_'+b][sel][i]) for b in ['mvs','da3','local_prior0']}) for i in range(len(p))]
    result['regions'][region]=r

for region in ['R1','R2']:
    r=result['regions'][region]
    local=root/overrides.get(region,{}).get('local_prior0',region+'/local_prior0')
    sampling=[json.loads(x) for x in (local/'camera_sampling.jsonl').read_text().splitlines()];byit={x['iteration']:x for x in sampling}
    trace=[json.loads(x) for x in (local/'local_prior_trace.jsonl').read_text().splitlines()]
    active=[t for t in trace if t['zero_weight_valid']>0]
    r['traced_masked_steps']=len(active)
    r['recorded_weights']=sorted(set((s['mvs_weight'],s['prior_weight']) for s in sampling))
    ratios=[(byit[t['iteration']]['mvs_weight']/byit[t['iteration']]['valid_mvs_loss_pixels'])/
            (byit[t['iteration']]['prior_weight']/t['original_valid']) for t in active]
    r['traced_per_pixel_image_prior_coefficient_ratio']=summary(ratios)
    r['ratio_above_one_percent']=float(100*(np.asarray(ratios)>1).mean())
    inputs=(Path('/art')/run['r1_prep_relative']/'result/input') if region=='R1' else root/region/'preparation/input'
    views=sorted(read(inputs/'scene/split_manifest.json')['train'],key=lambda v:v['name'])
    maskrec=read(root/region/'masks/receipt.json');maskcounts={t['name']:t['pixels'] for t in maskrec['masks']}
    extracts={b:root/overrides.get(region,{}).get('extract_'+b,region+'/extract_'+b) for b in ['mvs','local_prior0']}
    if region=='R1':extracts['mvs']=legacy/read(legacy/'mesh_recovery.json')['relative']/'extract_final'
    parts={k:[] for k in ['mvs_minus_prior_target','control_minus_mvs','release_minus_mvs','control_minus_prior','release_minus_prior','release_minus_control']}
    perview=[]
    for i,v in enumerate(views):
        name=Path(v['name']).stem
        if not maskcounts[name]:continue
        mask=np.load(root/region/'masks'/(name+'.npy'))
        prior=np.load(inputs/'prior/raw_depth'/(name+'.npy'))[mask];mvs=np.load(inputs/'mvs_rgb/raw_depth'/(name+'.npy'))[mask]
        rendered={b:np.asarray(Image.open(d/'model/train/ours_30000/vis'/('depth_%05d.tiff'%i)))[mask] for b,d in extracts.items()}
        control=rendered['mvs'];release=rendered['local_prior0'];valid=np.isfinite(prior)&np.isfinite(mvs)&np.isfinite(control)&np.isfinite(release)&(mvs>0)&(prior>0)
        assert valid.all(),name
        values=dict(mvs_minus_prior_target=mvs-prior,control_minus_mvs=control-mvs,release_minus_mvs=release-mvs,
                    control_minus_prior=control-prior,release_minus_prior=release-prior,release_minus_control=release-control)
        for k,a in values.items():parts[k].append(a)
        perview.append(dict(name=name,masked_pixels=int(mask.sum()),target_gap=summary(mvs-prior),absolute_control_mvs_residual=summary(abs(control-mvs)),
                            absolute_release_mvs_residual=summary(abs(release-mvs)),absolute_render_change=summary(abs(release-control))))
    merged={k:np.concatenate(v) for k,v in parts.items()}
    r['masked_pixel_observations']={k:dict(signed=summary(v),absolute=summary(abs(v))) for k,v in merged.items()}
    r['per_view_masked_pixels']=perview
    r['masked_render_change_over_01m_percent']=float(100*(abs(merged['release_minus_control'])>.1).mean())
    r['masked_render_change_over_1m_percent']=float(100*(abs(merged['release_minus_control'])>1).mean())
    print(region,'masked',len(merged['release_minus_control']),json.dumps(r['masked_pixel_observations']),flush=True)

# The active matched keep run can advance while this diagnostic reads completed lines.
probe=root/'R1/local_prior0_matched_keep_20260918/probe_depth_trace.jsonl'
rows=[]
for line in probe.read_text().splitlines():
    try:rows.append(json.loads(line))
    except json.JSONDecodeError:continue
result['keep_probe_latest']={name:[x for x in rows if x['camera']==name][-1] for name in sorted(set(x['camera'] for x in rows))}
result['status']='PASS_MASKED_RAY_AND_SAMPLE_SUPPORT_DIAGNOSTIC'
result['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
result['limitations']=['Coefficient ratio is derivative magnitude w.r.t. rendered scalar depth, not the combined Gaussian parameter gradient.',
                       'Masked pixels are repeated observations, not independent samples.',
                       'Nearest mesh point need not be the same visible or semantically corresponding surface.',
                       'Intermediate keep probe is not a final mesh or completed keep/release comparison.']
(out/'receipt.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print('PASS')
