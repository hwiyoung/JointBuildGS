"""Complete seven case plates with exact-pixel depth, forces, sections and numbers."""
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from PIL import Image
from common import *
from recount import load_eval
from build_visuals import save_figure,NAMES,photo_panel,case_values

def rows(name):return json.loads((DOC/'tables'/name).read_text())['rows']
def one(data,**kw):return next(x for x in data if all(x.get(k)==v for k,v in kw.items()))
def num(x,d=3):return '확인 불가' if x is None else f'{x:.{d}f}'
def image(ax,im,title,crop=None,**kw):
    if im is None:
        ax.text(.5,.5,'확인 불가\n선택된 주 시점 없음',ha='center',va='center',transform=ax.transAxes)
    else:
        if crop is not None:x0,y0,x1,y1=crop;im=im[y0:y1,x0:x1]
        ax.imshow(im,**kw)
    ax.set(xticks=[],yticks=[],title=title)
    for s in ax.spines.values():s.set_visible(False)

def depth_range(case,e,photo):
    if photo is None:return [0.,1.]
    cam=photo['camera'];ext=np.array(cam['world_to_camera']);ids=np.array(case['patch_indices'])
    gt=e['centre'][ids]+e['p_gt'][ids,None]*e['normal'][ids]
    z=(gt@ext[:3,:3].T+ext[:3,3])[:,2];z=z[np.isfinite(z)&(z>0)]
    return [float(z.min()-8),float(z.max()+2)]

