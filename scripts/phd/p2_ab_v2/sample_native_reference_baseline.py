"""Native-source point baselines under the unchanged evaluation-only NN metric."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import time
import numpy as np
import scipy
from scipy.spatial import cKDTree
from scripts.phd.p2_ab_v2.sample_build import read,write,record,REPO
from src.phd.p2_ab_v1.evaluation import distance_summary


def run(config_path):
    cfg=read(config_path);root=Path(cfg['artifact_root']);out=root/cfg['output_relative_root'];out.mkdir(parents=True,exist_ok=False)
    rp=root/cfg['reference_relative_path'];npth=root/cfg['native_relative_path'];sp=root/cfg['render_sample_relative_path']
    with np.load(rp) as f:r=f['uas_xyz'].astype(np.float64)
    native=np.load(npth);sample=np.load(sp)['xyz'];bounds=np.array(cfg['xy_bounds'])
    inside=lambda p:((p[:,:2]>=bounds[0])&(p[:,:2]<bounds[1])).all(1)
    r=r[inside(r)];tree=cKDTree(r);results=[]
    for source in ['als','mvs']:
        p=native[source+'_xyz'].astype(np.float64);p=p[inside(p)]
        started=time.perf_counter();forward=tree.query(p,workers=cfg['workers'])[0];forward_time=time.perf_counter()-started
        started=time.perf_counter();ptree=cKDTree(p);reverse=ptree.query(r,workers=cfg['workers'])[0];reverse_time=time.perf_counter()-started
        render_to_native=ptree.query(sample,workers=cfg['workers'])[0]
        row={'source':source,'native_points':len(p),'reference_points':len(r),
             'native_to_reference':distance_summary(forward),'reference_to_native':distance_summary(reverse),
             'forward_seconds':forward_time,'reverse_tree_and_query_seconds':reverse_time,
             'uniform_initial_render_sample_to_native':distance_summary(render_to_native),
             'tolerance_sweep':[{'tolerance_m':t,'precision':float((forward<=t).mean()),'recall':float((reverse<=t).mean()),
                                 'native_inlier_count':int((forward<=t).sum()),'reference_recovered_count':int((reverse<=t).sum())}
                                for t in cfg['tolerances_m']]}
        results.append(row);print(__import__('json').dumps(row),flush=True)
        np.savez_compressed(out/f'{source}_distances.npz',native_to_reference=forward,reference_to_native=reverse,
                            uniform_initial_render_sample_to_native=render_to_native)
    write(out/'native_reference_receipt.json',{'task_id':cfg['task_id'],'scientific_verdict':None,'results':results,
          'inputs':[record(p) for p in [rp,npth,sp]],'config':record(config_path),'source':record(__file__),
          'git_commit':subprocess.check_output(['git','-c',f'safe.directory={REPO}','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
          'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
          'docker_image_id':cfg['docker_image_id'],'reference_role':cfg['reference_role'],'existing_process_or_source_modified':False,
          'limits':['Native-source point density and multi-view rendered sample density differ; direct p90 differences do not isolate geometric deformation.',
                    'The preserved numerical frame/datum/epoch and reference uncertainty remain uncalibrated.',
                    'No correspondence tuning, reference-based parameter selection, source correction, trimming or approximate NN.']})
    for f in [Path(__file__),config_path]:shutil.copyfile(f,out/f.name)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);run(Path(parser.parse_args().config))
