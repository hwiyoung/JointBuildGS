"""Finite read-only parity queue; exits on a failure and never starts training."""
import sys,subprocess
from r8_screen_prepare import *
gpu=sys.argv[1];keys=[r['key'] for r in j(C/'rfix.json')['states']]
if len(sys.argv)>2:keys=keys[int(sys.argv[2])::2]
for mode in ['measure','gradient']:
 for key in keys:
  dest=O/'rfix_speed'/('states' if mode=='measure' else 'gradients')/key/'result.json'
  if dest.exists():assert j(dest)['status']=='PASS';continue
  subprocess.run([sys.executable,str(R/'scripts/phd/main_target_v1/rfix_speed_launch.py'),mode,key,gpu],check=True)
  assert j(dest)['status']=='PASS',(mode,key)
print('SPEED_QUEUE_COMPLETE',gpu,flush=True)
