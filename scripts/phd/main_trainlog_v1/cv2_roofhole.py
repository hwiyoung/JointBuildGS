"""PHD-MAIN-TRAINLOG-v1 B0 x LoD2: why the south end roof face (the w2/w3/w4 roof face rule) has no surface at 30,000 in one band (2026-11-15, user '지붕 확인해보자', '지붕 원인 확인').
Read-only, CPU, no training: GTJUDGE rows / distances (tl_<n>), FINALTRAIN targets (nearest patch centre within 1 m), concept_v2 discs (building-scope Gaussians),
gtj renders (depth of every mesh view) and the B0 view list; GT used only for measuring and drawing. Views where this face is seen = views where >= 50 % of
3,000 control rows (face rows with a surface at 30,000, seed 0) have the 30,000 render depth within 10 cm of the row (z-depth). Purpose: locate the cause;
no pass line. Output: <out>/roof_hole_cause.png and roof_hole_cause.json. scientific_verdict: null"""
import sys, time; from pathlib import Path; T0 = time.monotonic(); OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/out")
import json, numpy as np, shapely
from pathlib import Path
from scipy.spatial import cKDTree
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
FONT='/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(FONT); plt.rcParams['font.family']=fm.FontProperties(fname=FONT).get_name(); plt.rcParams['axes.unicode_minus']=False
PH=Path('/art/phase-payloads/phd'); GT=PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'; FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
O=PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1/concept_v2/case_B0_b10__LoD2'; V2=O/'concept_v2'; STEM='B0_b10__LoD2'
c=json.loads(Path('/docs/config/trainlog_v1.json').read_text()); g=c['scope']['ground_z']; up=np.asarray(c['coordinates']['up'],float); up/=np.linalg.norm(up)
fp=np.asarray(c['scope']['footprint']['coordinates'][0],float)[:,:2]; L=np.linalg.norm(np.diff(fp,axis=0),axis=1); ctr=fp[:-1].mean(0)
row=np.load(GT/'scenes'/STEM/'rows.npz'); X=row['xyz'].astype(float); Nr=row['normal'].astype(float); W=row['wall'].astype(bool); h=X[:,2]-g
ons=[]
for i in range(len(fp)-1):
    t2=(fp[i+1]-fp[i])/max(L[i],1e-9); n2=np.array([t2[1],-t2[0]]); n2=n2 if n2@((fp[i]+fp[i+1])/2-ctr)>0 else -n2; ons.append(n2)
e2=max([i for i,n2 in enumerate(ons) if n2[1]<-.9],key=lambda i:L[i]); a2,b2=fp[e2],fp[e2+1]; os_=ons[e2]
seg=shapely.distance(shapely.linestrings([a2,b2]),shapely.points(X[:,:2])); nh=Nr[:,:2]/np.maximum(np.linalg.norm(Nr[:,:2],axis=1,keepdims=True),1e-9); nn=Nr*np.sign(Nr[:,2:3]+1e-12)
t2=(b2-a2)/L[e2]; span=np.abs((X[:,:2]-(a2+b2)/2)@t2)<=L[e2]/2
m2=~W&(h>8)&(seg<=15)&span&((nh*np.sign(Nr[:,2:3]+1e-12))@os_>.5)&(nn[:,2]>.3)&(nn[:,2]<.95); idx=np.flatnonzero(m2)
on2=nn[m2].mean(0); on2/=np.linalg.norm(on2); al2=np.cross(up,np.r_[os_,0.]); al2/=np.linalg.norm(al2); vd=np.cross(on2,al2); vd=vd if vd@up>0 else -vd
foot2=X[m2].mean(0); P=X[idx]; u=(P-foot2)@al2; v=(P-foot2)@vd; sg=np.sign(Nr[idx]@on2); sg[sg==0]=1
VJ=json.load(open(O/'gtj/views/B0_b10.json'))['views']; R=O/'gtj/renders'
rs=np.load(O/'gtj/scenes'/STEM/'distances/tl_30000.npz')['row_s'][idx]; hole=~np.isfinite(rs); rng=np.random.default_rng(0)
ctrl=np.flatnonzero(~hole); ctrl=rng.choice(ctrl,min(3000,len(ctrl)),replace=False); hsel=np.flatnonzero(hole)
Nn=Nr[idx]*sg[:,None]  # row normal turned to the face normal (outward / up)
def view_stats(n, rows):
    out=[]
    for v in VJ:
        K=np.asarray(v['K']); E=np.asarray(v['W2C']); Pc=(E[:3,:3]@P[rows].T+E[:3,3:4]).T; z=Pc[:,2]; ok=z>.5
        uv=(K@Pc.T).T; u_=uv[:,0]/np.maximum(uv[:,2],1e-9); v_=uv[:,1]/np.maximum(uv[:,2],1e-9); ok&=(u_>=0)&(u_<v['width']-1)&(v_>=0)&(v_<v['height']-1)
        cc=-E[:3,:3].T@E[:3,3]; facing=((cc-P[rows])*Nn[rows]).sum(1)>0; ok&=facing
        if ok.sum()<5: continue
        f=R/f'{STEM}__tl_{n}'/f"{v['index']:04d}.npz"
        if not f.exists(): continue
        d=np.load(f)['depth'][v_[ok].astype(int),u_[ok].astype(int)].astype(float)
        out.append(np.c_[np.full(ok.sum(),v['index']),rows[ok],d,z[ok]])
    return np.concatenate(out) if out else np.zeros((0,4))
