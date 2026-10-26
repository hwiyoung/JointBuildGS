"""Independent small geometry and threshold checks for the amended rules."""
import numpy as np
from inputs import OUT, save
from direct_rules import edge_distance, prior_values, optimum, mixloss, RULES

def main():
    x,y=np.meshgrid(np.arange(5),np.arange(5),indexing='ij')
    c=np.column_stack((-170+.25+x.ravel()*.5,-237+.25+y.ravel()*.5,np.zeros(25)))
    n=np.tile([0.,0.,1.],(25,1));d,roof=edge_distance(c,n)
    assert roof.all() and d[12]==1.25 and d[0]==.25
    # A single-cell hole is closed; its wall receives the grid's filled distance.
    n[12]=[1,0,0];d,roof=edge_distance(c,n)
    assert not roof[12] and d[12]==1.25
    # > 1 m height jumps mark their 3x3 neighbours as edge, exactly 1 m does not.
    n[12]=[0,0,1];c[12,2]=1.;d,_=edge_distance(c,n);assert d[12]==1.25
    c[12,2]=1.0001;d,_=edge_distance(c,n);assert d[12]==-.25 and d[6]==-.25
    e=np.array([.499999,.5,1.499999,1.5,.5,.5,.5]);roof=np.array([1,1,1,1,1,1,0],bool)
    rt=np.array(['3100','3100','1000','1000','2100','missing','1000'])
    s,v,st,b=prior_values('LoD2',e,roof,rt,np.zeros(7))
    assert np.array_equal(st,[0,2,3,5,2,2,6])
    assert np.allclose(s,[.222725,.222725,.166113,.166113,.098442,.110188,.143818],rtol=0,atol=1e-12)
    s,v,st,b=prior_values('ALS',np.array([0,.5,1.5]),np.ones(3,bool),np.array(['']*3),np.array([.009999,.01,.03]))
    assert np.array_equal(st,[0,4,8]) and np.allclose(v,[.98,.98,.599285])
    assert np.array_equal(np.searchsorted(RULES['mvs_u_edges_cm'],[0,2.99999,3,5,10,20,40,100],side='right'),[0,0,1,2,3,4,5,5])
    # Both optima stay on the common surface; swapping equally trusted observations is symmetric.
    D=np.array([0.,.1,1.,6.]);s=np.full(4,.2);v=np.full(4,.5)
    z=optimum('fixed',D,s,s,v,v);assert np.allclose(z,D/2)
    z=optimum('dynamic',D,s,s,v,v)
    assert z[0]==0 and np.all(np.isfinite(mixloss(z,0,s,v)+mixloss(z,D,s,v)))
    save(OUT/'checks/direct_stage1/rule_unit_checks.json',dict(status='PASS',
        checks=['C.5 planar distance','closing single hole','height jump strict threshold','roof/wall distinction',
            'LoD2 types and strata','ALS u-prior bins','MVS boundary bins','C.4 fixed and dynamic optima'],scientific_verdict=None))
    print('direct rules geometry and threshold checks PASS')

if __name__=='__main__':main()
