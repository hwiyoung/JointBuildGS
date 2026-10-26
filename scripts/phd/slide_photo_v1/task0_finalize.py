from common import *
def main():
    c=config();data=load(PAY/'task0/top10_photos.json');review=load(DOC/'qa/task0_material_review.json');answers={r['rank']:r for r in review['answers']}
    for row in data['candidates']:
        answer=answers.get(row.get('rank'),dict(material='unknown',answer='사진 확인 불가'));row['material']=answer['material'];row['material_answer']=answer['answer'];row['material_ko']={'glass':'유리','metal':'금속','other':'그 밖','unknown':'모름'}[answer['material']]
    eligible=[r for r in data['candidates'] if r['material'] in ['glass','metal']]
    totals={}
    for r in eligible:totals[r['building']]=totals.get(r['building'],0)+r['area_m2']
    selected=None
    if totals:
        high=max(totals.values());bids=[b for b,a in totals.items() if a>=.9*high]
        candidates=[r for r in eligible if r['building'] in bids];candidates.sort(key=lambda r:(-r['mvs_abs_median_m'] if len(bids)>1 else -r['area_m2'],-r['area_m2'],r['component_id']));bid=candidates[0]['building'];group=[r for r in eligible if r['building']==bid];a=max(r['area_m2'] for r in group);group=[r for r in group if r['area_m2']>=.9*a];group.sort(key=lambda r:(-r['mvs_abs_median_m'],-r['area_m2'],r['component_id']));selected=group[0]
    # Compare the locked historical B173 skylight input footprint, not its outcomes.
    legacy=load(REPO/'configs/phd/main_photofig_v1/photofig_v1.json')['places']['fig1'];indices=legacy['case_patches']
    with np.load(S0/'s61/box/B173nb_b10/ALS/units.npz') as z:X=z['loc_center'][indices]
    lo=X[:,:2].min(0)-.25;hi=X[:,:2].max(0)+.25
    for r in data['candidates']:
        p=np.asarray(r['centre']);r['b173_skylight_xy_overlap_fraction']=float(np.all((p[:,:2]>=lo)&(p[:,:2]<=hi),axis=1).mean())
    top=sorted(eligible,key=lambda r:(-r['area_m2'],r['component_id']))[:5]
    out=dict(task_id=c['task_id'],scientific_verdict=None,measurement_label='[이 발주에서 냄]',status='PASS' if selected else 'NO_QUALIFYING_MATERIAL',scope='24 full-area input tiles; development geometry only; 19 holdout buildings never opened',selected=selected,top_five=top,top_ten=data['candidates'],building_eligible_area_m2=totals,b173_glass_in_top_five=any(r['b173_skylight_xy_overlap_fraction']>.5 for r in top),limitations=['Material is an independent visual impression, not an observed material attribute.','Input GT uses the frozen alignment; MVS and UAS alignment are not independent validation.','Exact-pixel global visibility uses all 24 public raw GT input tiles; incomplete sampling can leave occlusion uncertainty.','Median normal residual is used for geometric comparison; cause is not proven by a large residual.'])
    # Preserve all patch IDs and photo positions; avoid repeating dense coordinate arrays.
    for key in ['top_five','top_ten']:out[key]=[{k:v for k,v in r.items() if k not in ['centre','normal','gt_representative']} for r in out[key]]
    dump(DOC/'figures/task0_specular_candidates.json',out);print('SELECTED',None if selected is None else {k:selected[k] for k in ['component_id','building','material','area_m2','mvs_abs_median_m','prior_abs_median_m']})
if __name__=='__main__':main()