a=view_stats(30000,ctrl); vi=a[:,0].astype(int); diff=100*(a[:,2]-a[:,3])
good=[int(k) for k in np.unique(vi) if (vi==k).sum()>=300 and (np.abs(diff[vi==k])<=10).mean()>=.5]
# figure
fig=plt.figure(figsize=(14.5,9.5),dpi=100)
# (a) cross-section across the band at 30,000 (GT, this method mesh cut, Gaussian centres, LoD2 cut)
from matplotlib.collections import LineCollection
hu=np.c_[u,v][hole]; c0=hu.mean(0); w_,V_=np.linalg.eigh(np.cov((hu-c0).T)); bd=V_[:,-1]   # band direction in (u, v)
bd3=bd[0]*al2+bd[1]*vd; bd3/=np.linalg.norm(bd3); ac3=np.cross(on2,bd3); p0=foot2+c0[0]*al2+c0[1]*vd
def sec(Q): r=Q-p0; return r@ac3, r@on2, r@bd3
def cutm(V,F_):
    vv=(V-p0)@bd3; sgn=np.sign(vv[F_]); T=F_[(sgn.min(1)<0)&(sgn.max(1)>0)]; E=[]
    for a,b in [(0,1),(1,2),(2,0)]:
        va,vb=vv[T[:,a]],vv[T[:,b]]; m=(va*vb)<0; w=np.where(m,va/np.where(m,va-vb,1),np.nan); E.append(V[T[:,a]]+w[:,None]*(V[T[:,b]]-V[T[:,a]]))
    E=np.stack(E,1); ok=np.isfinite(E[:,:,0]); k=ok.sum(1)==2; S_=E[k][ok[k]].reshape(-1,2,3); x,y,_=sec(S_); return np.stack([x,y],2)
