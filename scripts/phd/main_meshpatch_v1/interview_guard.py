"""Memory guard for one interview computation; no definition changes."""
import sys
from mesh_staged import policy,supervise
from mesh_common import D,dump,now
policy()
tag=sys.argv[1]
r=supervise([sys.executable,*sys.argv[2:]])
dump(D/'interview_v2/execution'/(tag+'.json'),r)
if r['exit_code']:
    dump(D/'interview_v2/status'/(tag+'.json'),dict(job=tag,status='WAIT_RESOURCE_REVIEW' if r['proactive_stop'] or r['oom_kill'] else 'FAILED',
        reason=r.get('stop_reason') or 'execution failed; inspect execution receipt and log',at=now(),execution=r,scientific_verdict=None))
raise SystemExit(0 if r['exit_code']==0 else 1)
