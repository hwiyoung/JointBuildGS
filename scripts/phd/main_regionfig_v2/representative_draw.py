"""Source-backed representative figures. Never changes supplied values or old figures."""
from representative_prepare import *
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
import argparse,gc

TITLES={
 '1':('다듬기','맞는 두 입력에서, 두 결과도 허용 범위 안에 남는다'),
 '2':('보정 · 실제 변화','A: 옛 사전 정보에 남던 결과가, 사진 검사 후 현재 면으로 이동한다'),
 '3':('보정 · 단순화','A: 낮게 단순화된 사전 정보에서, 두 결과가 현재 면으로 이동한다'),
 '4':('보존 · 일부 실패 포함','A는 허용 범위 안에 남지만, 주변 보존 영역까지 모두 지키지는 못한다'),
 '5':('보존 실패 · 사진 반박','A: 맞는 사전 정보를 사진이 반박하고, 검사 기반 결과가 틀어진다'),
 '6':('보존 실패 · 사진 지지','A: 사진이 사전 정보를 지지해도, 두 결과는 허용 범위를 벗어난다'),
 '7':('상속 · 사진 정보 부족','A: MVS가 없고 검사 사진이 부족해, 두 결과가 사전 정보에 그대로 남는다'),
 '8':('상속 · MVS 결측','A: 사진은 반박하지만 MVS가 없어, 틀린 사전 정보가 그대로 남는다')}
NOTES={
 '1':'A의 오차는 줄었음. 다듬기 영역 전체의 정밀도 향상을 뜻하지 않음.',
 '2':'실제 변화 사례의 현재 사진. 시간 변화의 별도 검증을 추가하지 않음.',
 '3':'두 결과가 겹치는 A에서도, 주변 영역의 두 결과는 다를 수 있음.',
 '4':'보존은 여기서 허용 오차 안이라는 뜻. A의 정확도는 사전 정보보다 낮음.',
 '5':'사진에서 어두운 띠와 밝은 구조물이 보임. 실패의 원인은 확인 불가.',
 '6':'사진에서 지붕 이음선과 밝은 돌출물이 보임. 실패의 원인은 확인 불가.',
 '7':'사진 속 지붕은 보임. 검사 사진 부족을 물리적 비가시로 해석하지 않음.',
 '8':'사진 반박만으로 이동할 현재 면이 생기지는 않음. 제공된 결과는 이동 0.'}
CASE={1:'다듬기',2:'보정',3:'보정',4:'보존',5:'보존',6:'보존',7:'사진 부족 상속',8:'사진 부족 외 상속'}
COLORS=['#242b33','#ce7b15','#23864d','#787878','#196aab']

def annotate_a(ax,point,size=15):
    ax.plot(*point,marker='o',ms=13,mfc='none',mec='white',mew=3,zorder=19)
    ax.plot(*point,marker='o',ms=13,mfc='none',mec='#172f43',mew=1.3,zorder=20)
    ax.annotate('A',xy=point,xytext=(17,16),textcoords='offset points',fontsize=size,
      fontweight='bold',color='#172f43',bbox=dict(fc='white',ec='#172f43',pad=2),
      arrowprops=dict(arrowstyle='-',color='#172f43',lw=1.1),zorder=21)

