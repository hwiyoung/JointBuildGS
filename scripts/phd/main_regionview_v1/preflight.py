"""CPU boundary checks and a source/configuration lock before measurement."""
import ast
import platform
import sys
import scipy
import shapely
import matplotlib
from shapely.geometry import box
from common import *
from geometry import associate, Catalog, plan_distance
from render import raster, Cameras

def checks():
    p=box(0,0,1,1);xy=np.array([[.5,.5],[1.,.5],[1.5,.5],[2.,.5],[2.0001,.5]])
    assert np.allclose(plan_distance(p,xy),[0,0,.5,1,1.0001])
    f=dict(gml='a',building='A',type='roof',poly=p,ground=p)
    d=dict(area=np.ones(5),centre=np.c_[xy,np.zeros(5)],building=np.array(['']*5),surf=np.zeros(5))
    result=associate(d,'ALS',{0:f},'unique_plan_building')
    assert list(result['face'])==['a','a','a','a','']
    f2=dict(f,gml='b',building='B',poly=box(.4,.4,.8,.8),ground=box(.4,.4,.8,.8))
    overlap=associate(d,'ALS',{0:f,1:f2},'unique_plan_building')
    assert overlap['face'][0]=='' and overlap['association_status'][0]=='ambiguous_building'
    known=dict(d,building=np.array(['B']*5));same=associate(known,'ALS',{0:f},'unique_plan_building')
    assert np.all(same['face']==''),'must not transfer to another building'
    rr=raster(np.array([[0,0],[.05,.05],[.1,.1],[1,0]]),np.array([.1,.3,.1,.2]),np.array([1,3,1,0]),np.array([0,1,0,6]),np.array([0,0,0,1]))
    assert rr['region'][0,0]==3 and rr['cell'][0,0]==1 and rr['overlapping_cells']==1
    assert rr['occupied_cells']==2 and np.isclose(rr['area'].sum(),.7)
    assert np.sum(rr['region']==-99)>0,'empty bins must be transparent, never unknown or agreement'
    for p in (REPO/'scripts/phd/main_regionview_v1').glob('*.py'):ast.parse(p.read_text())
    return ['polygon containment and 1m boundary','overlapping buildings stay unassigned','same-building constraint',
        'area-weighted raster plurality','overlap cell count','empty bins preserved','script syntax']

def main():
    tests=checks();ledger=Ledger();catalog=Catalog(ledger);units=[]
    held=set(ledger.json(JN/'holdout/scope_membership.json',sealed=True)['buildings'])
    for site in SITES:
        faces=catalog.context(site=site);cam=Cameras(site,ledger)
        for prior in ['ALS','LoD2']:
            p=TG/'r2/targets'/f'{site}_{prior}.npz';meta=ledger.json(p.with_suffix('.json'))
            assert sha(p)==meta['target_sha256']
            with np.load(p) as z:
                ev=z['in_eval'];buildings=set(z['building'][ev])-{''}
                assert not buildings&held
                if prior=='LoD2':
                    assert set(z['surf'][ev])<=set(faces)
                    unit_ids={faces[int(e)]['gml'] for e in np.unique(z['surf'][ev])}
                else:unit_ids=set()
                units.append(dict(site=site,prior=prior,evaluation_patches=int(ev.sum()),face_count=len(unit_ids),train_views=len(cam.split['train'])))
    dump(OUT/'preflight.json',dict(status='PASS',at=stamp(),checks=tests,units=units,scientific_verdict=None))
    cfg=CFG/'regionview_v1.json'
    lock=dict(at=stamp(),config_sha256=sha(cfg),order_sha256=sha(CFG/'order_v1.txt'),
        implementation_sha256={str(p.relative_to(REPO)):sha(p) for p in sorted((REPO/'scripts/phd/main_regionview_v1').glob('*')) if p.is_file()},
        before_face_statistics=True,source_commit=os.environ['REGIONVIEW_COMMIT'],image_id=os.environ['REGIONVIEW_IMAGE'],
        versions=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,shapely=shapely.__version__,matplotlib=matplotlib.__version__,platform=platform.platform()),scientific_verdict=None)
    target=CFG/'regionview_v1.lock.json'
    if target.exists():
        previous=read(target)
        if previous['config_sha256']==lock['config_sha256'] and previous['implementation_sha256']==lock['implementation_sha256']:
            print('EXISTING_LOCK_UNCHANGED',flush=True);return
        dump(CFG/'revisions'/('lock_'+previous['at'].replace(':','-')+'.json'),previous)
        lock['before_face_statistics']=not (OUT/'measurement_complete_r2.json').exists()
        lock['previous_lock_sha256']=sha(target)
    dump(target,lock)
    print('PREFLIGHT_PASS',units,flush=True)

if __name__=='__main__':main()
