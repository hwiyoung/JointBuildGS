"""Small read-only cKDTree worker/time diagnostic; never changes the C process."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import time
import numpy as np
import scipy
from scipy.spatial import cKDTree
from scripts.phd.p2_ab_v2.sample_build import read,write,record,quantiles,REPO


def run(config_path):
    cfg=read(config_path);root=Path(cfg['artifact_root']);out=root/cfg['output_relative_root'];out.mkdir(parents=True,exist_ok=False)
    rp=root/cfg['reference_relative_path'];pp=root/cfg['prediction_relative_path']
    with np.load(rp) as f:r=f['uas_xyz'].astype(np.float64)
    with np.load(pp) as f:p=f['xyz'].astype(np.float64)
    bounds=np.array(cfg['xy_bounds']);inside=lambda a:((a[:,:2]>=bounds[0])&(a[:,:2]<bounds[1])).all(1)
    all_p_count=len(p);r=r[inside(r)];p=p[inside(p)]
    summary=lambda a:{'count':len(a),'bbox_min':a.min(0).tolist(),'bbox_max':a.max(0).tolist(),
                       'xyz_quantiles':quantiles(a),'finite':bool(np.isfinite(a).all())}
    t=time.perf_counter();tree=cKDTree(r);build_seconds=time.perf_counter()-t
    results=[]
    for name,ix in [('uniform',np.linspace(0,len(p)-1,min(cfg['sample_count'],len(p)),dtype=np.int64)),
                    ('first',np.arange(min(cfg['sample_count'],len(p))))]:
        query=p[ix];baseline=None;timings=[]
        for workers in cfg['worker_order']:
            t=time.perf_counter();d,index=tree.query(query,workers=workers);seconds=time.perf_counter()-t
            if baseline is None:baseline=(d.copy(),index.copy())
            timings.append({'workers':workers,'seconds':seconds,'distance_bitwise_equal':bool(np.array_equal(d,baseline[0])),
                            'index_bitwise_equal':bool(np.array_equal(index,baseline[1]))})
        d=baseline[0]
        result={'sample':name,'count':len(query),'query_xyz':summary(query),'distance_m':quantiles(d),
                'distance_gt_1m':int((d>1).sum()),'distance_gt_10m':int((d>10).sum()),
                'distance_gt_100m':int((d>100).sum()),'timings':timings,
                'workers1_median_seconds':float(np.median([t['seconds'] for t in timings if t['workers']==1])),
                'workers4_median_seconds':float(np.median([t['seconds'] for t in timings if t['workers']==4]))}
        results.append(result);print(__import__('json').dumps(result),flush=True)
        np.savez_compressed(out/f'{name}_1000_query.npz',filtered_prediction_row=ix,xyz=query,distance_m=d,reference_index=baseline[1])
    receipt={'task_id':cfg['task_id'],'scientific_verdict':None,'reference':summary(r),'prediction_fixed_xy':summary(p),
             'all_prediction_point_count':all_p_count,'tree_build_seconds':build_seconds,'queries':results,
             'inputs':[record(rp),record(pp)],'config':record(config_path),'source':record(__file__),
             'git_commit':subprocess.check_output(['git','-c',f'safe.directory={REPO}','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
             'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
             'docker_image_id':cfg['docker_image_id'],'reference_role':cfg['reference_role'],
             'existing_process_or_source_modified':False,
             'limits':['Timing while existing evaluation and other services run; not an isolated benchmark.',
                       'Only fixed 1000-row samples, not the complete evaluation or a geometric correctness test.',
                       'No depth/source correction, GT tuning, trimming, or approximate NN.']}
    write(out/'performance_receipt.json',receipt)
    for f in [Path(__file__),config_path]:shutil.copyfile(f,out/f.name)
    print(__import__('json').dumps({'reference':receipt['reference'],'prediction_fixed_xy':receipt['prediction_fixed_xy'],
                                  'all_prediction_points':all_p_count,'tree_build_seconds':build_seconds}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);run(Path(parser.parse_args().config))
