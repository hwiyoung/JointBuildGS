"""Release paused queue locks only after its preserved child has exited."""
import signal
from runtime import *


def main():
    root=OUT/'freespace_v1';record=read(root/'legacy_scheduler_yield.json');pid=record['pid']
    path=Path(f'/proc/{pid}/cmdline')
    assert path.exists() and str(SCRIPTS/'mv_followups.py').encode() in path.read_bytes()
    parent=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()
    assert parent[0] in ['T','t']
    children=Path(f'/proc/{pid}/task/{pid}/children').read_text().split();observed=[]
    assert set(children)==set(record['running_children_preserved'])
    for child in children:
        fields=Path(f'/proc/{child}/stat').read_text().rsplit(') ',1)[1].split()
        assert fields[0]=='Z','Live computation must be preserved'
        status=int(fields[49]);assert os.waitstatus_to_exitcode(status)==0
        observed.append(dict(pid=int(child),state='Z',raw_wait_status=status,exit_code=0))
    # The exact child was the existing B0 post stage. Its output is retained;
    # recover its missing host receipt from the kernel's unreaped exit status.
    dest=OUT/'runs/B0_b10/fp_k5_ALS_s0/execution/post'
    cmd=read(dest/'command.json');assert 'jbgs-farpull-post-11' in cmd
    assert '/repo/scripts/phd/main_farpull_v1/post.py' in cmd and cmd[-3:]==['B0_b10','ALS','fp_k5_ALS_s0']
    assert not (dest/'receipt.json').exists()
    save(dest/'receipt.json',dict(observed_at=now(),exit_code=0,status='PASS',seconds=None,
        recovered_from='Linux zombie child wait status after explicitly paused parent scheduler',
        kernel_child=observed,command_sha256=sha(dest/'command.json'),
        exact_start_finish_times='UNAVAILABLE; parent was paused, no timing invented',scientific_verdict=None),True)
    # A queued termination is delivered before the stopped parent can run more
    # Python, so none of its unstarted arms can be dispatched.
    os.kill(pid,signal.SIGTERM);os.kill(pid,signal.SIGCONT)
    save(root/'legacy_scheduler_retired.json',dict(at=now(),pid=pid,state='RETIRED_AFTER_CHILD_SUCCESS',
        preserved_children=observed,recovered_receipt=str(dest/'receipt.json'),
        no_live_compute_signalled=True,automatic_resume=False,scientific_verdict=None),True)
    print('Existing B0 post child completed successfully; scheduler retired, locks released.')


if __name__=='__main__':main()
