"""Compare actual old/new training commands after removing output/record-only flags."""
import json
from train_calibration import OUT,REPO,save,sha,now

RECORD_FLAGS={'--jbgs_lt_monitor','--jbgs_lt_monitor_v2','--jbgs_lt_opacity_reset_grace',
    '--jbgs_lt_nojudge_opacity','--jbgs_lt_nojudge_inventory','--jbgs_lt_diagnostic_cells'}

def strip(command):
    args=command[command.index('train.py')+1:];kept=[];records={};i=0
    while i<len(args):
        flag=args[i]
        if flag in RECORD_FLAGS or flag in ['-m','--model_path']:
            records[flag]=args[i+1];i+=2
        else:kept.append(flag);i+=1
    return kept,records

def main():
    unit=OUT/'runs/B173nb_b10/lt_dyngt_ALS_s0'
    old=unit/'attempt_1/command.json';new=unit/'attempt_3/command.json'
    a,ar=strip(json.loads(old.read_text()));b,br=strip(json.loads(new.read_text()))
    assert a==b,'non-observational training arguments changed'
    row=dict(status='PASS',at=now(),old_command=str(old),old_sha256=sha(old),new_command=str(new),new_sha256=sha(new),
        identical_training_arguments=a,old_record_output_flags=ar,new_record_output_flags=br,
        definition='all arguments identical after removing model output path and explicit observation flags; source loss bytes separately verified',
        scientific_verdict=None)
    save(OUT/'checks/monitor_v2/camera_fix/argument_comparison.json',row)
    save(REPO/'docs/experiments/phd/main_losstrain_v1/provenance/restart_argument_comparison.json',row)
    print('old/new dynamic-GT training arguments identical except output and observation flags PASS')

if __name__=='__main__':main()
