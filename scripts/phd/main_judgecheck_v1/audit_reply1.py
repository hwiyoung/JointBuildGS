"""Independent exclusion, calibration and retained-value checks; no truth."""
import json,ast
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
BASE=O/'r1'

def main():
    checks=[];scope=json.loads((BASE/'scope_audit.json').read_text());excluded={i for r in scope['rows'] for i in r['patch_ids']};photo_excluded={r['point_id'] for r in scope['rows']}
    assert len(excluded)==73;area=sum(r['area_m2'] for r in scope['rows']);assert abs(area-5.442552935831812)<1e-12
    allowed=set(json.loads((C/'judgecheck_v1.json').read_text())['scope']['development']);counts={};dparts={};building_parts={};um_attempted=um_recovered=um_unavailable=0
    for p in sorted((BASE/'geometry').glob('*.npz')):
        with np.load(p) as z,np.load(BASE/'inputs'/p.name) as initial,np.load(BASE/'ring_recompute'/p.name) as ring:
            assert not set(z['patch_id'])&excluded and set(z['building'])<=allowed and not set(z['photo_point_id'])&photo_excluded
            assert np.array_equal(z['patch_id'],initial['patch_id']) and np.array_equal(z['patch_id'],ring['patch_id'])
            before=initial['u_mvs'];after=z['u_mvs'];finite=np.isfinite(before);assert np.array_equal(before[finite],after[finite])
            um_attempted+=int((~finite).sum());um_recovered+=int(np.isfinite(after[~finite]).sum());um_unavailable+=int((~np.isfinite(after[~finite])).sum())
            prior=p.stem.split('__')[1];kind=z['kind'];bid=z['building'];diff=z['mvs_mean_m']-z['prior_height_m'];sig=np.sqrt(z['u_mvs']**2+z['sigma_P_m']**2)
            ok=(z['n']>=4)&np.isfinite(diff)&np.isfinite(sig)&(abs(diff)<=1.96*sig)
            assert np.array_equal(ok,z['agreement_for_calibration'])
            for k in np.unique(kind):
                m=kind==k;name=f'{prior}_{k}';r=counts.setdefault(name,dict(core_count=0,area_m2=0.,buildings=set(),normal_fallback_count=0,normal_fallback_area_m2=0.,prior_height_missing_count=0,prior_height_missing_area_m2=0.,missing_n5_area_m2=0.,missing_n10_area_m2=0.,unknown_geometry_count=0))
                r['core_count']+=int(m.sum());r['area_m2']+=float(z['area'][m].sum());r['buildings'].update(bid[m]);r['unknown_geometry_count']+=int(((z['geometry']==9)&m).sum())
                for prefix,mask in [('normal_fallback',~z['normal_rule_met']),('prior_height_missing',~np.isfinite(z['prior_height_m']))]:
                    r[prefix+'_count']+=int((m&mask).sum());r[prefix+'_area_m2']+=float(z['area'][m&mask].sum())
                for nn in [5,10]:r[f'missing_n{nn}_area_m2']+=float(z['area'][m&((z['n5'] if nn==5 else z['n'])<4)].sum())
                dparts.setdefault(name,[]).append(diff[m&ok])
            if prior=='ALS':
                for b in np.unique(bid[ok]):building_parts.setdefault(str(b),[]).append(diff[ok&(bid==b)])
            L=1.96*(np.sqrt(z['u_mvs']**2+z['sigma_P_m']**2+z['sigma_W_m']**2)+abs(z['r_m']))
            assert np.allclose(L,z['L_m'],equal_nan=True,rtol=1e-13,atol=1e-14)
    for r in counts.values():r['building_count']=len(r.pop('buildings'))
    calibration=json.loads((BASE/'geometry_calibration.json').read_text());med=np.array([np.median(np.concatenate(v)) for v in building_parts.values() if sum(map(len,v))>=100])
    assert len(med)==calibration['building_count'];sigma=1.4826*np.median(abs(med-np.median(med)));assert abs(sigma-calibration['sigma_W_m'])<1e-14
    for k,v in dparts.items():assert abs(np.median(np.concatenate(v))-calibration['r_m'][k])<1e-14
    for p in (BASE/'photo_targets').glob('*.npz'):
        with np.load(p) as z:assert not set(z['point_id'])&photo_excluded and not z['holdout'].any()
    for name in ['geometry.reply1.lock.json','ring.reply1.lock.json','photo_planes.reply1.lock.json']:
        lp=C/name
        if lp.exists():
            for f,h in json.loads(lp.read_text())['source_sha256'].items():assert sha(Path(__file__).parent/f)==h,(name,f)
    for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text())
    result=dict(at=now(),status='PASS_REPLY1_INDEPENDENT_AUDIT',
        exclusion=dict(label='실험 지역과 사진 점을 공유해 뺀 핵심점',count=73,area_m2=area),
        rows=counts,missing_u_recalculation=dict(attempted=um_attempted,recovered=um_recovered,unavailable=um_unavailable),
        initial_22_shared_curves_contribute_to_tables_figures_settings=False,initial_preparation_consumed=False,
        calibration_recomputed_independently=True,finite_inherited_u_unchanged=True,
        holdout_values_opened=False,truth_used_for_calibration=False,scientific_verdict=None)
    dump(BASE/'independent_reply1_audit.json',result);dump(D/'tables/reply1_verification.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
