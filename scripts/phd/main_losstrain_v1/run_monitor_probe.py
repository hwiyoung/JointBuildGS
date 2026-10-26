"""Host launcher for one no-optimizer B173 ALS monitoring integration check."""
import subprocess
from train_calibration import OUT,P,save,now

def main():
    root=OUT/'checks/monitor_v2/gpu_probe';root.mkdir(exist_ok=False)
    args=P.train_args('B173nb_b10','ALS',P.to_container(root/'model'),sw_off=['judgment'])
    args+=['--jbgs_sw_depth_loss','dynamic','--jbgs_vfile_dir','/o/direct_stage1_v2/B173nb_b10__ALS',
        '--jbgs_vfile_vprior','gt','--jbgs_depth_lambda','0.0025','--jbgs_lt_monitor','1','--jbgs_lt_monitor_v2','1',
        '--jbgs_lt_nojudge_inventory','/o/checks/monitor_v2/nojudge/B173nb_b10__ALS.json',
        '--jbgs_lt_diagnostic_cells','/o/direct_stage1_v2/B173nb_b10__ALS/evaluation.npz',*P.RECORDS]
    command=P.docker('jbgs-lt-monitor-v2-probe',1,'r17','B173nb_b10',['/repo/scripts/phd/main_losstrain_v1/probe_monitor_v2.py',*args])
    command[2:2]=['--memory','48g'];save(root/'command.json',command)
    with (root/'run.log').open('w') as f:rc=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT).returncode
    save(root/'receipt.json',dict(at=now(),exit_code=rc,optimizer_steps=0,scientific_verdict=None))
    assert rc==0,root/'run.log'
    print('monitor v2 GPU probe PASS')

if __name__=='__main__':main()
