"""Input-only selection for figures c/a/d, prior to rendering any figure."""
from common import *
def select_repr():
    p=U/'patch_values/B0_b10__LoD2__R1.5.npz'
    with np.load(p) as zz:z={k:zz[k] for k in ['centre','normal','in_eval','roof_like','surf','gt_p','mvs_a_p','mvs_a_status']}
    valid=z['in_eval']&z['roof_like']&np.isfinite(z['gt_p'])&(z['mvs_a_status']==0)&np.isfinite(z['mvs_a_p'])
    rows=[]
    for f in np.unique(z['surf'][valid]):
        ix=np.flatnonzero(valid&(z['surf']==f));n=z['normal'][ix,2]
        prior=-z['gt_p'][ix]*n;mvs=(z['mvs_a_p'][ix]-z['gt_p'][ix])*n
        rows.append(dict(face=int(f),n=len(ix),prior_signed_median_m=float(np.median(prior)),mvs_abs_median_m=float(np.median(np.abs(mvs))),patch_indices=ix.tolist()))
    for sign in [1,-1]:
        good=[r for r in rows if .10<=sign*r['prior_signed_median_m']<=.30 and r['mvs_abs_median_m']<.05]
        if good:
            best=dict(sorted(good,key=lambda r:(-r['n'],r['face']))[0]);best.update(status='PASS',sign_reversed=sign<0,source=str(p),tau_m=.1975,all_faces=rows,scientific_verdict=None)
            dump(PAY/'selection_c_repr.json',best);print('repr', {k:v for k,v in best.items() if k not in ['patch_indices','all_faces']});return
    dump(PAY/'selection_c_repr.json',dict(status='BLOCKED',reason='No face meets the exact positive or negative rule',all_faces=rows,scientific_verdict=None));print('repr BLOCKED')

def select_views():
    allposes=G.poses(G.DENSE/'triangulated/images.bin');best=None;dviews=[];counts=[]
    for site in ['B0_b10','B173nb_b10','R1rep_b10']:
        with np.load(U/'patch_values'/f'{site}__LoD2__R1.5.npz') as zz:z={k:zz[k] for k in ['centre','normal','in_eval','roof_like','surf']}
        flat=z['in_eval']&z['roof_like']&(np.abs(z['normal'][:,2])>=np.cos(np.deg2rad(10)))
        train=load(S0/'fork_inputs/s61'/site/'split.json')['train'];validfaces=np.unique(z['surf'][flat]);counter=0
        for name in train:
            stem=Path(name).stem;ex=S0/'s61/export'/site/'LoD2';lp=ex/'locmap'/f'{stem}.npy'
            if not lp.exists():continue
            lm=np.load(lp);inside=lm>=0;idx=lm[inside].astype(int)
            D=np.load(ex/'mvs'/f'{stem}.npy');cf=np.load(ex/'conf'/f'{stem}.npy');passmap=np.isfinite(D)&(D>0)&(cf>0)
            if site=='B0_b10':
                roi=np.zeros_like(inside);roi[inside]=z['in_eval'][idx];share=float(roi.mean())
                if share>.5:dviews.append(dict(view=stem,eval_image_share=share,pass_share=float(passmap[roi].mean())))
            if G.tilt(allposes[stem])>20:continue
            ff=z['surf'][idx];isflat=flat[idx]
            for face in np.unique(ff[isflat]):
                pix=inside.copy();pix[inside]=isflat&(ff==face);n=int(pix.sum())
                if not n:continue
                missing=float((~passmap[pix]).mean());row=dict(site=site,face=int(face),view=stem,missing_share=missing,pixels=n)
                if best is None or (-missing,site,int(face),stem)<(-best['missing_share'],best['site'],best['face'],best['view']):best=row
                counter+=1
        counts.append(dict(site=site,flat_faces=len(validfaces),face_view_pairs=counter))
        print('view selection',site,'pairs',counter,flush=True)
    dump(PAY/'selection_a_roof.json',dict(status='PASS' if best else 'BLOCKED',selected=best,scope=counts,scientific_verdict=None))
    dviews.sort(key=lambda r:(-r['pass_share'],r['view']))
    dump(PAY/'selection_d_view.json',dict(status='PASS' if dviews else 'BLOCKED',selected=dviews[0] if dviews else None,candidates=dviews,scientific_verdict=None))
    print('roof',best,'d',dviews[:1],flush=True)

if __name__=='__main__':config();select_repr();select_views()
