"""Bounded Docker execution for renderer diagnostics; each GPU has its existing lease."""
import os,sys,time,fcntl,subprocess
from r8_screen_prepare import R,A,PH,O,C,j,local,dump,sha
ROOT=O/'rfix'
def main():
 mode,gpu,key=sys.argv[1:4];assert mode in ['build','unit','measure','gradient','train','score','probe_build','probe','extra_unit']
 cfg=j(C/'rfix.json');row=next((r for r in cfg['states'] if r['key']==key),cfg['states'][0]);label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target')
 if mode in ['build','unit','extra_unit']:
  label=key;row=next(r for r in cfg['states'] if {'image_only':'imageonly','geogs':'geogs'}.get(r['family'],'target')==label)
 if mode not in ['build','probe_build']:
  handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
  active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk'] for n in active.splitlines()),'GPU_BUSY'
 cmd=['docker','run','--rm','--read-only','--network','none','--name','jbgs-rfix-'+mode+'-'+key,*(['--runtime','runc'] if mode in ['build','probe_build'] else ['--gpus','device='+gpu]),'--user',f'{os.getuid()}:{os.getgid()}','--cpus','6','--memory','40g','--memory-swap','40g','--shm-size','2g']
 for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=2','OPENBLAS_NUM_THREADS=1','MAX_JOBS=2','TORCH_CUDA_ARCH_LIST=8.6','TMPDIR=/out/tmp','HOME=/out/tmp','MPLCONFIGDIR=/out/tmp/mpl','XDG_CACHE_HOME=/out/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul','JBGS_SPLIT_JSON=/s0/fork_inputs/s61/B173nb_b10/split.json','LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6']:cmd+=['-e',e]
 for src,dst,perm in [(R,'/repo','ro'),(A,'/art','ro'),(PH,'/ph','ro'),(O,'/out','rw'),(C,'/cfg','rw' if mode=='build' else 'ro'),(local(row['source']),'/source','ro'),(local(row['scene']),'/scene','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/p','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61/B173nb_b10/images','/scene/images','ro'),(PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]:cmd+=['-v',f'{src}:{dst}:{perm}']
 script_mode='gradient_fast' if mode=='gradient' else mode
 cmd+=['-w','/source','--entrypoint','python',row['image_id'],'-B','-u','/repo/scripts/phd/main_target_v1/rfix_'+script_mode+'.py',label if mode in ['build','unit','extra_unit'] else key]
 dest=ROOT/'execution';dest.mkdir(exist_ok=True);prefix=mode+'_'+key;dump(dest/(prefix+'_command.json'),cmd)
 with (dest/(prefix+'.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 dump(dest/(prefix+'_receipt.json'),dict(exit_code=rc,at=__import__('datetime').datetime.now().astimezone().isoformat(),scientific_verdict=None));print(mode,key,rc,flush=True);raise SystemExit(rc)
if __name__=='__main__':main()
