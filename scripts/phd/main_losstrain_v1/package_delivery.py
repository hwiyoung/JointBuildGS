"""Versioned handover: current reports, explicit completion status, SHA-256 and CRC."""
import argparse
import hashlib
import json
import zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from inputs import OUT,save,sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',required=True);ap.add_argument('--status',choices=['STOPPED_PARTIAL','COMPLETE'],required=True);a=ap.parse_args()
    assert a.revision.replace('_','').isalnum()
    cfg=Path('/config/losstrain_v1.json');assert sha(cfg)==json.loads(cfg.with_suffix('.lock.json').read_text())['sha256']
    root=OUT/'deliveries'/a.revision;root.mkdir(parents=True,exist_ok=False)
    full=[p for p in (OUT/'runs').glob('*/*/PASS.json') if not p.parent.name.startswith('lt_cal_')]
    post=list((OUT/'runs').glob('*/*/post_PASS.json'));cal=list((OUT/'runs').glob('*/lt_cal_*/PASS.json'))
    required=[p for p in full if not p.parent.name.startswith('lt_fixnow')];optional=[p for p in full if p.parent.name.startswith('lt_fixnow')]
    stopped=list((OUT/'runs').glob('*/*/STOP_attempt_*.json'))
    if a.status=='COMPLETE':
        assert len(required)==24 and len(post)==len(full)
        assert all((p.parent/'measure_PASS.json').exists() for p in full)
        variants={'lt_fixgt','lt_dyngt','lt_dynsoft','lt_dynnow'}
        if optional:
            assert len(optional)==6
            variants.add('lt_fixnow')
        photo=json.loads(Path('/docs/tables/photo.json').read_text())['rows']
        photo_index={(r['site'],r['result']):r for r in photo}
        for p in full:
            site,result=p.parent.parent.name,p.parent.name
            q=photo_index[(site,result)]
            assert q['eval_views']>0 and q['training_views']>0 and q['unavailable'] is None
            for iteration in [15000,30000]:
                assert (Path('/docs/tables/opacity_saved')/site/result/f'{iteration}.json').exists()
        for q in photo:
            assert q['eval_views']>0 and q['training_views']>0 and q['unavailable'] is None
        expected=['section_B173nb_b10_ALS_0','section_B173nb_b10_LoD2_0','section_R1rep_b10_LoD2_1','section_R1rep_b10_ALS_2',
            'render_B173nb_b10_ALS','render_B173nb_b10_LoD2']
        expected += [prefix+'_'+site+'_'+prior for prefix in ['map','side_map','fates'] for site in ['B0_b10','B173nb_b10','R1rep_b10'] for prior in ['LoD2','ALS']]
        for key in expected:
            meta=Path('/docs/figures')/(key+'.json')
            assert meta.exists() and meta.with_suffix('.png').exists(),key
            m=json.loads(meta.read_text());assert m['visual_review']=='PASS',key
            if key.startswith('section_'):assert set(m['panels'])==variants,key
            elif key.startswith('map_'):assert {r['variant'] for r in m['panels']}==variants|{'analytic'},key
            elif key.startswith('fates_'):
                assert len(m['rows'])==len(variants)+1,key
                assert {r['result'].rsplit('_',2)[0] for r in m['rows'] if r['result'].startswith('lt_')}==variants,key
            elif key.startswith('render_'):assert len(m['panels'])==len(variants)+1,key
    else:assert any((OUT/'checks').glob('*STOP.json'))
    status=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',status=a.status,calibration_complete=len(cal),required_training_complete=len(required),
        optional_training_complete=len(optional),postprocessing_complete=len(post),preserved_attempt_stop_files=len(stopped),
        historical_pre_amendment_opacity_stops=2,at=datetime.now(timezone(timedelta(hours=9))).isoformat(),scientific_verdict=None)
    save(root/'STATUS.json',status)
    members=[]
    for folder,prefix in [(Path('/docs'),'docs'),(Path('/config'),'config'),(Path('/repo/scripts/phd/main_losstrain_v1'),'scripts'),
        (Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r17'),'fork_r17')]:
        for p in sorted(folder.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
            if p.suffix=='.py':compile(p.read_text(),str(p),'exec')
            members.append((p,prefix+'/'+p.relative_to(folder).as_posix()))
    members.append((root/'STATUS.json','STATUS.json'))
    # Compact factual receipts, never incomplete Gaussian checkpoints or holdout payloads.
    for p in sorted((OUT/'runs').glob('*/*/attempt_*/*')):
        if p.name in ['receipt.json','command.json','start_binding.json','receipt_at_completion_unadjusted.json']:
            members.append((p,'run_receipts/'+p.relative_to(OUT/'runs').as_posix()))
    for p in sorted((OUT/'runs').glob('*/*/*.json')):
        members.append((p,'run_receipts/'+p.relative_to(OUT/'runs').as_posix()))
    for p in sorted((OUT/'runs').glob('*/*/attempt_*/model/monitor/losstrain_*.jsonl')):
        members.append((p,'run_receipts/'+p.relative_to(OUT/'runs').as_posix()))
    for p in sorted((OUT/'checks/opacity_grace_v1').glob('*.json')):members.append((p,'checks/opacity_grace_v1/'+p.name))
    for p in sorted((OUT/'checks/monitor_v2').rglob('*.json')):
        if any(x in p.parts for x in ['rebuilt_fork','rebuild_docs','before','model','synthetic']):continue
        members.append((p,'checks/monitor_v2/'+p.relative_to(OUT/'checks/monitor_v2').as_posix()))
    for p in sorted((OUT/'checks/fixed_post_host_oom').glob('*')):
        if p.is_file():members.append((p,'checks/fixed_post_host_oom/'+p.name))
    for p in sorted((OUT/'logs').glob('*.queue_seconds.txt')):
        members.append((p,'cpu_queue_receipts/'+p.name))
    for name in ['full_STOP.json','full_grace_STOP.json','full_monitor_v2_STOP.json','full_monitor_v2_camera_fix_STOP.json','lambda_selection.json','preparation_commit.json']:
        p=OUT/'checks'/name
        if p.exists():members.append((p,'checks/'+name))
    report=Path('/docs/손실학습시험_보고_v1.md');assert len(report.read_text())<=20000
    receipts=[]
    for light in [True,False]:
        selected=list(members)
        if not light:selected += [(p,'patch_z/'+p.name) for p in sorted((OUT/'patch_z').glob('*.npz'))]
        assert len(selected)==len({n for _,n in selected})
        # Freeze each member once; an independently running arm may append logs.
        payloads={name:p.read_bytes() for p,name in selected}
        hashes={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
        checksum=''.join(hashes[n]+'  '+n+'\n' for n in sorted(hashes)).encode()
        dest=root/('PHD-MAIN-LOSSTRAIN-v1_handover'+('_light' if light else '')+'.zip')
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p,n in selected:z.writestr(n,payloads[n])
            z.writestr('SHA256SUMS',checksum)
        assert dest.stat().st_size<400_000_000,'split required; do not ship oversized archive'
        with zipfile.ZipFile(dest) as z:
            assert z.testzip() is None
            for line in z.read('SHA256SUMS').decode().splitlines():
                digest,n=line.split('  ',1);assert hashlib.sha256(z.read(n)).hexdigest()==digest,n
        receipts.append(dict(path=str(dest),bytes=dest.stat().st_size,sha256=sha(dest),CRC='PASS',member_hashes='PASS',members=len(selected)+1))
    save(root/'receipt.json',dict(**status,archives=receipts));save('/docs/provenance/delivery_'+a.revision+'.json',dict(**status,archives=receipts))
    print(json.dumps(receipts,indent=2),flush=True)

if __name__=='__main__':main()
