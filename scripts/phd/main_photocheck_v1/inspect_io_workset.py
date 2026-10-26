"""Describe development-only photo working sets for cache sizing."""
from common import *
from cameras import Cameras
from run_measure import selected_geometry
def main():
    cam=Cameras();rows=[]
    for prior in ['LoD2','ALS']:
        tile='6908_53359';g,idx=selected_geometry('full',tile,prior);pilot=O/'work/pilot'/f'{tile}__{prior}.npz'
        if pilot.exists():
            old=npz(pilot);keep=~np.isin(idx,old['geometry_index'][old['kind']==1]);g={k:v[keep] for k,v in g.items()};idx=idx[keep]
        sel=npz(O/'work/full_preselection'/f'{tile}__{prior}_selection.npz')['selected_images'];sets=[]
        for start in range(0,len(idx),8192):
            c=g['centre'][start:start+8192];s=sel[start:start+8192];pairs=set()
            for j in np.unique(s[s>=0]):
                local=np.flatnonzero((s==j).any(1));gsd=np.linalg.norm(c[local]-cam.centres[j],axis=1)/np.sqrt(cam.p[0]*cam.p[1]);opts=gsd[:,None]*2.**np.arange(6);lev=np.argmin(abs(opts-.02),axis=1);lev[gsd>=.02]=0
                pairs.update((int(j),int(l)) for l in np.unique(lev))
            sets.append(pairs);size=sum((cam.w//2**l)*(cam.h//2**l)*4+128 for j,l in pairs)
            rows.append(dict(prior=prior,start=start,points=min(8192,len(idx)-start),files=len(pairs),image_bytes=size,overlap_previous=len(pairs&sets[-2]) if len(sets)>1 else None))
    dump(O/'inspection/io_workset.json',rows);print(json.dumps(rows))
if __name__=='__main__':main()
