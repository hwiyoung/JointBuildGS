"""Independent final core/point identities, ordered decisions, tables and figure checks."""
import json,sys
import numpy as np
from PIL import Image
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz
BASE=O/'r2';GROUPS=[('ALS',1),('LoD2',1),('LoD2',2)]
def main(mode='full'):
    expected=GROUPS if mode=='full' else GROUPS[:2];excluded={v for r in json.loads((O/'r1/scope_audit.json').read_text())['rows'] for v in r['patch_ids']};allowed=set(json.loads((C/'judgecheck_v1.json').read_text())['scope']['development']);counts={};checks=[]
    for prior,kind in expected:
        key=f'{prior}_{kind}';count=0;tx=[];tw=[];locked_t=json.loads((C/f'photo_threshold.{key}.reply2.lock.json').read_text())['t']
        for p in sorted((BASE/'core_points').glob(f'*__{prior}__{kind}.npz')):
            z=loadz(p);tile=p.stem.split('__')[0];original=loadz(O/'r1/geometry'/f'{tile}__{prior}.npz');take=original['kind']==kind;assert np.array_equal(z['patch_id'],original['patch_id'][take]);assert not set(z['patch_id'])&excluded;assert set(z['building'])<=allowed;count+=len(z['patch_id'])
            for k in ['centre','normal','u_mvs','prior_height_m','L_m','geometry']:assert np.array_equal(z[k],original[k][take],equal_nan=True),k
            n=len(z['patch_id']);valid=np.isfinite(z['prior_height_m'])&np.isfinite(z['normal']).all(1);geom=z['geometry'];inside=valid&(geom==0);outside=valid&(geom==1);missing=valid&(z['n']<4)
            for variant in range(3):
                photo=z['photo_code'][variant];expected_reg=np.full(n,9,np.int8);reason=np.full(n,9,np.int8);expected_reg[missing]=4;expected_reg[missing&z['free10']]=3;expected_reg[inside]=0
                for i in np.flatnonzero(outside):
                    if photo[i]==0:expected_reg[i]=1;reason[i]=0
                    elif photo[i]==1:expected_reg[i]=2;reason[i]=1
                    else:expected_reg[i]=1 if prior=='ALS' else 2;reason[i]=2
                assert np.array_equal(expected_reg,z['region'][variant]) and np.array_equal(reason,z['reason'][variant])
            assert (z['region'][0,(z['n']>=4)&~np.isfinite(z['u_mvs'])]==9).all();assert not (z['sight_unavailable']&z['free10']).any()
            assert np.all(z['arm_region'][:,missing]==z['region'][0,missing]);assert np.all(np.isnan(z['arm_height_m'][:,z['region'][0]==3]));assert np.isin(z['old_photo_code'],[0,1,2,3,4,9]).all()
            photo=loadz(BASE/'photo_points'/p.name);owner={v:i for i,v in enumerate(photo['point_id'])};ix=np.array([owner[v] for v in z['photo_point_id']],dtype=np.int64);assert np.array_equal(z['new_photo_code'],photo['new_code'][:,ix]);assert np.array_equal(z['old_photo_code'],photo['old_code'][ix]);assert np.isin(photo['new_code'],list(range(8))+[9]).all()
            assert np.array_equal(photo['selected_count'],(photo['selected_images']>=0).sum(-1))
            assert np.array_equal(photo['computed'],photo['target_type_bits']>0)
            for mode_index in range(2):
                score=photo['best_score'][mode_index];texture=photo['texture'][mode_index];decision=np.full(len(score),9,np.int8)
                if locked_t is not None:
                    pscore,mscore=score.T
                    decision[(pscore<locked_t)&(mscore>=locked_t)]=1
                    decision[(pscore>=locked_t)&(mscore<locked_t)]=0
                    decision[(pscore<locked_t)&(mscore<locked_t)]=2
                    decision[(pscore>=locked_t)&(mscore>=locked_t)]=3
                    decision[~np.isfinite(score).all(1)]=5
                decision[~photo['available'][:,1]]=4
                decision[(texture<5).all(1)]=6
                decision[(photo['selected_count']<3).any(1)]=7
                decision[~photo['computed']|~photo['sweep_defined']]=9
                assert np.array_equal(decision,photo['new_code'][mode_index]),(key,tile,mode_index,'photo precedence')
            mvar=z['u_mvs']**2+z['sigma_W_m']**2;pvar=z['sigma_P_m']**2
            with np.errstate(divide='ignore',invalid='ignore'):
                blend=(z['mvs_mean_m']*pvar+z['prior_height_m']*mvar)/(pvar+mvar)
            zero=(mvar==0)|(pvar==0);blend[zero]=z['mvs_mean_m'][zero]
            assert np.array_equal(zero,z['zero_weight_denominator'])
            for arm_index,regions in enumerate(z['arm_region']):
                heights=np.full(n,np.nan);heights[regions==0]=blend[regions==0]
                heights[np.isin(regions,[1,4])]=z['prior_height_m'][np.isin(regions,[1,4])]
                heights[regions==2]=z['mvs_mean_m'][regions==2]
                assert np.allclose(heights,z['arm_height_m'][arm_index],rtol=0,atol=1e-12,equal_nan=True),(key,tile,arm_index,'chosen height')
            sample=(photo['target_type_bits']&2)>0;tx.append(photo['best_score'][0,sample,0]);tw.append(photo['eligible_area_m2'][sample])
            known=outside&np.isin(z['cell'],[0,1,2]);correct=np.isin(z['region'][0],[2,3]);wrong=known&(((z['cell']==1)&~correct)|((z['cell']==2)&correct))
            primary=(photo['target_type_bits'][ix]&3)>0;missing_plane=primary&z['photo_computed']&~z['mvs_plane_available']
            checks.append(dict(group=key,tile=tile,count=n,accuracy_denominator=float(z['area'][known].sum()),wrong_area=float(z['area'][wrong].sum()),
                primary_missing_plane_count=int(missing_plane.sum()),primary_missing_plane_area_m2=float(z['area'][missing_plane].sum()),primary_photo_area_m2=float(z['area'][primary&z['photo_computed']].sum()),
                primary_inside_refuted_area_m2=[float(z['area'][(geom==0)&primary&(z['photo_code'][vi]==1)].sum()) for vi in range(2)]))
        counts[key]=count;x=np.concatenate(tx);w=np.concatenate(tw);good=np.isfinite(x)&(w>0);xx=x[good];ww=w[good];order=np.argsort(xx,kind='stable');threshold=xx[order][np.flatnonzero(np.cumsum(ww[order])>=.05*ww.sum())[0]] if len(xx) else None
        stored=json.loads((C/f'photo_threshold.{key}.reply2.lock.json').read_text())['t'];assert threshold==stored
        metric=json.loads((BASE/'metrics'/f'{key}.json').read_text());row=next(r for r in metric['accuracy'] if r['variant']=='new_clipped' and r['stratum']=='all');den=sum(r['accuracy_denominator'] for r in checks if r['group']==key);wrong=sum(r['wrong_area'] for r in checks if r['group']==key);assert abs(row['denominator_area_m2']-den)<1e-7 and abs(row['area_m2']-wrong)<1e-7
        cross_file=json.loads((D/'tables'/f'{key}_6_1_cross.json').read_text());cross=cross_file['rows'];provenance=cross_file['provenance']
        assert provenance['calculation_source_sha256']==sha(Path(__file__).parent/'metrics_reply2.py')
        for path,digest in provenance['input_sha256'].items():assert sha(Path(path))==digest,path
        for variant in ['new_clipped','new_oldphoto']:
            for panel in ['geometry','judgment']:
                rows=[r for r in cross if r['variant']==variant and r['panel']==panel and r['cell']<6]
                if rows[0]['denominator_area_m2']:
                    assert abs(sum(r['fraction'] for r in rows)-1)<1e-10,(key,variant,panel)
        arms=metric['ablation'];reference=next(r for r in arms if r['arm']=='main')
        for arm in arms:assert abs(arm['scored_area_m2']-reference['scored_area_m2'])<1e-7,(key,arm['arm'],'different evaluation denominator')
        causes=json.loads((D/'tables'/f'{key}_6_3_causes.json').read_text())['rows']
        plane_row=next(r for r in json.loads((D/'tables'/f'{key}_6_4_planes.json').read_text())['rows'] if r['metric']=='MVS 면 없음')
        tiles=[r for r in checks if r['group']==key]
        assert plane_row['count']==sum(r['primary_missing_plane_count'] for r in tiles)
        assert abs(plane_row['area_m2']-sum(r['primary_missing_plane_area_m2'] for r in tiles))<1e-7
        assert abs(plane_row['denominator_area_m2']-sum(r['primary_photo_area_m2'] for r in tiles))<1e-7
        for vi,variant in enumerate(['new_clipped','new_unclipped']):
            observed=next(r['area_m2'] for r in causes if r['variant']==variant and r['reason']=='한계 안 사진 반박(전체 한계 안 분모)')
            assert abs(observed-sum(r['primary_inside_refuted_area_m2'][vi] for r in tiles))<1e-7,(key,variant,'type 3 entered section 6')
        for variant in ['new_clipped','new_unclipped','new_oldphoto']:
            accounted=sum(r['area_m2'] for r in causes if r['variant']==variant and (r['reason'] in ['사진이 틀리게 지지','사진이 틀리게 반박'] or r['reason'].startswith('기본 방향:')))
            expected_wrong=next(r['area_m2'] for r in metric['accuracy'] if r['variant']==variant and r['stratum']=='all')
            assert abs(accounted-expected_wrong)<1e-7,(key,variant,'unaccounted error cause')
        for table in ['6_1_cross','6_2_accuracy','6_2_buildings','6_3_causes','6_4_photos','6_4_planes','6_5_geometry','6_5_precision','6_5_cell_cross','7_ablation']:
            for suffix in ['json','csv','md']:assert (D/'tables'/f'{key}_{table}.{suffix}').exists()
            assert json.loads((D/'tables'/f'{key}_{table}.json').read_text())['provenance']==provenance
    assert counts==({'ALS_1':501840,'LoD2_1':644427,'LoD2_2':1485308} if mode=='full' else {'ALS_1':501840,'LoD2_1':644427}),counts
    figures=[]
    for prior in ['ALS','LoD2']:
        maps=list((D/'figures').glob(f'그림1_{prior}_*.png'));assert len(maps)==8
        for p in maps:
            with Image.open(p) as im:assert im.width>3000 and min(im.info.get('dpi',[0,0]))>=299
            meta=json.loads(p.with_suffix('.json').read_text());assert not set(meta['patch_ids'])&excluded;figures.append(str(p))
        scope='all' if prior=='LoD2' and mode=='full' else 'roofs';selection=json.loads((C/f'figure2.{prior}.{scope}.selection.reply2.json').read_text());seen={};reasons={}
        for r in selection['selected']:
            assert r['area_m2']>=1;assert not set(r['indices'])&excluded;seen[r['building']]=seen.get(r['building'],0)+1;reasons[r['reason']]=reasons.get(r['reason'],0)+1
        assert all(v<=2 for v in seen.values()) and len(selection['selected'])<=4;assert len(list((D/'figures').glob(f'그림2_{prior}_{scope}_*.png')))==selection['selected_count']
    report=D/('판단검증_보고가_v1.md' if mode=='full' else '판단검증_지붕중간보고_v1.md');assert len(report.read_text())<=20000
    result=dict(at=now(),status='PASS_INDEPENDENT_STAGE_A_OUTPUTS' if mode=='full' else 'PASS_INDEPENDENT_ROOF_INTERIM',counts=counts,core_checks=checks,photo_thresholds_recomputed=True,
        training=False,holdout_values_opened=False,photo_precedence_recomputed_from_scores=True,all_nine_arm_heights_recomputed=True,source_sha256=sha(Path(__file__)),report_sha256=sha(report),scientific_verdict=None)
    dump(BASE/'validation'/f'{mode}.json',result);dump(D/f'validation_{mode}_reply2.json',result);print(result['status'],counts,flush=True)
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'full')
