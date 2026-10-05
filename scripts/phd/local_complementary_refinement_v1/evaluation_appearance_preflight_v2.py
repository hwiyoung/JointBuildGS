"""Validate v2 appearance evaluator on real historical saved RGB arrays.

This preflight does not relabel historical receipts. Sealed candidate render
hashes bind predictions; exported-GT files lack old producer digests and are
checked byte-for-pixel against independently sealed source photographs. The
adapter below exists only for testing the new evaluator's actual format path.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import time

from evaluate_v2 import (Evidence, PARENT_SEAL_SHA, BASELINE_CONDITIONS, GEOMETRY_DIR,
    load_module, load_split, appearance_rows, evaluation_runtime, snapshot_implementation)
from evaluation_utils_v2 import read_json, write_json, write_csv, sha, safe_child


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent',type=Path,default=Path('/parent'))
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--region',choices=('P1','P2','P3'),default='P2')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    parent=args.parent.resolve();output=safe_child(args.output,'appearance_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    if output.is_relative_to(parent):raise ValueError('Output overlaps historical parent')
    output.mkdir(parents=True,exist_ok=False);started=time.time();evidence=Evidence();rows=[]
    evidence.bind(args.config);cfg=read_json(args.config)
    if cfg.get('scientific_verdict') is not None or cfg['evaluation']['reference_for_training_or_parameter_selection']:
        raise ValueError('Null verdict and evaluation-only reference required')
    runtime=evaluation_runtime(evidence,cfg['runtime']['image_id'])
    for path in (Path(__file__),Path(__file__).with_name('evaluate_v2.py'),Path(__file__).with_name('evaluation_utils_v2.py')):evidence.bind(path)
    seal_path=parent/'contracts/candidates_sealed_v1.json';evidence.bind(seal_path,PARENT_SEAL_SHA);seal=read_json(seal_path)
    _,views=load_split(parent,args.region,evidence)
    quality=load_module('appearance_preflight_quality',GEOMETRY_DIR/'render_quality.py');evidence.bind(GEOMETRY_DIR/'render_quality.py')
    snapshots=snapshot_implementation(output,(Path(__file__),Path(__file__).with_name('evaluate_v2.py'),
        Path(__file__).with_name('evaluation_utils_v2.py'),Path(__file__).with_name('run_evaluation_v2.sh'),
        GEOMETRY_DIR/'render_quality.py'),evidence)
    bounds_path=parent/'evaluation/geometry'/args.region/'D005_Pnative.anchor_512.raw/sample0.1_reference0.1.json'
    evidence.bind(bounds_path);bounds=read_json(bounds_path)['bounds_half_open']
    try:
        for name in BASELINE_CONDITIONS:
            candidates=[c for c in seal['candidates'] if c['region']==args.region and c['condition']==name
                        and c['variant']=='final' and c['mesh_kind']=='raw']
            if len(candidates)!=1:raise ValueError('Historical full final candidate absent')
            records=candidates[0]['render_records'];expected={r['name']:r for r in records}
            if len(expected)!=len(records) or set(expected)!={v['name'] for v in views}:
                raise ValueError('Historical evaluation pose membership differs')
            run=parent/'runs_allocator_v2'/args.region/name;digest_records=[]
            for index,view in enumerate(views):
                record=expected[view['name']]
                for key,value in [('evaluation_index',index),('image_id',view['image_id']),('camera_id',view['camera_id'])]:
                    if record[key]!=value:raise ValueError('Frozen camera mapping differs')
                render=safe_child(parent,record['render_path']);evidence.bind(render,record['render_sha256'])
                digest_records.append(dict(path=str(render.relative_to(run)),sha256=record['render_sha256']))
                gt=render.parent.parent/'gt'/render.name
                evidence.bind(gt)
                digest_records.append(dict(path=str(gt.relative_to(run)),sha256=sha(gt)))
            for filename in ('per_view.json','results.json'):evidence.bind(run/'model'/filename)
            case=output/name;case.mkdir()
            adapted={'render':{'outputs':digest_records,'input_manifest_sha256':sha(parent/'inputs'/args.region/'input_manifest.json')}}
            rows.extend(appearance_rows(parent,args.region,dict(id=name,parent_condition=name),run,adapted,views,bounds,evidence,quality,case))
            print(json.dumps(dict(region=args.region,condition=name,status='PASS_ACTUAL_APPEARANCE_COMPATIBILITY')),flush=True)
        write_csv(output/'appearance_preflight_rows.csv',rows)
        write_json(output/'receipt.json',dict(schema='jbgs.local_complementary_appearance_preflight.v2',
            status='PASS_ACTUAL_APPEARANCE_COMPATIBILITY',scientific_verdict=None,region=args.region,
            historical_condition_count=len(BASELINE_CONDITIONS),frozen_camera_count=len(views),domain_rows=len(rows),
            tests=['candidate-sealed render hashes','frozen image/camera/pose/order identity','all RGB PNG dimensions',
                   'exported GT equals actual sealed photo pixels','official per-image metrics match means',
                   'CPU float64 fullframe PSNR differs from saved native PSNR by at most 0.001dB',
                   'exact camera, photo/render digest, crop rectangle, pixel count and status match historical appearance CSV'],
            new_render_execution=False,training_execution=False,actual_reference_geometry_access=False,
            legacy_gt_digest_is_new_snapshot=True,legacy_gt_independently_verified_against_sealed_photo=True,
            wall_seconds=time.time()-started,process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            runtime=runtime,implementation_snapshots=snapshots,
            reference_used_for_training_or_parameter_selection=False,inputs=list(evidence.files.values()),
            outputs=[dict(path=str(p.relative_to(output)),sha256=sha(p),bytes=p.stat().st_size)
                     for p in sorted(output.rglob('*')) if p.is_file()]))
    except Exception as error:
        write_json(output/'failure.json',dict(status='FAIL_ACTUAL_APPEARANCE_COMPATIBILITY',scientific_verdict=None,
            error=str(error),exception_type=type(error).__name__,completed_domain_rows=len(rows),inputs=list(evidence.files.values())))
        raise


if __name__=='__main__':main()
