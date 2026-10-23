"""Independent NumPy recounts directly from immutable source NPZ (no browser code)."""
import sys
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *

TD=DOC/'tables_v1_1'

def quant(a,p):
    a=np.asarray(a,np.float64);a=a[np.isfinite(a)]
    return float(np.quantile(a,p)) if len(a) else None

def one_row(u,e,label,source):
    with np.errstate(divide='ignore',invalid='ignore'):ratio=np.where(u>0,e/u,np.nan)
    return dict(source=source,label=label,n=len(u),u_median_cm=quant(u,.5),e_median_cm=quant(e,.5),
                e_p25_cm=quant(e,.25),e_p75_cm=quant(e,.75),median_e_over_u=quant(ratio,.5))

def calibration(u,e,site,roof,rt,source,lod2,pooled,detail=False):
    if not lod2:
        edges=[0,2,5,10,20,40,np.inf];out=[]
        for lo,hi in zip(edges[:-1],edges[1:]):
            mask=(u>=lo)&(u<hi);out.append(one_row(u[mask],e[mask],'40 초과' if np.isinf(hi) else f'{lo}~{hi}',source))
        return out
    labels=np.array([(s+' · ' if pooled else '')+('벽' if not r else '지붕 '+(t or '형태 없음') if (not pooled or detail) else '지붕') for s,r,t in zip(site,roof,rt)])
    return [one_row(u[labels==label],e[labels==label],str(label),source) for label in sorted(set(labels))]

def sparsification(u,e,patch,site,lod2=False):
    n=len(u)
    if lod2:return dict(available=False,n=n)
    base=float(e.mean()) if n else None
    if not n or not base:return dict(available=False,n=n,base_mean_cm=base)
    rows=[];ou=np.lexsort((site,patch,-u));oe=np.lexsort((site,patch,-e))
    for percent in range(0,91,5):
        k=n*percent//100
        a=float(e[ou[k:]].mean());b=float(e[oe[k:]].mean())
        rows.append(dict(percent=percent,removed=k,remaining=n-k,mean_cm=a,ideal_mean_cm=b,curve=a/base,ideal=b/base,random=1))
    x=np.arange(0,91,5)/100;curve=np.array([r['curve'] for r in rows]);ideal=np.array([r['ideal'] for r in rows]);trap=getattr(np,'trapezoid',np.trapz)
    return dict(available=True,n=n,base_mean_cm=base,rows=rows,area_curve_ideal=float(trap(curve-ideal,x)),area_random_ideal=float(trap(1-ideal,x)))

def chart(datasets,prior,exclude=False,v='a',detail=False):
    pooled=len(datasets)>1;out=dict(prior=prior,pooled=pooled,exclude=exclude,detail=detail,calibration=[],sparse={},counts={})
    for source in ['mvs','prior']:
        rows=[]
        for si,(site,z) in enumerate(datasets):
            key='mvs_'+v if source=='mvs' else 'als' if prior=='ALS' else None
            u=z[key+'_u'] if source=='mvs' else z['u_prior'];e=z[key+'_e'] if key else z['eL']
            mask=z['in_eval'].astype(bool)&np.isfinite(u)&np.isfinite(e)
            if key:mask&=z[key+'_status']==0
            if source=='prior' and exclude:mask&=z['cell']!=U.CELLS.index('c_corr4p')
            idx=np.flatnonzero(mask);rows.append((u[idx].astype(np.float64)*100,e[idx].astype(np.float64)*100,idx,np.full(len(idx),si),np.full(len(idx),site),z['roof_like'][idx],z['roof_type'][idx]))
        u,e,patch,si,site,roof,rt=[np.concatenate([a[k] for a in rows]) for k in range(7)]
        out['calibration']+=calibration(u,e,site,roof,rt,source,source=='prior' and prior=='LoD2',pooled,detail)
        out['sparse'][source]=sparsification(u,e,patch,si,source=='prior' and prior=='LoD2');out['counts'][source]=len(u)
    return out

