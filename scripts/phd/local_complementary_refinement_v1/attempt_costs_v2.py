"""Account for successful and failed main-v2 phase costs without quality selection."""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import resource
import time

from run_selection_v2 import digest, load_selection, read, receipt_identity, require, safe_run


def interval_union_seconds(intervals):
    total=0.;end=None
    for start,stop in sorted(intervals):
        require(math.isfinite(start) and math.isfinite(stop) and stop>=start,'Invalid phase interval')
        total+=stop-max(start,end) if end is not None and stop>end else stop-start if end is None else 0.
        end=stop if end is None else max(end,stop)
    return total


def sampled_device_usage(path):
    if not path.exists():return dict(sample_count=0,device_uuids='',sampled_device_memory_peak_mib=None,sampled_device_utilization_peak_pct=None)
    with path.open() as stream:rows=list(csv.reader(stream))
    uuids=set();memory=[];utilization=[]
    for row in rows:
        require(len(row)==4,'Malformed GPU sampling row')
        uuid=row[1].strip();m=float(row[2]);u=float(row[3])
        require(uuid.startswith('GPU-') and math.isfinite(m) and m>=0 and math.isfinite(u) and 0<=u<=100,'Invalid device sample')
        uuids.add(uuid);memory.append(m);utilization.append(u)
    return dict(sample_count=len(rows),device_uuids=';'.join(sorted(uuids)),
                sampled_device_memory_peak_mib=max(memory,default=None),sampled_device_utilization_peak_pct=max(utilization,default=None))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['task','config','binding','selection','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();require(Path('/.dockerenv').is_file(),'Docker required')
    out=args.output/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir(parents=True,exist_ok=False)
    started=time.time();inputs={}
    def bind(path,expected=None):
        path=Path(path);value=digest(path);require(expected is None or expected==value,'Cost source hash differs')
        inputs[str(path)]=dict(path=str(path),sha256=value,bytes=path.stat().st_size);return value
    for path in [Path(__file__),Path(__file__).with_name('run_selection_v2.py'),args.config,args.binding,args.selection]:bind(path)
    cfg=read(args.config);config_sha=digest(args.config);binding_sha=digest(args.binding)
    try:
        load_selection(args.selection,args.task,cfg,config_sha,binding_sha,bind)
        selection=read(args.selection);rows=[]
        for chosen in selection['runs']:
            region,condition=chosen['region'],chosen['condition']
            paths=[(x['relative_path'],False) for x in chosen['failed_attempts']]+[(chosen['relative_path'],True)]
            for relative,is_selected in paths:
                run=safe_run(args.task,region,condition,relative)
                for phase in ['train','render','metrics']:
                    path=run/(phase+'_receipt.json')
                    if not path.exists():continue
                    bind(path);r=read(path)
                    receipt_identity(r,cfg,region,condition,phase,config_sha,binding_sha,'PASS' if is_selected else 'FAIL')
                    start,finish,wall=[float(r[k]) for k in ['started_unix','finished_unix','wall_seconds']]
                    require(wall>=0 and abs((finish-start)-wall)<.01,'Driver wall and interval disagree')
                    gpu=run/(phase+'_gpu.csv')
                    if gpu.exists():bind(gpu)
                    rows.append(dict(region=region,condition=condition,relative_run=relative,selected=is_selected,phase=phase,
                        status=r['status'],native_exit_code=r['native_exit_code'],validated_exit_code=r['validated_exit_code'],
                        started_unix=start,finished_unix=finish,driver_wall_seconds=wall,child_peak_rss_bytes=r['child_peak_rss_bytes'],
                        completed_training_iteration=r.get('training_end_iteration') if is_selected and phase=='train' else None,
                        **sampled_device_usage(gpu)))
        with (out/'phase_costs.csv').open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        groups=[]
        for selected in [True,False]:
            for phase in ['train','render','metrics']:
                subset=[r for r in rows if r['selected']==selected and r['phase']==phase]
                groups.append(dict(selected=selected,phase=phase,phase_count=len(subset),
                    sum_driver_wall_seconds=sum(r['driver_wall_seconds'] for r in subset),
                    max_child_peak_rss_bytes=max((r['child_peak_rss_bytes'] for r in subset),default=None)))
        for path in [Path(__file__),Path(__file__).with_name('run_selection_v2.py')]:
            (out/path.name).write_bytes(path.read_bytes())
        receipt=dict(schema='jbgs.local_attempt_costs.v2',status='PASS_FULL18_ATTEMPT_COSTS',scientific_verdict=None,
            task_id=cfg['task_id'],selected_conditions=18,selected_training_attempts=sum(r['selected'] and r['phase']=='train' for r in rows),
            failed_training_attempts=sum(not r['selected'] and r['phase']=='train' for r in rows),phase_groups=groups,
            all_driver_wall_sum_seconds=sum(r['driver_wall_seconds'] for r in rows),
            model_phase_observed_span_seconds=max(r['finished_unix'] for r in rows)-min(r['started_unix'] for r in rows),
            model_phase_interval_union_seconds=interval_union_seconds([(r['started_unix'],r['finished_unix']) for r in rows]),
            inputs=list(inputs.values()),analysis_wall_seconds=time.time()-started,
            analysis_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            limitations=['Phase wall sums include parallel work and are not elapsed calendar time or GPU compute time.',
                'Observed span includes gaps; interval union measures at least one recorded phase active, not exclusive device use.',
                'GPU samples are whole-device usage including desktop/other processes at approximately 5-second intervals; not exact process peak.',
                'Peak RSS cannot be added across phases or subtracted to remove Anchor prefix cost.',
                'Probes, CPU evaluation, QA, queue waiting and historical G/Anchor production costs are separate.',
                'Failed attempts are operational recovery, not independent scientific repeats.'],
            outputs=[dict(path=str(p.relative_to(out)),sha256=digest(p)) for p in sorted(out.iterdir()) if p.is_file()])
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
        print(json.dumps(dict(status=receipt['status'],output=str(out),failed_training_attempts=receipt['failed_training_attempts'],scientific_verdict=None)))
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(status='FAIL',scientific_verdict=None,error=str(error),inputs=list(inputs.values())),indent=2)+'\n')
        raise


if __name__=='__main__':main()
