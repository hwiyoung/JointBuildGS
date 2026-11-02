"""Forward-only GPU lane, original source/image, task-local outputs only."""
import os,sys,json,time,fcntl,subprocess
from r8_screen_prepare import R,A,PH,O,C,local,dump
def main():
 gpu=sys.argv[1];keys=sys.argv[2:];assert gpu in ['0','1'];cfg=json.loads((C/'screen_sim.json').read_text());root=O/'screen_sim';(root/'execution').mkdir(exist_ok=True)
 handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks'/f'photo_gpu_{gpu}.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
 active=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True);assert all(not n.strip() or n.strip() in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg'] for n in active.splitlines()),'GPU_BUSY'
 for key in keys:
  r=next(x for x in cfg['states'] if x['key']==key);assert subprocess.check_output(['docker','image','inspect','-f','{{.Id}}',r['image']],text=True).strip()==r['image_id']
  cmd=['docker','run','--rm','--read-only','--network','none','--name','jbgs-sim-'+key,'--gpus','device='+gpu,'--user',f'{os.getuid()}:{os.getgid()}','--cpus','5','--memory','18g','--memory-swap','18g','--shm-size','2g']
  for e in ['PYTHONDONTWRITEBYTECODE=1','PYTHONUNBUFFERED=1','OMP_NUM_THREADS=2','OPENBLAS_NUM_THREADS=1','MAX_JOBS=2','TORCH_CUDA_ARCH_LIST=8.6','TMPDIR=/out/tmp','HOME=/out/tmp','MPLCONFIGDIR=/out/tmp/mpl','XDG_CACHE_HOME=/out/tmp/cache','TORCH_HOME=/weights/torch','TZ=Asia/Seoul','JBGS_SPLIT_JSON=/s0/fork_inputs/s61/B173nb_b10/split.json','LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6']:cmd+=['-e',e]
  for src,dst,mode in [(R,'/repo','ro'),(A,'/art','ro'),(PH,'/ph','ro'),(O,'/out','rw'),(C,'/cfg','ro'),(local(r['source']),'/source','ro'),(local(r['scene']),'/scene','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1','/s0','ro'),(PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61/B173nb_b10/images','/scene/images','ro'),(PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights','/weights','ro')]:cmd+=['-v',f'{src}:{dst}:{mode}']
  cmd+=['-w','/source','--entrypoint','python',r['image'],'-B','-u','/repo/scripts/phd/main_target_v1/screen_sim_render_r2.py',key];dump(root/'execution'/(key+'_r2_command.json'),cmd);start=time.time()
  with (root/'execution'/(key+'_r2.log')).open('x') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
  dump(root/'execution'/(key+'_r2_receipt.json'),dict(exit_code=rc,seconds=time.time()-start,training=False,scientific_verdict=None));assert rc==0,(key,rc)
if __name__=='__main__':main()
