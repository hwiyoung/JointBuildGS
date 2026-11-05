from common import *
for site in SITES:
    for prior in PRIORS:
        z=loadz(cells_path(site,prior),['row_tau_m','row_owner'])
        r=loadz(S1/'defs'/site/f'rows_{prior}.npz',['kind','thin'])
        kind=r['kind'][r['thin'].astype(bool)]
        tr=next(t for t in readcsv(cfg()['tau_source']) if t['site']==site and t['prior']==prior)
        print(site,prior,z['row_tau_m'].dtype,len(kind),np.unique(kind),np.unique(z['row_tau_m']),tr['roof_tau_m'],tr['wall_tau_m'],int((z['row_owner']<0).sum()))
issue('첫 실행의 τ 일치 확인이 실패했다. 저장 거리·τ를 변경하지 않고 surface_tau.by_wall의 자료형을 확인해 동일한 저장 정밀도로 대조한다. 실패 로그: PH/main_recount_v1/PHD-MAIN-RECOUNT-v1/logs/B173nb_ALS.log.')
