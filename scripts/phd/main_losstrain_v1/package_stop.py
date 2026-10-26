"""Validate and package a STOPPED partial handover, never a completed experiment."""
import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
import numpy as np
from inputs import OUT, sha, save

def main():
    repo=Path('/repo');docs=Path('/docs');cfg=Path('/config')
    stop=json.loads((OUT/'checks/STOP.json').read_text())
    assert stop['status']=='STOPPED' and stop['training_optimizer_steps']==0
    a=json.loads((docs/'tables/nearest_distance_v2.json').read_text())
    for r in a['rows']:
        h=[p for p in a['histogram'] if all(p[k]==r[k] for k in ['site','prior','scope'])]
        assert sum(p['patches'] for p in h)==r['patches']
        assert abs(sum(p['percent'] for p in h)-100)<1e-8
        assert r['joined_patches']+r['centre_over_18cm']+r['within_18cm_height_over_10cm']+r['within_18cm_unknown_normal']==r['patches']
    for name in ['join_v2','losstrain_v1']:
        lock=json.loads((cfg/f'{name}.lock.json').read_text())
        assert sha(cfg/f'{name}.json')==lock['sha256']
    build=json.loads((docs/'provenance/build_r17.json').read_text())
    for rel,digest in build['parent_hashes'].items():
        assert sha(repo/'src/phd/forks/GeoGS-conf-guided-v1-r16'/rel)==digest,rel
    for rel,digest in build['r17_hashes'].items():
        assert sha(repo/'src/phd/forks/GeoGS-conf-guided-v1-r17'/rel)==digest,rel
    for base in [repo/'scripts/phd/main_losstrain_v1',repo/'src/phd/forks/GeoGS-conf-guided-v1-r17']:
        for p in base.rglob('*.py'):compile(p.read_text(),str(p),'exec')
    for p in OUT.glob('checks/join_v2/*.npz'):
        with np.load(p,allow_pickle=False) as z:
            assert np.isfinite(z['distance_m']).all()
            expected=(z['distance_m']<=.18)&z['normal_defined']&(z['normal_height_stage1_m']<=.10)&(z['normal_height_vfile_m']<=.10)
            assert np.array_equal(z['joined'],expected)
    members=[]
    for root,prefix in [(docs,'docs'),(cfg,'config'),(repo/'scripts/phd/main_losstrain_v1','scripts'),
                        (repo/'src/phd/forks/GeoGS-conf-guided-v1-r17','fork_r17')]:
        members += [(p,prefix+'/'+str(p.relative_to(root))) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    extra=[(p,'payload/'+str(p.relative_to(OUT))) for sub in ['checks','logs','request'] for p in sorted((OUT/sub).rglob('*'))
           if p.is_file() and '/current/' not in str(p)]
    # Interrupted GPU logs and commands are included; no incomplete model output is promoted.
    extra += [(p,'payload/'+str(p.relative_to(OUT))) for p in sorted((OUT/'checks/current').rglob('*'))
              if p.is_file() and p.name in ['run.log','command.json','interrupted.json','receipt.json']]
    receipts=[]
    for light in [True,False]:
        name='PHD-MAIN-LOSSTRAIN-v1_handover'+('_light' if light else '')+'.zip'
        selected=list(members)
        if not light:selected+=extra
        assert len({n for _,n in selected})==len(selected)
        contents={n:p.read_bytes() for p,n in selected}
        status=b'STOPPED PARTIAL HANDOVER\nTraining: 0/4 short, 0/24 primary, 0/6 optional.\nNo scientific conclusion. See docs/decision_log.md and the stop report.\n'
        contents['STATUS.txt']=status
        checksums=''.join(hashlib.sha256(data).hexdigest()+'  '+n+'\n' for n,data in sorted(contents.items()))
        contents['SHA256SUMS']=checksums.encode()
        dest=OUT/name
        assert not dest.exists(),'refuse to replace an immutable delivery'
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for n,data in sorted(contents.items()):z.writestr(n,data)
        assert dest.stat().st_size<400_000_000
        with zipfile.ZipFile(dest) as z:
            assert z.testzip() is None
            for line in z.read('SHA256SUMS').decode().splitlines():
                digest,n=line.split('  ',1)
                assert hashlib.sha256(z.read(n)).hexdigest()==digest
        receipts.append(dict(path=str(dest),bytes=dest.stat().st_size,sha256=sha(dest),members=len(contents),CRC='PASS',member_hashes='PASS'))
    save(OUT/'checks/package_receipt.json',dict(task_id='PHD-MAIN-LOSSTRAIN-v1',status='STOPPED_PARTIAL',
        time=datetime.now().astimezone().isoformat(),validation=dict(report_counts='PASS',config_locks='PASS',
            source_hashes='PASS',join_rule_replay='PASS',python_syntax='PASS'),archives=receipts,scientific_verdict=None))
    print(json.dumps(receipts,indent=2))

if __name__=='__main__':main()
