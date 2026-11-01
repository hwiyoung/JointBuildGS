"""Area-weighted face summaries; no judgment, threshold or training computation."""
import time
from collections import defaultdict
from common import *
from geometry import Catalog, associate

def measurements(d,ids):
    a=d['area'][ids].astype(float);r=d['region'][ids];c=d['cell'][ids]
    total=float(a.sum());match=((r==1)&(c==0))|((r==2)&(c==2))|((r==3)&(c==1))
    comparable=np.isin(r,[1,2,3])&np.isin(c,[0,1,2]);baseline=np.isin(c,[0,1,2,3])
    out=dict(patch_count=len(ids),eval_area_m2=total,match_area_m2=float(a[match].sum()),
        match_comparable_area_m2=float(a[comparable].sum()),baseline_area_m2=float(a[baseline].sum()),
        prior_only_wrong_area_m2=float(a[np.isin(c,[1,3])].sum()),image_only_wrong_area_m2=float(a[np.isin(c,[2,3])].sum()))
    for lab,name in NAMES.items():out[name+'_area_m2']=float(a[r==lab].sum())
    for cell in range(7):out[f'cell{cell}_area_m2']=float(a[c==cell].sum())
    for lab in NAMES:
        for cell in range(7):out[f'joint_{lab}_{cell}_area_m2']=float(a[(r==lab)&(c==cell)].sum())
    return out

def decorate(row,aggregate=False):
    row=dict(row);total=row['eval_area_m2']
    ratio=lambda x,y:x/y if y>0 else None
    for name in NAMES.values():row[name+'_fraction']=ratio(row[name+'_area_m2'],total)
    for cell in range(7):row[f'cell{cell}_fraction']=ratio(row[f'cell{cell}_area_m2'],total)
    row['match_fraction_all_eval']=ratio(row['match_area_m2'],total)
    row['match_fraction_comparable']=ratio(row['match_area_m2'],row['match_comparable_area_m2'])
    for key in ['prior_only','image_only']:row[key+'_wrong_fraction']=ratio(row[key+'_wrong_area_m2'],row['baseline_area_m2'])
    areas=np.array([row[name+'_area_m2'] for name in NAMES.values()])
    code=list(NAMES)[int(areas.argmax())]
    row['dominant_region']=LABELS[code] if total>0 and not aggregate else None
    row['dominant_code']=code if total>0 and not aggregate else None
    row['purity']=ratio(float(areas.max()),total) if not aggregate else None
    row['wholly_one_region']=bool(np.count_nonzero(areas>0)==1) if not aggregate else None
    row['source_tag']=TAG
    return row

def combine(rows,metadata):
    cols=['patch_count']+[k for k in rows[0] if k.endswith('_area_m2')]
    return decorate({**metadata,**{k:sum(r[k] for r in rows) for k in cols}},aggregate=True)

def face_rows(d,scope,prior,faces):
    rows=[]
    by_gml={f['gml']:f for f in faces.values()}
    for gml in np.unique(d['face'][d['face']!='']):
        ids=np.flatnonzero(d['face']==gml);f=by_gml[gml]
        meta=dict(scope=scope,prior=prior,revision=REV,building=f['building'],building_name=building_label(f['building']),
            face_id=gml,face_name=f['name'],face_kind=f['type'],original_face_area_m2=f['area'],face_count=1,
            changed_building_note='평면 범위가 같아도 높이가 다를 수 있음' if building_label(f['building'])=='B173' else '')
        row=measurements(d,ids);row.pop('original_face_area_m2',None)
        rows.append(decorate(dict(**meta,**row)))
    return rows

def collapse_tiles(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['face_id']].append(r)
    result=[]
    for gml,rr in groups.items():
        summed=dict(rr[0])
        for k in ['patch_count']+[k for k in rr[0] if k.endswith('_area_m2') and k!='original_face_area_m2']:
            summed[k]=sum(r[k] for r in rr)
        result.append(decorate(summed))
    return result

def public_faces(rows):
    out=[r for r in rows if r['eval_area_m2']>=1]
    for kind in ['roof','wall']:
        small=[r for r in rows if r['face_kind']==kind and 0<r['eval_area_m2']<1]
        if small:
            meta={k:small[0][k] for k in ['scope','prior','revision']}
            out.append(combine(small,dict(**meta,building='합계',building_name='합계',face_id='SMALL_'+kind,
                face_name='작은 면',face_kind=kind,face_count=len(small),changed_building_note='각 면의 평가 넓이 1 m² 미만; 순도 분포는 개별 면으로 계산')))
    return sorted(out,key=lambda r:(-r['eval_area_m2'],r['face_id']))

