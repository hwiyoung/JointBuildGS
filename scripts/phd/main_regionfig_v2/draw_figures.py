"""Six-panel static figures; same native crop/rigid display transform in all four photos."""
from rfcore import *
import argparse
import gc
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, patheffects
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import Affine2D
from PIL import Image
import draw as olddraw

for p in ['/fonts/NotoSansCJK-Regular.ttc','/fonts/NotoSansCJK-Bold.ttc']:
    font_manager.fontManager.addfont(p)
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':12,'axes.linewidth':.7,'hatch.linewidth':.45})

def fmt(v,n=1):return '확인 불가' if v is None else f'{v:.{n}f}'

def geometry(ex,d):
    p=ex['photo'];pose={k:np.asarray(v) if k in ['R','t'] else v for k,v in p['pose'].items()};cam=dict(p['camera']);cam['p']=np.array(cam['p'])
    gt=np.isfinite(d['gt_p']);cc=d['centre']+np.where(gt,d['gt_p'],0)[:,None]*d['normal']
    uv,z=project(cc,pose,cam);x0,y0,x1,y1=p['crop_box_px']
    native_inside=d['matched']&(z>0)&(uv[:,0]>=x0)&(uv[:,0]<x1)&(uv[:,1]>=y0)&(uv[:,1]<y1)
    # The raw rational lens model folds outside its calibrated domain. Apply the
    # same actual undistorted training field used by v1 candidate selection.
    tcams=cameras(W/'mvs/full/sparse/cameras.bin');tposes=poses(W/'mvs/full/sparse/images.bin')
    tp=tposes[p['stem']];tc=tcams[tp['cam']];tuv,tz=project(cc,tp,tc)
    calibrated=(tz>0)&(tuv[:,0]>=0)&(tuv[:,0]<tc['w'])&(tuv[:,1]>=0)&(tuv[:,1]<tc['h'])
    inside=native_inside&calibrated
    ids=np.flatnonzero(inside&gt);ids=ids[np.argsort(-z[ids],kind='stable')]
    n=d['normal'][ids];helper=np.tile([0.,0.,1.],(len(ids),1));helper[abs(n[:,2])>.9]=[1.,0.,0.]
    t1=np.cross(n,helper);t1/=np.linalg.norm(t1,axis=1)[:,None];t2=np.cross(n,t1)
    h=np.sqrt(d['area'][ids].astype(float))/2
    poly=np.stack([cc[ids]+h[:,None]*(i*t1+j*t2) for i,j in [(-1,-1),(1,-1),(1,1),(-1,1)]],axis=1)
    puv,_=project(poly,pose,cam);puv-=[x0,y0]
    photo_w,photo_h=p['crop_size_px'];angle=np.radians(p['display_rotation_degrees'])
    transform=Affine2D().scale(1,-1).translate(-photo_w/2,photo_h/2).rotate(angle)
    polys=transform.transform(puv.reshape(-1,2)).reshape(puv.shape)
    corners=transform.transform([[0,0],[photo_w,0],[photo_w,photo_h],[0,photo_h]])
    line=transform.transform(np.array(p['display_line_pixels'])-[x0,y0])
    return dict(ids=ids,inside=inside,polys=polys,transform=transform,corners=corners,line=line,pose=pose,cam=cam,
                excluded_outside_calibration=int((native_inside&~calibrated).sum()))

