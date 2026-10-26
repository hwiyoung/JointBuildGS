"""Independent CPU-only pilot view selection while the GPUs are occupied."""
import time
from common import *
from cameras import Cameras,select_photos
from run_measure import selected_geometry
def main():
    cam=Cameras();folder=paths(False)/'work/pilot';folder.mkdir(exist_ok=True)
    for t in load(W/'inputs/tiles.json'):
      for prior in ['LoD2','ALS']:
        name=f'{t["id"]}__{prior}';dest=folder/f'{name}_selection.npz'
        if dest.exists():continue
        g,idx=selected_geometry('pilot',t['id'],prior)
        if not len(idx):continue
        start=time.monotonic();s=select_photos(g,cam,t['id'],prior)
        np.savez_compressed(dest,**s);dump(dest.with_suffix('.json'),dict(points=len(idx),seconds=time.monotonic()-start,environment=env(),config_sha256=sha(C/'photocheck_v1.json')))
        print('pilot selection complete',name,len(idx),flush=True)
if __name__=='__main__':main()
