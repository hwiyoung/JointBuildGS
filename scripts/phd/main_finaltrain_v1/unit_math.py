"""Independent known-value tests for target equations and linear pixel weights."""
from common import *
from targets import calculate

def main():
    d=dict(judge_region=np.array([0,1,2,3,4,9,9,9]),reason=np.full(8,9),
        prior_height_m=np.array([2.,2,2,2,2,2,2,2]),mvs_mean_m=np.array([4.,4,4,4,np.nan,4,4,4]),
        sigma_P_m=np.full(8,2.),u_mvs=np.array([1.,1.,1.,1.,np.nan,np.nan,np.nan,np.nan]),
        n=np.array([20,20,20,0,0,20,20,20]),photo_code=np.array([9,9,9,9,9,0,1,3]),
        centre=np.zeros((8,3)),normal=np.tile([0.,0.,1.],(8,1)),area=np.array([1.,2.,3.,4.,5.,6.,7.,8.]))
    a=calculate(d,'ALS');b=calculate(d,'LoD2')
    assert np.isclose(a['h'][0],3.6) and np.isclose(a['sigma'][0],np.sqrt(.8))
    assert np.array_equal(a['h'][[1,2,4,5,6,7]],[2,4,2,2,4,2])
    assert np.array_equal(b['h'][[5,6,7]],[2,4,4])
    assert np.isnan(a['h'][3]) and not a['surface_exists'][3]
    assert a['sigma'][6]==1 and b['sigma'][7]==1
    for x in [a,b]:
        m=x['surface_exists'];ref=x['sigma_ref'];unclipped=ref/x['sigma'][m]
        assert abs(np.average(unclipped,weights=d['area'][m])-1)<1e-14
        independent=d['area'][m].sum()/sum(area/sigma for area,sigma in zip(d['area'][m],x['sigma'][m]))
        assert np.isclose(ref,independent,rtol=1e-15)
    assert np.array_equal(np.clip(1/np.array([.01,1.,100.]),.1,10),[10,1,.1])
    dump(O/'verification/unit_math.json',dict(at=now(),status='PASS',known_targets=8,priors=2,
        agreement_no_sigma_W=True,no_registration_shift=True,scene_reference=True,unclipped_area_mean_one=True,
        linear_weight=True,missing_uncertainty_rules=True,scientific_verdict=None))
    print('PASS_UNIT_MATH')
if __name__=='__main__':main()
