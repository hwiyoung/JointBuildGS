from common import *
for site in cfg()['sites']:
    for prior in ['ALS','LoD2']:
        p=TG/'stage0_r1/inputs'/f'{site}_{prior}.npz'
        with np.load(p) as z:
            print('RAW',site,prior,[(k,z[k].shape) for k in z.files] if site=='B173nb_b10' else len(z['centre']),flush=True)
        d=loadz(JA/'core_points'/f'{site}__{prior}.npz',['region','n','u_mvs','sigma_P_m','prior_height_m','mvs_mean_m','source_index'])
        a=d['region'][5]
        print('EVAL',site,prior,len(a),'sigma_missing',int((~np.isfinite(d['sigma_P_m'])).sum()),'sigma_zero',int((d['sigma_P_m']<=0).sum()),'um_zero',int((d['u_mvs']<=0).sum()),'regions',np.unique(a,return_counts=True),'um_absent_observed',int(((d['n']>=4)&~np.isfinite(d['u_mvs'])).sum()),flush=True)
