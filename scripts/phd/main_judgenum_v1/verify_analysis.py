"""Small independent boundary checks for gating and optimization, not full-census claims."""
import numpy as np
from pathlib import Path
from analysis_core import judgment,select,summaries,choice,T2,minimum_area,smooth
from lock_config import dump,stamp

def main():
    d={'area':np.array([2.,3.,5.,7.,11.,13.]),'cell':np.array([0,1,1,2,2,3]),
       'building':np.array(['a','a','b','b','c','c']),'mvs_a_a':np.array([0.,0.,np.nan,0.,0.,0.]),
       'sigma_p':np.array([.1,.1,.1,.1,np.nan,.1]),
       'photo_judgments':np.tile(np.array([2,0,1,0,1,2],np.int8)[:,None],(1,15))}
    stats=np.zeros((6,7));stats[:,0]=[3,4,4,-1,4,4];stats[:,1]=[0,.5,-.5,.5,.5,5.];stats[:,3]=.02
    j,DL=judgment(d,stats,1.96)
    assert j.tolist()==[2,1,1,-1,-1,1]
    expected=1.96*np.sqrt(.02**2/4+.0275**2+.1**2)
    assert abs(DL[2]-expected)<1e-12
    after=np.ones(6,np.int8);dist=np.array([.5,.2,.7,.8,2.,4.]);mask=np.ones(6,bool)
    r=select(d,after,dist,mask)
    brute=[]
    for pi in range(15):
        for ti,t in enumerate(T2):
            error=0.
            for a,cell,p,dd in zip(d['area'],d['cell'],d['photo_judgments'][:,pi],dist):
                keep=(p==0) or (p>=2 and abs(dd)<=t)
                if (cell==1 and keep) or (cell==2 and not keep):error+=a
            brute.append(error)
    assert np.array_equal(r['errors'],brute)
    expected_index=min(range(135),key=lambda i:(brute[i],-T2[i%9],i//9))
    assert r['best']==expected_index
    # No photo threshold can win by dropping all uncertain decisions.
    assert r['denominator_m2']==28.
    for leave in r['leave_one_out']:
        bid=leave['building'];errors=[]
        for pi in range(15):
            for ti,t in enumerate(T2):
                cc=choice(d['photo_judgments'][:,pi],np.abs(dist),t)
                wrong=(d['building']!=bid)&(((d['cell']==1)&(cc==0))|((d['cell']==2)&(cc==1)))
                errors.append(float(d['area'][wrong].sum()))
        assert leave['choice_index']==min(range(135),key=lambda i:(errors[i],-T2[i%9],i//9))
    spatial={'centre':np.array([[0,0,0],[.25,0,0],[2,0,0],[2.25,0,0]]),
      'kind':np.ones(4,np.int8),'cell':np.zeros(4,np.int8),'area':np.array([5.,5.,5.,5.]),
      'building':np.array(['a','a','b','b'])}
    A,largest,rates=minimum_area(spatial,np.array([1,1,0,0]),.36)
    assert A=={1:10.,2:None}
    assert [r['largest_false_component_m2'] for r in largest]==[10.,0.]
    after,*_=smooth(spatial,np.array([1,0,0,0]),{1:6.,2:None},.36)
    assert after.tolist()==[0,0,0,0]
    dump(Path('/out/analysis_verification.json'),{'status':'PASS','at':stamp(),
      'checks':['inherit n<4 only with defined axis','missing sigma stays unavailable',
                'missing a uses zero with flag','135 candidates vs scalar reference',
                'joint-choice tie rule','leave-one-building-out recomputation',
                'building maximum component quantile','small-component boundary replacement'],
      'scientific_verdict':None})
    print('ANALYSIS_BOUNDARIES_PASS')

if __name__=='__main__':main()
