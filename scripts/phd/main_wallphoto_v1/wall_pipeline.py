"""Resumable authorized stages; numeric projection failure stops immediately."""
import traceback
from common import *
from wall_measure import pilot,fallback
from wall_report import report,truth_quality,projection_gate
def main():
    implementation=load(C/'implementation_lock.json')
    assert sha(C/'wallphoto_v1.json')==implementation['config_sha256']
    for name,digest in implementation['scripts_sha256'].items():assert sha(S/name)==digest,name
    assert load(O/'gates/reference_contract.json')['status']=='PASS'
    assert load(O/'gates/core.json')['status']=='PASS'
    from wall_holdout import main as sealed_geometry
    sealed_geometry()
    pilot();truth_quality();report('pilot')
    if load(O/'gates/projection.json')['status']=='FALLBACK_REQUIRED':fallback();report('pilot')
    from wall_replay import main as replay
    replay()
    from wall_figures import figures
    figures('pilot')
    from wall_validate import main as validate
    validate()
    if load(O/'gates/projection.json')['status']!='PASS':
        dump(O/'status.json',dict(at=now(),state='STOP_PROJECTION_REQUIRES_USER',reason='wall order 1.9 and 2.2',scientific_verdict=None));return
    if load(O/'gates/full_decision.json')['decision']!='START_FULL':
        dump(O/'status.json',dict(at=now(),state='COMPLETE_PILOT_ONLY',scientific_verdict=None));return
    from wall_full import main as full
    full();report('full');figures('full')
    validate()
    from package import package
    package('handover')
    dump(O/'status.json',dict(at=now(),state='COMPLETE',scientific_verdict=None))
if __name__=='__main__':
    try:main()
    except Exception:
        error=traceback.format_exc();dump(O/'status.json',dict(at=now(),state='ERROR',error=error,scientific_verdict=None))
        with (D/'issues.md').open('a') as f:f.write('\n'+now()+'\n```\n'+error+'\n```\n')
        raise
