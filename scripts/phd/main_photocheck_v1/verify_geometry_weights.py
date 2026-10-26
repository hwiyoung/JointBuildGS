"""Independent all-point center, area, normal and membership verification."""
from common import *
def main():
    rows=[]
    for sealed in [False,True]:
        base=paths(sealed)
        for prior in ['LoD2','ALS']:
            count=0;patches=0;area=0.
            for f in sorted((base/'geometry').glob(f'*__{prior}.npz')):
                g=npz(f);n=len(g['point_id'])
                if not n:continue
                m=npz(f.with_name(f.stem+'__mapping.npz'));owner=m['point_index'];tile=f.stem.split('__')[0]
                with np.load(W/('holdout/patch_values' if sealed else 'patch_values')/f'{tile}__{prior}__R1.5.npz') as z:
                    weights=z['area'][m['source_index']];centres=z['centre'][m['source_index']];normals=z['normal'][m['source_index']]
                    assert np.array_equal(z['patch_id'][m['source_index']],m['patch_id'])
                numbers=np.bincount(owner,minlength=n);A=np.bincount(owner,weights=weights,minlength=n)
                assert np.array_equal(numbers,g['patch_count']) and (numbers>0).all();assert np.allclose(A,g['area'],atol=1e-8,rtol=0)
                C0=np.stack([np.bincount(owner,weights=weights*centres[:,j],minlength=n)/A for j in range(3)],axis=1)
                N0=np.stack([np.bincount(owner,weights=normals[:,j],minlength=n)/numbers for j in range(3)],axis=1);N0/=np.maximum(np.linalg.norm(N0,axis=1,keepdims=True),1e-15)
                assert np.allclose(C0,g['centre'],atol=1e-8,rtol=0,equal_nan=True)
                assert np.allclose(N0,g['normal'],atol=1e-8,rtol=0,equal_nan=True)
                good=g['geometry_valid'];assert np.allclose(np.linalg.norm(g['tangent1'][good],axis=1),1,atol=1e-8)
                assert np.allclose(np.sum(g['normal'][good]*g['tangent1'][good],axis=1),0,atol=1e-8)
                assert np.allclose(np.cross(g['normal'][good],g['tangent1'][good]),g['tangent2'][good],atol=1e-8)
                roof=g['kind']==1;count+=int(roof.sum());patches+=int(g['patch_count'][roof].sum());area+=float(g['area'][roof].sum())
            rows.append(dict(prior=prior,holdout=sealed,points=count,patches=patches,area_m2=area))
    result=dict(status='PASS',at=now(),scope=rows,checks=['all patch IDs preserved','all point member counts','area weighted centers','unweighted unit mean normals','orthonormal tangent bases'],scientific_verdict=None)
    dump(O/'gates/geometry_weights.json',result);dump(D/'tables/geometry_weights_validation.json',result);print('all geometry weights verified',sum(r['points'] for r in rows))
if __name__=='__main__':main()
