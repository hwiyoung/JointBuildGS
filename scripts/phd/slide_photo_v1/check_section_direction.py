"""Post-render audit of fixed sections; does not select locations or alter figures."""
from common import *

def main():
    current=load(DOC/'figures/figS_b_correction_sections.json')
    original=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples']
    records=[]
    for row,src in zip(current['examples'],original):
        H=np.asarray(src['heights_model_m']);s=np.asarray(src['bin_centres_m'])
        # Diagnostic bins with a substantial input/reference vertical separation.
        mask=np.isfinite(H[:,0])&np.isfinite(H[:,2])&(np.abs(H[:,0]-H[:,2])>.5)
        methods=[]
        for out in row['outputs']:
            seg=np.asarray(out['section_segments']);dx=seg[:,1,0]-seg[:,0,0]
            valid=np.abs(dx)>1e-12;safe=np.where(valid,dx,1)
            hit=[]
            for k in np.flatnonzero(mask):
                t=(s[k]-seg[:,0,0])/safe
                use=valid&(t>=0)&(t<=1)
                z=seg[use,0,1]+t[use]*(seg[use,1,1]-seg[use,0,1])
                hit.append(dict(bin_index=int(k),s_m=float(s[k]),prior_m=float(H[k,0]),gt_m=float(H[k,2]),intersection_count=len(z),
                    nearest_prior_abs_vertical_m=float(np.min(np.abs(z-H[k,0]))) if len(z) else None,
                    nearest_gt_abs_vertical_m=float(np.min(np.abs(z-H[k,2]))) if len(z) else None))
            present=[h for h in hit if h['intersection_count']]
            methods.append(dict(result=out['result'],name=out['name'],bins=hit,present_bins=len(present),
                bins_with_surface_within_25cm_prior=sum(h['nearest_prior_abs_vertical_m']<=.25 for h in present),
                bins_with_surface_within_25cm_gt=sum(h['nearest_gt_abs_vertical_m']<=.25 for h in present),
                median_nearest_prior_vertical_m=float(np.median([h['nearest_prior_abs_vertical_m'] for h in present])) if present else None,
                median_nearest_gt_vertical_m=float(np.median([h['nearest_gt_abs_vertical_m'] for h in present])) if present else None))
        records.append(dict(id=row['example']['id'],selected_diagnostic_bins=int(mask.sum()),methods=methods,viscmp_v1_overlap=row['viscmp_v1_overlap']))
    d=dict(status='MEASURED',scientific_verdict=None,scope='[이 발주에서 냄]; post-render diagnostic, no location/threshold selection or figure modification',
           method='At unchanged REGIONFIG bin centres where |prior-GT|>0.5m, intersect every unfiltered TSDF section segment with vertical bin line. Count whether any intersection is within 0.25m vertically of each input height. All multiple intersections retained; nearest does not establish same-surface correspondence. The 0.25m tolerance is an audit aid, not DIST71 tau or a scientific pass criterion.',examples=records)
    dump(DOC/'qa/section_direction.json',d)
    for r in records:
        print(r['id'],r['selected_diagnostic_bins'],r['viscmp_v1_overlap'])
        for m in r['methods']:print(m['name'],m['present_bins'],m['bins_with_surface_within_25cm_prior'],m['bins_with_surface_within_25cm_gt'],m['median_nearest_prior_vertical_m'],m['median_nearest_gt_vertical_m'])
if __name__=='__main__':main()
