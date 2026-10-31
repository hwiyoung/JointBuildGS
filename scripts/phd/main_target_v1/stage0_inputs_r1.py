"""Apply the user's r1 input decision; inherited originals are read-only."""
import sys
import numpy as np
from common import *
from target_rules import uncertainties


def main():
    c,lock=locked();rows=[];root=OUT/'stage0_r1/inputs';root.mkdir(parents=True,exist_ok=True)
    deferred='--deferred' in sys.argv
    sites=c['deferred_sites'] if deferred else c['sites']
    for site in sites:
        for prior in c['priors']:
            source=OUT/'b173_uncert_r1' if deferred else UN
            if deferred:assert json.loads((source/'complete.json').read_text())['status']=='COMPLETE_OWN_B173_UNCERTAINTY'
            up=source/'patch_values'/f'{site}__{prior}__R1.5.npz'
            rp=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
            with np.load(up) as z:
                d={k:z[k] for k in ['centre','normal','kind','roof_type','area','u_prior','mvs_a_u','mvs_a_a','mvs_a_status','surf','building']}
                als_status=z['als_status'] if prior=='ALS' else None
                als_col=z['als_n_col'] if prior=='ALS' else None
            with np.load(rp) as z:
                assert np.array_equal(d['centre'],z['centre'])
                assert np.array_equal(d['area'],z['area']) and np.array_equal(d['kind'],z['kind'])
                assert np.array_equal(d['surf'],z['surf_ext']);ev=z['in_eval'].astype(bool)
            raw=np.sqrt(d['u_prior']**2+.0275**2)
            if prior=='LoD2':
                sig=c['detection']['prior_sigma'];raw=np.array([sig['LoD2_roof'].get(str(rt),sig['LoD2_roof']['other']) for rt in d['roof_type']])
                raw[d['kind']==2]=sig['LoD2_wall']
            values,medians=uncertainties(d['mvs_a_u'],raw,d['mvs_a_a'],d['kind'],np.full(len(ev),site))
            validnormal=np.isfinite(d['normal']).all(1)&(np.abs(np.linalg.norm(d['normal'],axis=1)-1)<1e-6)
            unavailable=~validnormal|~np.isfinite(values['u'])|~np.isfinite(values['sigma_p'])
            for range_name,mask in [('eval',ev),('band',~ev)]:
                area=float(d['area'][mask].sum());missing=float(d['area'][mask&unavailable].sum())
                row=dict(site=site,prior=prior,range=range_name,patches=int(mask.sum()),area_m2=area,
                    unavailable_area_m2=missing,unavailable_fraction=missing/area if area else None,
                    normal_missing_area_m2=float(d['area'][mask&~validnormal].sum()))
                for flag in ['u_replaced','sigma_p_replaced','any_replaced']:
                    row[flag+'_patches']=int((mask&values[flag]).sum());row[flag+'_area_m2']=float(d['area'][mask&values[flag]].sum())
                if prior=='ALS':
                    state1=mask&(als_status==1)
                    row['als_state1_count']=int(state1.sum());row['als_state1_area_m2']=float(d['area'][state1].sum())
                    row['als_state1_empty_column_count']=int((state1&(als_col==0)).sum())
                    row['als_state1_nonempty_column_count']=int((state1&(als_col>0)).sum())
                rows.append(row)
            dest=root/f'{site}_{prior}.npz'
            np.savez_compressed(dest,**d,**values,in_eval=ev,normal_defined=validnormal,unavailable=unavailable)
            dump(dest.with_suffix('.json'),{'source':str(up),'source_sha256':sha(up),'region_sha256':sha(rp),
                'medians':medians,'output_sha256':sha(dest),'config_sha256':lock['config_sha256'],'scientific_verdict':None})
            print(site,prior,'eval unavailable',float(d['area'][ev&unavailable].sum()/d['area'][ev].sum()),flush=True)
    failures=[r for r in rows if r['range']=='eval' and r['unavailable_fraction']>.1]
    result=dict(status='STOP_STAGE0_UNAVAILABLE_AREA' if failures else 'PASS_STAGE0_INPUTS_R1',at=stamp(),rows=rows,
        config_sha256=lock['config_sha256'],scientific_verdict=None,source_tag='[이 발주에서 냄]')
    name='input_gate_deferred_r1' if deferred else 'input_gate_r1'
    dump(OUT/'stage0_r1'/('input_gate_deferred.json' if deferred else 'input_gate.json'),result);dump(DOC/'tables'/f'{name}.json',result)
    print(result['status'],flush=True)


if __name__=='__main__':main()
