"""Host resource adapter; same numerical programs and 16 GiB reserve."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
from run_pilot_r7 import REPO,PH,OUT,CFG
def cpu(tag,script,args,heavy=False):
 handle=None
 if heavy:
  handle=(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock').open('r');fcntl.flock(handle,fcntl.LOCK_EX)
  stable=0
  while stable<15:
   lines=Path('/proc/meminfo').read_text().splitlines();gb=int(next(x.split()[1] for x in lines if x.startswith('MemAvailable:')))/(1024**2)
   stable=stable+5 if gb>=48 else 0;time.sleep(5)
 env=dict(os.environ,TARGET_LANE='continue_measure',IMG='jointbuildgs:geogs-conf-guided-v1',MEM='32' if heavy else '8',CPUS='6' if heavy else '2')
 subprocess.run(['bash',str(REPO/'scripts/phd/main_target_v1/run_cpu.sh'),tag,script]+args,env=env,check=True)
 if handle:handle.close()
