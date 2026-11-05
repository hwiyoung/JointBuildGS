"""Only the three requested map triptychs and three corresponding sections."""
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':11})

def provenance(paths):
    locked={r['path']:r['sha256'] for r in json.loads((D/'provenance/inputs.lock.json').read_text())['sources']}
    return [dict(path=str(p),sha256=locked.get(str(p)) or sha(p)) for p in paths]

def save(fig,name,meta):
    path=D/'figures';path.mkdir(exist_ok=True);fig.savefig(path/(name+'.png'),dpi=300,facecolor='white');plt.close(fig)
    dump(path/(name+'.json'),dict(**meta,config_sha256=sha(C/'recount_v1.json'),script_sha256=sha(__file__),dpi=300,crs='EPSG:25832 with inherited local XY shift [690953,5336071] m',scientific_verdict=None))

def main():
    c=cfg();colors=c['figures']['map_colors'];status=c['figures']['status_colors']
    for site,prior in c['figures']['scenes']:
        stem=f'{site}__{prior}';root=O/'scenes'/stem;z=loadz(root/'reference_rows.npz');section=json.loads((root/'section.json').read_text())
        if len(sys.argv)>1 and stem!=sys.argv[1]:continue
        xyz=z['xyz'];order=np.argsort(xyz[:,2],kind='stable');xy=xyz[:,:2];lo=xy.min(0)-1;hi=xy.max(0)+1
        if section['status']=='PASS':
            endpoints=np.array([section['start'],section['end']]);lo=np.minimum(lo,endpoints.min(0)-2);hi=np.maximum(hi,endpoints.max(0)+2)
        panelcolors=[np.array([colors[str(k)] for k in z['case_id']]),np.where(z['eligible'],np.where(z['judgment_correct'],status['correct'],status['wrong']),status['excluded']),np.where(z['row_owner']>=0,np.where(z['result_pass'],status['correct'],status['wrong']),status['excluded'])]
        legends=[[(CASES[k],colors[str(k)]) for k in [0,1,2,4,3,-1]],
                 [('판단 맞음',status['correct']),('판단 틀림',status['wrong']),('셈 제외·미소속',status['excluded'])],
                 [('결과 τ 안',status['correct']),('결과 τ 밖',status['wrong']),('미소속',status['excluded'])]]
        fig,axes=plt.subplots(1,3,figsize=(19,7.1));fig.subplots_adjust(left=.055,right=.99,top=.86,bottom=.25,wspace=.19)
        for i,ax in enumerate(axes):
            ax.scatter(xy[order,0],xy[order,1],c=panelcolors[i][order],s=1.15,linewidths=0,rasterized=True)
            ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),xlabel='지역 X (m)',ylabel='지역 Y (m)');ax.set_aspect('equal')
            ax.set_title(['(가) 경우: 참값 채점 기준 칸','(나) 판단: 정확 일치 여부','(다) 본 방법 결과: τ 안 / 밖'][i],pad=11)
            handles=[Line2D([],[],marker='s',linestyle='',color=col,label=name,markersize=7) for name,col in legends[i]]
            ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.16),ncol=2 if i==0 else 1,fontsize=9.5,frameon=False)
        if section['status']=='PASS':
            a,b=np.array(section['start']),np.array(section['end']);axes[0].plot([a[0],b[0]],[a[1],b[1]],color='black',linewidth=1.3)
            axes[0].annotate('A',a,xytext=(4,4),textcoords='offset points',fontweight='bold');axes[0].annotate('A′',b,xytext=(4,4),textcoords='offset points',fontweight='bold')
        n=int(z['eligible'].sum());pc=100*z['judgment_correct'].sum()/n if n else float('nan')
        fig.suptitle(f'{LABELS[site]} · '+('항공 LiDAR' if prior=='ALS' else 'LoD2')+f'  |  참값 {len(xyz):,}행 · 판단 맞음 {pc:.2f}%',fontsize=17,y=.97)
        fig.text(.5,.025,'평가 참값 행만 표시 · XY가 겹치면 높은 Z가 위에 표시됨 · A–A′: 사전 정보만 맞음의 가장 큰 모임',ha='center',fontsize=10)
        sources=[cells_path(site,prior),FT/'targets'/f'{stem}.npz',root/'reference_rows.npz',root/'section.json',score_dir(site,prior,'FINALTRAIN_30000')/'points.npz']
        save(fig,stem+'_maps',dict(title='경우·판단 맞음·결과 τ 안 세 지도',site=site,prior=prior,n_gt=len(xyz),n_judgment_eligible=n,judgment_correct_pct=pc,case_colors=colors,status_colors=status,extent=[lo.tolist(),hi.tolist()],display_order='all rows, ascending Z so highest point is painted last; no downsampling',section=section,sources=provenance(sources)))
        if '--maps-only' in sys.argv:continue
        fig,ax=plt.subplots(figsize=(14,6.8));fig.subplots_adjust(left=.08,right=.98,top=.84,bottom=.20)
        if section['status']!='PASS':
            ax.text(.5,.5,'확인 불가: '+section['reason'],transform=ax.transAxes,ha='center');ax.axis('off')
            save(fig,stem+'_section',dict(site=site,prior=prior,status='확인 불가',section=section,sources=provenance(sources)));continue
        points=loadz(root/'section_points.npz');allz=[]
        # Keep inherited colors for prior/MVS/final output; baseline and target use distinct styles.
        family_colors={'prior':'#D85A30','mvs':'#1D9E75','FINALTRAIN_30000':'#4B2E8A','baseline_30000':'#0072B2'}
        line_styles={'prior':'solid','mvs':'solid','FINALTRAIN_30000':'solid','baseline_30000':'dashed'}
        sources+=[root/'section_points.npz']
        for family in ['prior','mvs','FINALTRAIN_30000','baseline_30000']:
            path=root/(family+'_section.npz');segments=loadz(path)['segments'];sources.append(path)
            ax.add_collection(LineCollection(segments,colors=family_colors[family],linewidths=1.05,linestyles=line_styles[family],label=NAMES[family],rasterized=True))
            within=(segments[:,:,0]>=0)&(segments[:,:,0]<=section['length_m'])
            if within.any():allz.append(segments[:,:,1][within])
        for field,color,marker,size,name in [('gt','#111111','.',3,'참값 점'),('target','#CC79A7','x',14,'목표')]:
            p=points[field];ax.scatter(p[:,0],p[:,1],c=color,marker=marker,s=size,label=name,linewidths=.7,rasterized=True,zorder=4 if field=='gt' else 5)
            if len(p):allz.append(p[:,1])
        if allz:
            heights=np.concatenate(allz);ax.set_ylim(float(heights.min())-.5,float(heights.max())+.5)
        ax.set(xlim=(0,section['length_m']),xlabel='A에서 A′ 방향 단면 거리 (m)',ylabel='상속 지역 높이 (m)')
        ax.grid(alpha=.2);ax.legend(loc='upper center',bbox_to_anchor=(.5,-.12),ncol=6,frameon=False)
        fig.suptitle(f'{LABELS[site]} · '+('항공 LiDAR' if prior=='ALS' else 'LoD2')+'  |  A–A′ 단면',fontsize=17,y=.97)
        ax.set_title(f"사전 정보만 맞음의 가장 큰 모임: {section['component_n_gt']:,}행 · 참값·목표 점은 선에서 ±0.6 m",fontsize=11,pad=10)
        save(fig,stem+'_section',dict(title='참값·사전 정보·MVS·목표·본 방법·기준선 단면',site=site,prior=prior,section=section,sources=provenance(sources),colors=family_colors,point_band_halfwidth_m=.6,surface_rule='exact inherited triangle-plane intersections; cached surfaces unchanged',reference_points=len(points['gt']),target_points=len(points['target']),xlim=list(ax.get_xlim()),ylim=list(ax.get_ylim())))
        print('FIGURES_COMPLETE',stem,flush=True)

if __name__=='__main__':main()
