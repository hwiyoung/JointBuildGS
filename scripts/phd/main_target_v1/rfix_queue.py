"""Read-only validation queue; no implicit training or retry after execution failure."""
import sys,time,subprocess
from r8_screen_prepare import O,C,j,dump
ROOT=O/'rfix'
def wait_free(gpu):
 while True:
  apps=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-compute-apps=process_name','--format=csv,noheader'],text=True).splitlines()
  busy=[x for x in apps if x.strip() and x.strip() not in ['/usr/libexec/gnome-remote-desktop-daemon','/usr/lib/xorg/Xorg','/usr/share/rustdesk/rustdesk']]
  if not busy:return
  time.sleep(10)
def main():
 gpu=sys.argv[1];keys=sys.argv[2:];rows=j(C/'rfix.json')['states']
 for key in keys:
  row=next(r for r in rows if r['key']==key);label={'image_only':'imageonly','geogs':'geogs'}.get(row['family'],'target')
  operations=[('unit',label,ROOT/'units'/label/'result.json'),('measure',key,ROOT/'states'/key/'result.json'),('gradient',key,ROOT/'gradients'/key/'result.json')]
  for mode,arg,result in operations:
   if result.exists():continue
   # A separately launched existing measurement owns its GPU until complete.
   wait_free(gpu)
   if result.exists():continue
   rc=subprocess.call([sys.executable,str(__import__('pathlib').Path(__file__).with_name('rfix_launch.py')),mode,gpu,arg]);assert rc==0,(mode,arg,rc)
 dump(ROOT/f'queue_gpu{gpu}.json',dict(status='COMPLETE_VALIDATION_QUEUE',keys=keys,scientific_verdict=None))
if __name__=='__main__':main()