def distribution(rows,scope,prior):
    out=[]
    for kind in ['roof','wall']:
        rr=[r for r in rows if r['face_kind']==kind and r['eval_area_m2']>0]
        den=sum(r['eval_area_m2'] for r in rr)
        for dominant in ['all',*LABELS.values()]:
            for bucket in ['90% 이상','70~90%','70% 미만']:
                pick=[r for r in rr if (dominant=='all' or r['dominant_region']==dominant) and
                    ('90% 이상' if r['purity']>=.9 else '70~90%' if r['purity']>=.7 else '70% 미만')==bucket]
                area=sum(r['eval_area_m2'] for r in pick)
                out.append(dict(scope=scope,prior=prior,revision=REV,face_kind=kind,dominant_region=dominant,purity_bin=bucket,
                    face_count=len(pick),eval_area_m2=area,denominator_area_m2=den,area_fraction=area/den if den else None,
                    wholly_one_region_count=sum(r['wholly_one_region'] for r in pick),
                    wholly_one_region_area_m2=sum(r['eval_area_m2'] for r in pick if r['wholly_one_region']),source_tag=TAG))
    return out

def save_patch(d,path):
    keep=['centre','area','kind','region','cell','face','assigned_building','association_status','face_distance_m','face_tie']
    for optional in ['patch_id','source_index']:
        if optional in d:keep.append(optional)
    np.savez_compressed(writable(path),**{k:d[k] for k in keep})

def audit_unit(d,scope,prior,unit):
    total=float(d['area'].sum());attached=d['face']!=''
    rows=[]
    for status in np.unique(d['association_status']):
        m=d['association_status']==status;area=float(d['area'][m].sum())
        rows.append(dict(scope=scope,prior=prior,unit=unit,association_status=status,patch_count=int(m.sum()),eval_area_m2=area,
            total_eval_area_m2=total,area_fraction=area/total if total else None,source_tag=TAG))
    return rows,dict(scope=scope,prior=prior,unit=unit,total_eval_area_m2=total,attached_area_m2=float(d['area'][attached].sum()),
        unassigned_area_m2=float(d['area'][~attached].sum()),unassigned_fraction=float(d['area'][~attached].sum())/total if total else None,
        face_tie_patch_count=int(d['face_tie'].sum()),face_tie_area_m2=float(d['area'][d['face_tie']].sum()),
        input_patch_count=len(d['area']),source_tag=TAG)

