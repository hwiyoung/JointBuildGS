"""Four independent CPU tiles under one shared 32 GiB container ceiling."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
from lock_config import dump,stamp
O=Path('/out');S=Path(__file__).parent

def work(tile):
    with (O/'logs'/f'cylinder_{tile}.log').open('w') as f:
        subprocess.run([sys.executable,'-B','-u',str(S/'census_cylinders.py'),'--tile',tile],stdout=f,stderr=subprocess.STDOUT,check=True)
    print('TILE_COMPLETE',tile,flush=True)

def main():
    gate=json.loads((O/'time_gate.json').read_text());assert gate['status']=='PASS_CPU_ESTIMATE'
    tiles=sorted({p.stem.split('__')[0] for p in (O/'inputs').glob('*.npz')})
    dump(O/'census_started.json',{'at':stamp(),'tiles':tiles,'workers':4,'container_total_memory_gib':32,
      'cpu_limit':8,'nice':19,'gpu':False,'scientific_verdict':None})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(work,tiles))
    dump(O/'census_complete.json',{'at':stamp(),'tiles':tiles,'status':'COMPLETE','scientific_verdict':None})

if __name__=='__main__':main()
