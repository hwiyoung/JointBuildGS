"""Publish the fixed-arm bundle when its six posts finish, without model polling."""
from add2_host import *
while True:
    complete=all((O/'queue/addendum2/post'/f'{s}__{p}__fix.json').exists() for s in ['R1rep_b10','B173nb_b10','B0_b10'] for p in ['ALS','LoD2'])
    if complete and (O/'queue/addendum2/cpu_done.json').exists():
        subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),'fixed'],cwd=R,check=True)
        break
    time.sleep(30)