def photos(fig,ex,row,d,g,im):
    # Retain the exact source crop, camera and orientation; only display limits change.
    ax=fig.add_axes([.035,.455,.29,.365]);photo(ax,ex,d,g,im,'raw')
    olddraw.section_arrow(ax,g['line'],np.array(ex['photo']['line_midpoint_occluded']),halo=True,lw=1.1)
    ax.annotate('0 m',xy=g['line'][0],xytext=(-14,-15),textcoords='offset points',fontsize=9,
                bbox=dict(fc='white',ec='none',alpha=.9,pad=1),zorder=22)
    point=np.mean(row['focus_polygon_display_px'],axis=0);annotate_a(ax,point)
    bounds=row['focus_zoom_bounds_px'];ax.add_patch(Rectangle((bounds[0],bounds[2]),bounds[1]-bounds[0],bounds[3]-bounds[2],
      fill=False,ec='white',lw=2,zorder=10,path_effects=[patheffects.Stroke(linewidth=3.5,foreground='#172f43'),patheffects.Normal()]))
    ax.text(.02,.98,'북 ↑',transform=ax.transAxes,va='top',fontsize=11,bbox=dict(fc='white',ec='none',alpha=.85))
    ax.set_title('① 실제 사진에서 A 찾기',loc='left',fontsize=15,fontweight='bold',pad=8)
    ax.text(0,-.04,'상자: 확대 범위 · A: 단면 폭 안 패치(중심선 위 점 아님)',transform=ax.transAxes,fontsize=9,color='#4b5560')
    az=fig.add_axes([.355,.455,.265,.365]);photo(az,ex,d,g,im,'raw')
    poly=np.array(row['focus_polygon_display_px']);judge=int(row['focus_values']['judgment'])
    fc={0:'#1b9e77',1:'#e7298a',2:'#ffffff',3:'#ffffff',4:'#dddddd',-1:'#ffffff'}[judge]
    az.add_collection(PolyCollection([poly],facecolors=fc,edgecolors='white',linewidths=1.5,alpha=.75,zorder=10))
    annotate_a(az,point)
    az.set_xlim(*bounds[:2]);az.set_ylim(*bounds[2:]);az.set_aspect('equal')
    judge_label={0:'사전 정보 지지',1:'사전 정보 반박',2:'판단 유보',3:'무늬 부족',4:'검사 사진 부족',-1:'판단 없음'}[judge]
    az.set_title('② A 확대 · 사진 검사의 판단',loc='left',fontsize=15,fontweight='bold',pad=8)
    short={0:'지지',1:'반박',2:'유보',3:'무늬 부족',4:'사진 부족',-1:'판단 없음'}[judge]
    az.text(.025,.97,short,transform=az.transAxes,va='top',fontsize=13,fontweight='bold',
            bbox=dict(fc='white',ec=fc,pad=3),color='#263542',zorder=25)
    label='회색 = 사진 부족 · 선택 2장 / 최소 3장' if judge==4 else {0:'청록 = 검사에서 사전 정보 지지',1:'분홍 = 검사에서 사전 정보 반박'}.get(judge,judge_label)
    az.text(0,-.04,label,transform=az.transAxes,fontsize=10,color='#4b5560')
    return ax,az

def ruler(fig,row):
    v=row['focus_values'];errors=np.array([-v['gt_p'],v['z_category']-v['gt_p'],v['z_check']-v['gt_p']])*100
    tau=v['tau']*100;lo=min(-tau,float(errors.min()));hi=max(tau,float(errors.max()));span=hi-lo
    ax=fig.add_axes([.73,.505,.215,.27]);ax.axvspan(-tau,tau,fc='#e2f0e8',ec='none',zorder=0)
    ax.axvline(0,color='#23864d',lw=1.5,zorder=1)
    for y,(e,color,marker) in enumerate(zip(errors,[COLORS[0],COLORS[3],COLORS[4]],['s','D','o'])):
        yy=2-y;ax.plot([0,e],[yy,yy],color=color,lw=1.3,zorder=2)
        ax.plot(e,yy,marker=marker,ms=8,mfc=color,mec='white',mew=.6,zorder=3)
        ok=abs(e)<=tau
        ax.text(.99,(yy+.21)/3.05,f'{e:+.1f} cm  ·  '+('맞음' if ok else '틀림'),transform=ax.transAxes,
                ha='right',va='center',fontsize=11,fontweight='bold',bbox=dict(fc='white',ec='none',alpha=.85,pad=1))
    ax.set_yticks([2,1,0],['사전 정보','범주별 결과','검사 기반 결과'],fontsize=11)
    ax.set_ylim(-.55,2.5);ax.set_xlim(lo-.08*span,hi+.1*span);ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True);ax.tick_params(axis='y',length=0)
    ax.set_xlabel('참조면에서 법선 방향 오차 (cm)',fontsize=10,labelpad=6)
    for spine in ['top','left','right']:ax.spines[spine].set_visible(False)
    fig.text(.672,.837,'③ A의 판정 · 제공 참조값 기준',fontsize=15,fontweight='bold')
    fig.text(.672,.805,f'초록 띠: 허용 범위 ±{tau:g} cm',fontsize=11,color='#38634a')
    return ax,errors

