"""Fixed r6 camera/section/color ranges, with r6 and matched-iteration baseline comparators."""
import numpy as np
from common import *
from report_stage0 import plt,save
from report_movement_r7 import loadz,read
def main():
    rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);camera=rep['camera']['name']
    for prior in ['ALS','LoD2']:
        run=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7';old=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';base=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0'
        t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');s=loadz(run/'model/target_monitor/snapshot_7000.npz');zero=loadz(run/'model/target_monitor/snapshot_0.npz');e=loadz(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'B173nb_b10__{prior}/evaluation.npz')
        posts=[base/'post7000',old/'post7000',run/'post7000'];zs=[loadz(p/'patch_z.npz') for p in posts];names=['기존 방법 7,000회','r6 7,000회','r7 7,000회']
        a,b=np.array(rep['start']),np.array(rep['end']);direction=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a)
        def crop(x):
            q=x[:,:2]-a;d=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);return d,(d>=0)&(d<=length)&(off<=rep['half_width'])
        d,sel=crop(t['centre']);roof=sel&(t['kind']==1)&e['scoring_allowed'];limits=read(DOC/'figures'/f'r6_{prior}_section_comparison.json')['values']['height_limits_m']
        gt=t['centre'][:,2]+e['p_gt']*t['normal'][:,2];mvs=t['centre'][:,2]+t['d']*t['normal'][:,2]
        fig,axes=plt.subplots(1,3,figsize=(14,4.5))
        for ax in axes:
            ax.scatter(d[roof],gt[roof],s=8,c='black',label='참값')
            ax.errorbar(d[roof],t['target'][roof,2],yerr=1.96*t['sigma'][roof]*abs(t['normal'][roof,2]),fmt='.',ms=2,c='gray',alpha=.35,label='목표 ±1.96σ')
            ax.set(xlabel='고정 단면 거리 (m)',ylim=limits,xlim=(0,length))
        axes[0].scatter(d[sel],t['centre'][sel,2],s=5,c='#e6ab42',label='사전 지붕·벽');axes[0].scatter(d[roof],mvs[roof],s=4,c='#478ac3',label='MVS 지붕')
        # Wall point samples are drawn directly; a vertical normal-height plot cannot locate a wall in XY.
        for filename,color,label in [('gt_xyz.npy','black','참값 점'),('mvs_a_xyz.npy','#478ac3','MVS 점')]:
            points=np.load(UN/'points/B173nb_b10'/filename,mmap_mode='r');dd,mask=crop(points);ids=np.flatnonzero(mask);ids=ids[::max(1,len(ids)//4000)];axes[0].scatter(dd[ids],points[ids,2],s=.5,c=color,alpha=.3,label=label)
        dz,mz=crop(zero['xyz']);ds,ms=crop(s['xyz'])
        for tag,label,color in [(0,'배경','#61a8a7'),(1,'패치','#a94e83'),(2,'풀림','#e09c36')]:
            before=mz&(zero['target_tag']==tag);after=ms&(s['target_tag']==tag)
            if before.any():axes[1].scatter(dz[before],zero['xyz'][before,2],s=9,marker='+',c=color,alpha=.4,label='0회 '+label)
            axes[1].scatter(ds[after],s['xyz'][after,2],s=3,c=color,label='7,000회 '+label)
        for z,name,color in zip(zs,names,['#50a27a','#888888','#c95b4f']):axes[2].scatter(d[roof],(t['centre'][:,2]+z['z']*t['normal'][:,2])[roof],s=6,c=color,label=name+' 첫 면')
        for ax,title in zip(axes,['고정 입력과 목표','r7 초기와 7,000회 중심','채점한 메시의 첫 면']):ax.set_title(title);ax.legend(fontsize=6,loc='upper right')
        axes[0].set_ylabel('지역 높이 (m)');fig.subplots_adjust(top=.81,bottom=.19,wspace=.2)
        save(fig,f'r7_{prior}_section_comparison',f'B173 날개 · {prior}: 같은 단면의 목표·중심·첫 면',dict(prior=prior,representative=rep,height_limits_m=limits,patch_z_sha256=[sha(p/'patch_z.npz') for p in posts],saved_centres_in_section=int(ms.sum()),saved_centres_outside_height=int((ms&((s['xyz'][:,2]<limits[0])|(s['xyz'][:,2]>limits[1]))).sum())),'폭 1.2 m · r6와 같은 높이 범위 · 벽은 입력 점과 중심으로 표시 · 사라짐에는 목표 없음')
        eligible=e['in_eval']&e['scoring_allowed'];fig,axes=plt.subplots(1,3,figsize=(14,4.5));target_ok=abs(t['h']-e['p_gt'])<=e['tau']
        for ax,ok,name in zip(axes,[z['category']==0 for z in zs],names):
            colors=np.where(ok,'#55a577','#c95d55');colors=np.where((t['region']==5)&(name=='r7 목표 자체'),'#cccccc',colors);ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],c=colors[eligible],s=.7);ax.set_aspect('equal');ax.set(title=name,xlabel='동쪽 (m)',ylabel='북쪽 (m)')
        fig.subplots_adjust(top=.8,bottom=.18,wspace=.28);save(fig,f'r7_{prior}_within_tau',f'{prior}: 같은 평가 패치의 τ 안 여부',read(run/'post7000/score.json')['result_vs_target'],'초록 τ 안 · 빨강 τ 밖 또는 면 없음 · 세 결과 모두 같은 평가 패치')
        fig,axes=plt.subplots(1,3,figsize=(14,4.5));attrs=[]
        for ax,post,name in zip(axes,posts,names):
            z=loadz(post/'patch_z.npz');floating=eligible&(z['category']==1);labels=np.full(len(eligible),3,np.int8)
            if (post/'origin_attribution.npz').exists():
                att=loadz(post/'origin_attribution.npz');f=att['mean_fraction'];seen=att['views']>0
                for code,ch in [(0,0),(1,2),(2,1)]:labels[seen&(f[:,ch]>=.5)]=code
            ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],s=.4,c='#dddddd')
            for code,color,label in [(0,'#61a8a7','배경 우세'),(1,'#a94e83','패치 우세'),(2,'#e09c36','풀림 우세'),(3,'#444444','혼합·확인 불가')]:
                mask=floating&(labels==code);ax.scatter(t['centre'][mask,0],t['centre'][mask,1],s=2,c=color,label=label)
            ax.set_aspect('equal');ax.set(title=name,xlabel='동쪽 (m)',ylabel='북쪽 (m)');ax.legend(fontsize=6);attrs.append(dict(method=name,floating_patches=int(floating.sum()),counts={str(k):int((floating&(labels==k)).sum()) for k in range(4)},baseline_lineage_unavailable=not (post/'origin_attribution.npz').exists()))
        fig.subplots_adjust(top=.8,bottom=.2,wspace=.25);save(fig,f'r7_{prior}_floating_origin',f'{prior}: 뜬 면과 렌더 기여 출신',attrs,'우세: 보이는 영상 평균 기여 ≥0.5 · 기존 방법은 계보가 없어 검정 · 화소 최대 기여 표와 별개')
        renders=[loadz(root/'model/check7000/renders'/f'{camera}.npz') for root in [base,old,run]];photo=loadz(OUT/'r2/preflight'/f'B173nb_b10_{prior}'/f'{camera}.npz')['photo_rgb'].transpose(1,2,0)
        for suffix,select,titles in [('fixed_render',[1,2],['r6 7,000회','r7 7,000회']),('fixed_render_baseline',[0,2],['기존 방법 7,000회','r7 7,000회'])]:
            fig,axes=plt.subplots(1,3,figsize=(12,4))
            for ax,im,label in zip(axes,[photo]+[renders[i]['rgb'] for i in select],['원본 사진']+titles):ax.imshow(im);ax.set_title(label);ax.axis('off')
            fig.subplots_adjust(top=.82,bottom=.15,wspace=.03);save(fig,f'r7_{prior}_{suffix}',f'{prior}: 같은 고정 영상의 렌더',dict(camera=camera,render_sha256=[sha(root/'model/check7000/renders'/f'{camera}.npz') for root in [base,old,run]]),'같은 카메라·해상도 · 저장 모델 모두 7,000회')
        maps=OUT/'r7/stage1'/f'B173nb_b10_{prior}/maps';m=loadz(maps/f'{camera}.npz');meta=read(maps/'index.json')['views'][camera];owner=m['owner'];has=owner>=0;j=np.maximum(owner,0);K=np.array(meta['K']);inv=np.linalg.inv(np.array(meta['W2C']));vv,uu=np.indices(owner.shape)
        def height(arr):
            dd=arr['depth'];q=np.stack([(uu-K[0,2])/K[0,0]*dd,(vv-K[1,2])/K[1,1]*dd,dd,np.ones_like(dd)],-1);world=(q.reshape(-1,4)@inv.T)[:,:3].reshape(*owner.shape,3);h=((world-t['centre'][j])*t['normal'][j]).sum(2);h[~has|~np.isfinite(dd)|(dd<=0)]=np.nan;return h
        for suffix,select,titles in [('fixed_height',[1,2],['r6 7,000회','r7 7,000회']),('fixed_height_baseline',[0,2],['기존 방법 7,000회','r7 7,000회'])]:
            fig,axes=plt.subplots(1,3,figsize=(12,4))
            for ax,arr,label in zip(axes,[np.where(has,t['h'][j],np.nan)]+[height(renders[i]) for i in select],['r7 목표']+titles):im=ax.imshow(arr,cmap='coolwarm',vmin=-5,vmax=5);ax.set_title(label);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.04,extend='both')
            fig.subplots_adjust(top=.8,bottom=.2,wspace=.15);save(fig,f'r7_{prior}_{suffix}',f'{prior}: 같은 사전 패치 법선의 높이 h',dict(camera=camera,h_color_range_m=[-5,5],owner_map_sha256=sha(maps/f'{camera}.npz')),'r6와 같은 −5~5 m 색 범위 · r7 원반 소유 패치로 역투영 · 사라진 원반은 빈칸')
    print('SECTION_REPORT_R7_COMPLETE',flush=True)
if __name__=='__main__':main()
