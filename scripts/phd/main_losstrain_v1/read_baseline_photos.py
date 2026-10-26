"""Host Docker driver for authorized existing-model photo measurements; no training."""
import argparse
import subprocess
import time
import json
import train_calibration as C

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',type=int,required=True);ap.add_argument('--site');ap.add_argument('--prior');a=ap.parse_args()
    for site,prior in C.P.UNITS6:
        if (a.site and site!=a.site) or (a.prior and prior!=a.prior):continue
        for result in [f'nojudge_{prior}_s0',f'prop_{prior}_s0',f'prop_{prior}_s1']:
            dest=C.OUT/'photo'/site/result
            if (dest/'receipt.json').exists():
                assert json.loads((dest/'receipt.json').read_text())['exit_code']==0
                print(site,result,'reuse own completed readout',flush=True);continue
            assert not dest.exists(),dest
            cmd=C.P.docker('jbgs-lt-baseline-photo-'+str(a.gpu),a.gpu,'r17',site,
                ['/repo/scripts/phd/main_losstrain_v1/baseline_photo_gpu.py',site,prior,result])
            idx=cmd.index(C.P.IMG);cmd[idx:idx]=['-v',f'{C.P.S0}:/s0:ro','-v',f'{C.P.S1}:/out:ro']
            cmd[2:2]=['--memory','48g']
            for attempt in [0,1]:
                log=C.OUT/'logs'/f'photo_{site}_{result}_a{attempt}.log';assert not log.exists()
                C.save(log.with_suffix('.command.json'),cmd);start=time.monotonic()
                with log.open('w') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
                rec=dict(exit_code=rc,attempt=attempt,seconds=time.monotonic()-start,at=C.now(),command=cmd,optimizer_steps=0,scientific_verdict=None)
                dest.mkdir(parents=True,exist_ok=True);C.save(dest/'receipt.json',rec)
                if rc:
                    oom='out of memory' in log.read_text().lower()
                    if oom and attempt==0:dest.rename(dest.with_name(dest.name+'_oom_attempt_0'));continue
                    C.save(C.OUT/'checks/baseline_photo_STOP.json',dict(site=site,prior=prior,result=result,**rec));raise SystemExit('baseline photo readout stopped; see log')
                assert (dest/'train_quality.json').exists();print(site,result,'all-view photo PASS',flush=True);break

if __name__=='__main__':main()
