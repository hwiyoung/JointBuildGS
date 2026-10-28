"""Photo-count maps and deterministic up-to-three per-class render examples."""
import argparse
import json
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from common import *
from recount import load_eval
from build_visuals import save_figure,NAMES

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    e,_=load_eval(a.site,a.prior);cases=[c for c in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if c['site']==a.site]
    results=[f'nojudge_{a.prior}_s0',f'lt_dynnow_{a.prior}_s0']
    selection=json.loads((DOC/'provenance'/f'multiview_selection_{a.site}_{a.prior}.json').read_text())['rows']
    stats=json.loads((DOC/'tables'/f'multiview_summary_{a.site}_{a.prior}.json').read_text())['rows']
    z={}
    for res in results:
        with np.load(OUT/'multiview'/a.site/res/'patch_views.npz') as f:z[res]={k:f[k] for k in f.files}
    for c in cases:
        b=np.array(c['bbox'])+np.array([-3,-3,3,3]);fig,axs=plt.subplots(1,2,figsize=(12,5));maxcount=1
        for res in results:
            q=z[res];xy=e['centre'][q['patch_id'],:2];m=((xy>=b[:2])&(xy<=b[2:])).all(1)
            if m.any():maxcount=max(maxcount,int(q['float_photo_count'][m].max()))
        for ax,res in zip(axs,results):
            q=z[res];xy=e['centre'][q['patch_id'],:2];m=((xy>=b[:2])&(xy<=b[2:])).all(1)
            ref=((e['centre'][:,:2]>=b[:2])&(e['centre'][:,:2]<=b[2:])).all(1)&e['in_eval']&e['scoring_allowed']
            ax.scatter(e['centre'][ref,0],e['centre'][ref,1],s=2,c='#dddddd')
            sc=ax.scatter(xy[m,0],xy[m,1],c=q['float_photo_count'][m],s=8,cmap='viridis',vmin=0,vmax=maxcount,marker='s')
            r=next(r for r in stats if r['result']==res and r['case']==c['id'])
            val='확인 불가' if r['at_least_one_float_photo_area_fraction'] is None else f"{100*r['at_least_one_float_photo_area_fraction']:.2f}%"
            ax.set(title=NAMES.get(res,res)+f" · 1장 이상 넓이 {val}\n뜬 면 패치 N={r['patches']:,}",xlabel='로컬 X (m)',ylabel='로컬 Y (m)',xlim=b[[0,2]],ylim=b[[1,3]],aspect='equal')
            fig.colorbar(sc,ax=ax,label='뜬 면을 본 학습 사진 수')
        fig.suptitle(c['id']+' · 모든 학습 사진의 대표 화소',fontsize=16)
        fig.tight_layout();save_figure(fig,c['id']+'_multiview_map_A2',dict(case=c,results=results,counts_colour_range=[0,maxcount],definition='One saved mesh first-hit representative per patch per in-frame training photo; signed local normal plane; no occlusion prefilter',sources=[str(OUT/'multiview'/a.site/r/'patch_views.npz') for r in results]))
        selected=[r for r in selection if r['case']==c['id']];examples=[]
        for res in results:
            for kind in ['float','roof']:
                row=next(r for r in selected if r['result']==res and r['kind']==kind)
                examples.extend([(res,kind,x) for x in row['selected']] or [(res,kind,None)])
        # At most twelve rows; independent small horizontal strips remain readable.
        fig,axs=plt.subplots(len(examples),2,figsize=(13,2.2*len(examples)),squeeze=False)
        details=[]
        for i,(res,kind,r) in enumerate(examples):
            label=NAMES.get(res,res)+' · '+('뜬 면을 본' if kind=='float' else '지붕을 본')
            if r is None:
                for ax in axs[i]:ax.text(.5,.5,label+' 사진 없음',ha='center',va='center');ax.axis('off')
                continue
            name=r['view'];base=OUT/'renders'/a.site/res/'iteration_30000';cams=json.loads((base/'quality.json').read_text())['train'];cam=next(x for x in cams if x['view']==name)
            q=z[res];vi=list(q['view_names']).index(name);xy=e['centre'][q['patch_id'],:2]
            in_case=((xy>=b[:2])&(xy<=b[2:])).all(1);inside=in_case&(q['classification'][:,vi]>0)
            xs=q['pixel_x'][inside,vi];ys=q['pixel_y'][inside,vi];H,W=cam['height'],cam['width']
            x0=max(0,int(xs.min())-30);x1=min(W,int(xs.max())+31);y0=max(0,int(ys.min())-30);y1=min(H,int(ys.max())+31)
            # Bound crop to avoid tiny points forcing a misleading zoom; all
            # representatives in the case are retained, no outcome-based crop.
            rgb=np.array(Image.open(base/'train'/(name+'.png')))[y0:y1,x0:x1]
            with np.load(base/'train'/(name+'.npz')) as f:d=f['depth'][y0:y1,x0:x1]
            pids=q['patch_id'][inside];gt=e['centre'][pids]+e['p_gt'][pids,None]*e['normal'][pids]
            ext=np.array(cam['world_to_camera']);zz=(gt@ext[:3,:3].T+ext[:3,3])[:,2];limits=[float(zz.min()-8),float(zz.max()+2)]
            axs[i,0].imshow(rgb);sc=axs[i,1].imshow(np.where(d>0,d,np.nan),cmap='turbo_r',vmin=limits[0],vmax=limits[1])
            mark=in_case&(q['classification'][:,vi]==(2 if kind=='float' else 1));xx=q['pixel_x'][mark,vi]-x0;yy=q['pixel_y'][mark,vi]-y0
            for ax in axs[i]:
                ax.scatter(xx,yy,s=2,facecolors='none',edgecolors='#d9534f' if kind=='float' else '#2e8b57',linewidths=.4);ax.set(xticks=[],yticks=[])
            axs[i,0].set_title(label+f" · {int(mark.sum())}패치 · 색",fontsize=10)
            axs[i,1].set_title(name+' · 깊이 m',fontsize=9);fig.colorbar(sc,ax=axs[i,1],fraction=.025,pad=.02)
            details.append(dict(result=res,kind=kind,view=name,crop_xyxy=[x0,y0,x1,y1],patches=int(mark.sum()),depth_range_m=limits,counts=r))
        fig.suptitle(c['id']+' · 뜬 면 / 지붕을 본 사진을 각각 최대 세 장',fontsize=16)
        fig.text(.01,.005,'둘레 표시는 분류된 대표 화소. 각 줄의 깊이 범위는 그 시점 참값 깊이 최저−8~최고+2 m. 모든 사진 집계는 선택 여부와 무관하다.',fontsize=9)
        fig.tight_layout(rect=[0,.02,1,.97]);save_figure(fig,c['id']+'_multiview_examples_A2',dict(case=c['id'],selection=details,selection_rule=selected,width_limit=1800))
        print(c['id'],'multiview map and examples PASS',flush=True)
if __name__=='__main__':main()
