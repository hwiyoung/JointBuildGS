"""Validate the complete six-building pilot before committing its interim report."""
import ast
from common import *
from evaluate import join,write_table
def main():
    assert load(O/'gates/pilot.json')['status']=='PASS';assert sha(C/'photocheck_v1.json')==load(C/'photocheck_v1.lock.json')['sha256']
    held=set(load(W/'building_split.json')['holdout']);rows=[];wall=[]
    for prior in ['LoD2','ALS']:
        d,p=join(prior,'pilot');roof=d['kind']==1;actual=set(d['patch_id'][roof]);expected=set()
        for f in (W/'patch_values').glob(f'*__{prior}__R1.5.npz'):
            with np.load(f) as z:expected.update(z['patch_id'][(z['kind']==1)&np.isin(z['building'],EXAMPLES)])
        assert actual==expected and len(actual)==int(roof.sum())
        assert p['curve'].dtype==np.float16 and p['judgment'].dtype==np.int8
        labels=np.full(p['judgment'].shape,2,np.int8);difference=p['s_in']-p['s_out']
        for k,c in enumerate(load(C/'photocheck_v1.json')['judgments']['candidates']):
            labels[(difference>=c['delta'])&(p['s_in']>=c['s_min']),k]=0
            labels[(difference<=-c['delta'])&(p['s_out']>=c['s_min']),k]=1
            labels[p['texture']<5,k]=3;labels[p['selected_count']<3,k]=4
        assert np.array_equal(labels,p['judgment'])
        tab=load(D/'tables/pilot'/f'{prior}_summary_15.json')['rows'];assert len(tab)==60
        for r in tab:
            mask=roof.copy()
            if 'gt_known' in r['scope']:mask&=d['gt_valid']
            if 'unexplained' in r['scope']:mask&=d['unexplained']
            assert np.isclose(d['area'][mask].sum(),r['area_m2'])
            for j,key in enumerate(['support','refute','ambiguous','textureless','few_photos']):
                assert np.isclose(d['area'][mask&(d['judgment'][:,r['combination']]==j)].sum(),r[key+'_area_m2'])
        wm=d['kind']==2;wall.append(dict(prior=prior,building=EXAMPLES[5],points=int((p['kind']==2).sum()),patches=int(wm.sum()),area_m2=d['area'][wm].sum(),main_tables_included=False,status='observation only' if wm.any() else 'no inherited wall patches'))
        rows.append(dict(prior=prior,roof_points=int((p['kind']==1).sum()),roof_patches=int(roof.sum()),roof_area_m2=d['area'][roof].sum(),candidate_decisions_verified=int(labels.size)))
    write_table('observation_wall',wall,'pilot')
    for f in D.rglob('*'):
        if f.is_file() and f.suffix in ['.md','.json','.csv']:assert not any(b in f.read_text() for b in held),f
    for f in S.glob('*.py'):ast.parse(f.read_text())
    png=list((D/'figures/pilot').glob('*.png'))
    assert len(png)==46,len(png)
    for f in png:assert f.with_suffix('.json').exists()
    for r in load(O/'gates/pilot.json')['pilot_files']:assert sha(O/'work/pilot'/r['file'])==r['sha256']
    result=dict(status='PASS',at=now(),rows=rows,pilot_figures=len(png),projection_figures=24,checks=['all six-building inherited roof patch IDs exactly once','all persisted point decisions replayed','all 60 summary rows per prior','wall excluded from roof summaries','public holdout ID scan','source syntax','pilot file hashes'],scientific_verdict=None)
    dump(O/'gates/pilot_delivery.json',result);dump(D/'tables/pilot_validation.json',result);print('pilot delivery PASS',clean(rows))
if __name__=='__main__':main()