def sections_pair(fig,ex,row):
    sec=load(PAY/f'section_{ex["id"]}.json');s=np.array(sec['bin_centres_m']);h=np.array(sec['heights_relative_m'],float)
    v=row['focus_values'];base=v['centre'][2];nz=v['normal'][2];zero=sec['reference_zero_model_m']
    raw=np.array([base,base+(v['mvs_p'] if v['mvs_p'] is not None else np.nan)*nz,
          base+v['gt_p']*nz,base+v['z_category']*nz,base+v['z_check']*nz])-zero
    both=np.r_[h.ravel(),raw];finite=both[np.isfinite(both)];lo,hi=finite.min(),finite.max();pad=max((hi-lo)*.12,.035)
    ylims=[lo-pad,hi+pad];loc=row['focus_along_m'];axes=[]
    labels=['사전 정보','MVS','참조면','범주별 결과','검사 기반 결과']
    styles=[dict(color=COLORS[0],lw=1.3,alpha=.7),dict(color=COLORS[1],lw=1.3,alpha=.7),dict(color=COLORS[2],ls='none',marker='.',ms=4,alpha=.7),
       dict(color=COLORS[3],ls='--',lw=2,alpha=.7),dict(color=COLORS[4],lw=1.2,alpha=.7)]
    for rect,ks,title in [([.065,.15,.405,.205],[0,1,2],'④ 입력 단면 · 사전 정보 / MVS / 참조면'),
                          ([.555,.15,.405,.205],[3,4,2],'⑤ 결과 단면 · 범주별 / 검사 기반 / 참조면')]:
        ax=fig.add_axes(rect);axes.append(ax)
        ax.axvspan(max(0,loc-.14),min(sec['length_m'],loc+.14),color='#172f43',alpha=.09,zorder=0)
        ax.axvline(loc,color='#172f43',lw=.8,ls=':',zorder=0)
        for k in ks:
            ax.plot(s,h[:,k],label=labels[k],**styles[k])
            if np.isfinite(raw[k]):
                ax.plot(loc,raw[k],marker={0:'s',1:'v',2:'o',3:'D',4:'x'}[k],color=COLORS[k],ms=8,
                        mfc='white' if k in [2,3] else COLORS[k],mew=1.4,zorder=6+k)
        ax.text(loc,ylims[1],'A',ha='center',va='bottom',fontweight='bold',fontsize=12,color='#172f43')
        k=0 if ks[0]==0 else 4
        target_y=(raw[k]-ylims[0])/(ylims[1]-ylims[0])
        text_y=.68 if target_y>.35 else .28
        label='A 사전 정보 원값' if k==0 else 'A 검사 기반 원값'
        ax.annotate(label,xy=(loc,raw[k]),xytext=(.67,text_y),textcoords='axes fraction',
          fontsize=10,color=COLORS[k],fontweight='bold',
          bbox=dict(fc='white',ec='none',alpha=.9,pad=2),
          arrowprops=dict(arrowstyle='->',color=COLORS[k],lw=1),zorder=20)
        ax.set_xlim(0,sec['length_m']);ax.set_ylim(ylims);ax.set_ylabel('상대 높이 (m)',fontsize=11)
        ax.set_xlabel('고정 단면 시작점부터 거리 (m)',fontsize=11);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
        ax.set_title(title,loc='left',fontsize=14,fontweight='bold',pad=52)
        ax.text(0,1.19,'선·작은 점: 주변 중앙값   큰 기호: A 한 패치 원값',transform=ax.transAxes,
                    fontsize=11.5,color='#364653')
        handles=[Line2D([],[],color=COLORS[k],ls='--' if k==3 else 'none' if k==2 else '-',
                        marker={0:'s',1:'v',2:'o',3:'D',4:'x'}[k],ms=7,
                        mfc='white' if k in [2,3] else COLORS[k],label=labels[k]) for k in ks]
        ax.legend(handles=handles,loc='lower left',bbox_to_anchor=(0,1.015),ncol=3,fontsize=10,frameon=False,borderaxespad=0,
                  handlelength=1.7,columnspacing=1.0)
        for sp in ['top','right']:ax.spines[sp].set_visible(False)
        if ex['id'] in ['7','8']:
            msg='A에서 MVS 없음' if ks[0]==0 else 'A: 두 결과 = 사전 정보 (이동 0)'
            ax.text(.98,.96,msg,transform=ax.transAxes,ha='right',va='top',fontsize=11,
              bbox=dict(fc='white',ec='none',alpha=.9,pad=2))
    return sec,raw,ylims

