from rfcore import *
import gc

def main():
    receipts=[]
    for prior in ['ALS','LoD2']:
        source=PAY/'input'/f'{prior}_sites.npz'
        with np.load(source,allow_pickle=False) as z:d={k:z[k] for k in z.files}
        n=len(d['patch_id']);assert len(np.unique(d['patch_id']))==n
        d.update(centre=np.full((n,3),np.nan),normal=np.full((n,3),np.nan),matched=np.zeros(n,bool))
        tiles=np.array([s.split(':')[1] for s in d['patch_id']]);sources=[]
        for tile in np.unique(tiles):
            path=W/'patch_values'/f'{tile}__{prior}__R1.5.npz';ids=np.flatnonzero(tiles==tile)
            if not path.exists():continue
            with np.load(path,allow_pickle=False) as z:
                lookup={s:i for i,s in enumerate(z['patch_id'])}
                ix=np.array([lookup.get(s,-1) for s in d['patch_id'][ids]]);valid=ix>=0
                for key in ['centre','normal']:
                    arr=z[key];d[key][ids[valid]]=arr[ix[valid]];del arr
                d['matched'][ids[valid]]=True
                # Membership only; never read held-out outcomes.
                assert not z['holdout'][ix[valid]].any()
            sources.append(dict(path=str(path),sha256=sha(path),matched=int(valid.sum())))
            del lookup;gc.collect()
        for b in np.unique(d['building']):
            m=d['building']==b;missing=int((m&~d['matched']).sum());total=int(m.sum())
            q=dict(prior=prior,building=b,patches=total,unmatched=missing,unmatched_fraction=missing/total)
            receipts.append(q);print(q,flush=True)
        dump(PAY/f'join_{prior}.json',dict(source_sha256=sha(source),sources=sources,rows=[r for r in receipts if r['prior']==prior],environment=environment()))
        assert all(r['unmatched_fraction']<=.05 for r in receipts),'STOP: unmatched >5%'
        np.savez_compressed(PAY/f'joined_{prior}.npz',**d)
        del d;gc.collect()
    summary=load(PAY/'input/sites_summary.json');checks=[]
    for q in summary:
        d=data(q['prior'],q['building'].split('_')[-1]);a=d['area'].astype(float)
        valid=np.isfinite(d['gt_p']);rec=dict(prior=q['prior'],building=q['building'],expected=q)
        rec['actual']=dict(patches=len(a),area_m2=float(a.sum()),cell_area_m2={str(k):float(a[d['cell']==k].sum()) for k in range(7)},
                           judgment_area_m2={str(k):float(a[d['judgment']==k].sum()) for k in range(5)})
        for key in ['category','check']:
            ok=abs(d['z_'+key].astype(float)-d['gt_p'].astype(float))<=d['tau'].astype(float)
            rec['actual']['ok_'+key+'_pct']=safe_pct(a,valid,ok)
            rec['actual']['roof_ok_'+key+'_pct']=safe_pct(a,valid&d['roof_like'],ok)
        rec['rate_matches']=all(abs(rec['actual']['ok_'+key+'_pct']-q['ok_'+key+'_pct'])<=.005001 for key in ['category','check'])
        checks.append(rec);print(q['prior'],q['building'],rec['actual']['ok_category_pct'],rec['actual']['ok_check_pct'],rec['rate_matches'],flush=True)
    dump(DOC/'tables/input_validation.json',dict(joins=receipts,summary_checks=checks,environment=environment(),scientific_verdict=None))

if __name__=='__main__':main()
