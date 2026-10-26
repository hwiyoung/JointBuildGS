"""Audit surface identity and preserved zero-normal cases without reading GT."""
from common import *
def main():
    rows=[]
    for prior in ['LoD2','ALS']:
        nf=patches=0;area=0.;fallback=0;fallback_area=0.
        for f in (W/'patch_values').glob(f'*__{prior}__R1.5.npz'):
            with np.load(f) as z:
                roof=z['kind']==1;s=z['surf'][roof];b=z['building'][roof];a=z['area'][roof]
                for face in np.unique(s):
                    m=s==face
                    if len(np.unique(b[m]))>1:nf+=1;patches+=int(m.sum());area+=float(a[m].sum())
            rec=load(O/'geometry'/f.name.replace('__R1.5.npz','.json'))
            for item in rec['surface_audit']:
                if item['tangent_fallback']:fallback+=1;fallback_area+=item['area_m2']
        rows.append(dict(prior=prior,multi_building_faces=nf,patches_on_those_faces=patches,area_m2=area,tangent_fallback_groups=fallback,tangent_fallback_area_m2=fallback_area))
    dump(O/'gates/group_audit.json',dict(rows=rows,scientific_verdict=None));print(json.dumps(clean(rows)))
if __name__=='__main__':main()
