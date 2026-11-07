"""Only new eligibility behavior; previous preflight suites are not repeated."""
from add11 import *
def main():
 P=np.array([[0.,0.,0.],[5.,0.,0.]]);tree=Cylinder(P);q=np.array([[0.,0.,2.],[2.,0.,2.],[5.,0.,11.],[5.,0.,4.]]);n=np.tile([0.,0.,1.],(4,1));s,idx=tree.query(q,n,np.array([10.,10.,10.,5.]),1.);assert np.array_equal(idx>=0,[True,False,False,True]);small,_=tree.query(q[[0,3]],n[[0,3]],np.array([10.,5.]),.05);assert np.allclose(abs(small),[2.,4.]);tree.close();dump(W/'new_rule_check.json',meta(status='PASS',only_new_observability_rule=True,newly_included_floating_point=True,unobserved_side_point_excluded=True,axial_limits_preserved=True));print('ADD11_NEW_RULE_PASS',flush=True)
if __name__=='__main__':main()
