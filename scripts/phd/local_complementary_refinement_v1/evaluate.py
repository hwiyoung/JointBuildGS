"""Additive CPU evaluation of sealed local-refinement outputs.

Only /task/evaluation is writable. /parent and /references are evaluation-only
inputs. Existing geometry functions, original reference IDs, frozen RGB splits,
and raw/post512 surfaces are retained. No fitting or parameter selection occurs.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time

import numpy as np
from PIL import Image

from evaluation_utils import (evaluation_cohorts, paired_rows, psnr_uint8,
    read_json, require_membership, safe_child, self_test, sha, spatial_rows,
    validate_distances, write_csv, write_json)

REFERENCE_SHAS = {
    'P1':'3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2':'9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3':'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81'}
PARENT_SEAL_SHA='8fc78431dcdfc1bf803c0ac2db4a5bb2cad75c1c163ce2519b571d3710cd011d'
GEOMETRY_DIR=Path(__file__).resolve().parents[1]/'geogs_p1p2p3_v1/evaluation'
BASELINE_CONDITIONS=('D005_Pnative','D0005_Pnative','D0_Pnative',
                     'D005_Prelease','D0005_Prelease','D0_Prelease')


def load_module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Evidence:
    def __init__(self): self.files={}

    def bind(self,path,expected=None):
        path=Path(path)
        if not path.is_file(): raise FileNotFoundError(path)
        key=str(path.resolve())
        if key not in self.files:
            self.files[key]={'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
        record=self.files[key]
        if expected is not None and record['sha256']!=expected:
            raise ValueError('Source digest differs: '+str(path))
        return record


def receipt_digest(receipt,key):
    return receipt.get(key+'_sha256') or receipt.get(key,{}).get('sha256')


def output_digest(receipt,relative):
    found=set()
    for item in receipt.get('outputs',[])+receipt.get('validation',[]):
        if not isinstance(item,dict) or 'path' not in item or 'sha256' not in item: continue
        name=item['path']
        if name.startswith('/output/'): name=name[len('/output/'):]
        if name==relative: found.add(item['sha256'])
    if len(found)!=1: raise ValueError('Expected exactly one producer digest for '+relative)
    return next(iter(found))


def verify_run(task,parent,config_path,cfg,region,condition,evidence):
    run=safe_child(task,Path('runs')/region/condition['id'])
    input_path=parent/'inputs'/region/'input_manifest.json'
    input_sha=evidence.bind(input_path)['sha256']
    receipts={}
    for phase in ('train','render','metrics'):
        path=run/f'{phase}_receipt.json'
        evidence.bind(path)
        receipt=read_json(path)
        expected={'status':'PASS','region':region,'condition':condition['id'],'phase':phase,
                  'task_id':cfg['task_id'],'scientific_verdict':None,'input_manifest_sha256':input_sha}
        if any(receipt.get(k)!=v for k,v in expected.items()):
            raise ValueError('Incomplete or differently bound phase: '+str(path))
        if receipt_digest(receipt,'config')!=evidence.bind(config_path)['sha256']:
            raise ValueError('Phase config differs: '+str(path))
        if receipt.get('runtime_image_id')!=cfg['runtime']['image_id']:
            raise ValueError('Runtime image differs')
        receipts[phase]=receipt
    if (receipts['train'].get('training_start_iteration')!=8000 or
            receipts['train'].get('training_end_iteration')!=30000 or receipts['render'].get('mesh_res')!=512):
        raise ValueError('Expected same Anchor8k to final30k with TSDF512')
    if receipts['train']['parent_condition']!=condition['parent_condition']:
        raise ValueError('Parent condition differs')
    cloud='model/point_cloud/iteration_30000/point_cloud.ply'
    if receipts['render']['render_source_ply']['sha256']!=output_digest(receipts['train'],cloud):
        raise ValueError('Renderer consumed a different final training PLY')
    # No model checkpoint is loaded. Input binding and restore receipt establish
    # which existing Anchor produced this completed training.
    restore_path=run/'model/jbgs_restore.json'
    evidence.bind(restore_path)
    restore=read_json(restore_path)
    if (restore['iteration']!=8000 or restore['checkpoint_sha256']!=receipts['train']['anchor']['sha256']
            or restore['release']!=(condition['protection']=='release')):
        raise ValueError('Restore or structural-protection identity differs')
    for phase,paths in {
        'render':['model/train/ours_30000/fuse.ply','model/train/ours_30000/fuse_post.ply'],
        'metrics':['model/results.json','model/per_view.json']}.items():
        for relative in paths:
            evidence.bind(safe_child(run,relative),output_digest(receipts[phase],relative))
    return run,receipts


def load_split(parent,region,evidence):
    root=parent/'inputs'/region
    manifest=read_json(root/'input_manifest.json')
    if manifest['status']!='INPUTS_SEALED_FOR_EXECUTION' or manifest['region']!=region:
        raise ValueError('Parent input seal differs')
    records={r['path']:r for r in manifest['files']}
    if len(records)!=len(manifest['files']): raise ValueError('Duplicate input records')
    split_path=safe_child(root,manifest['split_path'])
    evidence.bind(split_path,manifest['split_sha256'])
    split=read_json(split_path)
    names=[r['name'] for role in ('train','evaluation') for r in split[role]]
    if len(set(names))!=len(names): raise ValueError('Train/test overlap or duplicate image names')
    for relative,row in records.items():
        parts=Path(relative).parts
        if len(parts)>=3 and parts[0]=='scene' and parts[1].startswith('sparse'):
            evidence.bind(safe_child(root,relative),row['sha256'])
    calibration='scene/jbgs_calibration.json'
    if calibration in records: evidence.bind(root/calibration,records[calibration]['sha256'])
    evaluation=sorted(split['evaluation'],key=lambda row:Path(row['name']).stem)
    if evaluation!=sorted(split['evaluation'],key=lambda row:row['name']):
        raise ValueError('Stem and full-name camera orders differ; explicit adapter needed')
    for row in evaluation:
        evidence.bind(safe_child(root/'scene/images',row['name']),row['sha256'])
    return split,evaluation


def source_expected(spatial_receipt,relative):
    matches=[r['sha256'] for p,r in spatial_receipt['sources'].items()
             if p.endswith('/'+relative)]
    if len(matches)!=1: raise ValueError('Expected unique spatial-diagnostic source: '+relative)
    return matches[0]


def load_baseline(parent,region,name,paired,spatial_receipt,seal,evidence,geometry):
    base=Path('evaluation/geometry')/region/name/'sample0.1_reference0.1'
    paths={suffix:parent/Path(str(base)+suffix) for suffix in ('.json','.npz')}
    for suffix,path in paths.items():
        expected=source_expected(spatial_receipt,str(base)+suffix) if name.endswith('.raw') else None
        evidence.bind(path,expected)
    metrics=read_json(paths['.json'])
    if (metrics['seed']!=0 or metrics['surface_sample_spacing_m']!=.1 or
        metrics['reference_voxel_size_m']!=.1 or metrics['mesh_res']!=512 or
        metrics['reference_sha256']!=REFERENCE_SHAS[region] or metrics['candidate_seal_sha256']!=PARENT_SEAL_SHA):
        raise ValueError('Baseline evaluation contract differs: '+name)
    matched=[c for c in seal['candidates'] if c['region']==region and
        f"{c['condition']}.{c['variant']}.{c['mesh_kind']}"==name]
    if len(matched)!=1 or matched[0]['surface']['sha256']!=metrics['source_sha256']:
        raise ValueError('Baseline surface identity differs from original candidate seal')
    with np.load(paths['.npz'],allow_pickle=False) as arrays:
        require_membership(arrays['reference_points'],arrays['reference_original_indices'],
                           paired['reference_points'],paired['reference_original_indices'])
        d=validate_distances(arrays['reference_to_triangle_distance'],len(paired['reference_points']))
        p=arrays['prediction_to_reference_distance']
        for row in metrics['thresholds']:
            precision=float(np.mean(p<row['threshold_m'])) if len(p) else 0.
            recall=float(np.mean(d<row['threshold_m'])) if len(d) else None
            if (row['precision'] is not None and not np.isclose(row['precision'],precision,rtol=0,atol=1e-12)
                    or row['recall'] is not None and not np.isclose(row['recall'],recall,rtol=0,atol=1e-12)):
                raise ValueError('Cached metrics and exact distance arrays disagree')
    metrics=dict(metrics,cache_verification='spatial_receipt_sha_and_membership' if name.endswith('.raw')
                 else 'current_digest_membership_metric_consistency_and_source_seal_metadata; no historical post-cache digest')
    return metrics,d


def metric_rows(region,candidate,kind,role,metrics):
    p,r=metrics['prediction_to_reference_point'],metrics['reference_to_prediction_triangle']
    base=dict(region=region,candidate=candidate,mesh_kind=kind,role=role,status=metrics['status'],
              mesh_res=512,surface_area_m2=metrics['surface_area_m2'],surface_samples=metrics['surface_samples'],
              reference_count=metrics['reference_points_after_voxel'])
    for label,values in [('accuracy_prediction_to_observed_reference',p),('completeness_reference_to_surface',r)]:
        base.update({label+'_'+key+'_m':value for key,value in values.items()})
    base.update({'xy_'+k:v for k,v in metrics['xy_support'].items() if not isinstance(v,(list,dict))})
    return [dict(base,**{k:row[k] for k in ('threshold_m','precision','recall','f1')}) for row in metrics['thresholds']]


def appearance_rows(parent,region,condition,run,receipts,evaluation,bounds,evidence,render_quality,output):
    """Reuse official full-frame SSIM/LPIPS; independently verify image identity.

    CPU float64 PSNR is reported separately for full frame and fixed-prism bbox.
    ROI SSIM/LPIPS are explicitly unmeasured, never copied from full-frame scores.
    """
    per_path=run/'model/per_view.json'; results_path=run/'model/results.json'
    per=read_json(per_path)['ours_30000']; means=read_json(results_path)['ours_30000']
    keys={f'{i:05d}.png' for i in range(len(evaluation))}
    for metric in ('PSNR','SSIM','LPIPS'):
        if set(per[metric])!=keys or not all(np.isfinite(v) for v in per[metric].values()):
            raise ValueError('Official per-view metric membership/nonfinite value differs')
        if not np.isclose(np.mean(list(per[metric].values())),means[metric],rtol=1e-5,atol=1e-5):
            raise ValueError('Official mean and per-view metrics disagree')
    renders=run/'model/test/ours_30000/renders'; saved_gt=run/'model/test/ours_30000/gt'
    if {p.name for p in renders.glob('*.png')}!=keys or {p.name for p in saved_gt.glob('*.png')}!=keys:
        raise ValueError('Rendered/evaluation PNG membership differs')
    rows=[]; mapping=[]
    parent_csv=parent/'evaluation/renders'/region/condition['parent_condition']/'final/per_image_metrics.csv'
    import csv
    evidence.bind(parent_csv)
    with parent_csv.open(newline='') as stream:
        old={(r['name'],r['domain']):r for r in csv.DictReader(stream)}
    for index,view in enumerate(evaluation):
        filename=f'{index:05d}.png'
        render_path,gt_path=renders/filename,saved_gt/filename
        rp=evidence.bind(render_path); gp=evidence.bind(gt_path)
        photo_path=parent/'inputs'/region/'scene/images'/view['name']
        photo=render_quality.read_rgb(photo_path); actual_gt=render_quality.read_rgb(gt_path)
        expected_gt=((photo.astype(np.float32)/255.)*255.).astype(np.uint8)
        if not np.array_equal(actual_gt,expected_gt):
            raise ValueError('Exported GT pixels do not establish frozen image order: '+filename)
        image=render_quality.read_rgb(render_path)
        if image.shape!=photo.shape or image.shape!=(view['height'],view['width'],3):
            raise ValueError('Native image shape differs from frozen calibration')
        mapping.append(dict(name=view['name'],evaluation_index=index,image_id=view['image_id'],camera_id=view['camera_id'],
            render_path=str(render_path.relative_to(run)),render_sha256=rp['sha256'],exported_gt_sha256=gp['sha256'],
            pose_binding='frozen calibration, native shuffle=False sorted stem order, exact exported GT pixel check'))
        bbox=render_quality.projected_prism_bbox(bounds,view['R'],view['t'],view['K'],view['width'],view['height'])
        for domain,box in [('full_frame',[0,0,view['width'],view['height']]),('fixed_prism_projected_bbox',bbox)]:
            row=dict(region=region,candidate=condition['id'],parent_condition=condition['parent_condition'],
                name=view['name'],evaluation_index=index,camera_id=view['camera_id'],domain=domain,
                status='ASSESSED' if box else 'PRISM_NOT_IN_CAMERA_DOMAIN',pixel_count=0,
                psnr_cpu_float64_db=None,psnr_positive_infinity=False,ssim_native=None,lpips_vgg_native_01=None,
                psnr_native_db=per['PSNR'][filename] if domain=='full_frame' else None,
                roi_ssim_lpips_status='NOT_COMPUTED_CPU_EVALUATION' if domain!='full_frame' else 'OFFICIAL_METRICS_REUSED')
            if box:
                x0,y0,x1,y1=box
                value,infinite=psnr_uint8(photo[y0:y1,x0:x1],image[y0:y1,x0:x1])
                row.update(psnr_cpu_float64_db=value,psnr_positive_infinity=infinite,pixel_count=(x1-x0)*(y1-y0),
                           roi_x0=x0,roi_y0=y0,roi_x1=x1,roi_y1=y1)
                if domain=='full_frame':
                    row.update(ssim_native=per['SSIM'][filename],lpips_vgg_native_01=per['LPIPS'][filename])
                    if not infinite and abs(value-per['PSNR'][filename])>1e-3:
                        raise ValueError('Native PSNR differs from independently matched RGB pixels')
            previous=old.get((view['name'],domain))
            if previous is None or int(previous['camera_id'])!=view['camera_id']:
                raise ValueError('Parent appearance camera membership differs')
            for metric in ('psnr_native_db','ssim_native','lpips_vgg_native_01'):
                value=float(previous[metric]) if previous.get(metric) not in ('',None) else None
                row['parent_'+metric]=value
                new=row[metric] if metric!='psnr_native_db' or domain=='full_frame' else row['psnr_cpu_float64_db']
                row['delta_'+metric]=new-value if new is not None and value is not None else None
            rows.append(row)
    write_json(output/'render_identity.json',dict(region=region,candidate=condition['id'],records=mapping,
               scientific_verdict=None,input_manifest_sha256=receipts['render']['input_manifest_sha256']))
    return rows


def compute_row(region,condition,run,receipts,parent,evidence):
    result=dict(region=region,candidate=condition['id'],parent_condition=condition['parent_condition'],
                start_iteration=8000,end_iteration=30000,new_iterations=22000,
                iteration_budget_is_not_equal_wall_time_or_primitive_compute=True)
    for phase,receipt in receipts.items():
        result[phase+'_driver_wall_seconds']=receipt['wall_seconds']
        result[phase+'_child_peak_rss_bytes']=receipt.get('child_peak_rss_bytes')
    trace_path=run/'model/jbgs_trace.jsonl'
    if trace_path.exists():
        evidence.bind(trace_path)
        trace=[json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        result['native_trace_rows']=len(trace)
        if trace:
            result.update(final_gaussians=trace[-1].get('gaussians'),final_protected=trace[-1].get('protected'),
                recorded_da_weight_min=min(float(r['da_weight']) for r in trace),
                recorded_da_weight_max=max(float(r['da_weight']) for r in trace))
            for key in ('peak_cuda_allocated_bytes','peak_cuda_reserved_bytes'):
                values=[r[key] for r in trace if key in r]
                result[key]=max(values) if values else None
    local=run/'model/local_trace.jsonl'
    if local.exists():
        evidence.bind(local)
        trace=[json.loads(line) for line in local.read_text().splitlines() if line.strip()]
        result['local_trace_rows']=len(trace)
    for phase in ('train','render','metrics'):
        path=parent/'runs_allocator_v2'/region/condition['parent_condition']/f'{phase}_receipt.json'
        evidence.bind(path)
        receipt=read_json(path)
        result['parent_'+phase+'_driver_wall_seconds']=receipt.get('wall_seconds')
        if phase=='train':result['parent_training_start_iteration']=receipt.get('training_start_iteration')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',type=Path,default=Path('/task'))
    parser.add_argument('--parent',type=Path,default=Path('/parent'))
    parser.add_argument('--config',type=Path,default=Path('/config.json'))
    parser.add_argument('--reference-root',type=Path,default=Path('/references'))
    parser.add_argument('--region',choices=('P1','P2','P3'),action='append')
    parser.add_argument('--allow-partial',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if not Path('/.dockerenv').is_file():raise RuntimeError('Docker is required')
    geometry=load_module('lc_existing_geometry',GEOMETRY_DIR/'geometry.py')
    if args.self_test:
        result=self_test()
        vertices=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        metrics,arrays=geometry.evaluate_geometry(vertices,np.array([[0,1,2]]),np.array([[.2,.2,.1]]),
            [[-1,2],[-1,2],[-1,2]],spacing=.25,reference_voxel_size=.1)
        assert np.isclose(arrays['reference_to_triangle_distance'][0],.1,atol=1e-6)
        empty,_=geometry.evaluate_geometry(np.empty((0,3)),np.empty((0,3),int),np.array([[.2,.2,.1]]),
            [[-1,2],[-1,2],[-1,2]],spacing=.25,reference_voxel_size=.1)
        assert empty['status']=='RECONSTRUCTION_FAILURE' and all(r['f1']==0 for r in empty['thresholds'])
        result['geometry_triangle_distance_and_empty_surface']='PASS'
        print(json.dumps(result));return
    task,parent=args.task.resolve(),args.parent.resolve()
    if task==parent or task.is_relative_to(parent) or parent.is_relative_to(task):
        raise ValueError('New and parent task roots must be disjoint')
    cfg=read_json(args.config)
    if cfg.get('scientific_verdict') is not None or cfg['evaluation']['reference_for_training_or_parameter_selection']:
        raise ValueError('Evaluation-only references and null scientific verdict required')
    selected=list(dict.fromkeys(args.region or cfg['regions']))
    if not set(selected)<=set(cfg['regions']):raise ValueError('Unknown selected region')
    evidence=Evidence();evidence.bind(args.config)
    for path in (Path(__file__),Path(__file__).with_name('evaluation_utils.py'),GEOMETRY_DIR/'geometry.py',GEOMETRY_DIR/'render_quality.py'):
        evidence.bind(path)
    seal_path=parent/'contracts/candidates_sealed_v1.json'
    evidence.bind(seal_path,PARENT_SEAL_SHA);seal=read_json(seal_path)
    spatial_path=parent/'evaluation/da3_refinement_spatial_v1/receipt.json'
    evidence.bind(spatial_path);spatial_receipt=read_json(spatial_path)
    jobs=[];missing=[]
    for region in selected:
        for condition in cfg['conditions']:
            run=task/'runs'/region/condition['id']
            if not all((run/f'{phase}_receipt.json').is_file() for phase in ('train','render','metrics')):
                missing.append(dict(region=region,condition=condition['id'],status='PENDING_OR_MISSING_PHASE'));continue
            run,receipts=verify_run(task,parent,args.config,cfg,region,condition,evidence)
            jobs.append((region,condition,run,receipts))
    if missing and not args.allow_partial:
        raise ValueError('All requested runs must be complete before reference evaluation: '+str(missing))
    if not jobs:raise ValueError('No complete runs to evaluate')
    output=safe_child(task,Path('evaluation')/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')))
    output.mkdir(parents=True,exist_ok=False)
    started=time.time();all_metrics=[];all_pairs=[];all_cells=[];all_appearance=[];all_compute=[]
    write_json(output/'config_snapshot.json',cfg)
    render_quality=load_module('lc_existing_render_quality',GEOMETRY_DIR/'render_quality.py')
    try:
        for region in selected:
            region_jobs=[j for j in jobs if j[0]==region]
            if not region_jobs:continue
            paired_path=parent/'evaluation/da3_refinement_spatial_v1'/f'{region}.paired.npz'
            evidence.bind(paired_path,spatial_receipt['outputs'][paired_path.name]['sha256'])
            with np.load(paired_path,allow_pickle=False) as loaded:
                wanted=('reference_points','reference_original_indices','reference_to_anchor_distance',
                    'strict_target_world_z_error_median','strict_view_count','strict_view_range',
                    'xy_cell_index','xy_cell_centres')
                paired={k:loaded[k] for k in wanted}
            ids,points=paired['reference_original_indices'],paired['reference_points']
            reference_path=args.reference_root/region/'reference.npz'
            evidence.bind(reference_path,REFERENCE_SHAS[region])
            with np.load(reference_path,allow_pickle=False) as data:reference=data['uas_xyz']
            if np.any(ids<0) or np.any(ids>=len(reference)) or not np.array_equal(reference[ids],points):
                raise ValueError('Paired IDs do not address the pinned original UAS array')
            split,evaluation=load_split(parent,region,evidence)
            baselines={};baseline_metrics={}
            for kind in ('raw','post'):
                for condition in ('ANCHOR',*BASELINE_CONDITIONS):
                    name=('D005_Pnative.anchor_512.' if condition=='ANCHOR' else condition+'.mesh_512.')+kind
                    metrics,distances=load_baseline(parent,region,name,paired,spatial_receipt,seal,evidence,geometry)
                    baselines[kind,condition]=distances;baseline_metrics[kind,condition]=metrics
                    all_metrics.extend(metric_rows(region,condition,kind,'parent_anchor' if condition=='ANCHOR' else 'parent_final',metrics))
            if not np.array_equal(baselines['raw','ANCHOR'],paired['reference_to_anchor_distance']):
                raise ValueError('Spatial diagnostic and Anchor raw512 distances differ')
            anchor_metrics=baseline_metrics['raw','ANCHOR'];bounds=anchor_metrics['bounds_half_open']
            # Prior proximity is an evaluation stratum, distinct from Anchor proximity.
            prior_npz=parent/'evaluation/geometry'/region/'prior_mesh/sample0.1_reference0.1.npz'
            evidence.bind(prior_npz)
            with np.load(prior_npz,allow_pickle=False) as old:
                require_membership(old['reference_points'],old['reference_original_indices'],points,ids)
                prior_distance=old['reference_to_triangle_distance']
            cohorts=evaluation_cohorts(paired,baselines['raw','ANCHOR'],prior_distance)
            new_distances={}
            for _,condition,run,receipts in region_jobs:
                case=output/region/condition['id'];case.mkdir(parents=True)
                for kind,filename in [('raw','fuse.ply'),('post','fuse_post.ply')]:
                    t0=time.time();mesh_path=run/'model/train/ours_30000'/filename
                    import open3d as o3d
                    mesh=o3d.io.read_triangle_mesh(str(mesh_path))
                    metrics,arrays=geometry.evaluate_geometry(np.asarray(mesh.vertices),np.asarray(mesh.triangles),reference,
                        bounds,spacing=.1,reference_voxel_size=.1,seed=0,
                        thresholds=[r['threshold_m'] for r in anchor_metrics['thresholds']],
                        voxel_origin=anchor_metrics['reference_voxel_origin'],xy_cell_size=anchor_metrics['xy_support']['cell_size_m'])
                    require_membership(arrays['reference_points'],arrays['reference_original_indices'],points,ids)
                    distances=arrays['reference_to_triangle_distance']
                    new_distances[condition['id'],kind]=distances.copy()
                    metrics.update(region=region,candidate=condition['id'],mesh_kind=kind,mesh_res=512,iteration=30000,
                        reference_sha256=REFERENCE_SHAS[region],source_sha256=evidence.bind(mesh_path)['sha256'],
                        crs=anchor_metrics['crs'],wall_seconds=time.time()-t0,scientific_verdict=None)
                    write_json(case/f'{kind}_metrics.json',metrics)
                    geometry.save_distance_arrays(case/f'{kind}_distances.npz',arrays)
                    all_metrics.extend(metric_rows(region,condition['id'],kind,'new_final',metrics))
                    for comparator in ('ANCHOR',*BASELINE_CONDITIONS):
                        before=baselines[kind,comparator]
                        all_pairs.extend(paired_rows(region,condition['id'],comparator,kind,before,distances,cohorts,
                                                    [r['threshold_m'] for r in anchor_metrics['thresholds']]))
                        if comparator in ('ANCHOR',condition['parent_condition']):
                            all_cells.extend(spatial_rows(region,condition['id'],comparator,kind,paired,before,distances))
                    del arrays,mesh
                all_appearance.extend(appearance_rows(parent,region,condition,run,receipts,evaluation,bounds,evidence,render_quality,case))
                all_compute.append(compute_row(region,condition,run,receipts,parent,evidence))
                print(json.dumps({'region':region,'condition':condition['id'],'status':'EVALUATED','scientific_verdict':None}),flush=True)
            # The new native/release pair is an independent protection contrast,
            # in addition to each method's comparison with its historical arm.
            for native in cfg['conditions']:
                if native['protection']!='native':continue
                releases=[c for c in cfg['conditions'] if c['protection']=='release' and c['lambda_p']==native['lambda_p']]
                if len(releases)!=1:raise ValueError('Expected one release counterpart per coefficient')
                release=releases[0]
                for kind in ('raw','post'):
                    if (native['id'],kind) not in new_distances or (release['id'],kind) not in new_distances:continue
                    before,after=new_distances[native['id'],kind],new_distances[release['id'],kind]
                    all_pairs.extend(paired_rows(region,release['id'],native['id'],kind,before,after,cohorts,
                                                [r['threshold_m'] for r in anchor_metrics['thresholds']]))
                    all_cells.extend(spatial_rows(region,release['id'],native['id'],kind,paired,before,after))
            del reference,baselines,paired,new_distances
        for name,rows in [('geometry_metrics',all_metrics),('paired_transitions',all_pairs),('same_cell_changes',all_cells),
                          ('appearance_per_image',all_appearance),('compute',all_compute)]:write_csv(output/(name+'.csv'),rows)
        complete=len(jobs)==len(cfg['regions'])*len(cfg['conditions']) and not missing
        receipt=dict(schema='jbgs.local_complementary_evaluation.v1',status='COMPLETE_DEVELOPMENT_EVALUATION' if complete else 'PARTIAL_DEVELOPMENT_EVALUATION',
            scientific_verdict=None,task_id=cfg['task_id'],run_count=len(jobs),expected_full_run_count=len(cfg['regions'])*len(cfg['conditions']),
            selected_regions=selected,missing=missing,wall_seconds=time.time()-started,
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            reference_used_for_training_or_parameter_selection=False,versions={'python':platform.python_version(),'numpy':np.__version__},
            inputs=list(evidence.files.values()),limitations=[
                'Development cases only; no scientific verdict or population inference.',
                'Correction/damage counts are transitions of fixed reference-point proximity, not structural area or temporal truth.',
                'Strict support and target-Z error reuse the prior posthoc diagnostic; not complete visibility or RGB observability labels.',
                'Raw512 is primary; post512 is separate. Parent1024 geometry is not mixed into this comparison.',
                'Prior-proximity/image-target-Z strata are evaluation proxies, not ground-truth source-decision labels.',
                'Full-frame native SSIM/LPIPS reuse verified producer metrics; fixed-bbox ROI SSIM/LPIPS are unmeasured.',
                'Native controller responses and CUDA trajectory variation remain part of observed whole-method differences.',
                'Point samples are not independent experiment repeats; same-shape or corrected temporal status is not inferred.'])
        receipt['outputs']=[dict(path=str(p.relative_to(output)),bytes=p.stat().st_size,sha256=sha(p))
                            for p in sorted(output.rglob('*')) if p.is_file()]
        write_json(output/'receipt.json',receipt)
        print(json.dumps({'status':receipt['status'],'receipt':str(output/'receipt.json'),'scientific_verdict':None}),flush=True)
    except Exception as error:
        write_json(output/'failure.json',dict(status='FAIL_EVALUATION',scientific_verdict=None,
            exception_type=type(error).__name__,error=str(error),wall_seconds=time.time()-started,inputs=list(evidence.files.values())))
        raise


if __name__=='__main__':main()
