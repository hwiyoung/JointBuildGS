"""Regional r and pooled sigma_W from raw no-reference agreements only."""
from common import *
def finite(x):return float(x) if np.isfinite(x) else None
def main():
    c=cfg();pieces=[];rmap={};buildings=[];summary=[]
    for site in c['sites']:
      for prior in c['priors']:
        p=O/'geometry_raw'/f'{site}__{prior}.npz';d=loadz(p)
        good=(d['n']>=4)&np.isfinite(d['d_m'])&np.isfinite(d['u_mvs'])&np.isfinite(d['sigma_P_m'])
        agree=good&(abs(d['d_m'])<=1.96*np.hypot(d['u_mvs'],d['sigma_P_m']));d['agreement_for_calibration']=agree
        rr=np.full(len(agree),np.nan)
        for kind in c['priors'][prior]:
            m=agree&(d['kind']==kind);key=f'{site}__{prior}__{kind}'
            r=float(np.median(d['d_m'][m])) if m.any() else np.nan;rmap[key]=finite(r);rr[d['kind']==kind]=r
            summary.append(dict(site=site,prior=prior,kind=kind,agreement_count=int(m.sum()),agreement_area_m2=float(d['area'][m].sum()),r_m=finite(r),source=str(p)))
        d['r_m']=rr
        if prior=='ALS':
            for bid in sorted(set(d['building'])-{''}):
                m=agree&(d['building']==bid)&(d['kind']==1)
                if m.sum()>=100:
                    med=float(np.median(d['d_m'][m]));buildings.append(dict(site=site,building=bid,n=int(m.sum()),median_d_m=med,regional_r_m=float(rr[m][0]),residual_m=med-float(rr[m][0])))
        pieces.append((p.name,d))
    values=np.array([b['residual_m'] for b in buildings]);sw=1.4826*np.median(abs(values-np.median(values))) if len(values) else np.nan
    report=dict(at=now(),sigma_W_m=finite(sw),building_count=len(values),buildings_per_site={s:sum(b['site']==s for b in buildings) for s in c['sites']},buildings=buildings,r_rows=summary,
                prior_reference_only=dict(sigma_W_m=.02450353934490731,r_m={'ALS_1':.016897281827748762,'LoD2_1':.05085196109104549,'LoD2_2':-.02272214187916248}),GT_read=False,source_tag='[이 발주에서 냄]',scientific_verdict=None)
    for name,d in pieces:
        d['sigma_W_m']=np.full(len(d['n']),sw);d['L_m']=1.96*(np.sqrt(d['u_mvs']**2+d['sigma_P_m']**2+sw**2)+abs(d['r_m']))
        g=np.full(len(d['n']),9,np.int8);valid=(d['n']>=4)&np.isfinite(d['d_m'])&np.isfinite(d['L_m']);g[(d['n']>=0)&(d['n']<4)]=2
        g[valid&(abs(d['d_m'])<=d['L_m'])]=0;g[valid&(abs(d['d_m'])>d['L_m'])]=1;d['geometry']=g
        savez(O/'geometry'/name,**d)
    dump(O/'calibration.json',report);dump(D/'tables/calibration.json',report)
    progress(f'참값 없이 정합 오차와 넓은 범위 오차 계산 완료. sigma_W={finite(sw)} m, 건물 {len(values)}개.')
    if len(values)<10:issue(f'넓은 범위 오차의 건물 표본은 {len(values)}동으로 10동 미만. 발주대로 값을 유지.')
    print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
