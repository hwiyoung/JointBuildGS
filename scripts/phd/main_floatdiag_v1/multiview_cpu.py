"""All training views: representative-pixel counts and full-pixel gate subset."""
import argparse
import csv
import gzip
import json
import numpy as np
from common import *
from recount import load_eval,classes
from reduce_diagnostics import table

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    e,root=load_eval(a.site,a.prior);cases=[c for c in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if c['site']==a.site]
    domains=[('전체',np.ones(len(e['area']),bool))]
    for c in cases:
        b=np.array(c['bbox']);domains.append((c['id'],((e['centre'][:,:2]>=b[:2]-3)&(e['centre'][:,:2]<=b[2:]+3)).all(1)))
    summary=[];hist=[];allviews=[];selections=[]
    for result in [f'nojudge_{a.prior}_s0',f'lt_dynnow_{a.prior}_s0']:
        predpath=LT/'patch_z'/f'{a.site}__{a.prior}__{result}.npz'
        with np.load(predpath) as f:pred={k:f[k] for k in f.files}
        cat=classes(e,pred);floating=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3)&(cat==1)
        ids=np.flatnonzero(floating);points=e['centre'][ids]+pred['z'][ids,None]*e['normal'][ids]
        base=OUT/'renders'/a.site/result/'iteration_30000';quality=json.loads((base/'quality.json').read_text());cams=quality['train']
        assert all(x['status']=='PASS' for x in quality['checks'])
        dest=OUT/'multiview'/a.site/result;dest.mkdir(parents=True,exist_ok=False)
        # 0 outside frame, 1 roof, 2 floating, 3 other, 4 invalid depth.
        cls=np.zeros((len(ids),len(cams)),np.uint8);delta=np.full(cls.shape,np.nan,np.float32)
        px=np.full(cls.shape,-1,np.int32);py=px.copy();totals={name:dict(full_gate_original_pixels=0,float_observed_pixels=0,all_own_dead=0,invalid_depth_pixels=0,roof_observed_pixels=0,other_observed_pixels=0) for name,_ in domains}
        own='current' if result.startswith('nojudge') else 'dynamic';source=[]
        for vi,cam in enumerate(cams):
            name=cam['view'];path=base/'train'/(name+'.npz')
            with np.load(path) as f:depth=f['depth']
            ext=np.array(cam['world_to_camera']);K=np.array(cam['intrinsic']);inv=np.linalg.inv(ext);H,W=depth.shape
            pc=points@ext[:3,:3].T+ext[:3,3];q=pc@K.T
            uv=q[:,:2]/q[:,2,None];xy=np.rint(np.nan_to_num(uv,nan=-1e9,posinf=-1e9,neginf=-1e9)).astype(np.int64)
            inside=(pc[:,2]>0)&np.isfinite(uv).all(1)&(xy[:,0]>=0)&(xy[:,0]<W)&(xy[:,1]>=0)&(xy[:,1]<H)
            ix=np.flatnonzero(inside);x=xy[ix,0];y=xy[ix,1];d=depth[y,x]
            ray=np.column_stack([(x-K[0,2])/K[0,0],(y-K[1,2])/K[1,1],np.ones(len(x))])
            world=(ray*d[:,None])@inv[:3,:3].T+inv[:3,3];signed=np.sum((world-e['centre'][ids[ix]])*e['normal'][ids[ix]],axis=1)-e['p_gt'][ids[ix]]
            valid=np.isfinite(d)&(d>0)&np.isfinite(signed);code=np.full(len(ix),3,np.uint8);code[~valid]=4
            code[valid&(np.abs(signed)<=e['tau'][ids[ix]])]=1;code[valid&(signed>e['tau'][ids[ix]])]=2
            cls[ix,vi]=code;delta[ix,vi]=signed;px[ix,vi]=x;py[ix,vi]=y
            diag=OUT/'diagnostics'/a.site/result/(name+'.npz')
            with np.load(diag) as f:z={k:f[k] for k in ['patch_id','pixel_y','pixel_x','pixel_type','has_mvs',own+'_prior_dead',own+'_mvs_dead']}
            take=z['pixel_type']==0;p=z['patch_id'][take];x=z['pixel_x'][take];y=z['pixel_y'][take];d=depth[y,x]
            assert np.all(floating[p]);assert len(np.unique(y.astype(np.int64)*W+x))==len(x)
            ray=np.column_stack([(x-K[0,2])/K[0,0],(y-K[1,2])/K[1,1],np.ones(len(x))])
            world=(ray*d[:,None])@inv[:3,:3].T+inv[:3,3];sd=np.sum((world-e['centre'][p])*e['normal'][p],axis=1)-e['p_gt'][p]
            valid=np.isfinite(d)&(d>0)&np.isfinite(sd);ff=valid&(sd>e['tau'][p]);rr=valid&(np.abs(sd)<=e['tau'][p]);other=valid&~ff&~rr
            dead=z[own+'_prior_dead'][take]&(~z['has_mvs'][take]|z[own+'_mvs_dead'][take])
            np.savez_compressed(dest/(name+'.npz'),patch_id=p,pixel_y=y,pixel_x=x,signed_normal_delta_m=sd.astype(np.float32),float_observed=ff,roof_observed=rr,valid=valid,all_own_dead=dead)
            for domain,mask in domains:
                m=mask[p];r=mask[ids];values=dict(full_gate_original_pixels=int(m.sum()),float_observed_pixels=int((m&ff).sum()),all_own_dead=int((m&ff&dead).sum()),invalid_depth_pixels=int((m&~valid).sum()),roof_observed_pixels=int((m&rr).sum()),other_observed_pixels=int((m&other).sum()))
                for k,v in values.items():totals[domain][k]+=v
                allviews.append(dict(site=a.site,result=result,case=domain,view=name,representative_in_frame=int((r&(cls[:,vi]>0)).sum()),representative_float=int((r&(cls[:,vi]==2)).sum()),representative_roof=int((r&(cls[:,vi]==1)).sum()),**values,source=str(dest/(name+'.npz'))))
            source.append(dict(view=name,depth_sha256=sha(path),force_sha256=sha(diag)))
            if vi%40==0:print(a.site,result,vi+1,'/',len(cams),flush=True)
        count=(cls==2).sum(1);roof=(cls==1).sum(1);inside=(cls>0).sum(1)
        np.savez_compressed(dest/'patch_views.npz',patch_id=ids,xyz=points,area_m2=e['area'][ids],view_names=np.array([c['view'] for c in cams]),classification=cls,signed_normal_delta_m=delta,pixel_x=px,pixel_y=py,
            float_photo_count=count,roof_photo_count=roof,in_frame_photo_count=inside)
        with gzip.open(dest/'patch_counts.csv.gz','wt') as f:
            w=csv.writer(f);w.writerow(['patch_id','area_m2','in_frame_photos','float_photos','roof_photos','other_photos','invalid_depth_photos'])
            for i,p in enumerate(ids):w.writerow([int(p),float(e['area'][p]),int(inside[i]),int(count[i]),int(roof[i]),int((cls[i]==3).sum()),int((cls[i]==4).sum())])
        gate=json.loads((OUT/'diagnostics'/a.site/result/'receipt.json').read_text())['gate_counts']
        assert totals['전체']['full_gate_original_pixels']==gate['floating_pixels']
        for domain,mask in domains:
            m=mask[ids];n=int(m.sum());area=float(e['area'][ids[m]].sum());has=m&(count>0);t=totals[domain]
            summary.append(dict(site=a.site,result=result,case=domain,patches=n,area_m2=area,at_least_one_float_photo_patches=int(has.sum()),at_least_one_float_photo_area_m2=float(e['area'][ids[has]].sum()),
                at_least_one_float_photo_area_fraction=float(e['area'][ids[has]].sum()/area) if area else None,
                float_photo_count_q25_q50_q75_q90=np.quantile(count[m],[.25,.5,.75,.9]).tolist() if n else None,
                no_in_frame_photo_patches=int((m&(inside==0)).sum()),**t,
                own_all_dead_fraction=t['all_own_dead']/t['float_observed_pixels'] if t['float_observed_pixels'] else None,
                sample_status='표본 부족' if n<100 else 'PASS',source=str(dest/'patch_views.npz')))
            for k in sorted(set(count[m].tolist())):
                mk=m&(count==k);ar=float(e['area'][ids[mk]].sum())
                hist.append(dict(site=a.site,result=result,case=domain,float_photo_count=int(k),patches=int(mk.sum()),area_m2=ar,area_fraction=ar/area if area else None,source=str(dest/'patch_views.npz')))
            if domain!='전체':
                vv=[r for r in allviews if r['result']==result and r['case']==domain]
                for kind in ['float','roof']:
                    key='representative_'+kind;candidates=[r for r in vv if r[key]>0]
                    chosen=sorted(candidates,key=lambda r:(-r[key],r['view']))[:3]
                    selections.append(dict(case=domain,result=result,kind=kind,selected=chosen,rule='largest classified representative-patch count, filename tie; maximum three, no fabricated substitute'))
        save(dest/'receipt.json',dict(at=now(),status='PASS',views=len(cams),patches=len(ids),source_pred=str(predpath),source_pred_sha256=sha(predpath),inputs=source,
            representative='saved mesh first-hit xyz projected to nearest image pixel in every training image; no occlusion/alpha exclusion',
            classification='signed local normal-plane displacement dot(render_world-centre,normal)-p_gt; roof abs<=tau, float >tau, other otherwise; nonpositive/nonfinite depth invalid',
            gate_subset='all original eligible own-floating-patch pixels from exact existing gate; retain only float-observing pixels; no representative-pixel substitution; each image pixel counted once',optimizer_steps=0,scientific_verdict=None))
    suffix=a.site+'_'+a.prior
    table(DOC/'tables'/('multiview_summary_'+suffix),summary,'사진별 확인 · 대표 화소 사진 수와 전체 화소 힘 비율')
    table(DOC/'tables'/('multiview_histogram_'+suffix),hist,'뜬 면을 본 사진 수 · 패치 수 및 넓이 분포')
    table(DOC/'tables'/('multiview_views_'+suffix),allviews,'모든 학습 사진의 분류 수')
    save(DOC/'provenance'/('multiview_selection_'+suffix+'.json'),dict(rows=selections,scientific_verdict=None))
    print(a.site,'multiview PASS',flush=True)
if __name__=='__main__':main()
