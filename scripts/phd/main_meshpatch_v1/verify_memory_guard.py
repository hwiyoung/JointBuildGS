"""Exercise proactive termination, normal exit and cgroup OOM distinction."""
import sys
from mesh_common import D, dump, now
from mesh_staged import memory, supervise

start=memory()['current_bytes']
guard=supervise([sys.executable,'-c','import time; a=bytearray(256*1024**2); time.sleep(30)'],start+128*1024**2)
assert guard['proactive_stop'] and not guard['oom_kill'] and guard['exit_code']!=0
normal=supervise([sys.executable,'-c','assert 2+2==4'])
assert normal['exit_code']==0 and not normal['proactive_stop'] and not normal['oom_kill']
dump(D/'tables/memory_guard_validation.json',dict(status='PASS',guard=guard,normal=normal,at=now(),scientific_verdict=None))
print('PASS: process guard stopped allocating child before cgroup OOM; normal child completed')