def main():
    start=time.monotonic();cfg=check_locked();ledger=Ledger();catalog=Catalog(ledger)
    source_lock=ledger.json(REPO/'configs/phd/main_target_v1/target_v1.r2.lock.json')
    assert sha(ledger.add(REPO/'configs/phd/main_target_v1/revisions/r2/target_v1.json'))==source_lock['config_sha256']
    if REV=='r7':
        r7cfg=REPO/'configs/phd/main_target_v1/target_v1.r7.stage0.json'
        r7lock=ledger.json(r7cfg.with_name('target_v1.r7.stage0.lock.json'))
        spec=ledger.json(r7cfg);assert sha(r7cfg)==r7lock['config_sha256']
        assert spec['eligible_region']==0 and spec['new_region']==5 and spec['new_region_name']=='disappeared'
        for s in cfg['sites']:
            for p in cfg['priors']:assert (TG/'r7/stage0'/f'{s}_{p}.json').exists(),'r7 experiment incomplete'
        for sc in ['development','holdout']:
            root=TG/('holdout/r7/stage0' if sc=='holdout' else 'r7/stage0/development')
            for p in cfg['priors']:assert (root/f'{p}.complete.json').exists(),'r7 census incomplete'
    jcfg=ledger.json(REPO/'configs/phd/main_judgenum_v1/judgenum_v1.json')
    held=set(ledger.json(JN/'holdout/scope_membership.json',sealed=True)['buildings']);dev=set(jcfg['scope']['development'])
    assert not held&dev
    all_distributions=[];all_summaries=[];association_rows=[];association_summary=[];face_total=0
    for site in cfg['sites']:
        faces=catalog.context(site=site)
        for prior in cfg['priors']:
            p=TG/'r2/targets'/f'{site}_{prior}.npz';meta=ledger.json(p.with_suffix('.json'))
            assert sha(p)==meta['target_sha256'] and meta['config_sha256']==source_lock['config_sha256']
            d=ledger.arrays(p,['centre','normal','kind','area','in_eval','surf','building','region'])
            r=ledger.arrays(S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz',['centre','kind','area','surf_ext','in_eval','code_ext_v3'])
            for key in ['centre','kind','area','in_eval']:assert np.array_equal(d[key],r[key]),(site,prior,key)
            assert np.array_equal(d['surf'],r['surf_ext'])
            d['cell']=np.array([CODE_TO_CELL[int(v)] for v in r['code_ext_v3']],np.int8)
            mask=d['in_eval'];d={k:v[mask] for k,v in d.items()};d['source_index']=np.flatnonzero(mask)
            assert np.isin(d['region'],[-1,0,1,2,3]).all()
            if REV=='r2':d.update(associate(d,prior,faces,cfg['building_missing_policy']))
            else:
                original=ledger.arrays(OUT/f'r2/patches/{site}_{prior}.npz')
                newpath=TG/'r7/targets'/f'{site}_{prior}.npz';receipt=ledger.json(TG/'r7/stage0'/f'{site}_{prior}.json')
                assert receipt['input_sha256']==sha(p) and receipt['output_sha256']==sha(newpath)
                assert receipt['config_sha256']==r7lock['config_sha256']
                new=ledger.arrays(newpath,['centre','area','kind','in_eval','surf','building','region'])
                for key in ['centre','area','kind','surf','building']:assert np.array_equal(new[key][mask],d[key]),key
                assert np.array_equal(new['in_eval'],mask)
                nr=new['region'][mask];assert np.all((nr==d['region'])|((d['region']==0)&(nr==5)))
                d=original;d['region']=nr
            assert not held&set(d['assigned_building']), 'holdout building in experiment: refuse public output'
            rows=face_rows(d,site,prior,faces);face_total+=len(rows)
            table(OUT/f'{REV}/tables/faces_full_{site}_{prior}.csv',rows)
            table(DOC/f'tables/faces_{site}_{prior}_{REV}.csv',public_faces(rows))
            save_patch(d,OUT/f'{REV}/patches/{site}_{prior}.npz')
            ar,au=audit_unit(d,site,prior,site);association_rows+=ar;association_summary.append(au)
            all_distributions+=distribution(rows,site,prior)
            for kind in ['roof','wall']:
                pick=[r for r in rows if r['face_kind']==kind]
                if pick:
                    summary=combine(pick,dict(scope=site,prior=prior,face_kind=kind,face_count=len(pick)))
                    summary['wholly_one_region_area_m2']=sum(r['eval_area_m2'] for r in pick if r['wholly_one_region'])
                    summary['high_purity_area_m2']=sum(r['eval_area_m2'] for r in pick if r['purity']>=.9)
                    all_summaries.append(summary)
            print('EXPERIMENT',site,prior,'faces',len(rows),'unassigned_m2',round(au['unassigned_area_m2'],3),flush=True)
    for scope,eligible in [('development',dev),('holdout',held)]:
        sealed=scope=='holdout';root=TG/('holdout/r2/stage0' if sealed else 'r2/stage0/development')
        input_root=JN/('holdout/inputs' if sealed else 'inputs');dest=OUT/('holdout' if sealed else 'development')/REV
        for prior in cfg['priors']:
            if REV=='r7':
                vote_root=TG/('holdout/r7/stage0' if sealed else 'r7/stage0/development')
                vote_receipt=ledger.json(vote_root/f'{prior}.complete.json',sealed=sealed)
                assert vote_receipt['config_sha256']==r7lock['config_sha256']
            pieces=[];seen=set();units=0;scope_audits=[];scope_details=[]
            for p in sorted(root.glob(f'*__{prior}.npz')):
                tile=p.stem.split('__')[0]
                d=ledger.arrays(p,['patch_id','building','kind','area','cell','region'],sealed=sealed)
                g=ledger.arrays(input_root/p.name,['patch_id','centre','surf','building','area','kind','cell'],sealed=sealed)
                ix=join(g['patch_id'],d['patch_id'])
                for k in ['building','area','kind','cell']:assert np.array_equal(d[k],g[k][ix]),k
                assert set(d['building'])<=eligible
                assert not seen&set(d['patch_id']);seen.update(d['patch_id'])
                d.update(centre=g['centre'][ix],surf=g['surf'][ix])
                faces=catalog.context(tile=tile,sealed=sealed)
                if REV=='r2':d.update(associate(d,prior,faces,cfg['building_missing_policy']))
                else:
                    original=ledger.arrays(OUT/('holdout' if sealed else 'development')/'r2/patches'/p.name,sealed=sealed)
                    # TARGET recorded its own writable mount as /out; that same
                    # immutable tree is mounted read-only as TG in this task.
                    receipt_key='/out/'+p.relative_to(TG).as_posix()
                    assert vote_receipt['input_files'][receipt_key]==sha(p)
                    votes=ledger.arrays(vote_root/p.name,['disappeared'],sealed=sealed)
                    gone=votes['disappeared'];assert gone.shape==d['region'].shape and np.all(d['region'][gone]==0)
                    nr=d['region'].copy();nr[gone]=5;d=original;d['region']=nr
                pieces+=face_rows(d,scope,prior,faces)
                ar,au=audit_unit(d,scope,prior,tile);scope_details+=ar;scope_audits.append(au)
                save_patch(d,dest/'patches'/f'{tile}__{prior}.npz');units+=1
            rows=collapse_tiles(pieces);face_total+=len(rows)
            table(dest/'tables'/f'faces_full_{prior}_{REV}.csv',rows)
            if not sealed:table(DOC/f'tables/faces_{scope}_{prior}_{REV}.csv',public_faces(rows))
            else:
                table(dest/'tables'/f'association_{prior}_{REV}.csv',scope_details)
                table(dest/'tables'/f'association_units_{prior}_{REV}.csv',scope_audits)
            # Sealed tile IDs, patch IDs and per-face values never enter public tables.
            total=sum(r['total_eval_area_m2'] for r in scope_audits);un=sum(r['unassigned_area_m2'] for r in scope_audits)
            association_summary.append(dict(scope=scope,prior=prior,unit='합계',unit_count=units,total_eval_area_m2=total,
                attached_area_m2=total-un,unassigned_area_m2=un,unassigned_fraction=un/total if total else None,
                face_tie_patch_count=sum(r['face_tie_patch_count'] for r in scope_audits),face_tie_area_m2=sum(r['face_tie_area_m2'] for r in scope_audits),
                input_patch_count=sum(r['input_patch_count'] for r in scope_audits),source_tag=TAG))
            if not sealed:association_rows+=scope_details
            all_distributions+=distribution(rows,scope,prior)
            for kind in ['roof','wall']:
                pick=[r for r in rows if r['face_kind']==kind]
                if pick:
                    summary=combine(pick,dict(scope=scope,prior=prior,face_kind=kind,face_count=len(pick)))
                    summary['wholly_one_region_area_m2']=sum(r['eval_area_m2'] for r in pick if r['wholly_one_region'])
                    summary['high_purity_area_m2']=sum(r['eval_area_m2'] for r in pick if r['purity']>=.9)
                    all_summaries.append(summary)
            print('CENSUS',scope,prior,'faces',len(rows),'patches',len(seen),flush=True)
    table(DOC/f'tables/purity_{REV}.csv',all_distributions)
    table(DOC/f'tables/summary_{REV}.csv',all_summaries)
    table(DOC/f'tables/association_{REV}.csv',association_rows)
    table(DOC/f'tables/association_units_{REV}.csv',association_summary)
    for prior in cfg['priors']:
        table(DOC/f'tables/faces_holdout_{prior}_{REV}.csv',[r for r in all_summaries if r['scope']=='holdout' and r['prior']==prior],
              privacy='counts, areas and ratios only; original-face details restricted to external holdout/')
    ledger.save()
    dump(OUT/f'measurement_complete_{REV}.json',dict(at=stamp(),status='MEASURED',face_records=face_total,seconds=time.monotonic()-start,
        source_commit=os.environ['REGIONVIEW_COMMIT'],image_id=os.environ['REGIONVIEW_IMAGE'],source_tag=TAG,scientific_verdict=None))

if __name__=='__main__':main()