def photo(ax,ex,d,g,im,mode):
    p=ex['photo'];W,H=p['crop_size_px'];ids=g['ids'];poly=g['polys'];r=regions(d)[ids];j=judgments(d)[ids]
    ax.imshow(im,extent=(0,W,H,0),interpolation='none',transform=g['transform']+ax.transData,zorder=0)
    if mode=='region':
        colors=[REGION_COLORS[k] if k<6 else 'none' for k in r]
        ax.add_collection(PolyCollection(poly,facecolors=colors,edgecolors='none',alpha=.45,zorder=5))
        wrong=d['cell'][ids]==5
        ax.add_collection(PolyCollection(poly[wrong],facecolors='none',edgecolors='#222222',linewidths=0,hatch='///',zorder=6))
    elif mode=='judgment':
        for k in range(3):
            ax.add_collection(PolyCollection(poly[j==k],facecolors=JUDGE_COLORS[k],edgecolors='none',alpha=.45,zorder=5))
        ax.add_collection(PolyCollection(poly[j==3],facecolors='none',edgecolors='#222222',linewidths=0,hatch='..',zorder=6))
    elif mode in ['category','check']:
        roof=d['roof_like'][ids];ok=abs(d['z_'+mode][ids].astype(float)-d['gt_p'][ids].astype(float))<=d['tau'][ids].astype(float)
        ax.add_collection(PolyCollection(poly[roof],facecolors=np.where(ok[roof],'#2171b5','#e31a1c'),edgecolors='none',alpha=.45,zorder=5))
    corners=g['corners'];ax.set_xlim(corners[:,0].min(),corners[:,0].max());ax.set_ylim(corners[:,1].min(),corners[:,1].max())
    ax.set_aspect('equal');ax.axis('off')
    if mode!='raw':
        olddraw.section_arrow(ax,g['line'],np.array(p['line_midpoint_occluded']),halo=True,lw=1.5)
        olddraw.marker(ax,g['line'][0],g['line'][min(5,len(g['line'])-1)],'#c0392b',photo=True,fontsize=11)
        ax.annotate('북',xy=(.96,.97),xytext=(.96,.85),xycoords='axes fraction',ha='center',va='top',fontsize=10,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=1),arrowprops=dict(arrowstyle='-|>',color='#222',lw=1))

def legends(ax,mode):
    if mode=='region':
        labels=['다듬기 · 둘 다 맞음','보정 · 사전 정보만 틀림','보존 · 영상의 면만 틀림',*REGIONS[3:]]
        handles=[Patch(facecolor=c,label=n) for n,c in zip(labels,REGION_COLORS)]
        handles.append(Patch(facecolor='white',edgecolor='black',hatch='///',label='상속 중 사전 정보 틀림'))
        ncol=3
    elif mode=='judgment':
        handles=[Patch(facecolor=c if c!='none' else 'white',edgecolor='#555',hatch='..' if i==3 else None,label=n) for i,(n,c) in enumerate(zip(JUDGMENTS[:4],JUDGE_COLORS[:4]))];ncol=4
    else:
        handles=[Patch(facecolor=c,label=n) for n,c in [('맞음','#2171b5'),('틀림','#e31a1c')]];ncol=2
    ax.legend(handles=handles,ncol=ncol,loc='upper center',bbox_to_anchor=(.5,-.015),frameon=False,fontsize=9 if mode=='region' else 10,
              handlelength=1.2,columnspacing=1.0,labelspacing=.5)

def section_panel(fig,grid,ex,sec):
    nested=grid.subgridspec(3,1,height_ratios=[9,.65,.65],hspace=.08)
    ax=fig.add_subplot(nested[0]);s=np.array(sec['bin_centres_m']);h=np.array(sec['heights_relative_m'],float)
    labels=['사전 정보','영상의 면','참값','결과 · 범주별','결과 · 검사 기반']
    styles=[dict(color='#222222',lw=2),dict(color='#d08a2e',lw=1.8),dict(color='#2e8b57',ls='none',marker='.',ms=6),
            dict(color='#888888',ls='--',lw=2),dict(color='#2171b5',lw=1.6)]
    for k in [0,1,3,4,2]:ax.plot(s,h[:,k],label=labels[k],**styles[k])
    ax.set_xlim(0,sec['length_m']);ax.set_ylabel('높이 (m)');ax.grid(axis='y',alpha=.2);ax.tick_params(labelbottom=False)
    ax.set_title('다  단면',loc='left',fontweight='bold',pad=9)
    ax.legend(ncol=2,loc='best',fontsize=10,framealpha=.9)
    for row,key,palette,name in [(1,'judgment',JUDGE_COLORS,'사진 검사'),(2,'region',REGION_COLORS,'영역')]:
        strip=fig.add_subplot(nested[row],sharex=ax);edges=np.array(sec['bin_edges_m']);vals=np.array(sec[key]);pol=[];col=[]
        for k,value in enumerate(vals):
            if value<0:continue
            pol.append([[edges[k],0],[edges[k+1],0],[edges[k+1],1],[edges[k],1]])
            col.append(palette[value] if value<len(palette) and palette[value]!='none' else 'white')
        strip.add_collection(PolyCollection(pol,facecolors=col,edgecolors='#aaaaaa',linewidths=.2));strip.set_ylim(0,1);strip.set_yticks([])
        strip.set_ylabel(name,rotation=0,ha='right',va='center',fontsize=10)
        if row==1:strip.tick_params(labelbottom=False)
        else:strip.set_xlabel('시작점부터 거리 (m)')
        if key=='judgment':
            for k,value in enumerate(vals):
                if value==3:strip.axvspan(edges[k],edges[k+1],facecolor='none',edgecolor='#444',hatch='..',lw=0)
        else:
            for k,value in enumerate(sec.get('inherit_wrong',[])):
                if value:strip.axvspan(edges[k],edges[k+1],facecolor='none',edgecolor='#222',hatch='///',lw=0)
    return ax

