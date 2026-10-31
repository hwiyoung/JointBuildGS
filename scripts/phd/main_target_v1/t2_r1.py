"""Calibrate T2 without reading GT fields or inherited GT-selected parameters."""
import numpy as np
from common import *
from target_rules import uncertainties,detection,fit_t2


def main():
    cfg,lock=locked()
    assert json.loads((OUT/'stage0_r1/input_gate.json').read_text())['status']=='PASS_STAGE0_INPUTS_R1'
    W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
    parts=[];sources=[]
    keys=['patch_id','building','kind','area','n','d_mean_cm','s_cm','sigma_p','normal_defined','mvs_a_a']
    for f in sorted((JN/'core_points').glob('*__ALS.npz')):
        with np.load(f) as z:d={k:z[k] for k in keys}
        tile=f.stem.split('__')[0];uf=W/'patch_values'/f'{tile}__ALS__R1.5.npz'
        with np.load(uf) as z:
            pid=z['patch_id'];o=np.argsort(pid);j=np.searchsorted(pid[o],d['patch_id']);ix=o[j]
            assert np.array_equal(pid[ix],d['patch_id'])
            d['raw_u']=z['mvs_a_u'][ix]
        parts.append(d);sources.extend([{'path':str(p),'sha256':sha(p)} for p in [f,uf]])
    d={k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
    values,med=uncertainties(d['raw_u'],d['sigma_p'],d['mvs_a_a'],d['kind'],d['building'])
    distance=d['d_mean_cm']/100.;s=d['s_cm']/100.
    out={}
    for name,u in [('main_u',values['u']),('sensitivity_a',values['a_sensitivity'])]:
        DL=detection(d['n'],s,u,values['sigma_p'])
        mask=(d['kind']==1)&d['normal_defined']&np.isfinite(DL)&(np.abs(distance)>DL)
        fit=fit_t2(distance[mask],d['area'][mask]);fit.update(eligible_patches=int(mask.sum()),eligible_area_m2=float(d['area'][mask].sum()))
        out[name]=fit
        np.savez_compressed(OUT/'stage0_r1'/f't2_distribution_{name}.npz',abs_d=np.abs(distance[mask]),area=d['area'][mask])
    result={'task_id':cfg['task_id'],'at':stamp(),'status':out['main_u']['status'],'fits':out,
        'config_sha256':lock['config_sha256'],'reference_a_only_T2_m':.855,
        'inputs':sources,'no_gt_fields_loaded':True,'no_gt_selected_parameters_loaded':True,
        'replacement_scope':'development building and kind; before selecting significant differences',
        'medians':med,'scientific_verdict':None,'source_tag':'[이 발주에서 냄]'}
    dump(OUT/'stage0_r1/T2.json',result);dump(DOC/'tables/T2_r1.json',result)
    print(json.dumps({'status':result['status'],'fits':out},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
