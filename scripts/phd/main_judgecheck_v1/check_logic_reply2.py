"""Boundary cases for ordered photo/region rules and evaluation-only replacement."""
import numpy as np
from judgment_reply2 import judge,ablations
from photo_judgment_reply2 import corrected,weighted_quantile,old_photo
from preflight import O,D,dump,now

def main():
    n=10;selected=np.zeros((n,2,10),int);available=np.ones((n,2),bool);texture=np.full((n,2),10.);scores=np.array([[.2,.8],[.8,.2],[.2,.2],[.8,.8],[np.nan,.8],[.1,.2],[.8,.9],[.8,.9],[.8,.9],[.8,.9]])
    available[5,1]=False;texture[6]=0;selected[7,0]=-1;selected[8,1]=-1;texture[8]=0;available[8,1]=False;scores[9]=.5
    code=corrected(scores,texture,selected,available,.5);assert np.array_equal(code,[1,0,2,3,5,4,6,7,7,3]),code
    g=dict(n=np.array([10,10,10,10,10,10,0,2,10,10]),geometry=np.array([0,1,1,1,1,9,2,2,1,9]),prior_height_m=np.zeros(n),normal=np.tile([0.,0.,1.],(n,1)),mvs_mean_m=np.ones(n),u_mvs=np.ones(n),sigma_P_m=np.ones(n),sigma_W_m=np.zeros(n))
    photos=np.array([1,0,1,2,7,0,0,1,0,1]);g['prior_height_m'][8]=np.nan;free=np.zeros(n,bool);free[6]=True
    a,r=judge(g,photos,'ALS',free);b,_=judge(g,photos,'LoD2',free);assert np.array_equal(a,[0,1,2,1,1,9,3,4,9,9]),a;assert np.array_equal(b,[0,1,2,2,2,9,3,4,9,9]),b
    regions=np.tile(a,(6,1));gt=np.array([0.,0.,1.,1.,0.,0.,0.,0.,0.,0.]);cell=np.array([2,2,1,1,2,2,4,4,9,2]);arms,h,zero,ties=ablations(g,regions,photos,gt,cell,'ALS')
    assert arms[1,0]==1 and arms[2,0]==2 and arms[3,0]==0
    assert (arms[:,6]==3).all() and (arms[:,7]==4).all() and (arms[:,5]==9).all();assert np.isnan(h[:,6]).all()
    assert weighted_quantile(np.array([.1,.3,.9]),np.array([1.,8.,1.]),.05)==.1
    assert weighted_quantile(np.array([.1,.3,.9]),np.array([1.,8.,1.]),.5)==.3
    result=dict(at=now(),status='PASS_ORDERED_RULE_BOUNDARIES',checks=['photo precedence including equality','prior defaults','unknown geometry remains 9','missing height excluded','reference substitutions only in diagnostic arms','n<4 unchanged in all arms','area-weighted inverse CDF'],scientific_verdict=None);dump(O/'r2/logic_checks.json',result);dump(D/'tables/reply2_logic_checks.json',result);print(result['status'])
if __name__=='__main__':main()
