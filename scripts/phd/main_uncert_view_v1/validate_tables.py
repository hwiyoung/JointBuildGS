"""Independent NumPy recount of the five required tables; preserve all differences."""
import sys
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *
from scipy.stats import spearmanr


def main():
    records=[]
    def compare(label,old,new,unit='cm',context=None):
        old=clean(old);new=clean(new)
        tol=.1 if unit=='cm' else 0 if unit=='count' else .01
        delta=abs(old-new) if old is not None and new is not None else None
        records.append(dict(label=label,context=context,report=old,recount=new,unit=unit,tolerance=tol,difference=delta,
                            match=(old is None and new is None) or (delta is not None and delta<=tol)))
    def quant(x,p):
        x=np.asarray(x,dtype=np.float64);x=x[np.isfinite(x)]
        return float(np.quantile(x,p)) if len(x) else None
    for folder,rarg in [('R1.0',1.),('R1.5',1.5),('R3.0',3.),('R_chosen_per_site','chosen')]:
        root=ROOT/'docs/experiments/phd/main_uncert_v1/tables'/folder
        reports={name:load(root/(name+'.json'))['values'] for name in ['t1_value_share','t2_u_distribution','t61_u_vs_error','t63_changed','t64_lod2']}
        cfg=load(CFG/'view_v1.json');store={}
        for site,prior in U.CASES:
            radius=cfg['default_radii'][site] if rarg=='chosen' else rarg
            z=pv(site,prior,radius);store[(site,prior)]=z;case=U.case_ko(site,prior);ev=z['in_eval'].astype(bool)
            context=dict(folder=folder,case=case)
            for d in L.DATAS[prior]:
                for face,mask in [('전체',ev),('지붕꼴',ev&z['roof_like'].astype(bool)),('벽꼴',ev&~z['roof_like'].astype(bool))]:
                    cc=dict(context,data=d,face=face);valid=mask&(z[d+'_status']==0)
                    t1=next(x for x in reports['t1_value_share'] if x['case']==case and x['data']==U.DATA_KO[d] and x.get('face')==face)
                    compare('t1 patches',t1['patches'],int(mask.sum()),'count',cc)
                    compare('t1 value share',t1['value'],float(valid.sum()/mask.sum()) if mask.sum() else None,'ratio',cc)
                    t2=next(x for x in reports['t2_u_distribution'] if x['case']==case and x['data']==U.DATA_KO[d] and x.get('face')==face)
                    for f,p in [('p25',.25),('p50',.5),('p75',.75)]:compare('t2 '+f,t2['u'][f],quant(z[d+'_u'][valid].astype(float)*100,p),'cm',cc)
                if d.startswith('mvs'):
                    for k in ['c_corr14','c_corr4p','c_refine']:
                        m=ev&(z['cell']==U.CID[k])&(z[d+'_status']==0)
                        row=next(x for x in reports['t63_changed'] if x['case']==case and x['data']==U.DATA_KO[d] and x['cell']==U.CELL_KO[k])
                        compare('t63 median',row['u']['p50'],quant(z[d+'_u'][m].astype(float)*100,.5),'cm',dict(context,data=d,cell=k))
            if prior=='LoD2':
                for row in reports['t64_lod2']:
                    if row['site']!=U.SITE_KO[site]:continue
                    group=row['group'];gm=z['roof_like'].astype(bool) if group=='지붕면' else ~z['roof_like'].astype(bool) if group=='벽면' else z['roof_like'].astype(bool)&(z['roof_type']==group.split(' ')[2])
                    basis=row['basis']
                    if basis.startswith('MVS'):
                        cutoff=5 if '≤ 5 cm' in basis else 10
                        m=ev&gm&(z['mvs_a_status']==0)&(z['mvs_a_u']<=cutoff/100);x=z['mvs_a_p'].astype(float)
                    else:
                        m=ev&gm&(z['gt_status']==0);x=z['gt_p'].astype(float)
                        if '뺌' in basis:m&=z['cell']!=U.CID['c_corr4p']
                    compare('t64 q68',row.get('q68_cm'),quant(np.abs(x[m])*100,.68),'cm',dict(context,group=group,basis=basis))
        for prior in U.PRIORS:
            for sites in [[s] for s in U.SITES]+[list(U.SITES)]:
                label=U.case_ko(sites[0],prior) if len(sites)==1 else '세 지역 합 · '+U.PRIOR_KO[prior]
                for d in L.DATAS[prior]:
                    us=[];es=[]
                    for site in sites:
                        z=store[(site,prior)];valid=z['in_eval'].astype(bool)&(z[d+'_status']==0)&np.isfinite(z[d+'_e'])
                        us.append(z[d+'_u'][valid].astype(float)*100);es.append(z[d+'_e'][valid].astype(float)*100)
                    u,e=np.concatenate(us),np.concatenate(es);rr=next(r for r in reports['t61_u_vs_error']['bins_u'] if r['unit']==label and r['data']==U.DATA_KO[d])
                    for j,(lo,hi) in enumerate(zip(U.CFG['tables']['u_bins_cm'][:-1],U.CFG['tables']['u_bins_cm'][1:])):
                        m=(u>=lo)&((u<hi) if hi is not None else True)
                        compare('t61 bin median',rr['rows'][j]['p50'],quant(e[m],.5),'cm',dict(folder=folder,unit=label,data=d,bin=rr['rows'][j]['bin']))
                    rho=spearmanr(u,e).statistic if len(u)>=3 else None
                    rank=next(r for r in reports['t61_u_vs_error']['rank'] if r['unit']==label and r['data']==U.DATA_KO[d])
                    compare('t61 rank',rank['faces']['전체']['rho_u_e'],rho,'rank',dict(folder=folder,unit=label,data=d))
    dump(DOC/'tables/table_recount.json',dict(made=now(),comparisons=len(records),matched=sum(r['match'] for r in records),rows=records,scientific_verdict=None))
    progress(f'일 3 표 맞춰 보기 완료: 독립 재집계 {len(records)}건 중 {sum(r["match"] for r in records)}건 허용차 안. 길이 0.1 cm, 비율·상관 0.01 기준.')
    print(len(records),'comparisons;',sum(not r['match'] for r in records),'differences')

if __name__=='__main__':main()
