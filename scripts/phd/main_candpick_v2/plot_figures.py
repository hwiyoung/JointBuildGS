"""Static research figures from exact saved observations; no image generation."""
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from scipy import ndimage
from cp2_common import *

COLORS={'v1':'#444444','a':'#b37c24','b':'#d0493d','c':'#307aaf','d':'#379273'}
LABELS={'v1':'v1 기준','a':'가 · 앞 후보만','b':'나 · 색 먼저','c':'다 · 모양 학습','d':'라 · 둘레 학습'}
SITES={'B173_ALS':'B173 · 항공 LiDAR','B173_LoD2':'B173 · LoD2','R1_LoD2':'R1 · LoD2'}
REP_NAMES={'B173_wing':'B173 날개','R1_stairs':'R1 계단 지붕','leaf_flat_roof':'낙엽 지붕 대체 자리','B173_LoD2_front':'B173 · LoD2 · 앞 자리'}

def setup():
    fonts=[str(CP1/'assets/NotoSansCJK-Regular.ttc')]
    assert Path(fonts[0]).exists(),'Korean figure font unavailable'
    if fonts:
        font_manager.fontManager.addfont(fonts[0]);plt.rcParams['font.family']=font_manager.FontProperties(fname=fonts[0]).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':11,'figure.facecolor':'white','savefig.facecolor':'white'})

def finish(fig,name,metadata):
    path=DOC/'figures'/name;path.parent.mkdir(parents=True,exist_ok=True)
    fig.text(.995,.003,SOURCE,ha='right',va='bottom',fontsize=8,color='#666666')
    fig.savefig(path.with_suffix('.png'),dpi=240,bbox_inches='tight');plt.close(fig)
    save(path.with_suffix('.json'),dict(source=SOURCE,scientific_verdict=None,**metadata),replace=True)

def curves():
    rows=json.loads((DOC/'tables/opacity_curves.json').read_text())['rows']
    for unit in UNITS:
        for start in ['equal','right']:
            fig,axes=plt.subplots(1,2,figsize=(13,4.8),sharey=True)
            for ax,side in zip(axes,['front','back']):
                for v in ['v1','a','b','c','d']:
                    data=[r for r in rows if r['unit']==unit and r['start']==start and r['variant']==v and r['group']=='a' and r['side']==side]
                    if data:ax.plot([r['iteration'] for r in data],[r['mean_right_minus_wrong'] for r in data],label=LABELS[v],color=COLORS[v],lw=2.2)
                    else:ax.plot([],[],marker='x',ls='',color=COLORS[v],label=LABELS[v]+' · 확인 불가')
                ax.axhline(0,color='#888888',lw=.7);ax.axhline(.2,color='#bbbbbb',ls=':',lw=1)
                ax.set_ylim(-1,1);ax.set_xlabel('학습 반복');ax.grid(alpha=.15)
                ax.set_title('맞는 후보가 '+('앞' if side=='front' else '뒤'))
            axes[0].set_ylabel('맞는 쪽 − 틀린 쪽 불투명도')
            fig.suptitle(SITES[unit]+' · 출발 '+('같음' if start=='equal' else '맞음')+' · 묶음 가',fontsize=16)
            handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=5,frameon=False)
            fig.tight_layout(rect=[0,.08,1,.94])
            finish(fig,f'curves_{unit}_{start}',dict(unit=unit,start=start,group='a',measure='unweighted point mean; full area-weighted values in tables'))

