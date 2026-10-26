"""Preserve the confirmed host-OOM event and retry only fixed's post, once.

No training/model or postprocessing argument changes. The completed model is read.
Admission waits for 48 GiB container limit plus 8 GiB host headroom.
"""
import fcntl
import json
import subprocess
import time
from pathlib import Path
import train_calibration as C


def available_gib():
    values=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(values['MemAvailable'].split()[0])/1024**2


def main():
    unit=C.OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0'
    record=C.OUT/'checks/fixed_post_host_oom'
    record.mkdir(exist_ok=True)
    assert not (record/'preparation.json').exists() and not (unit/'post_attempt_1.log').exists()
    receipt=json.loads((unit/'post_attempt_0_receipt.json').read_text())
    assert receipt['exit_code']==137 and (unit/'PASS.json').exists()
    until=str(int(time.time()))
    events=subprocess.run(['docker','events','--since','2026-10-26T20:12:00+09:00','--until',until,
        '--filter','container=jbgs-lt-post-0','--format','{{json .}}'],capture_output=True,text=True,check=True).stdout
    (record/'docker_events.jsonl').write_text(events)
    decoded=[json.loads(x) for x in events.splitlines()]
    # Docker keeps a small event ring; the persistent kernel record below is the
    # authority if this already-observed container's events have aged out.
    docker_oom=any(x.get('Action')=='oom' for x in decoded)
    kernel=subprocess.run(['journalctl','-k','--since','2026-10-26 20:18:50','--until','2026-10-26 20:19:10','--no-pager'],capture_output=True,text=True,check=True).stdout
    relevant='\n'.join(x for x in kernel.splitlines() if 'oom-kill:' in x or 'Killed process 290200' in x)+'\n'
    assert 'global_oom' in relevant and 'docker-2ac92009756efa74f' in relevant and 'Killed process 290200' in relevant
    (record/'kernel_oom.txt').write_text(relevant)
    # The historical runner reused its shared stop filename. Preserve the new
    # event separately, then restore the exact historical bytes bound by approval.
    shared=C.OUT/'checks/full_grace_STOP.json'
    old=C.OUT/'runs/B173nb_b10/lt_dyngt_ALS_s0/STOP_attempt_1.json'
    approval=json.loads((C.OUT/'checks/monitor_v2/approval.json').read_text())
    assert C.sha(old)==approval['superseded_stops']['checks/full_grace_STOP.json']
    current=json.loads(shared.read_text())
    assert current['reason']=='postprocessing post execution error' and current['run']['variant']=='lt_fixgt'
    (record/'shared_stop_before_restoration.json').write_bytes(shared.read_bytes())
    (unit/'post_STOP_attempt_0.json').write_bytes(shared.read_bytes())
    shared.write_bytes(old.read_bytes())
    # The attempt-named copy is retained too; its reason explicitly says post.
    command=json.loads((unit/'post_command.json').read_text())
    assert command[command.index('--memory')+1]=='48g'
    assert command[-4:]==['post','B173nb_b10','lt_fixgt_ALS_s0','ALS']
    C.save(record/'preparation.json',dict(at=C.now(),status='WAITING_FOR_MEMORY',
        error='confirmed host global OOM, not CUDA OOM',training_iteration=30000,
        docker_event_ring_status='OOM retained' if docker_oom else 'earlier read observed OOM/die; ring no longer retains it; persistent kernel evidence used',
        training_restarted=False,post_retry_limit=1,required_available_GiB=56,
        restored_historical_stop_sha256=C.sha(shared),command_sha256=C.sha(unit/'post_command.json'),
        original_receipt=receipt,scientific_verdict=None))
    C.save(C.REPO/'docs/experiments/phd/main_losstrain_v1/provenance/fixed_post_host_oom.json',
        json.loads((record/'preparation.json').read_text()))
    with (C.OUT/'checks/tsdf.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        start=time.monotonic()
        while available_gib()<56:
            C.save(record/'memory_wait.json',dict(at=C.now(),available_GiB=available_gib(),required_GiB=56,seconds=time.monotonic()-start,scientific_verdict=None))
            time.sleep(10)
        wait=time.monotonic()-start
        (unit/'post').rename(unit/'post_attempt_0_host_oom')
        for mode,attempt in [('post',1),('run',0)]:
            cmd=list(command);cmd[-4]=mode
            C.save(unit/(mode+'_command.json'),cmd)
            log=unit/f'{mode}_attempt_{attempt}.log';assert not log.exists()
            t=time.monotonic()
            with log.open('w') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
            C.save(unit/f'{mode}_attempt_{attempt}_receipt.json',dict(exit_code=rc,seconds=time.monotonic()-t,
                tsdf_queue_seconds=wait if mode=='post' else 0,at=C.now(),host_oom_recovery=True,scientific_verdict=None))
            if rc:
                stop=dict(run=dict(site='B173nb_b10',prior='ALS',variant='lt_fixgt'),attempt=attempt,
                    reason='postprocessing '+mode+' failed after confirmed host-OOM retry',at=C.now(),
                    known_same_arm_stops=3,requires_user=True,scientific_verdict=None)
                C.save(unit/'STOP_monitor_v2.json',stop);C.save(record/'STOP.json',stop)
                raise SystemExit('Fixed arm post retry failed; preserve output and ask user.')
            print('fixed',mode,'PASS',flush=True)
        C.save(unit/'post_PASS.json',dict(at=C.now(),recovered_host_oom=True,scientific_verdict=None))
        C.save(record/'PASS.json',dict(at=C.now(),same_post_parameters=True,training_restarted=False,scientific_verdict=None))


if __name__=='__main__':main()