ax=fig.add_axes([.05,.55,.40,.40])
Gd=np.load(GT/'reference/B0_b10/dense.npz')['xyz'].astype(float); gx,gy,gz=sec(Gd); m=(np.abs(gz)<=.1)&(np.abs(gx)<=4)&(gy>-3)&(gy<1.5); ax.scatter(gx[m],gy[m],s=3,c='#C9C6BC',lw=0,label='참값 점(±10 cm 띠)')
mz=np.load(V2/'meshcol/ours_30000.npz'); sgm=cutm(mz['V'].astype(float),mz['F'].astype('i8')); k=(np.abs(sgm[:,:,0])<=4.5).all(1)&(sgm[:,:,1]>-3.5).all(1)&(sgm[:,:,1]<2).all(1)
ax.add_collection(LineCollection(sgm[k],colors='#1F5FBF',lw=1.2,label='본 방법 메시'))
pr=np.load(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/defs/B0_b10/prior_LoD2.npz'); sgl=cutm(pr['V'].astype(float),pr['F'].astype('i8')); k=(sgl[:,:,0].max(1)>-4)&(sgl[:,:,0].min(1)<4)&(np.abs(sgl[:,:,1])<3).all(1)
ax.add_collection(LineCollection(sgl[k],colors='#E07B00',lw=1.4,linestyles=(0,(4,2)),label='LoD2'))
dz=np.load(V2/'discs/ours_30000.npz'); dx,dy,dw=sec(dz['xyz'].astype(float)); op=dz['opacity']; m=(np.abs(dw)<=.2)&(np.abs(dx)<=4)&(dy>-3)&(dy<1.5)&(op>=.1)
ax.scatter(dx[m],dy[m],s=10,c=op[m],cmap='Purples',vmin=0,vmax=1,edgecolors='#5F5E5A',linewidths=.2,label='가우시안 중심(±20 cm, 불투명도 색)')
hx,hy,hz=sec(P[hole]); mh=np.abs(hz)<=.3; ax.plot([hx[mh].min(),hx[mh].max()],[1.2,1.2],c='#C0392B',lw=4); ax.text(hx[mh].mean(),1.32,'빈 띠',color='#C0392B',ha='center',fontsize=9)
ax.set_xlim(-4,4); ax.set_ylim(-3,1.6); ax.set_aspect('equal'); ax.legend(fontsize=7,loc='lower left'); ax.grid(alpha=.3)
ax.set_xlabel('띠를 가로지르는 방향 m'); ax.set_ylabel('지붕면 법선 방향 m (+ = 위)'); ax.set_title('가: 30,000회 띠를 가로지르는 단면 (1:1)',loc='left',fontsize=11)
# (b) local normal bend
Tp=cKDTree(P); bend=np.array([np.degrees(np.arccos(np.clip(np.abs(Nr[idx][Tp.query_ball_point(P[i],.5)]@Nr[idx][i]),0,1))).max() for i in range(len(P))])
ax=fig.add_axes([.53,.55,.40,.40]); sc=ax.scatter(u,v,s=2,c=np.clip(bend,0,30),cmap='magma_r',lw=0); ax.scatter(u[hole][::2],v[hole][::2],s=3,c='#1F5FBF',lw=0,zorder=3)
ax.set_aspect('equal'); fig.colorbar(sc,ax=ax,fraction=.03,label='0.5 m 안 참값 법선 최대 각 (°)'); ax.set_title('나: 실제 지붕이 꺾이는 곳(진할수록 꺾임) · 파란 점 = 빈 띠',loc='left',fontsize=11); ax.set_xlabel('변 방향 m'); ax.set_ylabel('경사 위로 m')
# (c) render sees through
FRc=[0,100,300,1000,2000,3000,5000,7000,15000,30000]; rr={}
for n in FRc:
    for nm,rows in (('hole',hsel),('ctrl',ctrl)):
        b=view_stats(n,rows); b=b[np.isin(b[:,0].astype(int),good)]; d,z=b[:,2],b[:,3]; okd=d>0; df=100*(d-z); rr[(n,nm)]=(100*(okd&(np.abs(df)<=10)).mean(),100*(okd&(df>30)).mean())
ax=fig.add_axes([.05,.07,.40,.36]); it=np.arange(len(FRc))
for nm,col,lab in (('hole','#C0392B','빈 띠'),('ctrl','#77756D','나머지 지붕')):
    ax.plot(it,[rr[(n,nm)][1] for n in FRc],'o-',c=col,label=f'{lab}: 렌더 깊이가 실제 면보다 30 cm 넘게 뒤 %'); ax.plot(it,[rr[(n,nm)][0] for n in FRc],'s--',c=col,label=f'{lab}: ±10 cm 안 %')
ax.set_xticks(it); ax.set_xticklabels([f'{n:,}' for n in FRc],rotation=45,fontsize=8); ax.set_ylim(0,100); ax.legend(fontsize=7.5,loc='upper right'); ax.grid(alpha=.3)
ax.set_title(f'다: 이 면이 보이는 시점 {len(good)}개에서 렌더 깊이 (가림 없음 = 뒤가 비쳐 보임)',loc='left',fontsize=11)
# (d) disc offsets at 300 / 30000
for col_i,n in enumerate((300,30000)):
    dz=np.load(V2/'discs'/f'ours_{n}.npz'); xyz=dz['xyz'].astype(float); op=dz['opacity'].astype(float); du=(xyz-foot2)@al2; dv=(xyz-foot2)@vd; dn=(xyz-foot2)@on2
    j=cKDTree(np.c_[u,v]).query(np.c_[du,dv])[1]; off=dn-((P[j]-foot2)@on2)
    ax=fig.add_axes([.53,.07+(1-col_i)*.25,.40,.17])
    for nm,T,colr in (('빈 띠',cKDTree(np.c_[u,v][hole]),'#C0392B'),('나머지 지붕',cKDTree(np.c_[u,v][~hole]),'#77756D')):
        dd,_=T.query(np.c_[du,dv]); m=(dd<=.35)&(np.abs(off)<=3)&(op>=.1); ax.hist(100*off[m],bins=np.arange(-300,101,10),density=True,histtype='step',color=colr,lw=1.6,label=f'{nm} ({int(m.sum())}개)')
    ax.axvline(0,c='#3E9E6B'); ax.set_xlabel('가우시안 중심이 실제 지붕면에서 떨어진 거리 cm (+ = 위)'); ax.legend(fontsize=8); ax.set_title(f'라-{col_i+1}: {n:,}회 가우시안 (불투명도 ≥ 0.1, 면 위 0.35 m 안)',loc='left',fontsize=11); ax.set_yticks([])
fig.savefig(OUT/'roof_hole_cause.png',facecolor='white')


# numbers
FR=[0,100,300,1000,2000,3000,5000,7000,10000,15000,30000]; Dn={n:np.load(O/'gtj/scenes'/STEM/'distances'/f'tl_{n}.npz')['row_s'].astype(float)[idx]*sg*100 for n in FR}
tg=np.load(FT/'targets'/f'{STEM}.npz'); dd,ii=cKDTree(tg['centre']).query(P); okt=dd<=1.; JN={0:'일치',2:'보정',1:'보존',4:'결측'}
toff=100*((tg['target'][ii]-P)*(Nr[idx]*sg[:,None])).sum(1); mp=row['mvs_presence'][idx]; md=row['mvs_distance_m'][idx]; pd_=row['prior_distance_m'][idx]
grp={}
for nm,m in (('hole',hole),('rest',~hole)):
    j=ii[m&okt]
    grp[nm]=dict(rows=int(m.sum()),height_median_m=round(float(np.median(h[idx][m])),2),mvs_present_pct=round(100*float(mp[m].mean()),1),mvs_distance_median_cm=round(100*float(np.median(md[m&mp])),1),
        lod2_distance_median_cm=round(100*float(np.nanmedian(pd_[m])),1),judgment_pct_nearest_target_1m={JN.get(int(k),str(int(k))) if k>=0 else 'none':round(100*float((np.where(okt,tg['judge_region'][ii],-1)[m]==k).mean()),1) for k in np.unique(np.where(okt,tg['judge_region'][ii],-1)[m])},
        target_sigma_median_m=round(float(np.median(tg['target_sigma_m'][j])),3),target_offset_cm_q10_50_90=[round(float(x),1) for x in np.percentile(toff[m&okt],[10,50,90])],
        target_normal_alignment_median=round(float(np.median(np.abs((tg['normal'][j]*Nr[idx][m&okt]).sum(1)))),3),gt_normal_bend_0p5m_median_deg=round(float(np.median(bend[m])),1),
        surface_pct_by_iteration={str(n):round(100*float(np.isfinite(Dn[n][m]).mean()),1) for n in FR},median_cm_by_iteration={str(n):(round(float(np.nanmedian(Dn[n][m])),1) if np.isfinite(Dn[n][m]).any() else None) for n in FR},
        render_depth_good_views={str(n):dict(within_10cm_pct=round(rr[(n,'hole' if nm=='hole' else 'ctrl')][0],1),behind_30cm_pct=round(rr[(n,'hole' if nm=='hole' else 'ctrl')][1],1)) for n in FRc})
c2=np.load(V2/'gtj/scenes'/STEM/'distances/cmp_2dgs_30000.npz')['row_s'].astype(float)[idx]
json.dump(dict(face=dict(rule='w2 roof face rule (cv2_frames.py W2)',rows=int(len(idx)),edge=int(e2)),hole=dict(definition='face rows with no surface at 30,000 (tl_30000 row_s NaN)',rows=int(hole.sum()),pct=round(100*float(hole.mean()),1)),
    groups=grp,comparison_2dgs_30000_at_hole=dict(no_surface_pct=round(100*float((~np.isfinite(c2[hole])).mean()),1)),good_views=good,control_rows=int(len(ctrl)),
    band_section=dict(direction_uv=[float(x) for x in bd],centre_uv=[float(x) for x in c0]),seconds=round(time.monotonic()-T0,1),scientific_verdict=None),
    open(OUT/'roof_hole_cause.json','w'),ensure_ascii=False,indent=1)
print('ROOFHOLE done',round(time.monotonic()-T0,1))