def sections():
    cfg=config()
    for rep in cfg['representatives']:
        if not rep['selection']:continue
        unit=rep['unit'];d=arrays(CP1/'places'/(unit+'.npz'))
        ids=np.flatnonzero(np.isin(d['point_id'],rep['selection']['point_ids']))
        seed=np.flatnonzero(d['point_id']==rep['selection']['seed_point_id'])[0]
        origin=d['centre'][seed];frame=np.stack([d['tangent1'][seed],d['tangent2'][seed],d['normal'][seed]])
        local=(d['centre'][ids]-origin)@frame.T
        mv=(d['centre'][ids]+d['normal'][ids]*d['mvs_p'][ids,None]-origin)@frame.T
        gt=(d['centre'][ids]+d['normal'][ids]*d['gt_p'][ids,None]-origin)@frame.T
        selected=np.flatnonzero(np.abs(local[:,1])<=.251);selected=selected[np.argsort(local[selected,0])]
        fig,axes=plt.subplots(4,4,figsize=(17,13),sharex=True,sharey=True)
        allh=[local[:,2],mv[:,2],gt[:,2]];records=[]
        for row,v in enumerate('abcd'):
            arm=f'cp2_{v}_right_{unit}';root=OUT/'runs'/arm;end=cfg['arms'][v]['iterations']
            for col,step in enumerate([0,500,1000,end]):
                ax=axes[row,col];p=root/f'candidate_{step}.npz';ax.set_title(LABELS[v]+f' · {step:,}회',fontsize=11)
                if not p.exists():
                    ax.text(.5,.5,'확인 불가',transform=ax.transAxes,ha='center',va='center',color='#777777');continue
                with np.load(p) as z:
                    points=(z['geometry_means']-origin)@frame.T;alpha=1/(1+np.exp(-z['opacity']));original=z['original_ids']
                ax.plot(local[selected,0],local[selected,2],color='#555555',lw=1)
                ax.scatter(mv[selected,0],mv[selected,2],marker='x',color='#286c9e',s=30)
                ax.scatter(gt[selected,0],gt[selected,2],marker='D',facecolors='none',edgecolors='#151515',s=30)
                for ii in selected:
                    point=ids[ii]
                    for kind,color in [(0,'#bc8425'),(1,'#286c9e')]:
                        m=(original//8==point)&(original//4%2==kind)
                        if not m.any():continue
                        pos=points[m];a=alpha[m]
                        allh.append(pos[:,2])
                        if v=='c':
                            for xyz,op in zip(pos,a):ax.plot([xyz[0]-.08,xyz[0]+.08],[xyz[2],xyz[2]],color=color,lw=5,alpha=float(op),solid_capstyle='butt')
                        else:
                            x,h=pos.mean(0)[[0,2]];ax.plot([x-.19,x+.19],[h,h],color=color,lw=7,alpha=float(a.mean()),solid_capstyle='butt')
                        x,h=pos.mean(0)[[0,2]];ax.annotate(f'{a.mean():.2f}',(x,h),xytext=(0,7),textcoords='offset points',ha='center',fontsize=8,color=color)
                ax.grid(alpha=.14)
                if row==3:ax.set_xlabel('접선 u (m)')
                if col==0:ax.set_ylabel('법선 높이 h (m)')
                records.append(dict(arm=arm,iteration=step,file=bind(p)))
        hh=np.concatenate(allh);lo=np.nanmin(hh);hi=np.nanmax(hh);pad=max(.35,(hi-lo)*.15)
        for ax in axes.ravel():ax.set_ylim(lo-pad,hi+pad)
        handles=[Line2D([],[],color='#bc8425',lw=5,label='사전 정보 후보'),Line2D([],[],color='#286c9e',lw=5,label='영상 후보'),
                 Line2D([],[],marker='D',markerfacecolor='none',color='#151515',ls='',label='참값')]
        fig.legend(handles=handles,loc='lower center',ncol=3,frameon=False)
        fig.suptitle(REP_NAMES[rep['id']]+' · 출발 맞음 · 고정 단면',fontsize=18)
        fig.tight_layout(rect=[0,.04,1,.96])
        finish(fig,f'section_{rep["id"]}',dict(representative=rep,section_point_ids=d['point_id'][ids[selected]],snapshots=records,
            rendering='Line opacity is saved candidate opacity. Arm c draws each of the four moved Gaussian centers; other arms show their mean, as in v1.'))

def renders():
    cfg=config()
    for rep in cfg['representatives']:
        if not rep['selection']:continue
        root=OUT/'renders'/rep['id'];unit=rep['unit'];datasets={}
        for v in ['v1','a','b','c','d']:
            arm=f'cp_right_sh3_{unit}' if v=='v1' else f'cp2_{v}_right_{unit}'
            p=root/(arm+'.npz')
            if p.exists():datasets[v]=arrays(p)
        if not datasets:continue
        first=next(iter(datasets.values()));photo=first['photo']
        maps=[x['height_map'][np.isfinite(x['height_map'])] for x in datasets.values()]
        finite=np.concatenate(maps);lim=max(.5,float(np.max(np.abs(finite)))) if len(finite) else 1.
        fig,axes=plt.subplots(2,6,figsize=(20,7))
        axes[0,0].imshow(photo,interpolation='nearest');axes[0,0].set_title('실제 사진')
        axes[1,0].imshow(photo,interpolation='nearest');axes[1,0].set_title('같은 자리')
        last=None
        for col,v in enumerate(['v1','a','b','c','d'],1):
            axes[0,col].set_title(LABELS[v]+' · 끝 렌더');axes[1,col].set_title('깊이 → h')
            if v not in datasets:
                for row in range(2):axes[row,col].text(.5,.5,'확인 불가',transform=axes[row,col].transAxes,ha='center',va='center')
                continue
            a=datasets[v];axes[0,col].imshow(np.clip(a['rgb'],0,1),interpolation='nearest')
            axes[1,col].imshow(photo,interpolation='nearest',alpha=.3)
            last=axes[1,col].imshow(a['height_map'],cmap='RdBu_r',vmin=-lim,vmax=lim,interpolation='nearest')
        for ax in axes.ravel():ax.axis('off')
        fig.suptitle(REP_NAMES[rep['id']]+' · 출발 맞음 · '+rep['render_view']['name'],fontsize=16)
        fig.subplots_adjust(left=.01,right=.95,bottom=.03,top=.88,wspace=.04,hspace=.18)
        if last is not None:fig.colorbar(last,cax=fig.add_axes([.965,.14,.012,.32]),label='h (m)')
        finish(fig,f'render_{rep["id"]}',dict(representative=rep,shared_height_limit_m=lim,
            height_map='Per pixel median of the signed normal heights of all selected representative point supports; transparent pixels unavailable.'))

def photo_curves():
    target=arrays(OUT/'photo_dl/target_834.npz')
    ac=module('cp2_figure_components','/repo/scripts/phd/main_judgenum_v1/analysis_core.py')
    components=[]
    for bid in sorted(set(target['building'])):
        ix=np.flatnonzero(target['building']==bid);labels,n=ac.components(target['centre'][ix],.36)
        for j in range(n):
            ids=ix[labels==j];area=float(target['area'][ids].sum())
            points=sorted(set(target['photo_point_id'][ids]));rank=[]
            for point in points:rank.append((-float(target['area'][ids][target['photo_point_id'][ids]==point].sum()),point))
            _,point=min(rank)
            components.append(dict(building=str(bid),area_m2=area,point_id=point,patch_ids=sorted(target['patch_id'][ids].tolist()),
                min_patch_id=str(min(target['patch_id'][ids]))))
    selected=sorted(components,key=lambda r:(-r['area_m2'],r['building'],r['min_patch_id']))[:10]
    selection=OUT/'photo_dl/ten_curve_selection.json'
    if not selection.exists():save(selection,dict(at=now(),rule='Old selected cell1/support set; within-building 0.36m components; ten largest area; lexical building/patch tie; largest member point area then lexical point ID.',rows=selected,source=SOURCE,scientific_verdict=None))
    assert json.loads(selection.read_text())['rows']==selected
    fig,axes=plt.subplots(2,5,figsize=(20,8));metadata=[]
    for ax,rec,index in zip(axes.ravel(),selected,range(1,11)):
        point=rec['point_id'];tile=point.split(':')[2]
        p=arrays(PC/'points'/f'{tile}__LoD2.npz');row=np.flatnonzero(p['point_id']==point)[0]
        new=arrays(OUT/'photo_dl/points/roof'/f'{tile}__LoD2.npz');assert np.array_equal(new['point_id'],p['point_id'])
        h=p['heights'][row];s=p['curve'][row].astype(float);valid=np.isfinite(h)&np.isfinite(s);order=np.argsort(h[valid])
        old=3*p['sigma'][row];dl=new['DL_m'][row]
        ax.axvspan(-old,old,color='#d5a74b',alpha=.22,label='v1 범위')
        if np.isfinite(dl):ax.axvspan(-dl,dl,color='#3283b5',alpha=.23,label='검출 한계')
        ax.plot(h[valid][order],s[valid][order],color='#323a45',lw=1.2)
        ax.axvline(0,color='#666666',lw=.6);ax.set_ylim(-1,1);ax.grid(alpha=.15)
        ax.set_title(f'{index} · {rec["area_m2"]:.2f} m²\nDL {dl*100:.1f} cm' if np.isfinite(dl) else f'{index} · DL 확인 불가',fontsize=12)
        ax.set_xlabel('법선 높이 h (m)');ax.set_ylabel('사진 점수')
        metadata.append(dict(**rec,old_half_range_m=old,new_half_range_m=dl,point_file=bind(PC/'points'/f'{tile}__LoD2.npz')))
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=2,frameon=False)
    fig.suptitle('기존 사진 지지 834.44 m² · 큰 덩어리 10개의 대표 곡선',fontsize=18)
    fig.tight_layout(rect=[0,.05,1,.94]);finish(fig,'photo_834_ten_curves',dict(rows=metadata))

def main():
    setup();p=argparse.ArgumentParser();p.add_argument('which',choices=['photo','training','all']);a=p.parse_args()
    if a.which in ['photo','all']:photo_curves()
    if a.which in ['training','all']:curves();sections();renders()
    print('FIGURES',a.which,'complete',flush=True)

if __name__=='__main__':main()