def bar_panel(ax,m):
    x=np.arange(6);width=.34
    for i,q in enumerate(m['per_region']):
        if q['area_m2']<1:
            ax.text(i,6,'넓이\n적음',ha='center',va='bottom',fontsize=10,color='#666')
        else:
            for dx,key,color,hatch in [(-width/2,'category','#888888','//'),(width/2,'check','#2171b5',None)]:
                val=q['ok_'+key+'_pct'];ax.bar(i+dx,val,width=width,color=color,hatch=hatch,edgecolor='white',linewidth=.6)
            ax.text(i,min(109,max(q['ok_category_pct'],q['ok_check_pct'])+3),f'{q["area_m2"]:.1f} m²',ha='center',va='bottom',fontsize=10)
    ax.set_ylim(0,118);ax.set_xlim(-.6,5.6);ax.set_yticks([0,25,50,75,100]);ax.set_xticks(x,['다듬기','보정','보존','둘 다\n틀림','상속\n결측','상속\n비가시'],fontsize=11)
    ax.set_ylabel('맞은 넓이 비율 (%)');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    ax.set_title('바  영역마다 맞은 넓이 비율',loc='left',fontweight='bold',pad=12)
    ax.legend(handles=[Patch(facecolor='#888888',hatch='//',label='범주별 유효 확률'),Patch(facecolor='#2171b5',label='검사 기반 유효 확률')],fontsize=10,loc='upper center',bbox_to_anchor=(.5,-.13),frameon=False)

