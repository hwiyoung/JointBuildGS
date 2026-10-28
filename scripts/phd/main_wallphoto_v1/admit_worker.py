"""Durable low-memory wait before entering the 12 GiB CPU measurement job."""
import os,time,sys
from common import *
def main():
    start=time.monotonic();stable=0
    while stable<60:
        peer=Path('/art/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/status')
        states={}
        for prior in ['LoD2','ALS']:
            path=peer/f'patch_{prior}.json'
            states[prior]=load(path).get('stage') if path.exists() else 'not_started'
        task3_complete=all(x=='table_complete' for x in states.values())
        threshold=28 if task3_complete else 68
        mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if ':' in line and line.split()[1].isdigit()}
        available=mem['MemAvailable']/2**30
        stable=stable+15 if available>=threshold else 0
        rec=dict(at=now(),state='RESOURCE_WAIT',mem_available_gib=available,required_available_gib=threshold,meshpatch_reserved_gib=56 if not task3_complete else 16,meshpatch_task3_stages=states,own_cap_gib=12,wait_seconds=time.monotonic()-start,stable_seconds=stable,scientific_verdict=None)
        dump(O/'status.json',rec)
        with (O/'logs/resource_wait.jsonl').open('a') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n')
        if stable<60:time.sleep(15)
    dump(O/'admission.json',dict(at=now(),wait_seconds=time.monotonic()-start,threshold_gib=threshold,meshpatch_task3_stages=states,stable_seconds=60,scientific_verdict=None))
    os.execv(sys.executable, [sys.executable,'-B','-u',str(S/'wall_pipeline.py')])
if __name__=='__main__':main()
