"""Use whichever GPU becomes free for the remaining four read-only states."""
import os,sys,time,subprocess
from pathlib import Path
from r8_screen_prepare import O,dump
ROOT=O/'rfix';KEYS=['base_ALS_30000','r7_LoD2_30000','image_only_2DGS_30000','GeoGS_ALS_30000']
DISPLAY=['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk']
def free(gpu):
 names=subprocess.check_output(['nvidia-smi','-i',str(gpu),'--query-compute-apps=process_name','--format=csv,noheader'],text=True).splitlines();return all(not x.strip() or x.strip() in DISPLAY for x in names)
def worker(gpu,key):
 for mode in ['measure','gradient']:
  rc=subprocess.call([sys.executable,str(Path(__file__).with_name('rfix_launch.py')),mode,str(gpu),key]);assert rc==0,(key,mode,rc)
def main():
 if len(sys.argv)>1:return worker(int(sys.argv[1]),sys.argv[2])
 pending=KEYS.copy();active={};complete=[];failed=[]
 while pending or active:
  for gpu,(key,p) in list(active.items()):
   rc=p.poll()
   if rc is None:continue
   (complete if rc==0 else failed).append(key);del active[gpu];print('REMAINING_DONE',gpu,key,rc,flush=True)
  if failed:pending=[]
  for gpu in [0,1]:
   if not pending or failed:break
   if gpu in active or not free(gpu):continue
   key=pending.pop(0);assert not (ROOT/'states'/key).exists(),key
   p=subprocess.Popen([sys.executable,str(Path(__file__)),str(gpu),key]);active[gpu]=(key,p);print('REMAINING_START',gpu,key,p.pid,flush=True)
  if pending or active:time.sleep(10)
 dump(ROOT/'queue_remaining.json',dict(completed=complete,failed=failed,scientific_verdict=None));assert not failed,failed
if __name__=='__main__':main()
