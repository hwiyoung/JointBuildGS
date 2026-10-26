"""Host-stdlib launcher: after current comparisons, six checkpoint mask checks."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
import check_current_gpu as C
P=C.P;OUT=C.OUT

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',type=int,default=0)
    ap.add_argument('--units',nargs='+');a=ap.parse_args()
    units=[tuple(x.split('/')) for x in a.units] if a.units else P.UNITS6
    assert all(u in P.UNITS6 for u in units)
    current=OUT/'checks/current_direct_v1'
    assert all(json.loads((current/f'comparison_{s}_{p}.json').read_text())['status']=='PASS' for s,p in units)
    assert json.loads((OUT/'direct_stage1_v2/gates.json').read_text())['gate']=='PASS'
    for site,prior in sorted(units,key=lambda u:u!=('B173nb_b10','ALS')):
        tag=site+'_'+prior;dest=OUT/'checks/depth_direct_v2'/tag;dest.mkdir(parents=True,exist_ok=False)
        base=P.S3/'runs'/site/f'nojudge_{prior}_s0/model'
        ply=base/'point_cloud/iteration_15000/point_cloud.ply';ref=base/'monitor/init_points.npz'
        if not ply.exists() or not ref.exists():ply,ref=P.ckpt_of(site,prior,0)
        args=P.train_args(site,prior,f'/o/checks/depth_direct_v2/{tag}/model',sw_off=['judgment'],schedule=P.SP.SCHEDULE_PROBE)
        args+=['--jbgs_sw_depth_loss','fixed','--jbgs_vfile_dir',f'/o/direct_stage1_v2/{site}__{prior}','--jbgs_vfile_vprior','gt']
        entry=['/repo/scripts/phd/main_losstrain_v1/probe_depth.py','--probe_out',f'/o/checks/depth_direct_v2/{tag}/probe',
            '--probe_ply',P.to_container(ply),'--probe_ref_init',P.to_container(ref),'--',*args,*P.RECORDS]
        command=P.docker('jbgs-lt-depth-'+tag.lower().replace('_','-'),a.gpu,'r17',site,entry)
        command[2:2]=['--memory','48g'];start=time.monotonic()
        (dest/'command.json').write_text(json.dumps(command,indent=2)+'\n')
        with (dest/'run.log').open('w') as log:rc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT).returncode
        receipt=dict(exit_code=rc,seconds=time.monotonic()-start,optimizer_steps=0,
            checkpoint_sha256=hashlib.sha256(ply.read_bytes()).hexdigest(),scientific_verdict=None)
        (dest/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(tag,'actual depth check rc',rc,round(receipt['seconds'],1),'s',flush=True)
        if rc:raise RuntimeError(f'6.3 actual checkpoint STOP: {tag}; see {dest}/run.log')

if __name__=='__main__':main()
