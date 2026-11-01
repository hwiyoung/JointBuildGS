"""Historical T2 and accuracy, explicitly reference-only because its mask used GT-based A."""
import numpy as np
from common import *
from judgment_census import photo,accuracy_rows


def main():
    candidate=json.loads((OUT/'r2/input_audit/t2_reference_candidates.json').read_text())
    old=next(r for r in candidate['rows'] if r['field']=='judgment_after' and r['value']==1)
    T2=old['fit']['T2_m'];assert abs(T2-.8548248176865011)<1e-10
    rows=[]
    for sealed in [False,True]:
        jn=JN/'holdout' if sealed else JN;split='holdout' if sealed else 'development'
        for prior in ['ALS','LoD2']:
            accum={}
            for f in sorted((jn/'core_points').glob(f'*__{prior}.npz')):
                with np.load(f) as z:
                    d={k:z[k] for k in ['patch_id','kind','area','cell','d_mean_cm','DL_cm','judgment_after']}
                tile=f.stem.split('__')[0]
                photos,_,_=photo(tile,prior,d['patch_id'],d['kind'],d['DL_cm']/100,sealed)
                d['any_replaced']=np.zeros(len(photos),bool)
                sig=d['judgment_after']==1
                lab=np.full(len(sig),-1,np.int8);lab[d['judgment_after']==0]=1;lab[d['judgment_after']==2]=0
                for mode in ['historical_T2_only','historical_T2_and_fixed_DL_photo']:
                    ll=lab.copy();ll[sig]=2
                    correct=np.abs(d['d_mean_cm'])/100>T2
                    if mode.endswith('photo'):correct|=photos==1
                    ll[sig&correct]=3
                    for row in accuracy_rows(d,ll,mode,split,prior):
                        key=(row['kind'],row['replacement'],mode)
                        if key not in accum:accum[key]=row
                        else:
                            for k,v in row.items():
                                if k in ['patches'] or k.endswith('_m2'):accum[key][k]+=v
            for row in accum.values():
                den=row['denominator_area_m2'];row['wrong_fraction']=row['wrong_area_m2']/den if den else None
                rows.append(row)
    r1=json.loads((OUT/'stage0_r1/T2.json').read_text())
    result=dict(at=stamp(),historical=old,rows=rows,r1=r1['fits'],
        explanation='923.5357 m2 is saved JUDGENUM judgment_after==1, after GT-derived minimum-area smoothing. Before smoothing, saved a-only DL gives 4388.1562 m2. TARGET r1 fills missing a/sigma (a-only 4637.6756 m2), uses full u (2951.6116 m2), and explicitly forbids the GT-derived minimum-area rule. Thus these populations differ; the historical fit is not a reference value of the TARGET eligibility rule.',
        reference_accuracy_definition='historical saved after-smoothing masks, shared historical T2, and either no photo or fixed photo delta0.1/smin0.3 with saved DL; no GT-selected photo combination',
        forbidden_for_current_decisions=True,scientific_verdict=None)
    dump(DOC/'tables/T2_historical_reference_r2.json',result)
    print('REFERENCE_ACCURACY_COMPLETE',len(rows),flush=True)


if __name__=='__main__':main()
