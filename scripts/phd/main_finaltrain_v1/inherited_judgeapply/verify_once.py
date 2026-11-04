"""One independent recount of tables 7.1 and 6.3 from delivered core arrays."""
from common import *
def main():
    start=time.monotonic();checks=0;cache={};hashes={}
    for p in sorted((O/'core_points').glob('*.npz')):
        cache[tuple(p.stem.split('__'))]=loadz(p);hashes[p.name]=sha(p)
    def eq(a,b,label):
        nonlocal checks
        if a is None or b is None:assert a is None and b is None,(label,a,b)
        else:assert np.isclose(a,b,atol=1e-8,rtol=1e-11),(label,a,b)
        checks+=1
    def rows(name):return json.loads((D/'tables'/f'{name}.json').read_text())['rows']
    for row in rows('table7_1'):
        d=cache[row['site'],row['prior']];a=d['area'];m=np.ones(len(a),bool) if row['kind']=='all' else d['kind']==int(row['kind'])
        j=['prior_only','image_only','geometry_only','photo_only','fusion','method'].index(row['method'])
        index=d['cell'][m].astype(int)*10+d['region'][j,m];area=np.bincount(index,weights=a[m],minlength=100).reshape(10,10);count=np.bincount(index,minlength=100).reshape(10,10)
        den=area[1:3].sum();miss=area[1,[0,1,3,4,5,6,7,8]].sum();false=area[2,[0,2,3,4,5,6,7,8]].sum();um=area[1,9];uf=area[2,9]
        percent=lambda x:100*x/den if den else None
        expected=dict(count=m.sum(),denominator_count=count[1:3].sum(),denominator_m2=den,missed_known_m2=miss,false_known_m2=false,
          missed_mixing_m2=area[1,0],missed_one_side_m2=miss-area[1,0],false_mixing_m2=area[2,0],false_one_side_m2=false-area[2,0],
          unavailable_cell1_m2=um,unavailable_cell2_m2=uf,cell4_erased_m2=area[4,3],
          error_rate_pct=percent(miss+false) if um+uf==0 else None,missed_pct=percent(miss) if um==0 else None,false_pct=percent(false) if uf==0 else None,
          error_lower_pct=percent(miss+false),error_upper_pct=percent(miss+false+um+uf),missed_lower_pct=percent(miss),missed_upper_pct=percent(miss+um),false_lower_pct=percent(false),false_upper_pct=percent(false+uf))
        for k in [3,5,6,9]:expected[f'cell{k}_m2']=area[k].sum()
        for key,val in expected.items():eq(row[key],val,('7.1',row['site'],row['prior'],row['method'],key))
    for row in rows('section6_3_regions_by_truth'):
        d=cache[row['site'],row['prior']];r=d['region'][5];why=d['reason'][5];mapping={'일치':(0,None),'보존·사진':(1,0),'보존·기본':(1,2),'보정·사진':(2,1),'보정·기본':(2,2),'보정(빈 공간)':(3,None),'결측':(4,None),'확인 불가':(9,None)}
        reg,reason=mapping[row['region_reason']];m=(d['kind']==row['kind'])&(r==reg)
        if reason is not None:m&=why==reason
        values=np.bincount(d['cell'][m],weights=d['area'][m],minlength=10);counts=np.bincount(d['cell'][m],minlength=10);c=row['cell'];den=values.sum()
        for key,val in dict(count=counts[c],area_m2=values[c],row_area_m2=den,row_fraction=values[c]/den if den else None).items():eq(row[key],val,('6.3cross',key))
    for row in rows('section6_3_B173_ALS_cell2'):
        d=cache[row['site'],row['prior']];half=abs(d['d_m'])<=.53 if row['split'].endswith('le_0.53') else abs(d['d_m'])>.53
        ids=np.flatnonzero((d['cell']==2)&half&(d['region'][5]==row['region']));eq(row['count'],len(ids),'6.3split_count');eq(row['area_m2'],np.sum(d['area'][ids]),'6.3split_area')
    for row in rows('section6_3_prior_weight'):
        d=cache[row['site'],row['prior']];m=(d['kind']==row['kind'])&(d['region'][5]==0)
        vm=d['u_mvs'][m]**2+d['sigma_W_m'][m]**2;vp=d['sigma_P_m'][m]**2;x=(1/vp)/(1/vp+1/vm);eq(row['count'],len(x),'weights_count');eq(row['area_m2'],d['area'][m].sum(),'weights_area')
        for q in [10,25,50,75,90]:eq(row[f'q{q}'],np.percentile(x,q) if len(x) else None,'weights_q')
    for row in rows('section6_3_prior_weight_histogram'):
        d=cache[row['site'],row['prior']];m=(d['kind']==row['kind'])&(d['region'][5]==0);x=d['prior_weight'];m&=(x>=row['left'])&((x<row['right']) if row['left']<.9 else (x<=1))
        eq(row['count'],m.sum(),'hist_count');eq(row['area_m2'],d['area'][m].sum(),'hist_area')
    for row in rows('section6_3_r8_cross'):
        if row.get('status'):continue
        d=cache[row['site'],row['prior']];old=loadz(TG/'r8/targets'/f'{row["site"]}_{row["prior"]}.npz',['region'])['region'][d['source_index']]
        m=(d['kind']==row['kind'])&(old==row['r8_region'])&(d['region'][5]==row['region']);eq(row['count'],m.sum(),'r8_count');eq(row['area_m2'],d['area'][m].sum(),'r8_area')
    result=dict(at=now(),status='PASS_SINGLE_INDEPENDENT_SAVED_CORE_RECOUNT',checks=checks,files=hashes,tables=['table7_1','section6_3_regions_by_truth','section6_3_B173_ALS_cell2','section6_3_prior_weight','section6_3_prior_weight_histogram','section6_3_r8_cross'],seconds=time.monotonic()-start,scientific_verdict=None)
    dump(D/'tables/verification.json',result);dump(O/'timing/verification.json',result);progress(f'저장 핵심점에서 표7.1·6.3 단일 독립 검산 PASS: {checks}개 수치. CPU/GPU 일치 재검사 없음.');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
