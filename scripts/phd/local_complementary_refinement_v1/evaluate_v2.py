"""Additive CPU evaluation v2 of sealed local-refinement outputs.

Only the selected new evaluation output root is writable. /parent and /references are evaluation-only
inputs. Existing geometry functions, original reference IDs, frozen RGB splits,
and raw/post512 surfaces are retained. No fitting or parameter selection occurs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
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
from run_selection_v2 import load_selection

from evaluation_utils_v2 import (evaluation_cohorts, paired_rows, psnr_uint8,
    read_json, require_membership, safe_child, self_test, sha, spatial_rows,
    validate_distances, write_csv, write_json, validate_evaluation_spec,
    verify_metric_cache, three_way_rows, coverage_row, postprocess_row)

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


def evaluation_runtime(evidence, expected_image_id):
    """Bind the image checked by the host launcher and loaded CPU libraries."""
    import PIL
    import scipy
    import open3d
    launcher=Path(__file__).with_name('run_evaluation_v2.sh')
    record=evidence.bind(launcher)
    actual=os.environ.get('JBGS_EVALUATION_IMAGE_ID')
    if not actual or actual!=expected_image_id:
        raise ValueError('Verified evaluation launcher image ID is absent or differs')
    if os.environ.get('JBGS_EVALUATION_LAUNCHER_SHA256')!=record['sha256']:
        raise ValueError('Evaluation launcher bytes differ from host invocation')
    return dict(runtime_image_id=actual,launcher_sha256=record['sha256'],
        runtime_identity_source='host Docker image inspect plus pinned image-ID invocation',
        versions=dict(python=platform.python_version(),numpy=np.__version__,
                      scipy=scipy.__version__,open3d=open3d.__version__,pillow=PIL.__version__),
        cpu_only=True,reference_used_for_training_or_parameter_selection=False,
        cgroup_memory_max=(Path('/sys/fs/cgroup/memory.max').read_text().strip()
                           if Path('/sys/fs/cgroup/memory.max').is_file() else None),
        cgroup_cpu_max=(Path('/sys/fs/cgroup/cpu.max').read_text().strip()
                       if Path('/sys/fs/cgroup/cpu.max').is_file() else None),
        process_cpu_affinity_count=len(os.sched_getaffinity(0)))


def snapshot_implementation(output, paths, evidence):
    directory=output/'implementation';directory.mkdir(exist_ok=False)
    snapshots=[]
    for path in paths:
        path=Path(path);record=evidence.bind(path);payload=path.read_bytes()
        if hashlib.sha256(payload).hexdigest()!=record['sha256']:
            raise ValueError('Evaluation source changed during snapshot')
        destination=directory/path.name
        with destination.open('xb') as stream:stream.write(payload)
        snapshots.append(dict(path=str(destination.relative_to(output)),source_path=record['path'],
                              bytes=len(payload),sha256=record['sha256']))
    return snapshots


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


def run_phase_presence(run,evidence=None):
    """Known failures stay failures even when later phase receipts are absent."""
    states={};errors={}
    for phase in ('train','render','metrics'):
        path=Path(run)/f'{phase}_receipt.json'
        if not path.is_file():states[phase]='MISSING'
        else:
            try:
                if evidence is not None:evidence.bind(path)
                receipt=read_json(path)
                if not isinstance(receipt,dict):raise ValueError('Phase receipt must be a JSON object')
                states[phase]=receipt.get('status','INVALID')
            except (ValueError,OSError) as error:
                states[phase]='UNREADABLE';errors[phase]=str(error)
    status=('INVALID_PHASE_RECEIPT' if errors else 'FAILED_PHASE' if 'FAIL' in states.values()
            else 'INVALID_PHASE_STATUS' if any(s not in ('PASS','MISSING') for s in states.values())
            else 'PENDING_OR_MISSING_PHASE' if 'MISSING' in states.values() else 'ALL_PHASE_RECEIPTS_PASS')
    return dict(status=status,phase_statuses=states,phase_read_errors=errors)


def verify_run(task,parent,config_path,cfg,region,condition,evidence,selected_run=None):
    run=selected_run if selected_run is not None else safe_child(task,Path('runs')/region/condition['id'])
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


def load_baseline(parent,region,name,paired,spatial_receipt,seal,evidence,geometry,evaluation_spec):
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
    evidence.bind(safe_child(parent,matched[0]['surface']['path']),matched[0]['surface']['sha256'])
    with np.load(paths['.npz'],allow_pickle=False) as arrays:
        d=verify_metric_cache(metrics,arrays,evaluation_spec,
            paired['reference_points'],paired['reference_original_indices'])
    metrics=dict(metrics,cache_verification='spatial_receipt_sha_and_membership' if name.endswith('.raw')
                 else 'current_digest_membership_metric_consistency_and_source_seal_metadata; no historical post-cache digest')
    return metrics,d


def metric_rows(region,candidate,kind,role,metrics):
    p,r=metrics['prediction_to_reference_point'],metrics['reference_to_prediction_triangle']
    base=dict(region=region,candidate=candidate,mesh_kind=kind,role=role,status=metrics['status'],
              mesh_res=512,surface_area_m2=metrics['surface_area_m2'],surface_samples=metrics['surface_samples'],
              reference_count=metrics['reference_points_after_voxel'],
              primary_or_secondary='PRIMARY' if kind=='raw' else 'SECONDARY_POSTPROCESSED',
              reference_coverage_certified=False)
    for label,values in [('accuracy_prediction_to_observed_reference',p),('completeness_reference_to_surface',r)]:
        base.update({label+'_'+key+'_m':value for key,value in values.items()})
    base.update({'xy_'+k:v for k,v in metrics['xy_support'].items() if not isinstance(v,(list,dict))})
    return [dict(base,**{k:row[k] for k in ('threshold_m','precision','recall','f1')},
        far_from_observed_reference_area_estimate_m2=(metrics['surface_area_m2']*(1-row['precision'])
            if row['precision'] is not None else None),
        far_area_is_confirmed_wrong_structure_area=False) for row in metrics['thresholds']]


def validate_parent_appearance(rows, region, condition, evaluation, render_records, boxes):
    """Reject altered camera identity or a crop domain that changes the comparison."""
    expected={(view['name'],domain) for view in evaluation
              for domain in ('full_frame','fixed_prism_projected_bbox')}
    lookup={(row['name'],row['domain']):row for row in rows}
    if len(lookup)!=len(rows) or set(lookup)!=expected:
        raise ValueError('Parent appearance contains missing, duplicate, or extra camera/domain rows')
    render_lookup={row['name']:row for row in render_records}
    if len(render_lookup)!=len(render_records) or set(render_lookup)!={view['name'] for view in evaluation}:
        raise ValueError('Sealed parent render camera membership differs')
    for index,view in enumerate(evaluation):
        sealed=render_lookup[view['name']]
        for key,value in (('image_id',view['image_id']),('camera_id',view['camera_id']),('evaluation_index',index)):
            if sealed[key]!=value:raise ValueError('Sealed parent render camera identity differs')
        for domain in ('full_frame','fixed_prism_projected_bbox'):
            row=lookup[view['name'],domain];box=boxes[view['name'],domain]
            expected_text=dict(region=region,condition=condition,stage='final',name=view['name'],
                photo_sha256=view['sha256'],render_sha256=sealed['render_sha256'],
                status='ASSESSED' if box is not None else 'PRISM_NOT_IN_CAMERA_DOMAIN')
            if any(row.get(key)!=value for key,value in expected_text.items()):
                raise ValueError('Parent appearance source/status identity differs')
            expected_int=dict(image_id=view['image_id'],camera_id=view['camera_id'],evaluation_index=index,
                pixel_count=(box[2]-box[0])*(box[3]-box[1]) if box is not None else 0)
            if any(int(row[key])!=value for key,value in expected_int.items()):
                raise ValueError('Parent appearance camera or pixel denominator differs')
            actual_box=[int(row[key]) if row.get(key) not in ('',None) else None
                        for key in ('roi_x0','roi_y0','roi_x1','roi_y1')]
            if actual_box!=(list(box) if box is not None else [None]*4):
                raise ValueError('Parent appearance fixed crop rectangle differs')
    return lookup


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
        old_rows=list(csv.DictReader(stream))
    seal_path=parent/'contracts/candidates_sealed_v1.json'
    evidence.bind(seal_path,PARENT_SEAL_SHA)
    candidates=[row for row in read_json(seal_path)['candidates'] if row['region']==region
                and row['condition']==condition['parent_condition'] and row['variant']=='final' and row['mesh_kind']=='raw']
    if len(candidates)!=1:raise ValueError('Expected one sealed parent final render candidate')
    parent_records=candidates[0]['render_records']
    boxes={}
    for view in evaluation:
        boxes[view['name'],'full_frame']=[0,0,view['width'],view['height']]
        boxes[view['name'],'fixed_prism_projected_bbox']=render_quality.projected_prism_bbox(
            bounds,view['R'],view['t'],view['K'],view['width'],view['height'])
    old=validate_parent_appearance(old_rows,region,condition['parent_condition'],evaluation,parent_records,boxes)
    for record in parent_records:
        evidence.bind(safe_child(parent,record['render_path']),record['render_sha256'])
    for index,view in enumerate(evaluation):
        filename=f'{index:05d}.png'
        render_path,gt_path=renders/filename,saved_gt/filename
        rp=evidence.bind(render_path,output_digest(receipts['render'],str(render_path.relative_to(run))))
        gp=evidence.bind(gt_path,output_digest(receipts['render'],str(gt_path.relative_to(run))))
        photo_path=parent/'inputs'/region/'scene/images'/view['name']
        photo=render_quality.read_rgb(photo_path); actual_gt=render_quality.read_rgb(gt_path)
        if not np.array_equal(actual_gt,photo):
            raise ValueError('Exported GT pixels do not establish frozen image order: '+filename)
        image=render_quality.read_rgb(render_path)
        if image.shape!=photo.shape or image.shape!=(view['height'],view['width'],3):
            raise ValueError('Native image shape differs from frozen calibration')
        mapping.append(dict(name=view['name'],evaluation_index=index,image_id=view['image_id'],camera_id=view['camera_id'],
            render_path=str(render_path.relative_to(run)),render_sha256=rp['sha256'],exported_gt_sha256=gp['sha256'],
            pose_binding='frozen calibration, native shuffle=False sorted stem order, exact exported GT pixel check'))
        bbox=boxes[view['name'],'fixed_prism_projected_bbox']
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


def command_values(receipt,flag):
    command=receipt.get('command',[])
    if command.count(flag)>1:raise ValueError('Repeated cost-scope command flag: '+flag)
    if flag not in command:return []
    values=[]
    for item in command[command.index(flag)+1:]:
        if item.startswith('-'):break
        values.append(item)
    return values


def phase_cost_scope(receipt,phase,timing_owner):
    """Report observed command/timing scope without manufacturing adjusted cost."""
    command=receipt.get('command',[])
    result=dict(phase=receipt.get('phase',phase),timing_owner=timing_owner,
        wall_seconds_unit='elapsed seconds',peak_rss_unit='bytes',
        includes_host_contention_and_process_polling=True,
        pure_gpu_kernel_time=False)
    if timing_owner=='parent_auxiliary_variant':
        result['wall_scope']='native subprocess plus 2s polling; excludes model copy, preflight, host wait, output validation and hashing'
    elif timing_owner=='parent_primary_driver':
        result['wall_scope']='phase driver after preflight and extraction lock; subprocess plus 5s polling, validation and output hashing'
    else:
        result['wall_scope']='v2 driver including input/source verification, subprocess plus 5s polling, validation and output hashing'
    if phase=='train':
        end_values=command_values(receipt,'--iterations')
        end=receipt.get('training_end_iteration') or (int(end_values[0]) if len(end_values)==1 else None)
        start=receipt.get('training_start_iteration')
        captures=[int(value) for value in command_values(receipt,'--jbgs_capture_iterations')]
        result.update(start_iteration=start,end_iteration=end,
            iteration_count=end-start if start is not None and end is not None else None,
            includes_new_anchor_prefix=start==0,declared_complete_capture_iterations=captures,
            complete_capture_iterations_in_executed_range=[i for i in captures if start is not None and end is not None and start<i<=end],
            capture_scope='command-declared complete model/optimizer/RNG/controller checkpoint writes; raw wall cost includes serialization')
    elif phase=='render':
        specified=command_values(receipt,'--mesh_res')
        candidates=[receipt.get('mesh_res'),receipt.get('realized_extraction',{}).get('mesh_res'),
                    int(specified[0]) if len(specified)==1 else None]
        values={v for v in candidates if v is not None}
        if len(values)>1:raise ValueError('Receipt and command extraction resolutions differ')
        result.update(mesh_res=next(iter(values)) if values else None,
            exports_train_images='--skip_train' not in command,exports_test_images='--skip_test' not in command,
            extracts_mesh='--skip_mesh' not in command,
            phase_scope='native rendering, requested PNG export, raw TSDF extraction and postprocessing')
    elif phase=='metrics':
        result.update(mesh_res=None,phase_scope='official saved evaluation RGB full-frame PSNR/SSIM/LPIPS; no TSDF extraction or ROI scores',
            image_domain='full_frame',psnr_unit='dB',ssim_unit='dimensionless',lpips_unit='dimensionless',
            roi_psnr_in_this_phase=False,roi_ssim_lpips_in_this_phase=False,
            roi_psnr_scope='computed separately by CPU evaluation on a fixed projected bbox; not included in native metrics receipt')
    else:raise ValueError('Unknown compute phase: '+phase)
    return result


def cost_scope_differences(new,old,phase):
    keys={'train':('start_iteration','end_iteration','complete_capture_iterations_in_executed_range'),
          'render':('mesh_res','exports_train_images','exports_test_images','extracts_mesh'),
          'metrics':('image_domain',)}[phase]
    differences=[key for key in keys if new.get(key)!=old.get(key)]
    if new['wall_scope']!=old['wall_scope']:differences.append('driver_timing_boundary_and_instrumentation')
    return differences


def parent_512_extraction_cost(parent,region,condition,parent_render,evidence):
    """Reuse the exact sealed 512 producer duration as contextual extraction cost.

    It omits RGB exports and uses a narrower timing interval than LC's phase
    driver, so even a verified 512 record is not a matched pure-method cost.
    """
    directory=parent/'extraction_resource_v3/primary'/region/condition/'auxiliary/mesh_512'
    path=directory/'receipt.json'
    result=dict(parent_aux512_cost_status='UNAVAILABLE',parent_aux512_wall_seconds=None,
        parent_aux512_not_comparable_as_pure_method_cost=True,
        parent_aux512_matched_phase_cost_available=False)
    if not path.is_file():
        return dict(result,parent_aux512_unavailable_reason='No exact auxiliary512 producer receipt')
    evidence.bind(path)
    receipt=read_json(path)
    try:
        expected=dict(region=region,condition=condition,phase='auxiliary_variant',variant='mesh_512',
            iteration=30000,mesh_res=512,status='PASS',scientific_verdict=None)
        if any(receipt.get(key)!=value for key,value in expected.items()):
            raise ValueError('Auxiliary512 completed identity differs')
        if (receipt['input_manifest_sha256']!=parent_render['input_manifest_sha256'] or
                receipt['runtime_image_id']!=parent_render['runtime_image_id'] or
                receipt['source_complete_ply_sha256']!=parent_render['render_source_ply']['sha256'] or
                receipt['copied_ply_sha256']!=receipt['source_complete_ply_sha256']):
            raise ValueError('Auxiliary512 source/input/runtime differs from corresponding final')
        seal_path=parent/'contracts/candidates_sealed_v1.json';evidence.bind(seal_path,PARENT_SEAL_SHA)
        seal=read_json(seal_path)
        for kind,filename in [('raw','fuse.ply'),('post','fuse_post.ply')]:
            candidates=[row for row in seal['candidates'] if row['region']==region and row['condition']==condition
                        and row['variant']=='mesh_512' and row['mesh_kind']==kind]
            if len(candidates)!=1:raise ValueError('Auxiliary512 candidate seal membership differs')
            relative=f'model/train/ours_30000/{filename}'
            files=[row for row in receipt['files'] if row['path']==relative and row.get('exists')]
            if len(files)!=1 or files[0]['sha256']!=candidates[0]['surface']['sha256']:
                raise ValueError('Auxiliary512 output differs from sealed evaluated surface')
            if safe_child(parent,candidates[0]['surface']['path'])!=directory/relative:
                raise ValueError('Auxiliary512 producer path differs from evaluated surface')
            evidence.bind(directory/relative,files[0]['sha256'])
        if not np.isfinite(receipt['wall_seconds']) or receipt['wall_seconds']<0:
            raise ValueError('Invalid auxiliary512 duration')
        scope=phase_cost_scope(receipt,'render','parent_auxiliary_variant')
        return dict(result,parent_aux512_cost_status='VERIFIED_EXACT_SURFACE_CONTEXTUAL_COST',
            parent_aux512_wall_seconds=receipt['wall_seconds'],
            parent_aux512_child_peak_rss_bytes=receipt.get('child_peak_rss_bytes'),
            parent_aux512_mesh_res=scope['mesh_res'],parent_aux512_phase=scope['phase'],
            parent_aux512_exports_train_images=scope['exports_train_images'],
            parent_aux512_exports_test_images=scope['exports_test_images'],
            parent_aux512_wall_scope=scope['wall_scope'],
            parent_aux512_receipt_sha256=evidence.bind(path)['sha256'],
            parent_aux512_unavailable_reason=None,
            parent_aux512_comparison_limit='same evaluated raw/post512 surface producer; no PNG exports and different timing boundaries from LC driver')
    except (KeyError,ValueError,FileNotFoundError) as error:
        return dict(result,parent_aux512_cost_status='UNAVAILABLE_IDENTITY_NOT_VERIFIED',
            parent_aux512_unavailable_reason=str(error))


def compute_row(region,condition,run,receipts,parent,evidence):
    result=dict(region=region,candidate=condition['id'],parent_condition=condition['parent_condition'],
                start_iteration=8000,end_iteration=30000,new_iterations=22000,
                iteration_budget_is_not_equal_wall_time_or_primitive_compute=True,
                compute_schema='jbgs.local_complementary_compute.v2.1',
                not_comparable_as_pure_method_cost=True,
                cost_interpretation='recorded operational costs with explicit phase/capture scopes; no adjusted or pure-method cost delta')
    new_scopes={phase:phase_cost_scope(receipt,phase,'new_v2_driver') for phase,receipt in receipts.items()}
    for phase,receipt in receipts.items():
        result[phase+'_driver_wall_seconds']=receipt['wall_seconds']
        result[phase+'_child_peak_rss_bytes']=receipt.get('child_peak_rss_bytes')
        for key,value in new_scopes[phase].items():
            result['new_'+phase+'_'+key]=json.dumps(value) if isinstance(value,list) else value
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
    parents={}
    for phase in ('train','render','metrics'):
        path=parent/'runs_allocator_v2'/region/condition['parent_condition']/f'{phase}_receipt.json'
        evidence.bind(path)
        receipt=read_json(path)
        parents[phase]=receipt
        result['parent_'+phase+'_driver_wall_seconds']=receipt.get('wall_seconds')
        old_scope=phase_cost_scope(receipt,phase,'parent_primary_driver')
        for key,value in old_scope.items():
            result['parent_'+phase+'_'+key]=json.dumps(value) if isinstance(value,list) else value
        differences=cost_scope_differences(new_scopes[phase],old_scope,phase)
        result[phase+'_cost_scope_differences']=json.dumps(differences)
        result[phase+'_not_comparable_as_pure_method_cost']=bool(differences)
        if phase=='train':result['parent_training_start_iteration']=receipt.get('training_start_iteration')
    result.update(parent_512_extraction_cost(parent,region,condition['parent_condition'],parents['render'],evidence))
    metric_files=('metrics.py','utils/image_utils.py','utils/loss_utils.py','lpipsPyTorch/modules/lpips.py',
                  'lpipsPyTorch/modules/networks.py','lpipsPyTorch/modules/utils.py')
    result['same_native_fullframe_metric_implementation']=all(
        receipts['metrics'].get('implementation_hashes',{}).get(key) is not None and
        receipts['metrics']['implementation_hashes'][key]==parents['metrics'].get('implementation_hashes',{}).get(key)
        for key in metric_files)
    return result


def baseline_preflight(parent,reference_root,regions,seal,spatial_receipt,evidence,numeric,geometry,output,cfg,runtime,snapshots):
    """Read and verify actual historical bytes without recomputing model outputs."""
    started=time.time();rows=[]
    try:
        for region in regions:
            paired_path=parent/'evaluation/da3_refinement_spatial_v1'/f'{region}.paired.npz'
            evidence.bind(paired_path,spatial_receipt['outputs'][paired_path.name]['sha256'])
            with np.load(paired_path,allow_pickle=False) as loaded:
                paired={key:loaded[key] for key in ('reference_points','reference_original_indices',
                    'reference_to_anchor_distance','strict_target_world_z_error_median','strict_view_count','strict_view_range')}
            reference_path=reference_root/region/'reference.npz'
            evidence.bind(reference_path,REFERENCE_SHAS[region])
            with np.load(reference_path,allow_pickle=False) as loaded:
                reference=loaded['uas_xyz']
            ids,points=paired['reference_original_indices'],paired['reference_points']
            if (np.any(ids<0) or np.any(ids>=len(reference)) or not np.array_equal(reference[ids],points)):
                raise ValueError('Reference original membership fails: '+region)
            _,evaluation=load_split(parent,region,evidence)
            anchor=None
            for kind in ('raw','post'):
                for condition in ('ANCHOR',*BASELINE_CONDITIONS):
                    name=('D005_Pnative.anchor_512.' if condition=='ANCHOR' else condition+'.mesh_512.')+kind
                    metrics,distance=load_baseline(parent,region,name,paired,spatial_receipt,seal,evidence,geometry,numeric)
                    if anchor is None:anchor=metrics
                    if metrics['bounds_half_open']!=anchor['bounds_half_open'] or metrics['crs']!=anchor['crs']:
                        raise ValueError('Baseline bounds/CRS mismatch')
                    if condition=='ANCHOR' and kind=='raw' and not np.array_equal(distance,paired['reference_to_anchor_distance']):
                        raise ValueError('Anchor diagnostic distance cache mismatch')
                    rows.append(dict(region=region,condition=condition,kind=kind,status='PASS_REUSE_IDENTITY',
                        reference_count=len(ids),source_sha256=metrics['source_sha256'],
                        bounds_half_open=metrics['bounds_half_open'],crs=metrics['crs'],cache_verification=metrics['cache_verification']))
                    print(json.dumps(dict(region=region,condition=condition,kind=kind,status='PASS_BASELINE_CACHE')),flush=True)
            prior=parent/'evaluation/geometry'/region/'prior_mesh/sample0.1_reference0.1.npz'
            evidence.bind(prior)
            with np.load(prior,allow_pickle=False) as data:
                require_membership(data['reference_points'],data['reference_original_indices'],points,ids)
                prior_distance=validate_distances(data['reference_to_triangle_distance'],len(ids))
            cohorts=evaluation_cohorts(paired,paired['reference_to_anchor_distance'],prior_distance)
            write_json(output/f'{region}_reuse.json',dict(region=region,scientific_verdict=None,
                status='PASS_BASELINE_REUSE',mesh_cache_count=14,reference_points=len(ids),
                reference_sha256=REFERENCE_SHAS[region],frozen_evaluation_views=len(evaluation),
                strata_counts={key:int(mask.sum()) for key,mask in cohorts.items()},
                bounds_half_open=anchor['bounds_half_open'],crs=anchor['crs']))
            del reference,paired,points,ids,prior_distance,distance,cohorts
        write_json(output/'receipt.json',dict(schema='jbgs.local_complementary_baseline_preflight.v2',
            status='PASS_BASELINE_REUSE',task_id=cfg['task_id'],scientific_verdict=None,regions=regions,
            cache_count=len(rows),expected_cache_count=len(regions)*14,checks=rows,
            wall_seconds=time.time()-started,process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            reference_used_for_training_or_parameter_selection=False,model_or_metric_recomputed=False,
            runtime=runtime,implementation_snapshots=snapshots,inputs=list(evidence.files.values()),limitations=[
                'Postprocessed cached metrics have no historical digest in the spatial receipt; current snapshot, actual sealed mesh hash and exact cached metric-distance consistency checked.',
                'Reference coverage/absolute vertical datum and physical image visibility remain uncertified.',
                'Strict target-Z strata are evaluation proxies, not raw photograph O/X or temporal truth.']))
    except Exception as error:
        write_json(output/'failure.json',dict(status='FAIL_BASELINE_REUSE',scientific_verdict=None,
            error=str(error),exception_type=type(error).__name__,completed_checks=rows,
            inputs=list(evidence.files.values()),wall_seconds=time.time()-started))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',type=Path,default=Path('/task'))
    parser.add_argument('--parent',type=Path,default=Path('/parent'))
    parser.add_argument('--config',type=Path,default=Path('/config.json'))
    parser.add_argument('--reference-root',type=Path,default=Path('/references'))
    parser.add_argument('--output',type=Path,required=False,
                        help='Separate writable output root; a fresh attempt directory is created')
    parser.add_argument('--region',choices=('P1','P2','P3'),action='append')
    parser.add_argument('--allow-partial',action='store_true')
    parser.add_argument('--run-selection',type=Path,help='Explicit full18 successful-attempt manifest; original failed runs remain preserved')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--baseline-preflight',action='store_true')
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
    numeric=validate_evaluation_spec(cfg['evaluation'])
    selected=list(dict.fromkeys(args.region or cfg['regions']))
    if not set(selected)<=set(cfg['regions']):raise ValueError('Unknown selected region')
    evidence=Evidence();evidence.bind(args.config)
    runtime=evaluation_runtime(evidence,cfg['runtime']['image_id'])
    implementation_paths=(Path(__file__),Path(__file__).with_name('evaluation_utils_v2.py'),Path(__file__).with_name('run_selection_v2.py'),
        Path(__file__).with_name('run_evaluation_v2.sh'),GEOMETRY_DIR/'geometry.py',GEOMETRY_DIR/'render_quality.py')
    for path in implementation_paths:
        evidence.bind(path)
    seal_path=parent/'contracts/candidates_sealed_v1.json'
    evidence.bind(seal_path,PARENT_SEAL_SHA);seal=read_json(seal_path)
    spatial_path=parent/'evaluation/da3_refinement_spatial_v1/receipt.json'
    evidence.bind(spatial_path);spatial_receipt=read_json(spatial_path)
    output_root=(args.output or task/'evaluation').resolve()
    if output_root==parent or output_root.is_relative_to(parent) or parent.is_relative_to(output_root):
        raise ValueError('Evaluation output must not overlap historical parent inputs')
    output=safe_child(output_root,'attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir(parents=True,exist_ok=False)
    snapshots=snapshot_implementation(output,implementation_paths,evidence)
    if args.baseline_preflight:
        baseline_preflight(parent,args.reference_root,selected,seal,spatial_receipt,evidence,numeric,geometry,output,cfg,runtime,snapshots)
        print(json.dumps(dict(status='PASS_BASELINE_REUSE',receipt=str(output/'receipt.json'),scientific_verdict=None)),flush=True)
        return
    run_selection=None;selected_runs={}
    if args.run_selection is not None:
        binding_path=args.config.with_name('input_binding.json');evidence.bind(binding_path)
        selected_runs=load_selection(args.run_selection,task,cfg,sha(args.config),sha(binding_path),evidence.bind)
        run_selection=evidence.bind(args.run_selection)
    jobs=[];missing=[]
    for region in selected:
        for condition in cfg['conditions']:
            run=selected_runs.get((region,condition['id']),task/'runs'/region/condition['id'])
            presence=run_phase_presence(run,evidence)
            if presence['status']!='ALL_PHASE_RECEIPTS_PASS':
                missing.append(dict(region=region,condition=condition['id'],**presence,
                                    quality_metrics=None,reference_absence=False));continue
            try:
                run,receipts=verify_run(task,parent,args.config,cfg,region,condition,evidence,selected_run=run)
                jobs.append((region,condition,run,receipts))
            except Exception as error:
                missing.append(dict(region=region,condition=condition['id'],status='INVALID_OR_FAILED_PHASE',
                    exception_type=type(error).__name__,error=str(error),quality_metrics=None,
                    reference_absence=False))
    write_json(output/'run_presence_audit.json',dict(task_id=cfg['task_id'],scientific_verdict=None,
        expected_selected_run_count=len(selected)*len(cfg['conditions']),valid_run_count=len(jobs),
        missing_or_invalid=missing,config_sha256=evidence.bind(args.config)['sha256']))
    if missing and not args.allow_partial:
        write_json(output/'failure.json',dict(status='FAIL_INCOMPLETE_OR_INVALID_RUN_SET',
            scientific_verdict=None,missing_or_invalid=missing))
        raise ValueError('All requested runs must be complete before reference evaluation: '+str(missing))
    if not jobs:
        write_json(output/'failure.json',dict(status='FAIL_NO_VALID_COMPLETE_RUNS',
            scientific_verdict=None,missing_or_invalid=missing))
        raise ValueError('No complete runs to evaluate')
    started=time.time();all_metrics=[];all_pairs=[];all_cells=[];all_appearance=[];all_compute=[]
    all_three_way=[];all_coverage=[];all_postprocessing=[]
    thresholds=numeric['thresholds_m'];primary_threshold=numeric['paired_primary_threshold_m']
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
                    metrics,distances=load_baseline(parent,region,name,paired,spatial_receipt,seal,evidence,geometry,numeric)
                    baselines[kind,condition]=distances;baseline_metrics[kind,condition]=metrics
                    all_metrics.extend(metric_rows(region,condition,kind,'parent_anchor' if condition=='ANCHOR' else 'parent_final',metrics))
            if not np.array_equal(baselines['raw','ANCHOR'],paired['reference_to_anchor_distance']):
                raise ValueError('Spatial diagnostic and Anchor raw512 distances differ')
            anchor_metrics=baseline_metrics['raw','ANCHOR'];bounds=anchor_metrics['bounds_half_open']
            if any(m['bounds_half_open']!=bounds or m['crs']!=anchor_metrics['crs']
                   for m in baseline_metrics.values()):
                raise ValueError('Baseline raw/post fixed spatial bounds or CRS differ')
            # Prior proximity is an evaluation stratum, distinct from Anchor proximity.
            prior_npz=parent/'evaluation/geometry'/region/'prior_mesh/sample0.1_reference0.1.npz'
            evidence.bind(prior_npz)
            with np.load(prior_npz,allow_pickle=False) as old:
                require_membership(old['reference_points'],old['reference_original_indices'],points,ids)
                prior_distance=old['reference_to_triangle_distance']
            cohorts=evaluation_cohorts(paired,baselines['raw','ANCHOR'],prior_distance,numeric['source_stratum_threshold_m'])
            strict_count=int(cohorts['STRICT_SUPPORT'].sum())
            for kind in ('raw','post'):
                for baseline in ('ANCHOR',*BASELINE_CONDITIONS):
                    all_coverage.append(coverage_row(region,baseline,kind,baseline_metrics[kind,baseline],strict_count))
                    if baseline!='ANCHOR':
                        all_pairs.extend(paired_rows(region,baseline,'ANCHOR',kind,baselines[kind,'ANCHOR'],
                            baselines[kind,baseline],cohorts,thresholds,numeric['distance_change_reporting_epsilon_m']))
                        all_cells.extend(spatial_rows(region,baseline,'ANCHOR',kind,paired,
                            baselines[kind,'ANCHOR'],baselines[kind,baseline],primary_threshold))
            for baseline in ('ANCHOR',*BASELINE_CONDITIONS):
                all_postprocessing.append(postprocess_row(region,baseline,baseline_metrics['raw',baseline],baseline_metrics['post',baseline]))
            new_distances={}
            for _,condition,run,receipts in region_jobs:
                case=output/region/condition['id'];case.mkdir(parents=True)
                case_metrics={}
                for kind,filename in [('raw','fuse.ply'),('post','fuse_post.ply')]:
                    t0=time.time();mesh_path=run/'model/train/ours_30000'/filename
                    import open3d as o3d
                    mesh=o3d.io.read_triangle_mesh(str(mesh_path))
                    metrics,arrays=geometry.evaluate_geometry(np.asarray(mesh.vertices),np.asarray(mesh.triangles),reference,
                        bounds,spacing=numeric['surface_sample_spacing_m'],reference_voxel_size=numeric['reference_voxel_m'],seed=numeric['seed'],
                        thresholds=thresholds,voxel_origin=numeric['reference_voxel_origin'],xy_cell_size=numeric['xy_cell_m'])
                    require_membership(arrays['reference_points'],arrays['reference_original_indices'],points,ids)
                    distances=arrays['reference_to_triangle_distance']
                    new_distances[condition['id'],kind]=distances.copy()
                    metrics.update(region=region,candidate=condition['id'],mesh_kind=kind,mesh_res=512,iteration=30000,
                        reference_sha256=REFERENCE_SHAS[region],source_sha256=evidence.bind(mesh_path)['sha256'],
                        crs=anchor_metrics['crs'],wall_seconds=time.time()-t0,scientific_verdict=None)
                    write_json(case/f'{kind}_metrics.json',metrics)
                    geometry.save_distance_arrays(case/f'{kind}_distances.npz',arrays)
                    all_metrics.extend(metric_rows(region,condition['id'],kind,'new_final',metrics))
                    case_metrics[kind]=metrics
                    all_coverage.append(coverage_row(region,condition['id'],kind,metrics,strict_count))
                    all_three_way.extend(three_way_rows(region,condition['id'],condition['parent_condition'],kind,
                        baselines[kind,'ANCHOR'],baselines[kind,condition['parent_condition']],distances,cohorts,thresholds))
                    for comparator in ('ANCHOR',*BASELINE_CONDITIONS):
                        before=baselines[kind,comparator]
                        all_pairs.extend(paired_rows(region,condition['id'],comparator,kind,before,distances,cohorts,
                                                    thresholds,numeric['distance_change_reporting_epsilon_m']))
                        if comparator in ('ANCHOR',condition['parent_condition']):
                            all_cells.extend(spatial_rows(region,condition['id'],comparator,kind,paired,before,distances,primary_threshold))
                    del arrays,mesh
                all_appearance.extend(appearance_rows(parent,region,condition,run,receipts,evaluation,bounds,evidence,render_quality,case))
                all_compute.append(compute_row(region,condition,run,receipts,parent,evidence))
                all_postprocessing.append(postprocess_row(region,condition['id'],case_metrics['raw'],case_metrics['post']))
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
                                                thresholds,numeric['distance_change_reporting_epsilon_m']))
                    all_cells.extend(spatial_rows(region,release['id'],native['id'],kind,paired,before,after,primary_threshold))
            del reference,baselines,paired,new_distances
        for name,rows in [('geometry_metrics',all_metrics),('paired_transitions',all_pairs),('same_cell_changes',all_cells),
                          ('appearance_per_image',all_appearance),('compute',all_compute),
                          ('anchor_global_local_transitions',all_three_way),('coverage',all_coverage),
                          ('postprocessing_effect',all_postprocessing),('missing_runs',missing)]:write_csv(output/(name+'.csv'),rows)
        complete=len(jobs)==len(cfg['regions'])*len(cfg['conditions']) and not missing
        receipt=dict(schema='jbgs.local_complementary_evaluation.v2',status='COMPLETE_DEVELOPMENT_EVALUATION' if complete else 'PARTIAL_DEVELOPMENT_EVALUATION',
            scientific_verdict=None,task_id=cfg['task_id'],run_count=len(jobs),expected_full_run_count=len(cfg['regions'])*len(cfg['conditions']),
            selected_regions=selected,missing=missing,wall_seconds=time.time()-started,
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            reference_used_for_training_or_parameter_selection=False,versions=runtime['versions'],runtime=runtime,
            implementation_snapshots=snapshots,run_selection=run_selection,
            selected_run_sources=[dict(region=r,condition=c['id'],relative_path=str(run.relative_to(task)),
                phase_receipt_sha256={phase:sha(run/f'{phase}_receipt.json') for phase in ('train','render','metrics')})
                for r,c,run,receipts in jobs],
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
