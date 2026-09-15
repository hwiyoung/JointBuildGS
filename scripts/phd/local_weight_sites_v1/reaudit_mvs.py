"""Recompute all retained MVS case statistics on exact frozen source rows."""
import argparse
import csv
import hashlib
import json
import shutil
import time
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main(config, art, output, repository):
    started=time.time(); cfg=read(config); base=read(repository/'viewer_v1.json')
    parent=art/cfg['parent_relative']; parent_receipt=read(parent/'build_receipt.json')
    original=read(art/cfg['original_viewer_relative']/'build_receipt.json')
    for name,digest in parent_receipt['files'].items():
        assert sha(parent/'site'/name)==digest,name
    shutil.copytree(parent/'site',output)
    root=art/base['comparison_relative']; search=art/base['search_relative']
    catalog=read(output/'catalog.json'); cache={}; sources={}; rows=[]

    def frozen(path):
        digest=sha(path)
        assert digest==original['source_bindings'][str(path)],str(path)
        sources[str(path)]=digest
        return path

    def stats(values):
        values=np.asarray(values)
        assert len(values) and np.isfinite(values).all()
        return dict(n=len(values),median_m=float(np.median(values)),mean_m=float(np.mean(values)),
                    p90_m=float(np.quantile(values,.9)),max_m=float(np.max(values)),
                    within_counts={str(b):int((values<=b).sum()) for b in cfg['bands_m']},
                    at_distance_cap_count=int((values>=10).sum()))

    for entry in catalog['cases']:
        cid,region=entry['id'],entry['region']; detail=read(output/entry['file'])
        if region not in cache:
            ref=np.load(frozen(root/base['uas_folder']/(region+'_reference.npz')))['xyz']
            ud=np.load(frozen(root/base['uas_folder']/(region+'_uas_distances.npz')))
            pd=np.load(frozen(root/base['uas_folder']/(region+'_uas_to_prior.npy')))
            sd=np.load(frozen(search/'result'/(region+'_sample_diagnostic.npz')))
            cache[region]=(ref,ud,pd,sd,cKDTree(ref))
        ref,ud,pd,sd,tree=cache[region]
        ids=np.array([p['source_row'] for p in detail['photo_views'][0]['points']]) if detail['metric_basis']=='UAS' else np.array(detail['support']['sample_indices'])
        if detail['metric_basis']=='UAS':
            prior,mvs,da3=pd[ids],ud['mvs'][ids],ud['da3'][ids]
            secondary=None
        else:
            prior,mvs,da3=sd['prior_surface_distance'][ids],sd['distance_mvs'][ids],sd['distance_da3'][ids]
            near,nearest=tree.query(sd['xyz'][ids],workers=2)
            ui=np.unique(nearest[near<=.5]); existing=detail['reference']
            assert len(ui)==existing['nearby_unique_uas']
            secondary=dict(unique_uas_count=len(ui),mvs_near_uas_count=int((near<=.5).sum()),
                           source_rows=ui.tolist(),role='SECONDARY_NEARBY_UAS_NOT_SAME_SURFACE_CERTIFICATION',
                           metrics={k:stats(v[ui]) for k,v in [('prior',pd),('mvs',ud['mvs']),('da3',ud['da3'])]} if len(ui) else None)
            if len(ui):
                for k in ['prior','mvs','da3']:
                    assert abs(secondary['metrics'][k]['median_m']-existing['distances_on_nearby_uas'][k]['median'])<1e-8
        current={k:stats(v) for k,v in [('prior',prior),('mvs',mvs),('da3',da3)]}
        for k in current:
            for metric in ['median_m','p90_m']:
                assert abs(current[k][metric]-detail['cohorts']['all']['metrics'][k][metric])<1e-8,(cid,k,metric)
        delta=mvs-prior; change=cfg['paired_change_m']
        paired=dict(definition='same sample: distance to MVS-GeoGS minus distance to prior',
                    median_m=float(np.median(delta)),mean_m=float(np.mean(delta)),
                    farther_count=int((delta>0).sum()),farther_over_01m_count=int((delta>change).sum()),
                    closer_over_01m_count=int((delta < -change).sum()),
                    prior_within_025_mvs_over_05_count=int(((prior<=.25)&(mvs>.5)).sum()))
        cohorts={}
        for name,cohort in detail['cohorts'].items():
            selected=np.array(cohort['indices']); cohorts[name]={k:stats(v[selected]) for k,v in [('prior',prior),('mvs',mvs),('da3',da3)]}
        diagnosis=cfg['classifications'][cid]
        audit=dict(id=cid,title=detail['title'],region=region,zone=detail['zone'],metric_basis=detail['metric_basis'],
                   **diagnosis,metrics=current,paired_prior_comparison=paired,cohorts=cohorts,source_rows=ids.tolist(),
                   secondary_uas=secondary,render_diagnostic=detail.get('view_observations'),
                   reference_layer_audit=detail.get('source_layer_audit'),scientific_verdict=None,
                   limitation='Small point-to-surface distances do not certify reverse completeness, extra surfaces, normals, roof topology, whole-building accuracy or local-weight causality.')
        rows.append(audit); detail['mvs_audit']=audit
        if cid=='C05':
            detail['baseline']='MVS_AND_DA3'
            detail['baseline_note']='DA3 큰 차이 · MVS 작은 보존 손실 별도 검토'
            entry['baseline']=detail['baseline']
        write(output/entry['file'],detail)
        entry['mvs_status']=diagnosis['status']; entry['mvs_label']=diagnosis['label']
        print(cid,diagnosis['status'],'median',round(current['mvs']['median_m'],4),'P90',round(current['mvs']['p90_m'],4),
              'paired >.1m worse',paired['farther_over_01m_count'],'/',len(ids),flush=True)
    audit=dict(task_id=cfg['task_id'],scientific_verdict=None,case_count=len(rows),
               status_counts=dict(Counter(r['status'] for r in rows)),bands_role=cfg['bands_role'],rows=rows,
               summary='C10 is the primary MVS intervention review; C05 retains a smaller preservation-loss question. Close cases and unresolved residuals must not be grouped as no improvement needed.',
               scope='All 20 retained viewer records; not all 161 search components or entire buildings')
    write(output/'assets/mvs_reaudit.json',audit)
    with (output/'assets/mvs_reaudit.csv').open('w') as stream:
        fields=['id','region','zone','metric_basis','n','status','label','prior_median_m','mvs_median_m','mvs_p90_m','mvs_max_m','within_025_count','farther_over_01m_count','paired_median_delta_m','reason']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in rows:
            m=r['metrics']['mvs'];p=r['paired_prior_comparison']
            writer.writerow({**{k:r[k] for k in ['id','region','zone','metric_basis','status','label','reason']},
                'n':m['n'],'prior_median_m':r['metrics']['prior']['median_m'],'mvs_median_m':m['median_m'],
                'mvs_p90_m':m['p90_m'],'mvs_max_m':m['max_m'],'within_025_count':m['within_counts']['0.25'],
                'farther_over_01m_count':p['farther_over_01m_count'],'paired_median_delta_m':p['median_m']})
    catalog.update(task_id=cfg['task_id'],mvs_reaudit='assets/mvs_reaudit.json',mvs_status_counts=audit['status_counts'])
    write(output/'catalog.json',catalog)
    for name in ['index.html','style.css','viewer.js']:
        shutil.copyfile(repository/'src/apps/local_weight_sites_v1'/name,output/name)
    for filename in ['candidate_ledger.md','mvs_reaudit_report.md']:
        shutil.copyfile(repository/filename,output/'assets'/filename)
    table=['\n## 원본 행에서 재집계한 전체 20기록\n',
           '| 사례 | 표본 | n | Prior 중앙값 | MVS 중앙값 | MVS P90 | prior보다 0.1m 넘게 먼 점 | 해석 |',
           '|---|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        m=r['metrics']['mvs']; p=r['paired_prior_comparison']
        table.append(f"| {r['id']} {r['region']} {r['zone']} | {r['metric_basis']} | {m['n']} | {r['metrics']['prior']['median_m']:.3f} | {m['median_m']:.3f} | {m['p90_m']:.3f} | {p['farther_over_01m_count']} | {r['label']} |")
    with (output/'assets/mvs_reaudit_report.md').open('a') as stream:stream.write('\n'.join(table)+'\n')
    for name,digest in parent_receipt['files'].items():
        if name.endswith('.bin') or name.startswith('assets/photo_'):
            assert sha(output/name)==digest,name
    for entry in catalog['cases']:
        old=read(parent/'site'/entry['file']);new=read(output/entry['file'])
        for key in ['cohorts','models','scored','uas','mvs_input','photo_views']:
            assert old[key]==new[key],(entry['id'],key)
    write(output.parent/'audit_receipt.json',dict(status='PASS_ALL_20_MVS_CASE_REAUDIT',task_id=cfg['task_id'],scientific_verdict=None,
          case_count=20,status_counts=audit['status_counts'],source_bindings=sources,
          config_sha256=sha(config),script_sha256=sha(__file__),training_changes=False))
    write(output.parent/'build_receipt.json',dict(status='PASS_VIEWER_DATA_AND_NATIVE_GEOMETRY',task_id=cfg['task_id'],scientific_verdict=None,
          case_count=20,priority_count=6,parent_build_receipt_sha256=sha(parent/'build_receipt.json'),
          geometry_replay_checks=parent_receipt['geometry_replay_checks'],photo_projection_checks=parent_receipt['photo_projection_checks'],
          audit_receipt_sha256=sha(output.parent/'audit_receipt.json'),elapsed_seconds=time.time()-started,
          original_geometry_and_metrics_changed=False,training_changes=False,
          files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ['config','art','output','repository']:parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();main(args.config,args.art,args.output,args.repository)