def main():
    ap=argparse.ArgumentParser();ap.add_argument('id');args=ap.parse_args()
    design=load(CFG/REV/'design.json');lock=load(CFG/REV/'design.lock.json')
    assert sha(CFG/REV/'design.json')==lock['config_sha256']
    assert sha(CFG/'regionfig_v2.json')==design['base_config_sha256']
    ex=next(q for q in load(CFG/'regionfig_v2.json')['examples'] if q['id']==args.id)
    row=next(q for q in design['examples'] if q['id']==args.id)
    d=data(ex['prior'],ex['building']);g=geometry(ex,d)
    im=np.asarray(Image.open(DOC/f'figures/crops/{args.id}_원본.png').convert('RGBA'))
    fig=plt.figure(figsize=design['design']['figsize']);fig.set_facecolor('white')
    title,sub=TITLES[args.id]
    heading=fig.text(.035,.967,f'{args.id}  {title}',fontsize=25,fontweight='bold',color='#172f43',va='top')
    subtitle=fig.text(.035,.925,sub,fontsize=17,color='#293642',va='top')
    meta=fig.text(.035,.884,f'건물 {ex["building"]} · {ex["prior"]}  |  A는 사례 설명을 위해 결과 확인 후 고른 한 패치  |  학습 없는 손실 최소점',fontsize=10.5,color='#5b6167')
    photos(fig,ex,row,d,g,im);_,errors=ruler(fig,row);sec,raw,ylims=sections_pair(fig,ex,row)
    tar=row['target'];zone=CASE[int(args.id)]
    stats=fig.text(.035,.072,f'사진 범위의 {zone} 영역 {tar["area_m2"]:.1f} m²  |  맞은 넓이: 범주별 {tar["ok_category_pct"]:.1f}%  /  검사 기반 {tar["ok_check_pct"]:.1f}%  |  A 한 점과 영역 전체를 구분',fontsize=12,fontweight='bold',color='#293642')
    note=fig.text(.035,.044,NOTES[args.id],fontsize=11,color='#4b5560')
    fig.text(.035,.02,'③ 법선 오차(cm)와 ④⑤ 연직 높이(m)는 다른 양 · ④⑤ 같은 축, 폭 안의 0.25 m별 중앙값 · ③ 축 범위는 사례마다 다름 · 사진 위치선의 점선은 가려짐 추정',fontsize=9,color='#626970')
    root=DOC/REV;root.mkdir(exist_ok=True);path=root/f'대표그림_{args.id}.png'
    fig.savefig(path,dpi=300,facecolor='white')
    fig.savefig(root/f'미리보기_{args.id}.png',dpi=90,facecolor='white')
    # Hide title, conclusion and contextual footnote for the first-viewer check.
    for obj in [heading,subtitle,note]:obj.set_visible(False)
    fig.savefig(root/f'검토용_{args.id}.png',dpi=110,facecolor='white')
    dump(root/f'대표그림_{args.id}.json',dict(task_id=design['task_id'],id=args.id,title=title,subtitle=sub,
      config_sha256=lock['config_sha256'],focus=row,section=sec,focus_heights_relative_m=raw,
      focus_normal_error_cm=errors,section_y_limits=ylims,photo_source_sha256=sha(DOC/f'figures/crops/{args.id}_원본.png'),
      figure_sha256=sha(path),generator_sha256=sha(__file__),environment=environment(),scientific_verdict=None))
    print('REPRESENTATIVE',args.id,'rendered',environment(),flush=True);plt.close(fig);gc.collect()

if __name__=='__main__':main()
