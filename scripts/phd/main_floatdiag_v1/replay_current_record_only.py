"""User-authorized single retry: only finite-opacity threshold becomes a record."""
import runpy
import sys
sys.path.insert(0,'/source')
import jbgs_judgment as J

assert sys.argv[sys.argv.index('--jbgs_sw_depth_loss')+1]=='current'
original_whole=J.lt_whole_stop
original_monitor=J.lt_monitor_step
context={}
def opacity_check(finite,median,offset):
    reason=original_whole(finite,median,offset)
    suppressed=bool(finite and reason=='whole-population opacity median < 0.05 after reset+100')
    j,it=context['j'],context['iteration']
    if it==1 or it%100==0 or reason:
        J.lt_write(j,'floatdiag_opacity_record_only.jsonl',dict(iteration=it,finite=finite,whole_opacity_median=median,
            iterations_after_reset=offset,original_stop=reason,opacity_stop_record_only=suppressed,
            effective_stop=None if suppressed else reason,scientific_verdict=None))
    return None if suppressed else reason
def monitor(j,iteration,*args,**kwargs):
    context.update(j=j,iteration=iteration)
    return original_monitor(j,iteration,*args,**kwargs)
J.lt_whole_stop=opacity_check
J.lt_monitor_step=monitor
runpy.run_path('/repo/scripts/phd/main_floatdiag_v1/replay_observer.py',run_name='__main__')
