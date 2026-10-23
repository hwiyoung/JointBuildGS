"""Distance-connected patch components; holdout outputs never leave holdout/."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from analysis_common import O,DOC,CFG,CELLS,KO,load,quantiles,number,csvwrite,save_table,dump

def labels_for(c,rule=None):
    if not len(c):return np.empty(0,np.int32),0,dict(median_spacing_m=None,radius_m=.36)
    tree=cKDTree(c)
    spacing=rule['median_spacing_m'] if rule is not None else (float(np.median(tree.query(c,k=2,workers=8)[0][:,1])) if len(c)>1 else None)
    radius=rule['radius_m'] if rule is not None else (1.5*spacing if spacing is not None and np.isfinite(spacing) and (spacing<.18 or spacing>.36) else .36)
    # Zero spacing cannot define a positive radius: exact duplicates remain linked.
    pairs=tree.query_pairs(radius,output_type='ndarray')
    graph=coo_matrix((np.ones(len(pairs),np.uint8),(pairs[:,0],pairs[:,1])),shape=(len(c),len(c)))
    count,labels=connected_components(graph,directed=False)
    return labels,count,dict(median_spacing_m=spacing,radius_m=radius,fallback=bool(radius!=.36))

def describe(d,ids,prior,cell,cid,tree=None):
    area=d['area'][ids];bids,bi=np.unique(d['building'][ids],return_inverse=True)
    ba=np.bincount(bi,weights=area);primary=str(bids[np.argmax(ba)])
    val=dict(component_id=cid,prior=prior,cell=cell,cell_ko=KO[CELLS.index(cell)] if cell in CELLS else '사전 정보가 틀림',
        building=primary,building_ids=bids.tolist(),building_area_m2={str(b):float(a) for b,a in zip(bids,ba)},
        shape='지붕꼴' if d['roof_like'][ids].all() else ('벽꼴' if not d['roof_like'][ids].any() else '지붕꼴·벽꼴'),
        roof_types=sorted(set(d['roof_type'][ids].tolist())),area_m2=float(area.sum()),patches=len(ids),
        roof_type_missing_patches=int((d['roof_type'][ids]=='').sum()),
        roof_type_missing_reason='Empty roof_type means the source LoD2 attribute is unavailable; no type is inferred.',
        roof_area_m2=float(area[d['roof_like'][ids]].sum()),wall_area_m2=float(area[~d['roof_like'][ids]].sum()),
        gt_p_m=quantiles(d['gt_p'][ids]),gt_density_points_m2=quantiles(d['gt_n_inner'][ids]/(np.pi*.5**2)),
        difference_m=quantiles(d['mvs_p'][ids]),mvs_actual_error_m=quantiles(d['mvs_a_e'][ids]),
        prior_actual_error_m=quantiles(d['prior_error'][ids]),mvs_uncertainty_m=quantiles(d['u_mvs'][ids]),prior_uncertainty_m=quantiles(d['u_prior'][ids]),
        difference_over_uncertainty=quantiles(d['difference_over_uncertainty'][ids]),
        signed_difference_over_uncertainty=quantiles(d['signed_difference_over_uncertainty'][ids]),
        normalized_difference_rule='signed mvs_p / sqrt(u_mvs^2 + u_prior^2); difference_over_uncertainty retains the absolute-value version',views=quantiles(d['mvs_a_views'][ids]),
        support=quantiles(d['mvs_a_support_lmeds'][ids]),support_final=quantiles(d['mvs_a_support_final'][ids]))
    if tree is not None:
        other=set();own=CELLS.index(cell)
        for start in range(0,len(ids),2000):
            for nb in tree.query_ball_point(d['centre'][ids[start:start+2000]],1.,workers=8):
                other.update(i for i in nb if d['cell'][i]!=own)
        jj=np.fromiter(other,np.int64);counts=np.bincount(d['cell'][jj],minlength=7)
        val['neighbour_cell']=CELLS[int(np.argmax(counts))] if len(jj) else None
        val['neighbour_patch_counts']={CELLS[i]:int(n) for i,n in enumerate(counts) if n}
    return val

def run(prior,held):
    d=load(prior,held);root=O/('holdout/components' if held else 'components');root.mkdir(parents=True,exist_ok=True)
    allrows=[];summ=[];lab_all=np.full(len(d['cell']),-1,np.int32);off=0;tree=cKDTree(d['centre'])
    spacing=float(np.median(tree.query(d['centre'],k=2,workers=8)[0][:,1])) if len(d['centre'])>1 else None
    radius=1.5*spacing if spacing is not None and (spacing<.18 or spacing>.36) else .36
    base_rule=dict(median_spacing_m=spacing,radius_m=radius,spacing_population='all patches of this prior and split before selecting a cell')
    for ci,cell in enumerate(CELLS):
        ids=np.flatnonzero(d['cell']==ci);lab,n,rule=labels_for(d['centre'][ids],base_rule);areas=np.bincount(lab,weights=d['area'][ids],minlength=n)
        lab_all[ids]=lab+off
        for k in np.flatnonzero(areas>=1.):allrows.append(describe(d,ids[lab==k],prior,cell,f'{prior}:{off+int(k)}',tree))
        summ.append(dict(prior=prior,cell=cell,cell_ko=KO[ci],patches=len(ids),area_m2=float(d['area'][ids].sum()),components=n,
            components_under_1m2=int((areas<1).sum()),area_under_1m2=float(areas[areas<1].sum()),
            size_counts={f'{lo:g}~{hi:g}':int(((areas>=lo)&(areas<hi)).sum()) for lo,hi in [(1,2.5),(2.5,10),(10,100),(100,np.inf)]},**rule))
        off+=n
    np.savez_compressed(root/f'{prior}_labels.npz',patch_id=d['patch_id'],component=lab_all)
    dump(root/f'{prior}_candidates.json',dict(rows=allrows,summary=summ,scientific_verdict=None))
    # Stage A: join all prior-wrong patches, independent of MVS correctness.
    ids=np.flatnonzero((d['gt_status']==0)&(np.abs(d['gt_p'])>d['tau']));lab,n,rule=labels_for(d['centre'][ids],base_rule);ar=np.bincount(lab,weights=d['area'][ids],minlength=n)
    priorrows=[describe(d,ids[lab==k],prior,'prior_error',f'{prior}:prior:{int(k)}') for k in np.flatnonzero(ar>=1)]
    for row in priorrows:row['cell_ko']='사전 정보가 틀림'
    dump(root/f'{prior}_prior_error.json',dict(rows=priorrows,components=n,small_count=int((ar<1).sum()),small_area_m2=float(ar[ar<1].sum()),**rule,scientific_verdict=None))
    if held:return
    bins=[]
    for sign in [-1,1]:
        for lo,hi in zip([CFG['tau_m'][prior],.5,1.,2.,4.],[.5,1.,2.,4.,np.inf]):
            z=d['gt_p'][ids]*sign;m=(z>lo)&(z<=hi)
            bins.append(dict(prior=prior,sign=sign,lower_exclusive_m=lo,upper_inclusive_m=float(hi) if np.isfinite(hi) else None,patches=int(m.sum()),area_m2=float(d['area'][ids[m]].sum())))
    bstat=[]
    for b in sorted(set(d['building'])):
        m=d['building']==b;gt=m&(d['gt_status']==0);wrong=gt&(np.abs(d['gt_p'])>d['tau'])
        area=float(d['area'][m].sum());ga=float(d['area'][gt].sum());wa=float(d['area'][wrong].sum())
        bstat.append(dict(prior=prior,building=str(b),patches=int(m.sum()),area_m2=area,gt_area_m2=ga,wrong_area_m2=wa,
            wrong_fraction_all=wa/area if area else None,wrong_fraction_GT=wa/ga if ga else None))
    bstat.sort(key=lambda r:(-(r['wrong_fraction_GT'] if r['wrong_fraction_GT'] is not None else -1),r['building']))
    save_table(f'사전정보_틀린자리_{prior}',priorrows,components=n,small_count=int((ar<1).sum()),small_area_m2=float(ar[ar<1].sum()),**rule)
    save_table(f'사전정보_크기부호_{prior}',bins);save_table(f'사전정보_건물상위30_{prior}',bstat[:30],denominator='GT-available surface area; also report all-surface denominator')

def main():
    for held in [False,True]:
        for prior in ['LoD2','ALS']:
            run(prior,held);print('components complete',prior,'sealed' if held else 'development',flush=True)
    rows=[];summary=[]
    for p in ['LoD2','ALS']:
        z=json.loads((O/'components'/f'{p}_candidates.json').read_text());rows+=z['rows'];summary+=z['summary']
    rows.sort(key=lambda r:(r['prior'],CELLS.index(r['cell']),-r['area_m2'],r['building'],r['component_id']))
    save_table('시험자리_정하는곳',rows);save_table('시험자리_요약',summary)
    chosen=[];counts={}
    for cell in ['prior_wrong','image_wrong','both_wrong']:
        n=0
        for r in sorted((r for r in rows if r['cell']==cell),key=lambda r:(-r['area_m2'],r['building'],r['component_id'])):
            if any(counts.get(b,0)>=3 for b in r['building_ids']):continue
            chosen.append(r);n+=1
            for b in r['building_ids']:counts[b]=counts.get(b,0)+1
            if n==20:break
    save_table('대표자리_선정',chosen,rule='Each cell: largest area across both priors; max 3 components involving any one building across all three photo cells; frozen cell order prior_wrong, image_wrong, both_wrong; ties building then component ID')
if __name__=='__main__':main()
