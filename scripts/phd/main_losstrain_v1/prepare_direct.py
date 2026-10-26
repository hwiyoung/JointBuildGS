"""Build direct stage-1 values and both amended CPU gates, without training.

Training NPZ contains no GT positions, labels, optima, or WIDEN correspondences.
The latter are diagnostic only. All generated files use a new revision path.
"""
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from inputs import OUT, PH, S0, S1, W, SITES, PRIORS, save, sha
from direct_rules import RULES, edge_distance, prior_values, optimum

DEST=OUT/RULES['revision']
U=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1'

def stats(x):
    x=np.asarray(x);x=x[np.isfinite(x)]
    return dict(n=len(x),median=float(np.median(x)) if len(x) else None,
        p95=float(np.quantile(x,.95)) if len(x) else None,max=float(x.max()) if len(x) else None)

def amount(mask,area,ev):
    return dict(patches=int(mask.sum()),area_m2=float(area[mask].sum()),
        eval_patches=int((mask&ev).sum()),eval_area_m2=float(area[mask&ev].sum()))

def load_widen_lod2():
    parts=[];sources=[]
    for vf in sorted((OUT/'vfile_v1').glob('*__LoD2__vfile.npz')):
        wf=W/'patch_values'/vf.name.replace('__vfile.npz','__R1.5.npz')
        with np.load(vf,allow_pickle=False) as v,np.load(wf,allow_pickle=False) as w:
            assert np.array_equal(v['patch_id'],w['patch_id']) and not w['holdout'].any()
            d={k:w[k] for k in ['centre','normal','roof_type','patch_id']}
            d.update({k:v[k] for k in ['sigma_prior','sigma_mvs','v_mvs','v_prior_now','stratum']})
            parts.append(d)
        sources.append(dict(vfile=str(vf),vfile_sha256=sha(vf),geometry=str(wf),geometry_sha256=sha(wf)))
    d={k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
    d['edge'],d['roof']=edge_distance(d['centre'],d['normal'])
    return d,sources

def main():
    assert not DEST.exists(),'refuse overwrite of direct-stage1 revision'
    DEST.mkdir(parents=True)
    cfg=Path('/config')/(RULES['revision']+'.json');assert not cfg.exists()
    save(cfg,RULES);save(cfg.with_suffix('.lock.json'),dict(sha256=sha(cfg),scientific_verdict=None))
    cfgsha=sha(cfg);rows=[];w,wsources=load_widen_lod2();tree=cKDTree(w['centre'])
    for site in SITES:
        for prior in PRIORS:
            unit=site+'__'+prior;dest=DEST/unit;dest.mkdir()
            upath=U/'patch_values'/f'{unit}__R1.5.npz'
            store=S0/'fork_inputs/s61'/site/f'store_{prior}.npz'
            region=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
            with np.load(upath,allow_pickle=False) as z,np.load(store,allow_pickle=False) as st,np.load(region,allow_pickle=False) as r:
                c=z['centre'];n=z['normal'];area=z['area'];ev=z['in_eval'].astype(bool)
                assert np.array_equal(c,st['loc_center']) and np.array_equal(c,r['centre'])
                assert np.array_equal(ev,r['in_eval']) and np.allclose(area,st['loc_area'],rtol=0,atol=1e-10)
                up=z['u_prior'];rt=z['roof_type'].astype(str)
                pM=np.where(z['mvs_a_status']==0,z['mvs_a_p'],np.nan)
                um=np.where(z['mvs_a_status']==0,z['mvs_a_u'],np.nan)
                pG=np.where(z['gt_status']==0,z['gt_p'],np.nan)
                missing_normal=~np.isclose(np.linalg.norm(n,axis=1),1,atol=1e-5)
                assert st['loc_extra'][missing_normal].all()
                ext=st['surf_ext'][st['loc_surface']][missing_normal]
                nf=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box'/site/f'{prior.lower()}_surfaces.json'
                tab={int(s['ext']):s for s in json.loads(nf.read_text())['surfaces']}
                if missing_normal.any():
                    n[missing_normal]=np.asarray([tab[int(e)]['normal'] for e in ext])
                assert np.isclose(np.linalg.norm(n,axis=1),1,atol=1e-5).all()
            assert not (np.isfinite(up)&(up<0)).any()
            edge,roof=edge_distance(c,n)
            sp,vp,st,e=prior_values(prior,edge,roof,rt,up)
            missing_p=(~np.isfinite(up)) if prior=='ALS' else np.zeros(len(c),bool)
            outside=np.zeros(len(c),bool)  # proven absent by exact array equality above
            known=~missing_p
            medp=dict(sigma_prior=float(np.median(sp[known])),v_prior_now=float(np.median(vp[known])))
            sp[missing_p]=medp['sigma_prior'];vp[missing_p]=medp['v_prior_now'];st[missing_p]=-1
            hasM=np.isfinite(pM)&np.isfinite(um)&(um>0)
            sm=np.where(hasM,np.sqrt(um**2+RULES['floor_m']**2),np.nan)
            b=np.searchsorted(RULES['mvs_u_edges_cm'],um*100,side='right')
            vm=np.where(hasM,np.array(RULES['v_mvs'][prior])[b],np.nan)
            medm=dict(sigma_mvs=float(np.median(sm[hasM])),v_mvs=float(np.median(vm[hasM])))
            tau=RULES['prior_tau_m'][prior];hasG=np.isfinite(pG);rightP=hasG&(np.abs(pG)<=tau)
            rightM=hasG&hasM&(np.abs(pM-pG)<=tau)
            cell=np.where(~hasG,6,np.where(~hasM,np.where(rightP,4,5),np.where(rightP,np.where(rightM,0,2),np.where(rightM,1,3)))).astype(np.int8)
            vgt=np.where(hasG,np.where(rightP,.999,.001),vp);vsoft=np.where(hasG,np.where(rightP,.98,.85),vp)
            coverage=known&~outside
            row=dict(site=site,prior=prior,patches=len(c),eval_patches=int(ev.sum()),eval_area_m2=float(area[ev].sum()),
                direct_eval_patches=int((ev&coverage).sum()),direct_eval_area_m2=float(area[ev&coverage].sum()),
                count_coverage=float(coverage[ev].mean()),area_coverage=float(area[ev&coverage].sum()/area[ev].sum()),
                missing_als_prior=amount(missing_p,area,ev),outside_uncert=amount(outside,area,ev),
                missing_mvs=amount(~hasM,area,ev),missing_gt=amount(~hasG,area,ev),
                invalid_normal=amount(~np.isclose(np.linalg.norm(n,axis=1),1,atol=1e-5),area,ev),
                normal_from_owning_surface=amount(missing_normal,area,ev),normal_source=str(nf),normal_source_sha256=sha(nf),
                fallback_medians={**medp,**medm},scoring_excluded_fallback=amount(missing_p|outside,area,ev),
                source=str(upath),source_sha256=sha(upath),store=str(store),store_sha256=sha(store),
                region=str(region),region_sha256=sha(region),rules_sha256=cfgsha,scientific_verdict=None)
            row['coverage_gate']='PASS' if row['area_coverage']>=.95 else 'STOP'
            if prior=='LoD2':
                d,idx=tree.query(c,workers=8);pair=d<=.01
                spdiff=np.abs(sp-w['sigma_prior'][idx]);vpdiff=np.abs(vp-w['v_prior_now'][idx])
                agree=(spdiff<=1e-4)&(vpdiff<=1e-4);bad=pair&~agree
                type_bad=rt!=w['roof_type'][idx]
                w_e=np.where(w['stratum'][idx]==6,-1,w['stratum'][idx]//2)
                edge_bad=roof&(e!=w_e)
                reason=np.zeros(len(c),np.int8)
                reason[bad]=3;reason[bad&edge_bad]=2;reason[bad&type_bad]=1
                fraction=float(agree[pair].mean()) if pair.any() else None
                row['lod2_check']=dict(pairs=int(pair.sum()),matching=int((pair&agree).sum()),fraction=fraction,
                    gate='PASS' if fraction is not None and fraction>=.90 else 'STOP',
                    groups={label:dict(pairs=int((pair&m).sum()),matching=int((pair&m&agree).sum()),
                        fraction=float(agree[pair&m].mean()) if (pair&m).any() else None)
                        for label,m in [('roof',roof),('wall',~roof)]},
                    mismatch_reason={'roof_type':int((reason==1).sum()),'edge_bin':int((reason==2).sum()),'other':int((reason==3).sum())},
                    mvs_sigma_abs_difference_m=stats((sm-w['sigma_mvs'][idx])[pair].__abs__()),
                    mvs_validity_abs_difference=stats((vm-w['v_mvs'][idx])[pair].__abs__()),
                    target='nearest whole-scene same-prior pair <= 1 cm; diagnostic only')
                np.savez_compressed(dest/'lod2_pairs.npz',stage1_patch=np.flatnonzero(pair),widen_patch_id=w['patch_id'][idx[pair]],
                    distance_m=d[pair],agree=agree[pair],reason=reason[pair],stage1_edge_m=edge[pair],widen_edge_m=w['edge'][idx[pair]],
                    stage1_roof_type=rt[pair],widen_roof_type=w['roof_type'][idx[pair]],stage1_stratum=st[pair],widen_stratum=w['stratum'][idx[pair]],
                    sigma_difference_m=spdiff[pair],validity_difference=vpdiff[pair])
            # No GT geometry or cell labels are exposed to the training loader.
            np.savez_compressed(dest/'values.npz',centre=c,normal=n,sigma_prior=sp.astype(np.float32),sigma_mvs=sm.astype(np.float32),
                v_mvs=vm.astype(np.float32),v_prior_now=vp.astype(np.float32),v_prior_gt=vgt.astype(np.float32),
                v_prior_soft=vsoft.astype(np.float32),fallback=missing_p|outside,missing_als_prior=missing_p,outside_uncert=outside,
                has_mvs=hasM,direct_prior=coverage)
            evaldata=dict(centre=c,normal=n,area=area,in_eval=ev,edge=edge,roof=roof,roof_type=rt,stratum=st,edge_bin=e,
                u_prior=up,u_mvs=um,p_mvs=pM,p_gt=pG,cell=cell,tau=np.full(len(c),tau),
                scoring_allowed=hasG&~missing_p&~outside,has_mvs=hasM)
            for name,mode,v in [('fixed_gt','fixed',vgt),('dyn_gt','dynamic',vgt),('dyn_soft','dynamic',vsoft),
                               ('dyn_now','dynamic',vp),('fixed_now','fixed',vp)]:
                z=np.zeros(len(c));z[hasM]=optimum(mode,pM[hasM],sp[hasM],sm[hasM],v[hasM],vm[hasM]);evaldata['z_'+name]=z
            np.savez_compressed(dest/'evaluation.npz',**evaldata)
            row['values_sha256']=sha(dest/'values.npz');row['evaluation_sha256']=sha(dest/'evaluation.npz')
            save(dest/'receipt.json',row);rows.append(row)
            print(unit,'coverage count/area',row['count_coverage'],row['area_coverage'],row['coverage_gate'],
                'LoD2 check',row.get('lod2_check'),flush=True)
    gate='PASS' if all(r['coverage_gate']=='PASS' and r.get('lod2_check',{}).get('gate','PASS')=='PASS' for r in rows) else 'STOP'
    report=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',revision=RULES['revision'],saved_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
        rules_sha256=cfgsha,rows=rows,widen_diagnostic_sources=wsources,gate=gate,training_started=False,scientific_verdict=None)
    save(DEST/'gates.json',report);save('/docs/tables/direct_stage1_gates.json',report)
    for row in rows:
        dest=DEST/(row['site']+'__'+row['prior'])
        save(dest/'manifest.json',dict(task_id=report['task_id'],revision=RULES['revision'],
            rules_sha256=cfgsha,values_sha256=row['values_sha256'],store_sha256=row['store_sha256'],
            coverage_gate=row['coverage_gate'],lod2_check_gate=row.get('lod2_check',{}).get('gate','NOT_APPLICABLE'),
            all_units_rules_gate=gate,gate_receipt_sha256=sha(DEST/'gates.json'),
            source_sha256=row['source_sha256'],scientific_verdict=None))
    cols=['site','prior','eval_patches','eval_area_m2','direct_eval_patches','direct_eval_area_m2','count_coverage','area_coverage','coverage_gate']
    with Path('/docs/tables/direct_stage1_coverage.csv').open('w') as f:
        writer=csv.DictWriter(f,cols,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(rows)
    print('amended rules gates',gate,flush=True)

if __name__=='__main__':main()
