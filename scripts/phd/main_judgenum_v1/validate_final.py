"""Independent full-row arithmetic and selection checks; sealed details never printed."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import analyse as a
from figures import data
from lock_config import dump,sha,stamp
O=Path('/out');C=Path('/cfg');D=Path('/docs');S=Path(__file__).parent

def rows(name):return json.loads((D/'tables'/f'{name}.json').read_text())['rows']

def best(errors):
    thresholds=[.3,.5,.75,1.,1.5,2.,3.,5.,np.inf]
    return min(range(135),key=lambda i:(errors[i],-thresholds[i%9],i//9))

def full_rows(d,cal):
    n=d['n'];j=d['judgment_before'];a0=np.where(d['a_missing'],0,d['a_cm'])
    valid=(n>=4)&np.isfinite(d['s_cm'])&np.isfinite(d['sigma_p_cm'])
    dl=1.96*np.sqrt(d['s_cm'][valid]**2/n[valid]+a0[valid]**2+2.75**2+d['sigma_p_cm'][valid]**2)
    assert np.allclose(d['DL_cm'][valid],dl,atol=1e-10,rtol=1e-12)
    assert np.array_equal(j[valid],(np.abs(d['d_mean_cm'][valid])>dl).astype(np.int8))
    assert np.all(j[(n>=0)&(n<4)]==2) and np.all(j[n<0]==-1)
    assert np.all(j[(n>=4)&~valid]==-1)
    for kind,group in [(1,'roof'),(2,'wall')]:
        mask=(d['kind']==kind)&(d['judgment_after']==1)
        if not mask.any():continue
        index=cal['photo_choices'][group];pi,ti=divmod(index,9);t=[.3,.5,.75,1.,1.5,2.,3.,5.,np.inf][ti]
        p=d['photo_judgments'][mask,pi]
        cc=np.where(p==0,0,np.where(p==1,1,np.abs(d['d_mean_cm'][mask])>t*100))
        assert np.array_equal(cc,d['initial_choice'][mask])
    assert np.all(d['initial_choice'][d['judgment_after']!=1]==9)

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());cal=json.loads((O/'calibration.json').read_text())['values']
    allowed=set(cfg['scope']['development']);excluded={r['building'] for r in cfg['scope']['excluded']}
    held=set(json.loads((O/'holdout/scope_membership.json').read_text())['buildings'])
    audits=[];mismatches=[];checked=0
    for prior in ['LoD2','ALS']:
        d,sources=data(prior);raw,where=a.load(prior);assert np.array_equal(d['patch_id'],raw['patch_id'])
        assert set(d['building'])<=allowed and not (set(d['building'])&(held|excluded))
        full_rows(d,cal[prior]['base']);checked+=len(d['area'])
        for p in sorted((O/'core_points').glob(f'*__{prior}.npz')):
            with np.load(p) as z,np.load(O/'core_points_stage_a'/p.name) as old:
                for k in ['patch_id','n','d_mean_cm','d_median_cm','s_cm','s_nmad_cm','a_cm','sigma_p_cm','DL_cm','judgment_before']:
                    if np.issubdtype(z[k].dtype,np.number):assert np.array_equal(z[k],old[k],equal_nan=True),(p,k)
                    else:assert np.array_equal(z[k],old[k]),(p,k)
        for name,h,z,half in a.SCENARIOS:
            settings=cal[prior][name];chosen={int(k):v for k,v in settings['radius'].items()}
            reduced,ix=a.spaced(raw,where,prior,cfg) if half else (raw,np.arange(len(raw['area'])))
            stats=a.read_stats(where,h,raw['kind'],chosen)[ix];after=d[f'{name}_judgment_after'][ix]
            initial=d[f'{name}_initial_choice'][ix]
            assert np.isclose(reduced['area'].sum(),raw['area'].sum(),rtol=0,atol=1e-7)
            for group,mask in [('roof',reduced['kind']==1),('wall',reduced['kind']==2),('combined',np.ones(len(ix),bool))]:
                if not mask.any():continue
                bnames,bi=np.unique(reduced['building'],return_inverse=True);nb=len(bnames)
                eligible=mask&(after==1)&np.isin(reduced['cell'],[0,1,2]);cell=reduced['cell'][eligible]
                area=reduced['area'][eligible].astype(np.longdouble);bb=bi[eligible];dist=np.abs(stats[eligible,1]);photo=reduced['photo_judgments'][eligible]
                errors=np.zeros((135,nb),np.longdouble);den=np.zeros(nb,np.longdouble);np.add.at(den,bb,area)
                for pi in range(15):
                    p=photo[:,pi]
                    for ti,t in enumerate([.3,.5,.75,1.,1.5,2.,3.,5.,np.inf]):
                        keep=(p==0)|((p>=2)&(dist<=t));wrong=((cell==1)&keep)|((cell==2)&~keep)
                        np.add.at(errors[pi*9+ti],bb[wrong],area[wrong])
                total=errors.sum(1);expected=best(total);index=settings['photo_choices'][group]
                saved=rows(f'{prior}_{name}_{group}_grid');observed=np.array([r['wrong_area_m2'] for r in saved])
                assert np.allclose(observed,total.astype(float),rtol=0,atol=1e-7)
                assert total[index]-total.min()<1e-8
                if index!=expected:mismatches.append({'prior':prior,'scenario':name,'group':group,'type':'area_choice','actual':index,'expected':expected,'difference_m2':float(total[index]-total[expected])})
                equal=errors[:,den>0]/den[den>0];equal_best=best(equal.mean(1))
                sr=next(r for r in rows('selected_values') if (r['prior'],r['scenario'],r['group'])==(prior,name,group))
                if sr['building_equal_choice_index']!=equal_best:mismatches.append({'prior':prior,'scenario':name,'group':group,'type':'building_equal','actual':sr['building_equal_choice_index'],'expected':equal_best})
                for leave in rows(f'{prior}_{name}_{group}_leave_one_out'):
                    b=int(np.flatnonzero(bnames==leave['building'])[0]);expected_leave=best(errors[:,np.arange(nb)!=b].sum(1))
                    if expected_leave!=leave['choice_index']:
                        mismatches.append({'prior':prior,'scenario':name,'group':group,'type':'leave_one_out','building':leave['building'],'actual':leave['choice_index'],'expected':expected_leave})
                if group!='combined':
                    pi,ti=divmod(index,9);p=reduced['photo_judgments'][:,pi];t=[.3,.5,.75,1.,1.5,2.,3.,5.,np.inf][ti]
                    cc=np.where(p==0,0,np.where(p==1,1,np.abs(stats[:,1])>t)).astype(np.int8);cc[after!=1]=9
                    assert np.array_equal(cc[mask],initial[mask])
                audits.append({'prior':prior,'scenario':name,'group':group,'eligible_cores':int(eligible.sum()),'135_errors_recomputed':True,
                  'choice_index':index,'longdouble_choice_index':expected,'leave_one_out_count':len(rows(f'{prior}_{name}_{group}_leave_one_out'))})
            for kind in [1,2]:
                vv=[r['largest_false_component_m2'] for r in rows(f'{prior}_{name}_null_buildings') if r['kind']==kind]
                A=settings['A'][str(kind)]
                if vv:assert A==float(np.quantile(vv,.95,method='higher')) and np.mean(np.array(vv)>A)<=.05
                else:assert A is None
        print('INDEPENDENT_DEVELOPMENT_CHECKED',prior,flush=True)
    dump(O/'selection_precision_audit.json',{'rows':audits,'mismatches':mismatches,'scientific_verdict':None})
    assert not mismatches, f'Selection precision mismatch count {len(mismatches)}; see task-local audit'
    private=[]
    for prior in ['LoD2','ALS']:
        for p in sorted((O/'holdout/core_points').glob(f'*__{prior}.npz')):
            with np.load(p) as zz:zz={k:zz[k] for k in zz.files}
            assert set(zz['building'])<=held and not(set(zz['building'])&excluded)
            full_rows(zz,cal[prior]['base']);private.append({'file':p.name,'rows':len(zz['area']),'sha256':sha(p)})
    dump(O/'holdout/validation.json',{'status':'PASS','files':private,'config_sha256':sha(C/'judgenum_v1.json'),
      'calibration_sha256':sha(O/'calibration.json'),'scientific_verdict':None})
    for r in rows('holdout_counts_and_hashes'):
        for f in r['files']:assert sha(O/'holdout'/f['file'])==f['sha256']
    old=json.loads((O/'holdout/private_config_history/judgenum_v1.r0.lock.json').read_text())
    for path,digest in old['sources'].items():assert sha(path)==digest
    scanned=0
    for root in [C,D,S]:
        for p in root.rglob('*'):
            if p.is_file() and p.suffix in ['.json','.md','.csv','.txt','.py','.sh','.cpp']:
                assert not any(b in p.read_text() for b in held),f'Sealed identity in public text: {p}'
                scanned+=1
    figures=[]
    expected=['judgment_map_LoD2','judgment_map_ALS','model_cdf_LoD2','model_cdf_ALS']
    for prior,group in [('LoD2','roof'),('LoD2','wall'),('ALS','roof')]:
        expected += [f'{stem}_{prior}_{group}' for stem in ['false_components','distance_distributions','choice_heatmap']]
    for i,section in enumerate(cfg['figures']['section_coordinates']):expected.append(f"section_{i+1}_{section['prior']}")
    for prior in ['LoD2','ALS']:
        for page in [1,2]:expected.append(f'wrong_montage_{prior}_{page}')
    for name in expected:assert (D/'figures'/f'{name}.png').exists(),name
    for p in (D/'figures').glob('*.png'):
        assert p.with_suffix('.json').exists()
        with Image.open(p) as im:assert min(im.info.get('dpi',(0,0)))>299;figures.append({'file':p.name,'width':im.width,'height':im.height})
    result={'status':'PASS','at':stamp(),'all_development_core_rows':checked,'selection_checks':audits,
      'all_source_locks_unchanged':True,'public_text_files_checked':scanned,'figures':figures,
      'holdout_validation_sha256':sha(O/'holdout/validation.json'),'scientific_verdict':None}
    dump(O/'final_validation.json',result);dump(D/'tables/final_validation.json',result)
    print('FINAL_VALIDATION_PASS',checked,len(figures),flush=True)

if __name__=='__main__':main()
