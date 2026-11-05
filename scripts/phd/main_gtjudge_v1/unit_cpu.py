"""Synthetic checks of the new distance and decision definitions, no real GT."""
import numpy as np
from common import *
from normal_line import MeshScene,measure,values,cases
from majority import decide

def plane(z,xmin=-2,xmax=2,ymin=-2,ymax=2):
    return np.array([[xmin,ymin,z],[xmax,ymin,z],[xmax,ymax,z],[xmin,ymax,z]],float),np.array([[0,1,2],[0,2,3]])

def main():
    cfg()
    V,F=plane(1.5)
    # A nearby side wall must not turn an elevated roof into a match.
    W=np.array([[.1,-2,-2],[.1,2,-2],[.1,2,2],[.1,-2,2]])
    sc=MeshScene(np.vstack([V,W]),np.vstack([F,F+4]))
    p=np.zeros((1,3));n=np.array([[0.,0.,1.]])
    s,_=measure(sc,p,n,False)
    assert abs(s[0]-1.5)<1e-6 and sc.distance(p)[0]<.11
    s,_=measure(MeshScene(*plane(-2)),p,n,False);assert abs(s[0]+2)<1e-6
    s,_=measure(MeshScene(*plane(6)),np.zeros((2,3)),np.repeat(n,2,axis=0),[False,True])
    assert abs(s[0]-6)<1e-6 and np.isnan(s[1])
    s,_=measure(MeshScene(*plane(11)),p,n,False);assert np.isnan(s[0])
    # Central ray misses a narrow opening; a 5 cm tangent offset reaches the face.
    s,k=measure(MeshScene(*plane(1,xmin=.04,xmax=.1,ymin=-.1,ymax=.1)),p,n,False)
    assert abs(s[0]-1)<1e-6 and k[0]>0
    # Tilted face gives signed perpendicular length, not a vertical displacement.
    V,F=plane(2);V[:,2]+=V[:,0]
    tilted=np.array([[-1.,0.,1.]])/np.sqrt(2)
    s,_=measure(MeshScene(V,F),p,tilted,False)
    assert abs(s[0]-np.sqrt(2))<1e-6
    v=values([.1,-.2,1,np.nan],.3,[True,True,True,True])
    assert v['within_pct']==50 and v['far_hit_pct']==25 and v['no_surface_pct']==25
    assert abs(v['median_signed_m']-.1)<1e-12
    assert abs(v['nmad_m']-1.4826*.3)<1e-12
    v2=values([.1,2,np.nan],.3,[True,False,True]);assert v2['n']==2 and v2['n_excluded']==1
    lab,absent=cases([0,2,0,0,2,np.nan,np.nan],[0,0,2,np.nan,2,0,np.nan],.5)
    assert lab.tolist()==[0,1,2,4,3,1,3] and absent.sum()==2
    owner=np.array([0,0,1,1,2,2,3,4,5,6])
    cell=np.array([0,1,1,2,3,3,2,1,0,0])
    orig=np.array([1,4,2,0,1,2,4,1])
    inev=np.array([1,1,1,1,1,1,0,1],bool)
    u=np.ones(8);u[5]=np.nan
    h=np.ones(8);h[4]=np.nan
    out,count,rec=decide(cell,owner,orig,inev,u,h)
    assert out.tolist()==[0,4,2,1,1,1,4,1]
    # Missing-value fallbacks must not alter no-reference/outside/both-wrong patches.
    out,_,_=decide(np.array([3,0]),np.array([0,1]),np.array([0,0,0]),
        np.array([True,False,True]),np.full(3,np.nan),np.ones(3))
    assert out.tolist()==[0,0,0]
    result=dict(at=now(),status='PASS_SYNTHETIC_ONLY',
        distance_checks=['nearby wall rejection','signed backward hit','roof 10m/wall 5m',
          'no hit within limit','five-origin opening','tilted triangle normal','signed statistics','accuracy exclusion denominator'],
        judgment_checks=['five cases','prior absence separate','agreement tie','other tie unchanged',
          'both wrong unchanged','missing h_M','missing u_M','outside eval unchanged','no rows unchanged'],
        scientific_scene_scoring=False,config_sha256=sha(C/'gtjudge_v1.json'),scientific_verdict=None)
    dump(O/'verification/unit_cpu.json',result);dump(D/'tables/unit_cpu.json',result)
    print('PASS_SYNTHETIC_DISTANCE_AND_MAJORITY')

if __name__=='__main__':main()
