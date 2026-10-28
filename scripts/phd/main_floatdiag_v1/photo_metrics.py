"""All-training-view colour error, image texture and camera-depth visibility."""
import argparse
import csv
import json
import cv2
import numpy as np
from PIL import Image
from common import *
from recount import load_eval,classes

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS',choices=['ALS','LoD2']);a=ap.parse_args()
    e,_=load_eval(a.site,a.prior);xy=e['centre'][:,:2]
    valid=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3)
    cases=json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'];cases=[x for x in cases if x['site']==a.site]
    rows=[];sources=[]
    for result in [f'{p}_{a.prior}_s0' for p in ['nojudge','lt_dyngt','lt_dynnow']]:
        root=OUT/'renders'/a.site/result/'iteration_30000';q=json.loads((root/'quality.json').read_text())
        assert all(x['status']=='PASS' for x in q['checks'])
        with np.load(LT/'patch_z'/f'{a.site}__{a.prior}__{result}.npz') as f:cat=classes(e,{k:f[k] for k in f.files})
        groups=[]
        for c in [None,*cases]:
            for kind,num in [('floating',1),('roof',0)]:
                region=valid.copy()
                if c:
                    b=np.array(c['bbox']);inner=((xy>=b[:2])&(xy<=b[2:])).all(1)
                    outer=((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)
                    region &= inner if kind=='floating' else outer&~inner
                mask=region&(cat==num)
                groups.append(dict(case=c['id'] if c else '전체',kind=kind,mask=mask,patches=int(mask.sum()),pixels=0,
                    colour_sum=0.,sobel_sum=0.,views_with_pixels=0))
        seeing=np.zeros(len(xy),np.int32)
        for i,cam in enumerate(q['train']):
            name=cam['view'];shape=(cam['height'],cam['width'])
            with np.load(root/'train'/(name+'.npz')) as f:depth=f['depth'];l1=f['rgb_l1']
            mp=S0/'fork_inputs/s61'/a.site/'maps'/f'locmap_{a.prior}';mp=mp/'raw_depth' if (mp/'raw_depth').exists() else mp
            loc=np.load(mp/(name+'.npy'))
            if loc.shape!=shape:loc=cv2.resize(loc.astype(np.float32),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)
            loc=loc.astype(np.int32);ok=(loc>=0)&(loc<len(xy));ids=loc[ok]
            photo=np.array(Image.open(OUT/'photos'/a.site/(name+'.png')).convert('RGB')).astype(np.float32)/255
            grey=cv2.cvtColor(photo,cv2.COLOR_RGB2GRAY)
            sobel=np.hypot(cv2.Sobel(grey,cv2.CV_32F,1,0,ksize=3),cv2.Sobel(grey,cv2.CV_32F,0,1,ksize=3))
            colour=l1[ok];texture=sobel[ok]
            for group in groups:
                take=group['mask'][ids];n=int(take.sum());group['pixels']+=n
                group['colour_sum']+=float(colour[take].sum(dtype=np.float64));group['sobel_sum']+=float(texture[take].sum(dtype=np.float64))
                group['views_with_pixels']+=int(n>0)
            ext=np.array(cam['world_to_camera']);K=np.array(cam['intrinsic']);pc=e['centre']@ext[:3,:3].T+ext[:3,3]
            pp=pc@K.T;uv=pp[:,:2]/pp[:,2,None];uv=np.rint(np.nan_to_num(uv,nan=-1e9)).astype(int)
            inside=valid&(pc[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<shape[1])&(uv[:,1]>=0)&(uv[:,1]<shape[0]);ix=np.flatnonzero(inside)
            dz=depth[uv[ix,1],uv[ix,0]];visible=np.isfinite(dz)&(dz>0)&(pc[ix,2]<=dz+.25)
            seeing[ix[visible]]+=1
            if i%50==0:print(a.site,result,'photo measures',i+1,'/',len(q['train']),flush=True)
        for g in groups:
            n=g['pixels'];pm=g.pop('mask');col=g.pop('colour_sum');sob=g.pop('sobel_sum')
            rows.append(dict(site=a.site,result=result,**g,colour_L1_mean=col/n if n else None,sobel_mean=sob/n if n else None,
                seeing_views_median=float(np.median(seeing[pm])) if pm.any() else None,
                sample_status='표본 부족' if g['patches']<100 else 'PASS',origin='[이 발주에서 냄]'))
        dest=OUT/'photo_metrics'/a.site;dest.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(dest/(result+'.npz'),seeing_views=seeing)
        sources.append(dict(result=result,render_receipt=str(root/'quality.json'),sha256=sha(root/'quality.json')))
    data=dict(rows=rows,sources=sources,texture='OpenCV RGB2GRAY on normalized original RGB, Sobel 3x3 unnormalized gradient magnitude',
        case_domains='floating inside component bbox; roof in its 3m exterior ring; whole-unit cells 0..3',
        visibility='original patch centre, exact saved model camera depth, 0.25m tolerance; all training views',scientific_verdict=None)
    dest=DOC/'tables'/('photo_'+a.site+('' if a.prior=='ALS' else '_'+a.prior));save(dest.with_suffix('.json'),data)
    with dest.with_suffix('.csv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 사진 쪽 값','','[이 발주에서 냄]. 색 오차는 RGB 평균 L1, 무늬는 정규화 회색값의 Sobel 크기다. 사진 수는 패치별 보이는 사진 수의 중앙값이다.','',
        '| 결과 | 사례 | 구분 | 패치 | 화소 | 색 오차 | 무늬 | 사진 수 |','|---|---|---|---:|---:|---:|---:|---:|']
    fmt=lambda x:'확인 불가' if x is None else f'{x:.6g}'
    for r in rows:lines.append('| '+' | '.join(str(r[k]) if k in ['result','case','kind','patches','pixels'] else fmt(r[k]) for k in ['result','case','kind','patches','pixels','colour_L1_mean','sobel_mean','seeing_views_median'])+' |')
    dest.with_suffix('.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
