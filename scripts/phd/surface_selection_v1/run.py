"""Surface segmentation, adjacency, and multiview selection without reference access."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import resource
import time
import traceback
import cv2
import numpy as np

from scripts.phd.surface_selection_v1.common import sha,write,clean,describe,REQUIRED
from scripts.phd.source_candidate_v1.run import require_isolation,native_input
from src.phd.source_candidate_v1.geometry import self_depth_buffer
from src.phd.surface_selection_v1.segmentation import segment_source
from src.phd.surface_selection_v1.units import make_units,unit_candidates


def notify(**value):print(json.dumps(clean(value)),flush=True)


def load_views(region,config,native,with_gray=True):
    meta=json.loads((Path('/inputs')/region/'views.json').read_text())['views'];views=[]
    contexts={s:{} for s in ('mvs','als')}
    for i,v in enumerate(meta):
        R=np.asarray(v['R']);t=np.asarray(v['t'])
        view=dict(id=v['image_id'],name=v['name'],path=v['path'],R=R,t=t,K=np.asarray(v['K']),
                  center=-R.T@t,width=v['width'],height=v['height'],image_url=f"/images/{region}/{v['image_id']}")
        if with_gray:
            gray=cv2.imread(v['path'],cv2.IMREAD_GRAYSCALE)
            if gray is None or gray.shape!=(v['height'],v['width']):raise ValueError('Original image mismatch')
            view['gray']=gray.astype(np.float32)
            for s in contexts:
                contexts[s][view['id']]=self_depth_buffer(native[s+'_xyz'],view,**config['self_visibility'])
        views.append(view)
    return views,contexts


def input_stage(config,out):
    up=np.asarray(json.loads(Path(config['gravity_manifest']).read_text())['gravity']['up']);up=up/np.linalg.norm(up)
    for region,spec in config['regions'].items():
        start=time.monotonic();root=out/region;root.mkdir(exist_ok=False)
        native=native_input(region,spec);components={};memberships={};graphs={}
        for source in ('mvs','als'):
            notify(stage='segment_start',region=region,source=source,points=len(native[source+'_xyz']))
            components[source],memberships[source],graphs[source]=segment_source(native[source+'_xyz'],up,config['segmentation'])
            for c in components[source]:c['source']=source
            notify(stage='segment_complete',region=region,source=source,components=len(components[source]),summary=graphs[source]['summary'])
        units,unit_members,unit_graph=make_units(native,memberships,components,spec['domain'],config['unit_spacing_m'])
        write(root/'components.json',components);write(root/'graphs.json',graphs)
        write(root/'units.json',units);write(root/'unit_graph.json',unit_graph)
        np.savez_compressed(root/'membership.npz',**{s+'_component':memberships[s] for s in memberships},**unit_members)
        rgb=[]
        for v in json.loads((Path('/inputs')/region/'views.json').read_text())['views']:
            if sha(v['path'])!=v['sha256']:raise ValueError('Image provenance changed')
            rgb.append(dict(id=v['image_id'],name=v['name'],sha256=v['sha256'],width=v['width'],height=v['height']))
        write(root/'rgb_ledger.json',rgb)
        summary=dict(region=region,native_counts={s:len(native[s+'_xyz']) for s in memberships},
            components={s:len(components[s]) for s in components},segmentation={s:graphs[s]['summary'] for s in graphs},
            total_units=len(units),unit_status_counts=dict(Counter(u['status'] for u in units)),
            unit_area_m2=describe([u['area_m2'] for u in units]),total_area_m2=sum(u['area_m2'] for u in units),
            gravity_up=up,gravity_manifest_sha256=sha(config['gravity_manifest']),views=len(rgb),
            original_native_sha256=spec['native_sha256'],original_views_sha256=spec['views_sha256'],
            reference_accessed=False,scientific_verdict=None,wall_seconds=time.monotonic()-start)
        write(root/'input_summary.json',summary);notify(stage='input_complete',**summary)


def observation_stage(config,out):
    from src.phd.surface_selection_v1.evidence import evaluate_unit
    for region,spec in config['regions'].items():
        start=time.monotonic();root=out/region;native=native_input(region,spec)
        comps=json.loads((root/'components.json').read_text());units=json.loads((root/'units.json').read_text())
        with np.load(root/'membership.npz',allow_pickle=False) as z:membership={k:z[k] for k in z.files}
        members={s:membership[s+'_component'] for s in ('mvs','als')}
        views,contexts=load_views(region,config,native)
        observations=[];decisions=[]
        for i,unit in enumerate(units):
            candidates=unit_candidates(unit,native,members,membership,comps,contexts)
            observation,decision=evaluate_unit(unit,candidates,views,config['evidence'])
            observations.append(dict(unit_id=unit['id'],observation=observation))
            decisions.append(dict(unit_id=unit['id'],**decision))
            if i%10==0:notify(stage='observation',region=region,units=i+1,total=len(units),
                decisions=dict(Counter(d.get('action') for d in decisions)),wall_seconds=time.monotonic()-start)
        write(root/'observations.json',observations);write(root/'decisions.json',decisions)
        summary=dict(region=region,total_units=len(units),total_area_m2=sum(u['area_m2'] for u in units),
            action_counts=dict(Counter(d['action'] for d in decisions)),
            action_unit_area_m2={a:sum(u['area_m2'] for u,d in zip(units,decisions) if d['action']==a) for a in ('IMAGE','PRIOR','ABSTAIN')},
            reason_counts=dict(Counter(d['reason'] for d in decisions)),
            accepted_units=sum(d['action']!='ABSTAIN' for d in decisions),reference_accessed=False,scientific_verdict=None,
            wall_seconds=time.monotonic()-start)
        write(root/'summary.json',summary);notify(stage='region_complete',**summary)


def seal(config,out):
    hashes={f'{r}/{n}':sha(out/r/n) for r in config['regions'] for n in REQUIRED}
    write(out/'method_seal.json',dict(status='METHOD_FROZEN_BEFORE_REFERENCE_ACCESS',reference_accessed=False,
        scientific_verdict=None,task_id=config['task_id'],config_sha256=sha(out/'config.json'),files=hashes,
        frozen_at=datetime.now(timezone.utc).isoformat(),source_snapshot_sha256=sha('SOURCE_MANIFEST.json'),
        replay_module_sha256={p:sha(p) for p in ('src/phd/surface_selection_v1/evidence.py','src/phd/surface_selection_v1/units.py','src/phd/source_candidate_v1/photometry.py')},
        source_git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'),container_image_id=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
    notify(stage='all_methods_frozen',method_seal_sha256=sha(out/'method_seal.json'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',default='/output/run')
    p.add_argument('--stage',choices=['all','input','observation','seal'],default='all');a=p.parse_args()
    require_isolation();cv2.setNumThreads(1)
    config=json.loads(Path(a.config).read_text());out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    if not (out/'config.json').exists():write(out/'config.json',config)
    elif json.loads((out/'config.json').read_text())!=config:raise ValueError('Frozen config changed')
    try:
        for stage,fn in [('input',input_stage),('observation',observation_stage),('seal',seal)]:
            if a.stage in ('all',stage):fn(config,out)
    except Exception:
        write(out/('failure_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json'),dict(stage=a.stage,error=traceback.format_exc(),scientific_verdict=None))
        raise


if __name__=='__main__':main()
