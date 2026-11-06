"""Exact six-scene denominators and reasons for rows outside cases 0..4."""
from add9_common import *
def main():
 records=[];sources=[]
 for site in SITES:
  for prior in PRIORS:
   root=O/'scenes'/f'{site}__{prior}';row=loadz(root/'rows.npz');cells=loadz(root/'stage1_cells.npz');lab=cells['case_id'];N=len(lab);outside=~np.isin(lab,range(5));pa=cells['prior_absent'];s=loadz(root/'distances/prior.npz',['row_s'])['row_s'];reasons={'prior_surface_absent':outside&pa,'invalid_tau':outside&~pa&~np.isfinite(row['row_tau_m']),'other_unassigned':outside&~pa&np.isfinite(row['row_tau_m'])};r=dict(site=site,prior=prior,n_total=N,**{'case_'+str(k):int((lab==k).sum()) for k in range(5)},n_unassigned=int(outside.sum()),prior_surface_absent_total=int(pa.sum()),prior_surface_absent_within_cases=int((pa&~outside).sum()),prior_absent_case1=int((pa&(lab==1)).sum()),prior_absent_case3=int((pa&(lab==3)).sum()),**{k:int(v.sum()) for k,v in reasons.items()},**{'case_'+str(k)+'_pct':100*int((lab==k).sum())/N for k in range(5)},unassigned_pct=100*int(outside.sum())/N,denominator_definition='all saved stage1 reference rows; per-case presentation completeness uses the corresponding case subset',same_stage1_population=True)
   assert sum(r['case_'+str(k)] for k in range(5))+r['n_unassigned']==N;assert sum(int(v.sum()) for v in reasons.values())==r['n_unassigned'];records.append(r);sources.extend([root/'rows.npz',root/'stage1_cells.npz'])
 csv9('case_counts',records);dump(T9/'case_counts.json',record('case_counts',dict(rows=records,denominator_statement='same saved stage1 reference-row population and case masks as pages 15-18; whole-scene N differs from each per-case completeness denominator, no area weighting; stage1 normal_line.cases assigns prior-absent rows to cases1/3 and records absence as an overlapping flag, not an exclusion'),sources));print('ADD9_COUNTS',len(records),flush=True)
if __name__=='__main__':main()