def md(path,headers,rows):
    def f(x):
        if x is None:return '없음'
        if isinstance(x,float):return f'{x:.6g}'
        return str(x)
    path.write_text('화면에서 다시 셈 · 참값 점검용 · scientific_verdict: null\n\n'+'| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(f(x) for x in r)+' |\n' for r in rows))

def main():
    config=load(CFG/'view_v1_1.json');assert sha(CFG/'view_v1_1.json')==load(CFG/'view_v1_1.lock.json')['sha256']
    data={site+'__'+prior:pv(site,prior,config['population']['pool_radii'][site]) for site,prior in U.CASES}
    result={}
    for prior in ['LoD2','ALS']:
        groups=[(site+'__'+prior,[(site,data[site+'__'+prior])]) for site in U.SITES]
        groups.append(('pool__'+prior,[(site,data[site+'__'+prior]) for site in U.SITES]))
        for label,ds in groups:
            for exclude in [False,True]:
                key=label+'__exclude_'+str(int(exclude));result[key]=chart(ds,prior,exclude)
        result['pool__'+prior+'__b']=chart(groups[-1][1],prior,False,'b')
        if prior=='LoD2':result['pool__LoD2__detail']=chart(groups[-1][1],prior,False,'a',True)
    dump(TD/'reference_charts.json',dict(made=now(),results=result,scientific_verdict=None))
    md(TD/'calibration.md',['경우','크게 틀린 곳 빼기','자료','구간 / 면','패치 수','불확실도 중앙값 cm','실제 오차 중앙값 cm','25 % cm','75 % cm','오차 ÷ 불확실도'],
       [[key,r['exclude'],p['source'],p['label'],p['n'],p['u_median_cm'],p['e_median_cm'],p['e_p25_cm'],p['e_p75_cm'],p['median_e_over_u']] for key,r in result.items() for p in r['calibration']])
    md(TD/'sparsification.md',['경우','자료','패치 수','처음 평균 cm','곡선−이상적 넓이','무작위−이상적 넓이'],[[key,src,p['n'],p.get('base_mean_cm'),p.get('area_curve_ideal'),p.get('area_random_ideal')] for key,r in result.items() for src,p in r['sparse'].items()])
    comparisons=[];old=load(ROOT/'docs/experiments/phd/main_uncert_v1/tables/R_chosen_per_site/t61_u_vs_error.json')['values']['bins_u']
    for prior in ['LoD2','ALS']:
        for source in (['mvs'] if prior=='LoD2' else ['mvs','prior']):
            prior_label='LoD2' if prior=='LoD2' else '항공 LiDAR';data_label='MVS 판 가' if source=='mvs' else '항공 LiDAR'
            before=next(x for x in old if x['unit']=='세 지역 합 · '+prior_label and x['data']==data_label)['rows']
            after=[x for x in result['pool__'+prior+'__exclude_0']['calibration'] if x['source']==source]
            for a,b in zip(before,after):
                for oldkey,newkey in [('n','n'),('p50','e_median_cm'),('p25','e_p25_cm'),('p75','e_p75_cm')]:
                    av,bv=a[oldkey],b[newkey];equal=(av is None and bv is None) or (av is not None and bv is not None and abs(av-bv)<=(0 if oldkey=='n' else .1))
                    comparisons.append(dict(prior=prior,source=source,bin=a['bin'],field=oldkey,report=av,recount=bv,match=equal,mark='' if equal else '!'))
    dump(TD/'report61_comparison.json',dict(rows=comparisons,differences=sum(not r['match'] for r in comparisons),scientific_verdict=None))
    md(TD/'report61_comparison.md',['사전 정보','자료','구간','항목','앞 보고','다시 셈','표시'],[[r[k] for k in ['prior','source','bin','field','report','recount','mark']] for r in comparisons])
    samples=[];pairs=[];coverage=[]
    keys={'mvs_u':('mvs_a_u','mvs_a_status'),'mvs_e':('mvs_a_e','gt_status'),'prior_u':('u_prior',None),'prior_e':(None,'gt_status'),'difference':('mvs_a_p','mvs_a_status'),'gt_p':('gt_p','gt_status')}
    for ci,(case,z) in enumerate(data.items()):
        prior=case.rsplit('__',1)[1]
        with np.load(OUT/f'faces_v1_1_{case}.npz') as a:assignment=a['face']
        faces=load(OUT/f'faces_v1_1_{case}.json')['faces'];ev=z['in_eval'].astype(bool)
        ids=[i for i,f in enumerate(faces) if not f['grid'] and np.any(ev&(assignment==i))]
        rng=np.random.default_rng(config['seed']+ci);chosen=set(rng.choice(ids,min(10,len(ids)),replace=False).tolist())
        full=[]
        for fi in ids:
            idx=np.flatnonzero(ev&(assignment==fi));stats={}
            for layer,(key,status) in keys.items():
                if layer=='prior_e':key='als_e' if prior=='ALS' else 'eL'
                values=z[key][idx].astype(np.float64)*100;mask=np.isfinite(values)
                if status:mask&=z[status][idx]==0
                a=values[mask];stats[layer]=dict(n=len(a),total=len(idx),p25=quant(a,.25),p50=quant(a,.5),p75=quant(a,.75),valid_fraction=len(a)/len(idx),insufficient=len(a)<10 or len(a)/len(idx)<.3)
            full.append(dict(face_index=fi,face_id=faces[fi]['id'],stats=stats))
            if fi in chosen:samples.append(dict(case=case,face_index=fi,face_id=faces[fi]['id'],stats=stats))
        for p in config['pairs']:
            rows=[f for f in full if not f['stats'][p['left']]['insufficient'] and not f['stats'][p['right']]['insufficient']]
            a=np.array([f['stats'][p['left']]['p50'] for f in rows]);b=np.array([f['stats'][p['right']]['p50'] for f in rows])
            from scipy.stats import spearmanr
            rho=float(spearmanr(a,b).statistic) if len(a)>=3 and np.ptp(a)>0 and np.ptp(b)>0 else None
            with np.errstate(divide='ignore',invalid='ignore'):ratio=np.where(a>0,b/a,np.nan)
            pairs.append(dict(case=case,pair=p['id'],n=len(rows),rho=rho,median_right_over_left=quant(ratio,.5)))
        coverage.append(dict(case=case,eval_faces=len(ids),insufficient_mvs_pair=sum(f['stats']['mvs_u']['insufficient'] or f['stats']['mvs_e']['insufficient'] for f in full),insufficient_prior_pair=sum(f['stats']['prior_u']['insufficient'] or f['stats']['prior_e']['insufficient'] for f in full)))
    dump(TD/'face_reference.json',dict(seed=config['seed'],samples=samples,coverage=coverage,scientific_verdict=None))
    dump(TD/'pair_reference.json',dict(rows=pairs,scientific_verdict=None))
    md(TD/'pairs.md',['경우','지도 짝','면 수','순위 상관','오른쪽 ÷ 왼쪽 중앙값'],[[r[k] for k in ['case','pair','n','rho','median_right_over_left']] for r in pairs])
    print('Independent references:',len(result),'chart sets;',len(comparisons),'report comparisons;',sum(not r['match'] for r in comparisons),'differences;',len(samples),'sampled faces')
    progress('v1.1 일 3: 원본 NPZ에서 보정 그림·희소화 곡선·지도 짝·고정 씨앗 60개 면의 독립 기준값 저장. 보고 6.1의 수와 25·50·75 % 값 비교 완료.')

if __name__=='__main__':main()
