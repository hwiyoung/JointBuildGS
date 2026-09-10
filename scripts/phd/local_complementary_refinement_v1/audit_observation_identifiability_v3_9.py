"""Known-geometry photometry probes, reusing the frozen projection and NCC code."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scripts.phd.local_complementary_refinement_v1 import photometric_walkthrough_v3_2 as photo
from src.phd import local_normal_photometry_v3_7 as geometry
from src.phd.local_source_weight_v3_8 import evidence_from_costs


def texture(u, v, kind):
    if kind == 'periodic_texture':
        return .5 + .2*np.sin(2*np.pi*u/4) + .15*np.sin(2*np.pi*v/7)
    if kind == 'linear_brightness_ramp':
        return np.clip(.5 + .013*(u-64) + .006*(v-64), 0, 1)
    if kind == 'flat_texture':
        return np.full_like(u, .5)
    return .5 + .16*np.sin(.89*u+.23*v) + .13*np.sin(.17*u-1.11*v) + .09*np.cos(.61*u+.77*v)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    a = parser.parse_args()
    assert Path('/.dockerenv').exists()
    cfg = json.loads(a.config.read_text())
    assert cfg['scientific_verdict'] is None and not cfg['training'] and not cfg['real_gt_input']
    assert os.environ['JBGS_RUNTIME_IMAGE_ID'] == cfg['docker_image']
    a.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    rows, fixtures, checks = [], [], []
    def check(name, value):
        checks.append({'name':name,'passed':bool(value)})
    size, f = cfg['image_size'], cfg['focal_px']
    cx, cy = cfg['center']
    K = np.array([[f,0,cx],[0,f,cy],[0,0,1.]])
    reference = dict(K=K,R=np.eye(3),t=np.zeros(3))
    y, x = np.mgrid[:size,:size].astype(float)
    whole_uv = np.stack([x,y],axis=-1)
    whole_rays = geometry.rays(whole_uv,K)
    displays=[]
    for kind in cfg['fixture_names']:
        n = np.asarray(cfg['slanted_normal'] if kind=='slanted_textured_plane' else [0,0,1.])
        dtrue, dwrong = cfg['plane_offset'], cfg['wrong_plane_offset']
        ref_gray=texture(x,y,kind)
        ref_rgb=np.repeat(ref_gray[...,None],3,-1)
        images=[]
        for j,b in enumerate(cfg['neighbor_baselines']):
            # Independently ray-cast the known plane from each camera center.
            z=(dtrue-n[0]*b)/(whole_rays@n)
            X=whole_rays*z[...,None] + np.array([b,0,0])
            u0=f*X[...,0]/X[...,2]+cx
            v0=f*X[...,1]/X[...,2]+cy
            g=texture(u0,v0,kind)
            if kind=='affine_brightness':
                g=.7*g+.12
            if kind=='occluding_patch':
                # A controlled neighbor-only occluder fixture, not a full scene renderer.
                occluded=(np.abs(x-(cx-f*b/dtrue))<=20)&(np.abs(y-cy)<=20)
                noise=np.random.default_rng(cfg['occluder_random_seed']+j).uniform(.1,.9,g.shape)
                g=np.where(occluded,noise,g)
            images.append(np.repeat(g[...,None],3,-1))
        for r in cfg['patch_sizes']:
            uv=photo.uv_grid(cfg['center'],r)
            ray=geometry.rays(uv,K)
            raw={ 'correct':dtrue/(ray@n), 'offset':dwrong/(ray@n) }
            normals={s:geometry.estimate_normal(uv,d,np.ones(d.shape,bool),K,9,.8) for s,d in raw.items()}
            plane={s:geometry.plane_depth(uv,d,np.ones(d.shape,bool),K,normals[s])[0] for s,d in raw.items()}
            if kind=='slanted_textured_plane':
                check('slanted_raw_plane_depth_'+str(r),all(np.allclose(raw[s],plane[s],atol=1e-10) for s in raw))
            A=geometry.crop(ref_rgb,r)
            for j,b in enumerate(cfg['neighbor_baselines']):
                neighbor=dict(K=K,R=np.eye(3),t=np.array([-b,0,0]))
                warps={}; masks={}
                for mode,targets in [('raw',raw),('plane',plane)]:
                    for source,d in targets.items():
                        q,z,_=photo.project(uv,d,reference,neighbor)
                        W,m=photo.bilinear(images[j],q)
                        warps[(mode,source)]=W
                        masks[(mode,source)]=m&(z>0)
                common=np.logical_and.reduce(list(masks.values()))
                costs={mode:{} for mode in ['raw','plane']}
                for (mode,source),W in warps.items():
                    result,_=photo.score(A,W,common,cfg['epsilon'])
                    costs[mode][source]=result
                row={'fixture':kind,'patch_size':r,'neighbor':j,'baseline':b,
                     'common_count':int(common.sum()),'costs':costs}
                rows.append(row)
                if j==0 and r==33:
                    displays.append((kind,A,warps[('raw','correct')],warps[('raw','offset')]))
        modes={}
        for mode in ['raw','plane']:
            source_stats={}
            for source in ['correct','offset']:
                E=[]; std=[]; eligible=[]
                for r in cfg['patch_sizes']:
                    group=[q for q in rows if q['fixture']==kind and q['patch_size']==r]
                    values=[q['costs'][mode][source]['cost'] for q in group]
                    E.append(float(np.median(values)) if all(v is not None for v in values) else None)
                    std.append(min(q['costs'][mode][source]['std_reference'] for q in group))
                    eligible.append(all(q['common_count']>=np.ceil(r*r*cfg['minimum_common_fraction']) and
                        q['costs'][mode][source]['cost'] is not None and
                        min(q['costs'][mode][source]['std_reference'],q['costs'][mode][source]['std_warp'])>=cfg['minimum_texture_std'] for q in group))
                possible=all(eligible)
                ev=evidence_from_costs([np.nan if e is None else e for e in E],1 if possible else 0)
                source_stats[source]={'median_cost_by_scale':E,'min_reference_std_by_scale':std,
                    'numeric_eligible_by_scale':eligible,'hypothetical_cost_only_evidence':dict(zip(['support','refutation','unknown'],[float(z) for z in ev]))}
            modes[mode]=source_stats
        fixtures.append({'fixture':kind,'modes':modes,'true_center_depth':10.,'offset_center_depth':20.,
            'normals_identical_between_sources':True,'operational_gate':0,
            'interpretation':cfg['expectations'][kind]})
    lookup={q['fixture']:q['modes']['raw'] for q in fixtures}
    for kind in ['textured_plane','affine_brightness']:
        check(kind+'_correct_lower_all_scales',all(a<b for a,b in zip(lookup[kind]['correct']['median_cost_by_scale'],lookup[kind]['offset']['median_cost_by_scale'])))
    check('positive_affine_brightness_invariance',np.allclose(lookup['textured_plane']['correct']['median_cost_by_scale'],lookup['affine_brightness']['correct']['median_cost_by_scale'],atol=1e-12))
    for kind in ['periodic_texture','linear_brightness_ramp']:
        check(kind+'_both_known_different_depths_near_zero_cost',all(abs(z)<1e-10 for s in ['correct','offset'] for z in lookup[kind][s]['median_cost_by_scale']))
        check(kind+'_passes_existing_texture_support_gate',all(z for s in ['correct','offset'] for z in lookup[kind][s]['numeric_eligible_by_scale']))
    check('flat_patch_undefined',all(v is None for v in lookup['flat_texture']['correct']['median_cost_by_scale']))
    check('occluder_cost_worse_than_visible',all(a>b for a,b in zip(lookup['occluding_patch']['correct']['median_cost_by_scale'],lookup['textured_plane']['correct']['median_cost_by_scale'])))
    fig,axes=plt.subplots(len(displays),3,figsize=(8,2.1*len(displays)),constrained_layout=True)
    for axs,(kind,A,P,I) in zip(axes,displays):
        for ax,arr,title in zip(axs,[A,P,I],['Reference','True surface warp','Offset surface warp']):
            ax.imshow(arr,interpolation='nearest',vmin=0,vmax=1);ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,fontsize=9)
        axs[0].set_ylabel(kind,fontsize=8)
    fig.suptitle('Synthetic probes: same cameras / 33 px patches / no real scene accuracy claim')
    fig.savefig(a.output/'synthetic_patches.png',dpi=140);plt.close(fig)
    photo.write(a.output/'results.json',{'scientific_verdict':None,'scope':cfg['scope'],'fixtures':fixtures,'rows':rows,'checks':checks})
    input_paths=[a.config,Path(__file__),Path(photo.__file__),ROOT/'src/phd/local_normal_photometry_v3_7.py',ROOT/'src/phd/local_source_weight_v3_8.py']
    receipt={'task_id':cfg['task_id'],'scientific_verdict':None,
        'status':'PASS_CONTROLLED_DIAGNOSTICS' if all(x['passed'] for x in checks) else 'FAIL_CONTROLLED_DIAGNOSTICS',
        'timestamp_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.time()-started,
        'commit':a.commit,'docker_image':cfg['docker_image'],'python':platform.python_version(),'numpy':np.__version__,
        'resources':cfg['resources'],'real_gt_read':False,'scene_inputs_read':False,'training_executed':False,
        'fixture_count':len(fixtures),'check_count':len(checks),'failed_checks':[c for c in checks if not c['passed']],
        'inputs_sha256':{str(p):photo.sha(p) for p in input_paths},
        'outputs_sha256':{p.name:photo.sha(p) for p in a.output.iterdir() if p.is_file()},
        'limitations':['synthetic geometric mechanism fixtures, not prevalence or scene accuracy',
            'occluding patch is a controlled image replacement, not a complete multi-surface scene',
            'observation gate unimplemented; g=1 values are hypothetical']}
    photo.write(a.output/'receipt.json',receipt)
    print(json.dumps({k:receipt[k] for k in ['status','fixture_count','check_count','failed_checks','elapsed_seconds']}))
    return 0 if not receipt['failed_checks'] else 1


if __name__=='__main__':
    raise SystemExit(main())
