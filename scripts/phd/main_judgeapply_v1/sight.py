"""The unchanged TARGET r7 experiment-region sight test on the 5m/10m union."""
from common import *
from cameras import Cameras
from inherit import functions
from scipy.spatial import cKDTree
import warnings
scope=dict(np=np,cKDTree=cKDTree,warnings=warnings,sha=sha)
nearest,test=functions('main_target_v1__disappearance_r7.py',['nearest','test'],scope)
def main(site):
    cam=Cameras(site);start=time.monotonic();rows=[]
    for prior in cfg()['priors']:
        g=loadz(O/'geometry'/f'{site}__{prior}.npz')
        d={k:g[k] for k in ['centre','u','u_replaced','sigma_p','area','kind']};d['region']=np.where(((g['n5']>=0)&(g['n5']<4))|((g['n10']>=0)&(g['n10']<4)),0,1)
        def read(name):
            p=S0/'s61/export'/site/'LoD2/mvs'/f'{name}.npy';cp=p.parent.parent/'conf'/p.name
            return np.load(p),np.load(cp),[p,cp]
        result,record=test(d,cam.sight_cameras(),read)
        result.update(patch_id=g['patch_id'],free5=result['disappeared']&(g['n5']<4)&(g['n5']>=0),free10=result['disappeared']&(g['n10']<4)&(g['n10']>=0))
        savez(O/'sight'/f'{site}__{prior}.npz',**result);dump(O/'sight'/f'{site}__{prior}.json',record)
        rows.append(dict(site=site,prior=prior,free_count=int(result['disappeared'].sum())))
    dump(O/'timing'/f'{site}_sight.json',dict(at=now(),seconds=time.monotonic()-start,rows=rows,scientific_verdict=None));print('SIGHT_DONE',site,time.monotonic()-start,flush=True)
if __name__=='__main__':main(sys.argv[1])
