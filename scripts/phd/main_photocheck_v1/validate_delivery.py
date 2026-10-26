"""Independent delivered-membership, decision, truth-summary and sealing checks."""
import ast
from common import *
def main():
    assert sha(C/'photocheck_v1.json')==load(C/'photocheck_v1.lock.json')['sha256']
    assert load(O/'gates/pilot.json')['status']=='PASS'
    assert load(O/'gates/benchmark.json')['status']=='PASS'
    cfg=load(C/'photocheck_v1.json');rows=[];totals={}
    for sealed in [False,True]:
      base=paths(sealed)
      for prior in ['LoD2','ALS']:
        npatches=npoints=0;area=0.;global_ids=set()
        for file in sorted((base/'points').glob(f'*__{prior}.npz')):
            p=npz(file);patch=npz(base/'patches'/file.name);tile=file.stem.split('__')[0]
            source=W/('holdout/patch_values' if sealed else 'patch_values')/f'{tile}__{prior}__R1.5.npz'
            with np.load(source) as z:
                roof=z['kind']==1;assert np.array_equal(z['patch_id'][roof],patch['patch_id']);A=float(z['area'][roof].sum())
                assert np.isclose(p['area'].sum(),A,rtol=0,atol=1e-7)
            assert not any(k.startswith('gt') or k=='cell' for k in p),file
            assert p['curve'].dtype==np.float16;assert patch['judgment'].shape==(len(patch['patch_id']),15)
            assert len(np.unique(p['point_id']))==len(p['point_id']);assert not global_ids.intersection(p['point_id']);global_ids.update(p['point_id'])
            # Recompute candidate precedence independently from persisted full-precision features.
            labels=np.full(p['judgment'].shape,2,np.int8);delta=p['s_in']-p['s_out']
            for k,c in enumerate(cfg['judgments']['candidates']):
                labels[(delta>=c['delta'])&(p['s_in']>=c['s_min']),k]=0
                labels[(delta<=-c['delta'])&(p['s_out']>=c['s_min']),k]=1
                labels[np.isfinite(p['texture'])&(p['texture']<5),k]=3
                labels[p['selected_count']<3,k]=4
            assert np.array_equal(labels,p['judgment']),file
            point_lookup={name:i for i,name in enumerate(p['point_id'])};pi=np.array([point_lookup[v] for v in patch['point_id']]);assert np.array_equal(p['judgment'][pi],patch['judgment'])
            counts=np.bincount(pi,minlength=len(p['point_id']));assert np.array_equal(counts,p['patch_count'])
            assert np.all(p['selected_count']==(p['selected_images']>=0).sum(1));assert np.all((p['selected_images']>=-1)&(p['selected_images']<819))
            assert np.all(p['eligible_images']>=p['selected_count']);assert np.all(p['selected_count']<=10)
            finite=np.isfinite(p['curve']);assert np.max(abs(p['curve'][finite]))<=1.001 if finite.any() else True
            assert np.all(np.isfinite(p['heights'][:,:141]))
            extra=np.isfinite(p['mvs_p'])&(abs(p['mvs_p'])>5);assert np.array_equal(np.isfinite(p['heights'][:,141:]).all(1),extra)
            npatches+=len(patch['patch_id']);npoints+=len(p['point_id']);area+=A
        totals[(prior,sealed)]=dict(prior=prior,holdout=sealed,points=npoints,patches=npatches,area_m2=area)
    expected=load(O/'geometry_summary.json')['rows']
    for x in expected:
        y=totals[(x['prior'],x['holdout'])];assert x['points']==y['points'] and x['patches']==y['patches'];assert np.isclose(x['area_m2'],y['area_m2'],rtol=0,atol=1e-6)
    # Existing input files must match the saved exact hashes.
    for p,h in load(O/'input_preflight.json')['sources'].items():assert sha(p)==h,p
    for sealed in [False,True]:
        for p in (paths(sealed)/'geometry').glob('*.json'):
            r=load(p);source=W/('holdout/patch_values' if sealed else 'patch_values')/f'{r["tile"]}__{r["prior"]}__R1.5.npz';assert sha(source)==r['source_sha256'],source
    held=set(load(W/'building_split.json')['holdout']);scanned=0
    for f in D.rglob('*'):
        if f.is_file() and f.suffix in ['.md','.json','.csv']:
            text=f.read_text();assert not any(b in text for b in held),f;scanned+=1
    # Contract code paths: photo score and decision modules have no evaluation data fields.
    for name in ['cameras.py','curves.py','features.py','run_measure.py']:
        text=(S/name).read_text();tree=ast.parse(text)
        strings=[node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)]
        assert not any(s in ['gt_p','gt_status','cell','prior_right'] for s in strings),name
    for prior in ['LoD2','ALS']:
        d=npz(O/'evaluation/full'/f'{prior}_patches.npz');tab=load(D/'tables/full'/f'{prior}_summary_15.json')['rows']
        for row in tab:
            mask=d['kind']==1
            if 'gt_known' in row['scope']:mask&=d['gt_valid']
            if 'unexplained' in row['scope']:mask&=d['unexplained']
            assert np.isclose(row['area_m2'],d['area'][mask].sum(),atol=1e-8)
            k=row['combination'];total=0.
            for j,label in enumerate(['support','refute','ambiguous','textureless','few_photos']):
                ix=mask&(d['judgment'][:,k]==j);value=d['area'][ix].sum();assert np.isclose(value,row[label+'_area_m2'],atol=1e-8);total+=value
            assert np.isclose(total,row['area_m2'],atol=1e-8)
        assert len(tab)==60
    report=D/'사진확인_보고_v1.md';assert len(report.read_text())<20000
    for p in (D/'figures').rglob('*.png'):assert p.with_suffix('.json').exists(),p
    result=dict(status='PASS',scope=list(totals.values()),public_text_files_scanned=scanned,checks=['exact source roof patch membership','one point per patch','15 decisions independently replayed','finite/missing counts preserved','height extension','input hashes unchanged','GT-free selection/scoring code paths','public holdout ID exclusion','all 60 summary rows per prior independently recomputed','PNG JSON pairing','report under 20000 characters'],environment=env(),scientific_verdict=None)
    dump(O/'gates/delivery.json',result);dump(D/'tables/validation.json',result);print('delivery validation PASS',clean(list(totals.values())))
if __name__=='__main__':main()
