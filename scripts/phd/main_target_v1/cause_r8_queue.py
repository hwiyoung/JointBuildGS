"""Host stdlib orchestration: independent inference jobs, protected GPU ownership."""
import fcntl,json,subprocess,sys,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[3];P=R.parent/'JointBuildGS-artifacts/phase-payloads/phd';O=P/'main_target_v1/PHD-MAIN-TARGET-v1';D=O/'r8_lod2_cause'
def main():
    gpu, *keys=sys.argv[1:];config=json.loads((R/'configs/phd/main_target_v1/cause_r8_lod2.json').read_text())
    handle=(P/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
    allowed={'/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'}
    active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True)
    assert all(not x.strip() or x.strip() in allowed for x in active.splitlines()),active
    rows={r['key']:r for r in config['rows']}
    for key in keys:
        row=rows[key];root=D/'commands'/key;root.mkdir(parents=True,exist_ok=False)
        old=json.loads((O/'r6/runs/tg_B173nb_b10_ALS_s0_r6/command.json').read_text());cmd=old[:old.index('/repo/scripts/phd/main_target_v1/train_entry_r6.py')]
        cmd[cmd.index('--name')+1]='jbgs-target-cause-r8-'+key.lower();cmd[cmd.index('--gpus')+1]='device='+gpu
        cmd=[x.replace('GeoGS-conf-guided-v1-r20',Path(row['source']).name) for x in cmd]
        cmd+=['/repo/scripts/phd/main_target_v1/cause_r8_render.py',key]
        (root/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');start=time.time()
        with (root/'run.log').open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
        (root/'receipt.json').write_text(json.dumps(dict(exit_code=rc,seconds=time.time()-start,gpu=gpu,optimization_steps=0,scientific_verdict=None),indent=2)+'\n')
        print(key,rc,flush=True)
        if rc:raise SystemExit(rc)
if __name__=='__main__':main()
