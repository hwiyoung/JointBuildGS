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
    if a.status=='COMPLETE':assert len(required)==24 and len(post)==len(full)
    else:assert (OUT/'checks/full_grace_STOP.json').exists()
    status=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',status=a.status,calibration_complete=len(cal),required_training_complete=len(required),
        optional_training_complete=len(optional),postprocessing_complete=len(post),new_stop_receipts=len(stopped),
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
        if p.name in ['receipt.json','command.json']:members.append((p,'run_receipts/'+p.relative_to(OUT/'runs').as_posix()))
    for p in sorted((OUT/'runs').glob('*/*/attempt_*/model/monitor/losstrain_*.jsonl')):
        members.append((p,'run_receipts/'+p.relative_to(OUT/'runs').as_posix()))
    for p in sorted((OUT/'checks/opacity_grace_v1').glob('*.json')):members.append((p,'checks/opacity_grace_v1/'+p.name))
    for name in ['full_STOP.json','full_grace_STOP.json','lambda_selection.json','preparation_commit.json']:
        p=OUT/'checks'/name
        if p.exists():members.append((p,'checks/'+name))
    report=Path('/docs/손실학습시험_보고_v1.md');assert len(report.read_text())<=20000
    receipts=[]
    for light in [True,False]:
        selected=list(members)
        if not light:selected += [(p,'patch_z/'+p.name) for p in sorted((OUT/'patch_z').glob('*.npz'))]
        assert len(selected)==len({n for _,n in selected})
        hashes={name:sha(p) for p,name in selected}
        checksum=''.join(hashes[n]+'  '+n+'\n' for n in sorted(hashes)).encode()
        dest=root/('PHD-MAIN-LOSSTRAIN-v1_handover'+('_light' if light else '')+'.zip')
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p,n in selected:z.write(p,n)
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