def title_for(ex,m):
    # Only factual, displayed-area statements; no scientific interpretation.
    regions_by_name={q['region']:q for q in m['per_region']};r=regions_by_name
    if ex['id']=='1':return '다듬기에서 두 결과는 대부분 맞았다'
    if ex['id']=='2':return '보정에서 검사 기반 결과의 맞은 넓이 비율이 높아졌다'
    if ex['id']=='3':return '계단 지붕의 보정에서 검사 기반 결과의 맞은 넓이 비율이 높아졌다'
    if ex['id']=='4':return '보존에서 두 결과는 대부분 맞았다'
    if ex['id']=='5':return '보존에서 검사 기반 결과가 틀린 곳이 남았다'
    if ex['id']=='6':return '사진이 지지한 보존에서도 결과가 틀린 곳이 남았다'
    if ex['id']=='7':return '사진 부족인 상속과 영상의 면이 없는 상속이 함께 보인다'
    return '영상의 면이 없는 곳에 사전 정보가 틀린 결과가 남았다'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('id');args=ap.parse_args();start=time.time()
    cfg=load(CFG/'regionfig_v2.json');lock=load(CFG/'regionfig_v2.lock.json');assert sha(CFG/'regionfig_v2.json')==lock['config_sha256']
    ex=next(q for q in cfg['examples'] if q['id']==args.id);d=data(ex['prior'],ex['building']);g=geometry(ex,d)
    im=np.asarray(Image.open(DOC/f'figures/crops/{ex["id"]}_원본.png').convert('RGBA'))
    m=metrics(d,g['inside']);sec=load(PAY/f'section_{ex["id"]}.json');title=title_for(ex,m)
    fig=plt.figure(figsize=cfg['layout']['inches']);grid=fig.add_gridspec(2,3,left=.035,right=.975,bottom=.105,top=.865,wspace=.20,hspace=.43)
    modes=['region','judgment','category','check'];axes=[]
    positions=[(0,0),(0,1),(1,0),(1,1)]
    panel_titles=['가  실제 사진과 영역','나  실제 사진과 사진 검사','라  결과 · 범주별 유효 확률','마  결과 · 검사 기반 유효 확률']
    for mode,pos,label in zip(modes,positions,panel_titles):
        ax=fig.add_subplot(grid[pos]);photo(ax,ex,d,g,im,mode);legends(ax,mode);axes.append(ax)
        if mode=='region':
            values=m['region_area_m2'];items=[f'{REGIONS[i]} {values[REGIONS[i]]:.1f}' for i in range(6)]
            note=' · '.join(items[:3])+'\n'+' · '.join(items[3:])+' m²'
        elif mode=='judgment':
            v=m['judgment_area_m2'];note=' · '.join(f'{k} {v[k]:.1f}' for k in JUDGMENTS[:3])+'\n'+f'사진 부족 {v["사진 부족"]:.1f} · 판단 없음 {v["판단 없음"]:.1f} m²'
        else:note=f'맞은 넓이 비율 {fmt(m["ok_"+mode+"_pct"])}% · 참값이 있는 지붕 {m["result_area_m2"]:.1f} m²'
        ax.set_title(label+'\n'+note,loc='left',fontsize=12,pad=12,linespacing=1.6)
    section_panel(fig,grid[0,2],ex,sec);bar_panel(fig.add_subplot(grid[1,2]),m)
    heading=fig.suptitle(title,y=.975,fontsize=21,fontweight='bold')
    prior='항공 LiDAR' if ex['prior']=='ALS' else '사전 지붕 모형'
    meta=f'그림 {ex["id"]} · 건물 {ex["building"]} · {prior} · 학습 없는 손실 최소점 해석'
    if ex['selected_after_results']:meta+=' · 결과를 보고 고른 자리'
    subtitle=fig.text(.5,.935,meta,ha='center',fontsize=13,color='#444')
    fig.text(.5,.046,f'자른 범위: 참값이 있는 지붕 {m["result_area_m2"]:.1f} m² · 참값이 없어 칠하지 않은 넓이 {m["unpainted_no_reference_area_m2"]:.1f} m² · 연결 누락 {int((~d["matched"]).sum())}패치',ha='center',fontsize=12)
    fig.text(.5,.022,'같은 사진·같은 자른 상자·같은 회전  |  점선은 가려짐 추정 구간  |  맞고 틀림은 제공된 참값과 허용 오차로 표시',ha='center',fontsize=11,color='#555')
    path=DOC/f'figures/영역표본_{ex["id"]}_{ex["slug"]}.png';fig.savefig(path,dpi=300,facecolor='white')
    if ex['id'] in ['5','6']:
        heading.set_visible(False);subtitle.set_visible(False)
        fig.savefig(DOC/f'figures/검토용_{ex["id"]}_제목숨김.png',dpi=160,facecolor='white')
    plt.close(fig);del fig;gc.collect()
    # Exact matched canvas geometry for the individual native and painted crops.
    for mode in ['raw',*modes]:
        W,H=ex['photo']['crop_size_px'];corners=g['corners'];size=np.ceil(np.ptp(corners,axis=0)).astype(int)
        f=plt.figure(figsize=size/200,dpi=200);ax=f.add_axes([0,0,1,1]);photo(ax,ex,d,g,im,mode)
        label={'raw':'북쪽원본','region':'영역','judgment':'사진검사','category':'범주별','check':'검사기반'}[mode]
        f.savefig(DOC/f'figures/crops/{ex["id"]}_{label}.png',dpi=200,facecolor='white');plt.close(f);gc.collect()
    rec=dict(task_id=cfg['task_id'],id=ex['id'],building=ex['building'],prior=ex['prior'],title=title,expected_title=ex['expected'],
             title_changed=title!=ex['expected'],selected_after_results=ex['selected_after_results'],config_sha256=lock['config_sha256'],
             figure=path.name,figure_sha256=sha(path),photo=ex['photo'],metrics=m,section=sec,
             crop_patch_ids=d['patch_id'][g['inside']],result_patch_ids=d['patch_id'][g['inside']&d['roof_like']&np.isfinite(d['gt_p'])],
             excluded_outside_calibration=g['excluded_outside_calibration'],
             amendments=[load(p) for p in sorted(CFG.glob('amendment_*.json'))],
             panel_identity=dict(same_photo=True,same_box=True,same_rotation=True,same_result_patch_population=True),
             seconds=time.time()-start,environment=environment(),scientific_verdict=None)
    dump(path.with_suffix('.json'),rec)
    dump(PAY/f'render_{ex["id"]}.json',dict(id=ex['id'],metrics=m,figure_sha256=sha(path),environment=environment(),seconds=time.time()-start))
    print('RENDERED',ex['id'],m['ok_category_pct'],m['ok_check_pct'],environment(),flush=True)

if __name__=='__main__':main()
