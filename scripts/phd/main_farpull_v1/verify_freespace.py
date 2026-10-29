"""Recompute delivered quantities from the saved per-Gaussian arrays (Docker)."""
import json
from pathlib import Path
import numpy as np
from scipy.stats import rankdata


def main():
    root=Path('/out/freespace_v1');record=json.loads((root/'preflight.json').read_text())
    with np.load(root/'pressure_and_gradients.npz') as z:data={k:z[k] for k in z.files}
    P=data['pressure'];floating=data['floating'];correct=data['roof']|data['wall']
    assert not (floating&correct).any() and floating.sum()==13934 and len(P)==record['gaussians']
    # Independent rank-sum calculation, subtracting half the exact tie count.
    x,y=P[floating],P[correct];rank=rankdata(np.r_[x,y],method='average')
    mid=(rank[:len(x)].sum()-len(x)*(len(x)+1)/2)/(len(x)*len(y))
    _,cx=np.unique(x,return_counts=True);ux,cx=np.unique(x,return_counts=True);uy,cy=np.unique(y,return_counts=True)
    both,ix,iy=np.intersect1d(ux,uy,return_indices=True)
    ties=(cx[ix].astype(np.float64)*cy[iy]).sum()/(len(x)*len(y))
    strict=mid-.5*ties
    assert abs(strict-record['ranks']['roof_or_wall']['strict'])<1e-12
    groups=dict(roof=data['roof'],wall=data['wall'],floating=floating,other=~(data['roof']|data['wall']|floating))
    for row in record['groups']:
        values=P[groups[row['group']]]
        assert np.allclose(np.quantile(values,[.5,.9,.99]),[row['p50'],row['p90'],row['p99']],rtol=1e-12,atol=1e-12)
        assert abs((values>0).mean()-row['positive_fraction'])<1e-12
    a=float(np.median(data['photo_samples'].astype(np.float64).mean(0)))
    b=float(np.median(data['free_samples'].astype(np.float64).mean(0)))
    assert np.isclose(a,record['calibration']['a'],rtol=1e-12,atol=0)
    assert np.isclose(b,record['calibration']['b'],rtol=1e-12,atol=0)
    assert record['views']==203 and record['optimizer_steps']==0
    cells=json.loads(Path('/docs/freespace_v1/cells.json').read_text())['rows']
    views=json.loads((root/'views.json').read_text())['rows'];assert len(views)==203
    assert len({v['view'] for v in views})==203
    for row in cells:
        c=row['cell'];n=sum(v['cells'][c]['G_gt_half'] for v in views);d=sum(v['cells'][c]['pixels'] for v in views)
        assert n==row['G_gt_half'] and d==row['pixels']
    result=dict(status='PASS_RECOMPUTATION',views=203,rank_probability=strict,tie_fraction=ties,a=a,b=b,
        pressure_quantiles=True,cell_aggregation=True,scientific_verdict=None)
    for p in [root/'recomputation.json',Path('/docs/freespace_v1/recomputation.json')]:p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
