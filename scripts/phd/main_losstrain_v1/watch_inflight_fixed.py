"""Apply the approved PSNR gate to the already-loaded fixed arm; host stdlib."""
import re,time,subprocess,json
from train_calibration import OUT,save,now

def main():
    unit=OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0';sub=unit/'attempt_1'
    baseline=json.loads((OUT/'checks/monitor_v2/nojudge/B173nb_b10__ALS.json').read_text())
    refs={x['iteration']:x['psnr_db'] for x in baseline['train_psnr_legacy5']}
    found={}
    while True:
        log=(sub/'run.log').read_text()
        for it,value in re.findall(r'\[ITER (\d+)\] Evaluating train: L1 \S+ PSNR (\S+)',log):
            it=int(it);value=float(value)
            if it in refs:found[it]=dict(iteration=it,train_psnr_legacy5=value,nojudge_train_psnr_legacy5=refs[it],drop_db=refs[it]-value,stop=refs[it]-value>3.)
        save(OUT/'checks/monitor_v2/inflight_fixed_psnr.json',dict(at=now(),rows=list(found.values()),scientific_verdict=None))
        failure=next((x for x in found.values() if x['stop']),None)
        if failure:
            row=dict(at=now(),run=dict(site='B173nb_b10',prior='ALS',variant='lt_fixgt'),attempt=1,
                reason='training PSNR more than 3 dB below same-iteration nojudge',comparison=failure,scientific_verdict=None)
            save(OUT/'checks/full_monitor_v2_STOP.json',row);save(unit/'STOP_monitor_v2.json',row)
            subprocess.run(['docker','stop','--time','10','jbgs-lt-full-0'],check=False)
            print('FIXED PSNR STOP',failure,flush=True);return
        if 30000 in found:
            print('fixed all three PSNR checks PASS',found,flush=True);return
        if (sub/'receipt.json').exists():
            print('fixed training ended; available PSNR checks',found,flush=True);return
        time.sleep(5)

if __name__=='__main__':main()
