# trainlog_proto_v1.py — PHD-MAIN-TRAINLOG-v1 참고 코드 (2026-11-10)
# PROCFIG-v1 네 시점(0·7000·15000·30000)으로 한 장면 네 칸(입체·단면·곡선·숫자)을 그리고 GIF로 묶는다.
# 실행: python3 trainlog_proto_v1.py <ROOT>  (ROOT 아래 procfig/gaussians/*.npz, procfig/figures/proc_30000_1_a.json, 출력 an/proto/)
# 4.1의 정의: site()=지금 놓인 자리의 판정, nrm()=목표면 국소 평면 법선, 단면 띠=30,000회 묶이지 않은 것이 가장 많은 폭 1 m 띠.
import sys,json,numpy as np
from scipy.spatial import cKDTree as T
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import EllipseCollection
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
P='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
fm.fontManager.addfont(P);plt.rcParams['font.family']=fm.FontProperties(fname=P).get_name();plt.rcParams['axes.unicode_minus']=False
S=sys.argv[1];O=S+'/an/proto';K=['0','7000','15000','30000'];IT=[0,7000,15000,30000];TAU=21.2
D={k:np.load(f'{S}/procfig/gaussians/{k}.npz',allow_pickle=True) for k in K};d0=D['0']
cam=json.load(open(f'{S}/procfig/figures/proc_30000_1_a.json'))['camera'];Bs=np.array(cam['basis']);ctr=np.array(cam['center']);LT=np.array([-.35,-.45,.82]);LT/=np.linalg.norm(LT)
COL={0:'#7FA7D9',2:'#D85A30',1:'#1D9E75',4:'#E8B931'};NEU='#C9C7BE';PINK='#C2378A';PALE=np.array(to_rgb('#EEECE6'))
sb=d0['target_tag']==1;ptx=d0['target_xyz'][sb];pj=d0['judgment'][sb];ptree=T(ptx[:,:2])
def site(xyz):
    dd,ii=ptree.query(xyz[:,:2],k=8,distance_upper_bound=.35);out=np.full(len(xyz),-1)
    for c in range(8):
        ok=(ii[:,c]<len(ptx))&(out<0)
        jj=np.where(ok)[0];z=np.abs(xyz[jj,2]-ptx[ii[jj,c],2])<=.5;out[jj[z]]=pj[ii[jj[z],c]]
    return out
def qrot(q):
    w,x,y,z=q.T;return np.stack([np.stack([1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)],1),np.stack([2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)],1),np.stack([2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)],1)],1)
m=(d0['target_tag']==1)&(d0['judgment']==2)&(~d0['wall']);tx=d0['target_xyz'][m];ts=d0['target_sigma'][m];tr=T(tx[:,:2])
def nrm(p):
    ii=tr.query_ball_point(p[:2],.5)
    if len(ii)<5: return np.array([0,0,1.])
    q=tx[ii];_,_,v=np.linalg.svd(q-q.mean(0),full_matrices=False);return v[2]*(1 if v[2][2]>=0 else -1)
c2=tx[:,:2].mean(0);_,_,vt=np.linalg.svd(tx[:,:2]-c2,full_matrices=False);a1,a2=vt[0],vt[1]
SEC={};STAT={}
for k,d in D.items():
    xyz=d['xyz'];idx=np.where(~d['wall'])[0];dist,nn=tr.query(xyz[idx,:2]);g=idx[dist<=.25];nn=nn[dist<=.25]
    sd=np.array([(xyz[i]-tx[j])@nrm(xyz[i]) for i,j in zip(g,nn)])*100;b=d['target_tag'][g]==1
    SEC[k]=dict(sd=sd,b=b,u=(xyz[g,:2]-c2)@a1,v=(xyz[g,:2]-c2)@a2,w=d['group33'][g]==1)
    STAT[k]=dict(n=len(xyz),wall=int(d['wall'].sum()),wrong=int((d['group33']==1).sum()),bt=(abs(sd[b])<=TAU).mean()*100,gt=(abs(sd[~b])<=TAU).mean()*100 if (~b).any() else np.nan,ba=float(np.median(d['opacity'][d['target_tag']==1])))