def section(ax,case):
    path=OUT/'sections'/(case['id']+'.npz');record=json.loads(path.with_suffix('.json').read_text())
    with np.load(path) as f:d={k:f[k] for k in f.files}
    for key,label,col,size in [('mvs','MVS 점','#4a7ec7',1),('gt','참값 점','#111111',1.5)]:
        x=d[key];ax.scatter(x[:,0],x[:,1],s=size,c=col,alpha=.5,label=label,rasterized=True)
    ax.add_collection(LineCollection(d['prior_segments'],colors='#e8a33d',linewidths=1.3,label='사전 정보'))
    for res,col in zip(RESULTS,config()['colours']['results']):
        x=d[res];ax.scatter(x[:,0],x[:,1],s=6,c=col,label=NAMES[res],rasterized=True)
    colors=list(config()['colours']['lineage'].values())
    for i,label in enumerate(['밀도 제어 생성','처음 사전','처음 영상','기록 없음']):
        x=d['gaussian'][d['lineage']==i];ax.scatter(x[:,0],x[:,1],s=3,c=colors[i],marker='x',alpha=.5,label='가우시안 '+label,rasterized=True)
    limits=[case['crop_min'][2],case['crop_max'][2]]
    record['display_ylim_m']=limits
    record['display_ylim_source']='already locked 3D crop GT minimum-2 to maximum+8; full arrays unchanged'
    record['outside_display_point_counts']={key:int(((x[:,1]<limits[0])|(x[:,1]>limits[1])).sum()) for key,x in d.items() if x.ndim==2 and x.shape[1]==2}
    ax.autoscale_view();ax.set(xlim=(-record['length_m']/2,record['length_m']/2),ylim=limits,xlabel='단면 거리 (m)',ylabel='높이 (m)',title='(바) 자료·처음 만난 면·판 4 가우시안 · 잠근 3D 높이 범위')
    ax.legend(ncol=5,fontsize=8,loc='upper center',bbox_to_anchor=(.5,1.0));ax.grid(alpha=.15)
    return record

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS',choices=['ALS','LoD2']);a=ap.parse_args();suffix='' if PRIOR=='ALS' else '_'+PRIOR
    cases=json.loads((CFG/f'geometry_{a.site}_{PRIOR}.json').read_text())['cases'];e,_=load_eval(a.site,PRIOR)
    gf=rows(f'gaussians_{a.site}_{PRIOR}.json');gr=rows(f'gradients_{a.site}{suffix}.json');fr=rows(f'forces_{a.site}{suffix}.json');ph=rows(f'photo_{a.site}{suffix}.json');four=rows(f'four_depths_{a.site}_{PRIOR}.json')
    unit=rows(f'recount_{PRIOR}.json');choices=json.loads((CFG/f'photos_{a.site}_{PRIOR}.json').read_text())['cases'];outrows=[]
    for case in cases:
        key=case['id'];choice=one(choices,case=key);meta=json.loads((DOC/'figures'/(key+'_plate_A1.json')).read_text())
        photo=meta['photo'];crop=photo['crop_xyxy'] if photo else None;dr=depth_range(case,e,photo);name=choice['main']['view'] if choice['main'] else None
        # Nine rows retain the required single-plate reading order.
        fig=plt.figure(figsize=(18,27));gs=fig.add_gridspec(9,12,height_ratios=[2.6,2.2,2.2,2.2,3.,2.1,2.,2.1,4.1])
        ax=fig.add_subplot(gs[0,:3]);_,typ=case_values(case,e,f'lt_dynnow_{PRIOR}_s0');photo_panel(ax,case,e,choice['main'],typ)
        numeric=[]
        for j,res in enumerate(RESULTS):
            ax=fig.add_subplot(gs[0,3+j*3:6+j*3]);ims=[np.array(Image.open(DOC/'3d'/key/res/f'view_{i}_gt.png')) for i in [4,5]]
            image(ax,np.concatenate(ims,axis=1),'(나) '+NAMES[res]+' · 낮은 두 각도')
            colour=depth=force=None;boundary=None
            if name:
                base=OUT/'renders'/a.site/res/'iteration_30000/train'
                colour=np.array(Image.open(base/(name+'.png')))
                with np.load(base/(name+'.npz')) as f:depth=f['depth']
                with np.load(OUT/'diagnostics'/a.site/res/(name+'.npz')) as f:d={k:f[k] for k in f.files}
                lm='current' if res.startswith('nojudge') else 'dynamic';dead=d[lm+'_prior_dead']&(~d['has_mvs']|d[lm+'_mvs_dead'])
                force=np.full(depth.shape,np.nan);boundary=np.zeros(depth.shape)
                y,x=d['pixel_y'],d['pixel_x'];fval=d[lm+'_prior_force']+d[lm+'_mvs_force']
                force[y[~dead],x[~dead]]=np.clip(np.log10(np.maximum(fval[~dead],1e-12)),-8,-.3)
                force[y[dead],x[dead]]=-99;boundary[y,x]=(d['pixel_type']==0)
            image(fig.add_subplot(gs[1,j*4:(j+1)*4]),colour,'(다) '+NAMES[res],crop)
            image(fig.add_subplot(gs[2,j*4:(j+1)*4]),depth,'(라) '+NAMES[res]+' · 깊이 m',crop,cmap='turbo_r',vmin=dr[0],vmax=dr[1])
            cmap=plt.get_cmap('magma').copy();cmap.set_bad('white');cmap.set_under('#9a9a9a');ax=fig.add_subplot(gs[3,j*4:(j+1)*4])
            image(ax,force,'(마) '+NAMES[res]+' · 자기 깊이 힘',crop,cmap=cmap,vmin=-8,vmax=-.3)
            if boundary is not None:
                x0,y0,x1,y1=crop;b=boundary[y0:y1,x0:x1]
                if b.min()!=b.max():ax.contour(b,levels=[.5],colors=['#d9534f'],linewidths=.45)
            v,_=case_values(case,e,res);whole=one(unit,site=a.site,result=res,cell='0~3')
            lin=one(gf,result=res,case=key,kind='floating');grad=one(gr,result=res,case=key,kind='roof')
            own='current' if res.startswith('nojudge') else 'dynamic';other='dynamic' if own=='current' else 'current'
            fown=one(fr,result=res,case=key,kind='floating',loss=own,term='prior');fother=one(fr,result=res,case=key,kind='floating',loss=other,term='prior')
            pfl=one(ph,result=res,case=key,kind='floating');pro=one(ph,result=res,case=key,kind='roof')
            wholelin=one(gf,result=res,case='전체',kind='floating');wholegrad=one(gr,result=res,case='전체',kind='roof')
            wholeforce=one(fr,result=res,case='전체',kind='floating',loss=own,term='prior')
            diff=next((x for x in four if x['result']==res and x['scope']==key),None)
            numeric.append(dict(case=key,result=res,geometric=v,whole_geometry=whole,lineage=lin,gradient=grad,force_own=fown,force_other=fother,
                photo_floating=pfl,photo_roof=pro,whole_lineage=wholelin,whole_gradient=wholegrad,whole_force=wholeforce,four_depth=diff))
        srec=section(fig.add_subplot(gs[4,:]),case)
        # Added row: identical camera rays, colour range and dynnow-defined mask.
        for j,(res,k,label) in enumerate([(RESULTS[0],'surf_depth','판정 끔 · 학습 깊이'),(RESULTS[0],'mesh_first_depth','판정 끔 · 메시 첫 교차'),
            (RESULTS[2],'surf_depth','판 4 · 학습 깊이'),(RESULTS[2],'mesh_first_depth','판 4 · 메시 첫 교차')]):
            arr=None
            if name:
                file=OUT/'four_depths'/a.site/res/(name+('_mesh' if k=='mesh_first_depth' else '')+'.npz')
                with np.load(file) as f:arr=f[k]
            image(fig.add_subplot(gs[5,j*3:(j+1)*3]),arr,label,crop,cmap='turbo_r',vmin=dr[0],vmax=dr[1])
        # Four requested definitions side by side for the same dynnow floating pixels.
        for j,(k,label) in enumerate([('surf_depth','① 학습 깊이'),('mesh_first_depth','② 메시 첫 교차'),('opacity_05','③ 누적 불투명도 0.5'),('opacity_mean','④ 가중 평균')]):
            arr=None
            if name:
                root=OUT/'four_depths'/a.site/RESULTS[2]
                with np.load(root/(name+('_mesh' if k=='mesh_first_depth' else '')+'.npz')) as f:arr=f[k]
                with np.load(root/(name+'_paired.npz')) as f:
                    mask=np.zeros(arr.shape,bool);mask[f['pixel_y'],f['pixel_x']]=True
                arr=np.where(mask,arr,np.nan)
            image(fig.add_subplot(gs[6,j*3:(j+1)*3]),arr,label,crop,cmap='turbo_r',vmin=dr[0],vmax=dr[1])
        # Oblique source photo plus paired RGB/depth for each result.
        ob=choice['oblique'];ax=fig.add_subplot(gs[7,:3]);obmeta=photo_panel(ax,case,e,ob,typ)
        for j,res in enumerate(RESULTS):
            ax=fig.add_subplot(gs[7,3+j*3:6+j*3]);im=None
            if obmeta:
                b=OUT/'renders'/a.site/res/'iteration_30000/train';x0,y0,x1,y1=obmeta['crop_xyxy']
                rgb=np.array(Image.open(b/(ob['view']+'.png')))[y0:y1,x0:x1]
                with np.load(b/(ob['view']+'.npz')) as f:z=f['depth'][y0:y1,x0:x1]
                odr=depth_range(case,e,obmeta);rgba=plt.get_cmap('turbo_r')(np.clip((z-odr[0])/(odr[1]-odr[0]),0,1))[:,:,:3]
                im=np.concatenate([rgb,(rgba*255).astype(np.uint8)],axis=1)
            image(ax,im,'빗각 · '+NAMES[res]+' 색 / 깊이')
        for j,n in enumerate(numeric):
            ax=fig.add_subplot(gs[8,j*4:(j+1)*4]);ax.axis('off');v=n['geometric'];w=n['whole_geometry'];lin=n['lineage'];g=n['gradient'];p=n['photo_floating'];r=n['photo_roof'];f=n['force_own'];o=n['force_other'];df=n['four_depth']
            lines=['(사) '+NAMES[n['result']]+' · 사례 / 단위 전체',
                f"τ 안 %  {num(v['within_tau_pct'],2)} / {num(w['within_tau_pct'],2)}",
                f"뜬 면 m²  {num(v['floating_area_m2'],1)} / {num(w['floating_area_m2'],1)}",
                f"뜬 면 %  {num(v['floating_pct'],2)} / {num(w['floating_pct'],2)}",
                f"뜬 높이 중앙값 m  {num(v['floating_height_median_m'])}",
                f"밀도 제어 생성 비율  {num(lin['densified_opacity_fraction'])} / {num(n['whole_lineage']['densified_opacity_fraction'])}",
                f"힘 없음·자기  {num(f['all_terms_dead_fraction'])} / {num(n['whole_force']['all_terms_dead_fraction'])}",
                f"힘 없음·반대  {num(o['all_terms_dead_fraction'])}",
                f"지붕 깊이÷사진 기울기  {num(g['depth_over_photo'])} / {num(n['whole_gradient']['depth_over_photo'])}",
                f"색 오차·뜬 면/둘레  {num(p['colour_L1_mean'])} / {num(r['colour_L1_mean'])}",
                f"보는 사진 수·뜬 면/둘레  {num(p['seeing_views_median'],1)} / {num(r['seeing_views_median'],1)}",
                f"무늬·뜬 면/둘레  {num(p['sobel_mean'])} / {num(r['sobel_mean'])}",
                f"패치 {v['patches']:,} · 뜬 면 화소 {f['group_pixels']:,} · 가우시안 {lin['count']:,}"]
            if df and df['status']=='MEASURED':
                d=df['surf_minus_mesh'];lines += [f"①−② m: Q25 {num(d['q25'])} · 중앙값 {num(d['median'])}",f"Q75 {num(d['q75'])} · P90 {num(d['p90'])} · N {d['n']:,}",f"메시 미교차 {df['mesh_miss']:,} · 0.5 미도달 {df['opacity_05_not_reached']:,}"]
            elif n['result']==RESULTS[1]:lines+=['네 깊이 추가 비교: 판 2는 대상 아님']
            else:lines+=['네 깊이 추가 비교: 주 시점 확인 불가']
            if lin['sample_status']!='PASS':lines+=['가우시안 구분의 패치 표본 부족']
            if f['sample_status']!='PASS':lines+=['힘 구분의 패치 표본 부족']
            if p['sample_status']!='PASS' or r['sample_status']!='PASS':lines+=['사진 비교의 패치 표본 부족']
            ax.text(.01,.98,'\n'.join(lines),va='top',fontsize=9.1,linespacing=1.4)
        height=numeric[2]['geometric']['floating_height_median_m']
        title=key+(' · 판 4의 뜬 면 높이 중앙값 '+num(height,2)+' m' if height is not None else ' · 실제 자료와 결과 면의 자리를 확인한다')
        fig.suptitle(title,x=.02,ha='left',fontsize=20)
        depth_caption=f'깊이 색 범위 {dr[0]:.2f}~{dr[1]:.2f} m (가까운 면 빨강).' if photo else '주 시점 없음: 깊이 색 범위 적용 안 함.'
        fig.text(.02,.011,depth_caption+" 힘 색 범위 log10 −8~−0.3, 힘 없는 화소 회색·계산 대상 밖 흰색.\n모든 수치는 [이 발주에서 냄]. 사례가 겹치므로 합산하지 않는다. 사진 값은 뜬 면 안과 바깥 3 m 지붕을 비교한다. 과학 판정 없음.",fontsize=10)
        fig.subplots_adjust(top=.95,bottom=.05,left=.04,right=.98,hspace=.30,wspace=.3)
        path=save_figure(fig,key+'_plate_A2',dict(case=key,phase='A2',title=title,depth_colour_range_m=dr,depth_range_source='same-case GT camera depth min-8 to max+2, all methods identical',photo=photo,oblique=obmeta,section=srec,values=numeric,visual_review='PENDING'))
        outrows.append(dict(case=key,plate=path,values=numeric));print(key,'A2 case plate PASS',flush=True)
    save(DOC/'보기'/f'A2_{a.site}.json',dict(cases=outrows,scientific_verdict=None))

if __name__=='__main__':main()
