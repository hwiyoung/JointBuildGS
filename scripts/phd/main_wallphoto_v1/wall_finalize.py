"""Validate completed measurements and resume packaging without rerunning them."""
import importlib.util
from common import *


def task_packager():
    # Cameras adds an inherited code directory to sys.path. Avoid its package.py.
    path=S/'package.py'
    spec=importlib.util.spec_from_file_location('wallphoto_delivery_package',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve()==path.resolve()
    return module.package


def finalize():
    lock=load(C/'implementation_lock.json')
    assert sha(C/'wallphoto_v1.json')==lock['config_sha256']
    for name,digest in lock['scripts_sha256'].items():assert sha(S/name)==digest,name
    assert load(O/'full_complete.json')['status']=='COMPLETE'
    assert load(O/'gates/full_decision.json')['decision']=='START_FULL'
    assert load(O/'gates/reference_contract.json')['status']=='PASS'
    from wall_validate import main as validate
    validate()
    inv=load(O/'inventory.json');summary=load(O/'full_summary.json')
    assert summary['points']==inv['development']['points']
    assert summary['patches']==inv['development']['patches']
    assert abs(summary['area_m2']-inv['development']['area_m2'])<1e-6
    pilot=O/'pilot_delivery';snap=load(pilot/'manifest.json')
    for row in snap['files']:assert sha(pilot/row['path'])==row['sha256']
    held=load(D/'tables/holdout_totals_hashes.json')
    files=sorted((O/'holdout/points').glob('*__LoD2.npz'))+sorted((O/'holdout/patches').glob('*__LoD2.npz'))
    assert [sha(f) for f in files]==[r['sha256'] for r in held['files']]
    assert held['points']==inv['holdout']['points']
    assert held['patches']==inv['holdout']['patches']
    assert abs(held['area_m2']-inv['holdout']['area_m2'])<1e-6
    # Receipt-level timing is aggregate only; no sealed IDs or per-point values.
    receipts=[]
    for base in [O,O/'holdout']:
        for stage in ['pilot','full']:
            for f in (base/'work'/stage).glob('*.json'):
                r=load(f)
                if 'file_sha256' not in r:continue
                assert r['config_sha256']==lock['config_sha256']
                assert sha(f.with_suffix('.npz'))==r['file_sha256']
                receipts.append(r)
    measured=sum(r['points'] for r in receipts)
    assert measured==inv['development']['points']+inv['holdout']['points']
    checks=dict(at=now(),status='PASS',development_points=summary['points'],development_patches=summary['patches'],sealed_points=held['points'],sealed_patches=held['patches'],pilot_snapshot_files=len(snap['files']),measurement_receipts=len(receipts),measured_points_including_sealed=measured,measurement_elapsed_seconds_sum=sum(r['total_seconds'] for r in receipts),gpu_used=any(r['device']!='cpu' for r in receipts),config_sha256=lock['config_sha256'],scientific_verdict=None)
    dump(D/'tables/finalization_checks.json',checks)
    dump(O/'status.json',dict(at=now(),state='PACKAGING_COMPLETED_MEASUREMENTS',scientific_verdict=None))
    destination=task_packager()('handover')
    receipt=load(destination.with_suffix('.json'))
    for r in receipt['files']:assert sha(destination.parent/r['name'])==r['sha256']
    dump(O/'status.json',dict(at=now(),state='COMPLETE',handover_files=len(receipt['files']),development_points=summary['points'],development_patches=summary['patches'],scientific_verdict=None))
    print('wall task COMPLETE',len(receipt['files']),'handover files',flush=True)


if __name__=='__main__':finalize()