vv=SEC['30000']['v'][~SEC['30000']['b']];bins=np.arange(vv.min(),vv.max(),1.);h,_=np.histogram(vv,bins);b0=bins[h.argmax()]
rel=D['30000']['target_released_at'];rel=rel[(D['30000']['target_tag']==2)&(rel>=0)]
hw=float(np.median(1.96*ts))*100
# 화면 범위를 네 시점 공통으로
allp=np.concatenate([(D[k]['xyz']-ctr)@Bs[:2].T for k in K]);lo=np.percentile(allp,.2,0)-1;hi=np.percentile(allp,99.8,0)+1
def frame(fi):
    k=K[fi];d=D[k];xyz=d['xyz'];R=qrot(d['rotation']/np.linalg.norm(d['rotation'],axis=1,keepdims=True));sc=d['scale']*.6
    t1=R[:,:,0]*sc[:,:1];t2=R[:,:,1]*sc[:,1:2];M=np.stack([np.stack([t1@Bs[0],t2@Bs[0]],1),np.stack([t1@Bs[1],t2@Bs[1]],1)],1)
    U,s,_=np.linalg.svd(M);ang=np.degrees(np.arctan2(U[:,1,0],U[:,0,0]))
    p=(xyz-ctr)@Bs.T;order=np.argsort(-p[:,2])
    st=site(xyz);bound=d['target_tag']==1;j=np.where(bound,d['judgment'],st)
    base=np.array([to_rgb(COL.get(int(x),NEU)) for x in j]);base[d['group33']==1]=to_rgb(PINK)
    base[~bound&(d['group33']!=1)]=base[~bound&(d['group33']!=1)]*.45+PALE*.55
    sh=.55+.45*np.abs(d['normal']@LT);rgb=np.clip(base*sh[:,None],0,1);al=.25+.75*d['opacity']
    fig=plt.figure(figsize=(16,9),dpi=110,facecolor='white');gs=fig.add_gridspec(2,3,height_ratios=[1.75,1],width_ratios=[1.15,1.15,1],hspace=.28,wspace=.18,left=.055,right=.975,top=.9,bottom=.07)
    fig.text(.03,.955,f'B173 · 학습 {IT[fi]:,}회',fontsize=22,fontweight='bold',color='#16263d',va='center')
    ax=fig.add_axes([.27,.94,.71,.025]);ax.barh(0,30000,color='#E5E3DC',height=1);ax.barh(0,IT[fi],color='#5F5E5A',height=1);ax.set_xlim(0,30000);ax.axis('off')
    for x in IT: ax.plot([x,x],[-.5,.5],color='white',lw=1.5)
    A=fig.add_subplot(gs[0,:2]);A.add_collection(EllipseCollection(2*s[order,0],2*s[order,1],ang[order],units='xy',offsets=p[order,:2],offset_transform=A.transData,facecolors=np.c_[rgb[order],al[order]],edgecolors='none'))
    A.set_xlim(lo[0],hi[0]);A.set_ylim(lo[1],hi[1]);A.set_aspect('equal');A.axis('off');A.set_title('입체 · 같은 카메라',fontsize=14,loc='left',color='#2e3a48')
    A.plot([lo[0]+1,lo[0]+6],[lo[1]+1,lo[1]+1],color='#2e3a48',lw=2);A.text(lo[0]+3.5,lo[1]+1.6,'5 m',ha='center',fontsize=11,color='#2e3a48')
    B=fig.add_subplot(gs[0,2]);q=SEC[k];sm=(q['v']>=b0)&(q['v']<b0+1)
    B.axhspan(-hw,hw,color='#D85A30',alpha=.12,lw=0);B.axhline(0,color='#D85A30',lw=.9)
    for t in (-TAU,TAU): B.axhline(t,color='#16263d',lw=.8,ls=(0,(4,3)))
    nb=sm&~q['b'];bb=sm&q['b'];ww=sm&q['w']
    B.scatter(q['u'][nb],np.clip(q['sd'][nb],-60,40),s=10,c='#F0B49C',lw=0);B.scatter(q['u'][bb&~q['w']],np.clip(q['sd'][bb&~q['w']],-60,40),s=6,c='#D85A30',lw=0);B.scatter(q['u'][ww],np.clip(q['sd'][ww],-60,40),s=8,c=PINK,lw=0)
    B.set_ylim(-63,43);B.set_xlim(-46,31);B.set_title('단면 · 보정 자리 폭 1 m',fontsize=14,loc='left',color='#2e3a48');B.set_ylabel('목표면에서 (cm)',fontsize=11);B.set_xlabel('지붕 긴 방향 (m)',fontsize=11)
    C=fig.add_subplot(gs[1,:2]);hb=np.arange(0,15001,250);hh,_=np.histogram(rel,hb);C2=C.twinx()
    C2.bar(hb[:-1],hh,width=250,align='edge',color='#B4B2A9',alpha=.55,lw=0);C2.set_ylabel('풀린 가우시안 수 (250회당)',fontsize=10,color='#6b6a65');C2.tick_params(labelsize=9,colors='#6b6a65')
    for key,cl,lab in (('bt','#D85A30','묶인 것'),('gt','#E59A7A','묶이지 않은 것')):
        ys=[STAT[x][key] for x in K];C.plot(IT,ys,color=cl,lw=1.2,ls=(0,(4,3)),alpha=.5);C.scatter(IT[:fi+1],ys[:fi+1],s=60,color=cl,zorder=5,label=lab);C.scatter(IT[fi+1:],ys[fi+1:],s=60,facecolors='white',edgecolors=cl,zorder=5)
    C.axvline(IT[fi],color='#2e3a48',lw=1.5);C.set_xlim(-300,30300);C.set_ylim(0,105);C.set_ylabel('보정 자리 τ 안 (%)',fontsize=11);C.set_xticks(IT);C.set_xticklabels(['0','7,000','15,000','30,000'])
    C.set_zorder(C2.get_zorder()+1);C.patch.set_visible(False);C.legend(loc='lower right',fontsize=10.5,frameon=False);C.set_title('곡선 · 점은 저장된 네 시점, 막대는 풀린 때(30,000회에 남은 것)',fontsize=13,loc='left',color='#2e3a48')
    for x in (C,C2): x.spines['top'].set_visible(False)
    E_=fig.add_subplot(gs[1,2]);E_.axis('off');s_=STAT[k];E_.set_title('숫자',fontsize=14,loc='left',color='#2e3a48')
    rows=[('건물 가우시안',f'{s_["n"]:,}개'),('벽',f'{s_["wall"]:,}개'),('옛 지붕에 틀리게 놓인 것',f'{s_["wrong"]:,}개'),('묶인 것 불투명도 중앙',f'{s_["ba"]:.2f}'),('보정 자리 묶이지 않은 것 τ 안',f'{s_["gt"]:.0f} %')]
    for r,(a_,b_) in enumerate(rows): E_.text(0,.86-r*.19,a_,fontsize=13,color='#444441',transform=E_.transAxes);E_.text(1,.86-r*.19,b_,fontsize=14,fontweight='bold',ha='right',color='#16263d',transform=E_.transAxes)
    h=[Patch(color=COL[0],label='일치'),Patch(color=COL[2],label='보정'),Patch(color=COL[1],label='보존'),Patch(color=COL[4],label='결측'),Patch(color=PINK,label='옛 지붕에 틀리게 놓인 것'),Patch(color=NEU,label='가까운 목표 없음(벽 등)'),Patch(color=tuple(np.array(to_rgb(COL[2]))*.45+PALE*.55),label='연한 색 = 묶이지 않음')]
    fig.legend(handles=h,loc='lower center',ncol=7,frameon=False,fontsize=11.5,bbox_to_anchor=(.5,.0))
    fig.savefig(f'{O}/frame_{k}.png',facecolor='white');plt.close(fig)
for i in range(4): frame(i);print('frame',K[i],STAT[K[i]])
from PIL import Image
ims=[Image.open(f'{O}/frame_{k}.png').convert('RGB') for k in K]
ims[0].save(f'{O}/B173_학습과정_네시점_v1.gif',save_all=True,append_images=ims[1:],duration=[1800,1800,1800,3000],loop=0)
print('rel n',len(rel),'b0',b0)
