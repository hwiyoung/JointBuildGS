"""Run all three stages without any evaluation reference mounted."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import resource
import time
import traceback

import cv2
import numpy as np

from scripts.phd.source_candidate_v1.common import sha, write, clean, describe
from src.phd.source_candidate_v1.geometry import build_candidates, self_depth_buffer
from src.phd.source_candidate_v1.photometry import score_candidates
from src.phd.source_candidate_v1.decision import decide


def now(): return datetime.now(timezone.utc).isoformat()


def require_isolation():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    for path in ('/reference','/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw',
                 '/artifacts/JointBuildGS/phase-payloads/phd/wu_vallet_regions_v4'):
        if Path(path).exists(): raise RuntimeError('Reference storage must not be mounted during method')


def native_input(region, spec):
    root = Path('/inputs')/region
    for filename,key in [('native.npz','native_sha256'),('views.json','views_sha256')]:
        if sha(root/filename) != spec[key]: raise ValueError(f'{region}/{filename} identity changed')
    with np.load(root/'native.npz', allow_pickle=False) as archive:
        if any('uas' in k.lower() or 'reference' in k.lower() for k in archive.files):
            raise ValueError('Reference array in native source input')
        native = {k:archive[k] for k in archive.files}
    return native


def input_stage(config, output):
    gravity_path = Path(config['gravity_manifest'])
    up = np.asarray(json.loads(gravity_path.read_text())['gravity']['up'])
    up /= np.linalg.norm(up)
    all_summaries = {}
    for region,spec in config['regions'].items():
        start = time.monotonic()
        native = native_input(region,spec)
        rows,membership = build_candidates(native,spec['domain'],up,config['geometry'])
        root = output/region
        root.mkdir(exist_ok=False)
        write(root/'candidates.json',rows)
        np.savez_compressed(root/'membership.npz',**membership)
        views = json.loads((Path('/inputs')/region/'views.json').read_text())['views']
        if len(views) != spec['view_count']: raise ValueError('Regional view membership changed')
        rgb_ledger = []
        for view in views:
            path = Path(view['path'])
            actual = sha(path)
            if actual != view['sha256']: raise ValueError(f'RGB changed: {path}')
            rgb_ledger.append(dict(image_id=view['image_id'],name=view['name'],sha256=actual,
                                   width=view['width'],height=view['height']))
        write(root/'rgb_ledger.json',rgb_ledger)
        summary = dict(region=region,total_cells=len(rows),total_area_m2=sum(r['area_m2'] for r in rows),
            native_counts={s:len(native[s+'_xyz']) for s in ('mvs','als')},
            availability=dict(Counter(r['availability'] for r in rows)),
            both_valid_cells=sum(r['both_valid'] for r in rows),
            validity={s:dict(Counter(r['candidates'][s]['reason'] for r in rows)) for s in ('mvs','als')},
            native_inlier_counts={s:int(membership[s+'_inlier'].sum()) for s in ('mvs','als')},
            candidate_plane_rms_m={s:describe([r['candidates'][s]['rms_m'] for r in rows if r['candidates'][s]['valid']]) for s in ('mvs','als')},
            absolute_source_height_difference_m=describe([abs(r['height_difference_m']) for r in rows if r['height_difference_m'] is not None]),
            large_difference_cells_gt1m=sum(abs(r['height_difference_m'])>1 for r in rows if r['height_difference_m'] is not None),
            views=len(views),gravity_manifest_sha256=sha(gravity_path),gravity_up=up,
            native_sha256=spec['native_sha256'],views_sha256=spec['views_sha256'],
            reference_accessed=False,scientific_verdict=None,wall_seconds=time.monotonic()-start)
        write(root/'input_summary.json',summary)
        all_summaries[region]=summary
        print(json.dumps(clean(dict(stage='candidate_input_complete',**summary))),flush=True)
    write(output/'input_summary.json',all_summaries)


def observation_stage(config, output):
    for region,spec in config['regions'].items():
        start=time.monotonic()
        native=native_input(region,spec)
        root=output/region
        rows=json.loads((root/'candidates.json').read_text())
        with np.load(root/'membership.npz',allow_pickle=False) as a: membership={k:a[k] for k in a.files}
        metadata=json.loads((Path('/inputs')/region/'views.json').read_text())['views']
        views=[]
        contexts={s:{} for s in ('mvs','als')}
        for vi,value in enumerate(metadata):
            gray=cv2.imread(value['path'],cv2.IMREAD_GRAYSCALE)
            if gray is None or gray.shape != (value['height'],value['width']): raise ValueError('RGB dimensions mismatch')
            R=np.asarray(value['R'],float);t=np.asarray(value['t'],float)
            view=dict(id=value['image_id'],name=value['name'],path=value['path'],R=R,t=t,K=np.asarray(value['K'],float),
                      center=-R.T@t,width=value['width'],height=value['height'],gray=gray.astype(np.float32))
            views.append(view)
            for source in ('mvs','als'):
                contexts[source][view['id']]=self_depth_buffer(native[source+'_xyz'],view,
                    config['self_visibility']['downsample'],config['self_visibility']['splat_radius'])
            if vi%25==0: print(json.dumps(dict(stage='load_views_self_visibility',region=region,views=vi+1,total=len(metadata))),flush=True)
        records=[]
        for i,row in enumerate(rows):
            candidates={}
            for source in ('mvs','als'):
                c=dict(row['candidates'][source])
                mask=(membership[source+'_cell']==row['cell_id'])&membership[source+'_inlier']
                c.update(support_points=native[source+'_xyz'][mask],context_depths=contexts[source])
                candidates[source]=c
            observation=score_candidates(candidates,views,config['photometry'])
            records.append(dict(cell_id=row['cell_id'],observation=observation))
            if i%25==0:
                print(json.dumps(dict(stage='observation_evaluation',region=region,cells=i+1,total=len(rows),
                    measured=sum(r['observation']['shared']['common_scored_pair_count']>0 for r in records))),flush=True)
        write(root/'observations.json',records)
        summary=dict(region=region,cells=len(rows),status_counts=dict(Counter(r['observation']['status'] for r in records)),
            shared_scored_pairs=describe([r['observation']['shared']['common_scored_pair_count'] for r in records]),
            cells_with_common_scores=sum(r['observation']['shared']['common_scored_pair_count']>0 for r in records),
            cells_with_disjoint_groups=sum(r['observation']['shared']['disjoint_pair_count']>=2 for r in records),
            median_ncc={s:describe([r['observation']['candidates'][s]['median_ncc'] for r in records if r['observation']['candidates'][s]['median_ncc'] is not None]) for s in ('mvs','als')},
            source_model_visibility_fraction=describe([r['observation']['shared']['common_visibility_verified_fraction'] for r in records if r['observation']['shared']['common_scored_pair_count']>0]),
            reference_accessed=False,scientific_verdict=None,wall_seconds=time.monotonic()-start)
        write(root/'observation_summary.json',summary)
        print(json.dumps(clean(dict(stage='observation_complete',**summary))),flush=True)


def decision_stage(config, output):
    from itertools import product
    summaries={};sensitivity=[]
    for region in config['regions']:
        root=output/region
        candidates=json.loads((root/'candidates.json').read_text())
        observations=json.loads((root/'observations.json').read_text())
        decisions=[]
        for row,item in zip(candidates,observations,strict=True):
            if row['cell_id']!=item['cell_id']: raise ValueError('Cell identity mismatch')
            decisions.append(dict(cell_id=row['cell_id'],**decide(item['observation'],row['candidates'],config['decision'])))
        write(root/'decisions.json',decisions)
        counts=dict(Counter(d['action'] for d in decisions))
        summary=dict(region=region,total_cells=len(decisions),action_counts=counts,
                     reason_counts=dict(Counter(d['reason'] for d in decisions)),
                     accepted_cells=sum(d['accepted'] for d in decisions),
                     coverage_fraction=sum(d['accepted'] for d in decisions)/len(decisions),
                     reference_accessed=False,scientific_verdict=None,
                     observation_sha256=sha(root/'observations.json'))
        write(root/'decision_summary.json',summary);summaries[region]=summary
        for max_cost,margin,support in product(*[config['sensitivity'][k] for k in ('max_cost','margin','min_support_fraction')]):
            settings=dict(config['decision'],max_cost=max_cost,margin=margin,min_support_fraction=support)
            result=[dict(cell_id=r['cell_id'],**decide(o['observation'],r['candidates'],settings)) for r,o in zip(candidates,observations,strict=True)]
            sensitivity.append(dict(region=region,max_cost=max_cost,margin=margin,min_support_fraction=support,
                action_counts=dict(Counter(d['action'] for d in result)),
                accepted_cells=sum(d['accepted'] for d in result),
                actions=[d['action'] for d in result]))
        print(json.dumps(dict(stage='source_decision_complete',**summary)),flush=True)
    write(output/'decision_summary.json',summaries)
    write(output/'sensitivity.json',sensitivity)


def seal(config,output):
    hashes={}
    for region in config['regions']:
        for name in ('candidates.json','membership.npz','observations.json','decisions.json','input_summary.json','observation_summary.json','decision_summary.json','rgb_ledger.json'):
            p=output/region/name
            hashes[f'{region}/{name}']=sha(p)
    hashes['sensitivity.json']=sha(output/'sensitivity.json')
    write(output/'method_seal.json',dict(status='METHOD_FROZEN_BEFORE_REFERENCE_ACCESS',task_id=config['task_id'],
        frozen_at=now(),files=hashes,config_sha256=sha(output/'config.json'),scientific_verdict=None,
        reference_accessed=False,source_snapshot_sha256=sha(Path('/workspace/JointBuildGS/SOURCE_MANIFEST.json')),
        source_git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'),container_image_id=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',default='/output/run')
    parser.add_argument('--stage',choices=['all','input','observation','decision','seal'],default='all');args=parser.parse_args()
    require_isolation();cv2.setNumThreads(1)
    config=json.loads(Path(args.config).read_text());output=Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    if not (output/'config.json').exists(): write(output/'config.json',config)
    elif json.loads((output/'config.json').read_text()) != config: raise ValueError('Run config changed')
    try:
        for name,fn in [('input',input_stage),('observation',observation_stage),('decision',decision_stage),('seal',seal)]:
            if args.stage in ('all',name): fn(config,output)
    except Exception:
        p=output/('failure_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
        write(p,dict(stage=args.stage,exception=traceback.format_exc(),scientific_verdict=None))
        raise


if __name__=='__main__':main()
