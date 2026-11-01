"""Check saved source bindings, including the two documented descriptive corrections."""
import hashlib
from common import *

def read(p):return json.loads(p.read_text())

def main():
    lock=read(CFG/'readout_runtime_r8.r8.lock.json')
    corrections={}  # Earlier descriptive corrections are included in the r5 hashes.
    checked=[]
    for path,digest in lock['files'].items():
        current=sha(REPO/path)
        if path in corrections:
            r=corrections[path];assert digest==r['before'] and current==r['after']
            data=(REPO/path).read_text()
            if Path(path).name=='max_contributor_r8.py':old=data.replace('all depth arrays byte-equal saved r8','all depth arrays byte-equal saved r7')
            elif Path(path).name=='movement_r8.py':old=data.replace('r8 scientific measurement report','r7 scientific measurement report')
            else:raise AssertionError(path)
            assert hashlib.sha256(old.encode()).hexdigest()==r['before']
        else:assert current==digest,path
        checked.append(dict(path=path,sha256=current,descriptive_correction=path in corrections))
    resources=CFG/'readout_resources_r2.json'
    assert sha(resources)==read(CFG/'readout_resources_r2.lock.json')['config_sha256']
    schedule=read(CFG/'readout_schedule_r8.r3.json')
    for path,digest in schedule['files'].items():assert sha(REPO/path)==digest
    result=dict(at=stamp(),status='PASS_READOUT_SOURCE_BINDINGS',files=checked,resource_sha256=sha(resources),schedule_sha256=sha(CFG/'readout_schedule_r8.r3.json'),scientific_verdict=None)
    dump(OUT/'r8/verification/readout_bindings.json',result)
    print(result['status'],len(checked),flush=True)

if __name__=='__main__':main()
