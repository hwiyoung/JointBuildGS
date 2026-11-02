"""Independent spatial geometry checks, exact conservation and frozen-input integrity."""
import numpy as np
from shapely.geometry import Point,Polygon
from common import *
ROOT=OUT/'r8_lod2_cause'
def main():
    config=json.loads((CFG/'cause_r8_lod2.json').read_text());b=json.loads((ROOT/'boundaries.json').read_text());summary=json.loads((ROOT/'summary.json').read_text())
    cells=json.loads((ROOT/'counts.json').read_text())['rows'];views=json.loads((ROOT/'render_views.json').read_text())['rows'];rng=np.random.default_rng(0)
    lo,hi=b['lo'],b['hi'];basis=np.array(b['basis']);poly=Polygon(np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]])@basis)
    checks=[]
    for row in config['rows']:
        key=row['key'];dest=ROOT/'states'/key;a=dict(np.load(dest/'arrays.npz'));g=dict(np.load(dest/'groups.npz'));n=len(a['xyz']);selected=rng.choice(n,min(1000,n),replace=False)
        for i in selected:
            point=Point(a['xyz'][i,:2]);distance=poly.distance(point);expected=0 if poly.covers(point) else 1 if distance<=50 else 2 if distance<=200 else 3
            assert expected==g['xy'][i],(key,i,distance)
            z=float(a['xyz'][i,2]);expected=sum(z>=t if j==0 else z>t for j,t in enumerate(b['height_local_m']))
            assert expected==g['height'][i],(key,i,z)
        rr=[r for r in cells if r['state']==key];assert sum(r['count'] for r in rr)==n
        for r in rr:
            sel=g['group']==r['tag']*16+r['xy_bin']*4+r['height_bin'];assert int(sel.sum())==r['count']
            if r['count']:
                assert float(np.median(a['longest_axis'][sel]))==r['longest_axis_median_m']
                assert float(np.median(a['opacity'][sel]))==r['opacity_median']
        vv=[v for v in views if v['state']==key];assert len(vv)==203 and len({v['camera'] for v in vv})==203
        m=np.load(ROOT/'renders'/key/'grouped_overlaps.npz')['overlaps'];assert np.array_equal(m.sum(1),[v['overlaps'] for v in vv])
        for vi in [0,101,202]:
            tiles=np.load(ROOT/'renders'/key/'tiles'/(vv[vi]['camera']+'.npz'))['tiles']
            for r in rr:
                sel=(g['provenance']==r['tag'])&(g['xy']==r['xy_bin'])&(g['height']==r['height_bin'])
                assert int(tiles[sel].astype('i8').sum())==int(m[vi,r['tag']*16+r['xy_bin']*4+r['height_bin']])
        checks.append(dict(state=key,count=n,geometry_sample=1000,all_cell_medians=True,all203_overlap_totals=True,independent_mask_sum_views=[0,101,202]))
    files={}
    for name in ['cause_r8_lod2.lock.r2.json','cause_r8_spatial.lock.r1.json','cause_r8_reporting.lock.json']:
        lock=json.loads((CFG/name).read_text());files.update(lock['files'])
    for p,h in files.items():assert sha(p)==h,p
    figures=list((ROOT/'figures').glob('*.png'));assert len(figures)==26
    for p in figures:assert p.with_suffix('.json').exists() and p.with_suffix('.pdf').exists()
    dump(ROOT/'verification.json',dict(at=stamp(),status='PASS',states=checks,views=2436,unchanged_input_and_source_files=len(files),
        figures_with_json=len(figures),training=False,optimization_steps=0,source_hashes=True,scientific_verdict=None))
    print('VERIFIED',12,2436,len(files),flush=True)
if __name__=='__main__':main()
