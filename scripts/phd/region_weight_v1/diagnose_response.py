"""CPU-only input-fit and trace diagnostic of already completed weight runs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def stats(x):
    x = np.asarray(x, dtype=np.float64)
    return dict(n=x.size, mae_m=float(np.abs(x).mean()), median_abs_m=float(np.median(np.abs(x))),
                p95_abs_m=float(np.quantile(np.abs(x), .95)), signed_mean_m=float(x.mean())) if x.size else dict(n=0)


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--payload', default='/payload')
    ap.add_argument('--out', default='/out')
    args=ap.parse_args()
    cfg=read(args.config); p=Path(args.payload); out=Path(args.out)
    sys.path.insert(0, '/repo/src/phd/geogs_mvs_pgsr_v1')
    from mvs_depth import load_view_depth
    v=p/cfg['viewer_root']; manifest=read(v/cfg['destination']/'manifest.json')
    result=dict(status='PASS_CPU_INPUT_RESPONSE_DIAGNOSTIC', scientific_verdict=None,
                scope='existing final training-view expected-depth fit, not independent accuracy or causal attribution',
                training_changed=False, inputs={}, regions={})

    def bound(path):
        result['inputs'][str(path)]=sha(path)
        return read(path)

    for region in ['P1','P2','P3']:
        run=p/cfg['P1'] if region=='P1' else p/cfg['P2P3']/region
        rcfg=bound(run/'config.json'); rr=dict(views=[], training={})
        bp=p/cfg['mvs_root']/region; binding=bound(bp/'bindings.json')
        assert sha(bp/'bindings.json')==rcfg['binding_sha256']
        masks=None if region=='P1' else bound(run/'mask/manifest.json')
        for a in [0,1,4]:
            model=run/f'train/alpha_{a}/model'
            prefix='p1_weight' if region=='P1' else 'region_weight'
            alg=bound(model/(prefix+('_first_target_algebra.json' if region=='P1' else '_first_algebra.json')))
            assert alg['status']=='PASS' and all(alg['checks'].values())
            cameras=[json.loads(x) for x in (model/(prefix+'_camera_trace.jsonl')).read_text().splitlines()]
            counts=Counter(x['camera'] for x in cameras)
            regions_trace=model/(prefix+('_target_trace.jsonl' if region=='P1' else '_trace.jsonl'))
            rows=[json.loads(x) for x in regions_trace.read_text().splitlines()]
            total=[json.loads(x) for x in (model/'jbgs_trace.jsonl').read_text().splitlines()]
            result['inputs'][str(regions_trace)]=sha(regions_trace)
            result['inputs'][str(model/'jbgs_trace.jsonl')]=sha(model/'jbgs_trace.jsonl')
            result['inputs'][str(model/(prefix+'_camera_trace.jsonl'))]=sha(model/(prefix+'_camera_trace.jsonl'))
            supported={rcfg['target_camera']} if region=='P1' else {m['camera'] for m in masks['views'] if m['r1_pixels']>0}
            rr['training'][str(a)]=dict(iterations=len(cameras), cameras=len(counts), r1_support_cameras=len(supported),
                visits_to_r1_support_cameras=sum(counts[x] for x in supported), camera_visits=dict(counts),
                first_total_trace=total[0], last_total_trace=total[-1],
                first_regional_trace_by_camera={name:next(x for x in rows if x['camera']==name) for name in counts if any(x['camera']==name for x in rows)},
                last_regional_trace_by_camera={name:next(x for x in reversed(rows) if x['camera']==name) for name in counts if any(x['camera']==name for x in rows)})
        display=next(r for r in manifest['regions'] if r['id']==region)
        for view in display['views']:
            if view['split']!='train': continue
            name=view['image_name']; camera=next(x for x in binding['train'] if x['name']==name)
            target,valid,_=load_view_depth(camera,verify_rgb=False,depth_path=bp/camera['local_depth'])
            result['inputs'][str(bp/camera['local_depth'])]=camera['maps']['depth']['sha256']
            if region=='P1':
                mp=run/'mask/r1_mask.npz'
            else:
                row=next(m for m in masks['views'] if m['camera']==Path(name).stem)
                mp=run/'mask'/row['path']; assert sha(mp)==row['sha256']
            result['inputs'][str(mp)]=sha(mp)
            with np.load(mp,allow_pickle=False) as mask:
                labels=mask['region_id'].copy()
            prior_path=p/f'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/{region}/prior/raw_depth/{Path(name).stem}.npy'
            prior=cv2.resize(np.load(prior_path),(camera['width'],camera['height']),interpolation=cv2.INTER_LINEAR)
            result['inputs'][str(prior_path)]=sha(prior_path)
            prior_valid=np.isfinite(prior)&(prior>0)
            predictions={}
            for a in [0,1,4]:
                png=v/view['conditions'][f'alpha_{a}']['rgb']['url'].removeprefix('/data/')
                depth_path=png.parent.parent/'vis'/('depth_'+png.stem+'.tiff')
                assert sha(depth_path)==view['conditions'][f'alpha_{a}']['source_depth_sha256']
                predictions[a]=np.asarray(Image.open(depth_path),dtype=np.float32)
                result['inputs'][str(depth_path)]=sha(depth_path)
            common=valid & np.logical_and.reduce([np.isfinite(x)&(x>0) for x in predictions.values()])
            vr=dict(camera=name, native_valid_rgb_pixels=int(valid.sum()), prior_valid_rgb_pixels=int(prior_valid.sum()),
                    final_common_valid=int(common.sum()), subsets={})
            for key,selected in [('R1',labels==1),('R2_R3',np.isin(labels,[2,3])),('excluded',labels>=4)]:
                s=selected&common; both=s&prior_valid
                vr['subsets'][key]=dict(input_pixel_count=int((selected&valid).sum()),
                    prior_mvs_disagreement=stats(prior[both]-target[both]),
                    fits={str(a):stats(pred[s]-target[s]) for a,pred in predictions.items()},
                    fits_prior={str(a):stats(pred[both]-prior[both]) for a,pred in predictions.items()},
                    depth_change_1_to_4=stats(predictions[4][s]-predictions[1][s]))
            rr['views'].append(vr)
        result['regions'][region]=rr
    result.update(config_sha256=sha(args.config),script_sha256=sha(__file__),
        mvs_helper_sha256=sha('/repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py'),runtime=cfg['runtime_image'],
        python=sys.version,numpy=np.__version__,opencv=cv2.__version__)
    with (out/'response.json').open('x') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    for region,r in result['regions'].items():
        t=r['training']['1']; print(region,'visits',t['visits_to_r1_support_cameras'],'/',t['iterations'],'support cameras',t['r1_support_cameras'],'/',t['cameras'],'protected',t['last_total_trace']['protected'])
        for view in r['views']:
            print(view['camera'],'valid MVS/prior',view['native_valid_rgb_pixels'],view['prior_valid_rgb_pixels'])
            for k,s in view['subsets'].items():
                print(k,'n',s['input_pixel_count'],'prior-MVS',s['prior_mvs_disagreement'].get('mae_m'),
                      'fits', {a:round(x['mae_m'],4) for a,x in s['fits'].items()},'change1to4',s['depth_change_1_to_4'])
                if k=='R1': print('R1 fit to prior',s['fits_prior'])


if __name__=='__main__': main()
