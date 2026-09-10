"""Compare all available G/LC surfaces on fixed historical photo-case identities."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import time
import numpy as np


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def arrays(path, keys):
    with np.load(path, allow_pickle=False) as source:
        return {k: source[k] for k in keys}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['parent', 'evaluation', 'photo_audit', 'config', 'output', 'launcher']:
        parser.add_argument('--'+name.replace('_','-'), type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    require(Path('/.dockerenv').exists(), 'Docker required')
    out = args.output/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    started = time.time();inputs={};rows=[];paired_rows=[];policy_rows=[]

    def bind(path, expected=None):
        actual=sha(path);require(expected is None or actual==expected, 'Digest differs: '+str(path))
        inputs[str(path)]=dict(path=str(path),sha256=actual,bytes=path.stat().st_size)
        return path

    for p in [Path(__file__),args.config,args.launcher]:
        bind(p);shutil.copyfile(p,out/p.name)
    try:
        cfg=read(args.config);er=read(bind(args.evaluation/'receipt.json'));pr=read(bind(args.photo_audit/'receipt.json'))
        require(cfg['scientific_verdict'] is er['scientific_verdict'] is pr['scientific_verdict'] is None,'Verdict forbidden')
        full=er['status']=='COMPLETE_DEVELOPMENT_EVALUATION'
        require(full or args.allow_partial and er['status']=='PARTIAL_DEVELOPMENT_EVALUATION','Full18 required')
        require(pr['status']=='PASS_REUSED_CASES_AND_NATIVE_TARGET_RECOMPUTATION' and len(pr['cases'])==6,'Photo audit differs')
        eo={x['path']:x['sha256'] for x in er['outputs']};ei={x['path']:x['sha256'] for x in er['inputs']}
        po={x['path']:x['sha256'] for x in pr['outputs']}
        require(read(bind(args.evaluation/'config_snapshot.json',eo['config_snapshot.json']))==cfg,'Frozen config differs')
        require(cfg['runtime']['image_id']==os.environ['JBGS_RUNTIME_IMAGE_ID'],'Image differs')
        have={(Path(k).parts[0],Path(k).parts[1]) for k in eo if len(Path(k).parts)==3 and k.endswith('/raw_metrics.json')}
        all_conditions={(r,c['id']) for r in cfg['regions'] for c in cfg['conditions']}
        require(have<=all_conditions and len(have)==er['run_count'],'Evaluation membership differs')
        if full:require(have==all_conditions and len(have)==18,'Incomplete18')
        require(set(er['selected_regions'])==set(cfg['regions']),'All three regions required for six cases')
        th=cfg['evaluation']['paired_primary_threshold_m'];require(th==.5,'Threshold differs')
        keys=['reference_original_indices','reference_points','reference_to_triangle_distance']
        for region in cfg['regions']:
            baseline={};local={}
            for name in ['ANCHOR',*[c['parent_condition'] for c in cfg['conditions']]]:
                suffix='D005_Pnative.anchor_512.raw' if name=='ANCHOR' else name+'.mesh_512.raw'
                p=args.parent/'evaluation/geometry'/region/suffix/'sample0.1_reference0.1.npz'
                baseline[name]=arrays(bind(p,ei[str(p)]),keys)
            for c in cfg['conditions']:
                if (region,c['id']) in have:
                    rel=region+'/'+c['id']+'/raw_distances.npz';local[c['id']]=arrays(bind(args.evaluation/rel,eo[rel]),keys)
            anchor=baseline['ANCHOR'];ids=anchor['reference_original_indices'];xyz=anchor['reference_points']
            for d in [*baseline.values(),*local.values()]:
                require(np.array_equal(d['reference_original_indices'],ids) and np.array_equal(d['reference_points'],xyz),'Reference membership differs')
                distance=d['reference_to_triangle_distance'];require(not np.isnan(distance).any() and np.all(distance>=0),'Invalid distances')
            for case in [c for c in pr['cases'] if c['region']==region]:
                prefix=case['id']+'_'+region;fn=prefix+'_points.npz'
                selected=arrays(bind(args.photo_audit/fn,po[fn]),['original_ids','paired_indices','reference_points',
                    'selected_view_original_ids','selected_view_paired_indices','da3_camera_z','prior_camera_z'])
                indices=selected['paired_indices'];photo_indices=selected['selected_view_paired_indices']
                require(np.array_equal(ids[indices],selected['original_ids']) and np.array_equal(xyz[indices],selected['reference_points']),'Case reference identity differs')
                require(np.array_equal(ids[photo_indices],selected['selected_view_original_ids']) and np.isin(photo_indices,indices).all(),'Photo subset identity differs')
                D=selected['da3_camera_z'];P=selected['prior_camera_z'];valid=np.isfinite(P)&(P>0)
                require(np.isfinite(D).all() and np.all(D>0),'Invalid visual target')
                tau0,tau1=cfg['local_weight']['tau0_m'],cfg['local_weight']['tau1_m']
                ramp=np.clip((np.abs(P[valid]-D[valid])-tau0)/(tau1-tau0),0,1)
                visual=np.ones(len(D));visual[valid]=ramp
                policy_rows.append(dict(case_id=case['id'],region=region,photo=case['photo'],reference_samples=len(D),
                    prior_valid_samples=int(valid.sum()),both_valid_samples=int(valid.sum()),visual_only_samples=int((~valid).sum()),
                    a_zero_both_count=int((ramp==0).sum()),a_one_both_count=int((ramp==1).sum()),
                    mean_a_both=float(ramp.mean()),mean_prior_multiplier_valid=float((1-ramp).mean()),
                    mean_visual_multiplier_valid=float(visual.mean()),
                    sampling='Selected reference points projected to inherited nearest pixels; repeated raster pixels retained; not training-wide pixel or area average',
                    source_correctness_inferred=False,scientific_verdict=None))
                for scope,ii in [('historical_full_case',indices),('selected_photo_strict_subset',photo_indices)]:
                    da=anchor['reference_to_triangle_distance'][ii]
                    for name,d in {**baseline,**local}.items():
                        dist=d['reference_to_triangle_distance'][ii]
                        rows.append(dict(case_id=case['id'],region=region,scope=scope,candidate=name,reference_count=len(ii),threshold_m=th,
                            reference_recall=float(np.mean(dist<th)),reference_distance_median_m=float(np.median(dist)),
                            corrected_vs_anchor=int(np.count_nonzero((da>=th)&(dist<th))),
                            damaged_vs_anchor=int(np.count_nonzero((da<th)&(dist>=th))),scientific_verdict=None))
                    for c in cfg['conditions']:
                        if c['id'] not in local:continue
                        dg=baseline[c['parent_condition']]['reference_to_triangle_distance'][ii];dl=local[c['id']]['reference_to_triangle_distance'][ii]
                        an,gn,ln=da<th,dg<th,dl<th
                        corrected=int(np.count_nonzero(~gn&ln));damaged=int(np.count_nonzero(gn&~ln))
                        require(corrected-damaged==int(ln.sum())-int(gn.sum()),'Transition accounting differs')
                        paired_rows.append(dict(case_id=case['id'],region=region,scope=scope,condition=c['id'],parent_condition=c['parent_condition'],
                            reference_count=len(ii),threshold_m=th,global_recall=float(gn.mean()),local_recall=float(ln.mean()),
                            corrected_count=corrected,damaged_count=damaged,
                            global_correction_retained=int(np.count_nonzero(~an&gn&ln)),global_correction_lost=int(np.count_nonzero(~an&gn&~ln)),
                            global_damage_recovered=int(np.count_nonzero(an&~gn&ln)),additional_local_damage=int(np.count_nonzero(an&gn&~ln)),
                            scientific_verdict=None))
        write_csv(out/'all_methods.csv',rows);write_csv(out/'paired_changes.csv',paired_rows);write_csv(out/'selected_photo_policy.csv',policy_rows)
        require(len(policy_rows)==6 and len(paired_rows)==len(have)*4,'Case row count differs')
        outputs=[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(out.iterdir()) if p.is_file()]
        receipt=dict(schema='jbgs.local_photo_case_comparison.v2',status='PASS_FULL18_CASE_COMPARISON' if full else 'PASS_PARTIAL_CASE_COMPARISON',
            scientific_verdict=None,run_count=len(have),case_count=6,paired_rows=len(paired_rows),inputs=list(inputs.values()),outputs=outputs,
            command=sys.argv,wall_seconds=time.time()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            versions=dict(python=platform.python_version(),numpy=np.__version__),
            runtime=dict(image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'],cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip()),
            reference_used_for_training_or_parameter_selection=False,
            limitations=['Fixed historical posthoc cases, not population samples or independent training repeats.',
                         'Photo subset and full-case denominators remain separate; reference proximity is not accuracy, area or temporal truth.',
                         'Local policy averages use repeated projected reference samples, not all training pixels.',
                         'No mean-multiplier global control, controller replay or DA3-only causality.'])
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(dict(status=receipt['status'],output=str(out),paired_rows=len(paired_rows),scientific_verdict=None)))
    except Exception as exc:
        (out/'failure.json').write_text(json.dumps(dict(status='FAIL',error=repr(exc),inputs=list(inputs.values()),scientific_verdict=None),indent=2)+'\n')
        raise


if __name__=='__main__':main()
