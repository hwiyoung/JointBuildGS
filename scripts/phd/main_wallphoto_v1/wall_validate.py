"""Independent membership/area/labels/source checks, preserving missing measurements."""
import ast,zipfile
from common import *
from wall_prepare import table
def main():
    cfg=load(C/'wallphoto_v1.json');rows=[];total=0
    for f in sorted((O/'patches').glob('*__LoD2.npz')):
        tile=f.stem.split('__')[0];out=npz(f);p=npz(O/'points'/f.name);raw=npz(W/'patch_values'/f'{tile}__LoD2__R1.5.npz')
        allowed=(raw['kind']==2)&~raw['holdout'];index={str(v):i for i,v in enumerate(raw['patch_id'])};ix=np.array([index[str(v)] for v in out['patch_id']])
        assert allowed[ix].all() and len(set(out['patch_id']))==len(ix)
        lookup={str(v):i for i,v in enumerate(p['point_id'])};done=out['judgment'][:,0]>=0
        pi=np.array([lookup[str(v)] for v in out['point_id'][done]])
        assert np.array_equal(out['judgment'][done],p['judgment'][pi])
        assert (out['judgment'][~done]==-1).all();assert out['judgment'].dtype==np.int8
        assert not p['holdout'].any() and np.all(p['kind']==2)
        counts=np.bincount(pi,minlength=len(p['point_id']));areas=np.bincount(pi,weights=raw['area'][ix[done]],minlength=len(p['point_id']))
        assert np.array_equal(counts,p['patch_count']) and np.allclose(areas,p['area'],atol=1e-9,rtol=0)
        # Independently replay all decision formulas from pre-storage features.
        for k,c in enumerate(cfg['judgments']['candidates']):
            expected=np.full(len(pi),2,np.int8);a=p['s_in'][pi];b=p['s_out'][pi];diff=a-b
            expected[(diff>=c['delta'])&(a>=c['s_min'])]=0;expected[(diff<=-c['delta'])&(b>=c['s_min'])]=1
            expected[np.isfinite(p['texture'][pi])&(p['texture'][pi]<5)]=3;expected[p['selected_count'][pi]<3]=4
            assert np.array_equal(expected,out['judgment'][done,k]),(tile,k)
        rows.append(dict(tile=tile,patches=len(ix),measured_patches=int(done.sum()),points=len(p['point_id']),area_m2=float(raw['area'][ix].sum()),status='PASS'));total+=len(ix)
    assert rows,'no completed measurements'
    held=set(load(W/'building_split.json')['holdout'])
    for folder in [D/'tables',D/'figures']:
        for f in folder.rglob('*'):
            if f.suffix in ['.json','.csv','.md']:
                text=f.read_text();assert not any(b in text for b in held),str(f)
    from PIL import Image
    figures=[]
    for f in (D/'figures').rglob('*.png'):
        assert f.with_suffix('.json').exists()
        with Image.open(f) as im:
            dpi=im.info.get('dpi',(0,0));assert min(dpi)>299;im.verify()
        figures.append(dict(file=str(f.relative_to(D)),status='format PASS; visual inspection separate'))
    rec=dict(at=now(),status='PASS',patches=total,rows=rows,figures=figures,scope='all exported patch memberships, all 15 label formulas, point area weights, holdout ID exclusion, PNG/JSON and DPI; not a scientific verdict',scientific_verdict=None)
    dump(O/'gates/delivery.json',rec);dump(D/'tables/validation.json',rec);print('wall delivery checks PASS',total,flush=True)
if __name__=='__main__':main()
