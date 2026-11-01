"""Frozen B173 section with inputs, saved centres and measured mesh first hits."""
import numpy as np
from common import *
from report_stage0 import plt,save

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def main():
    rep=next(r for r in json.loads((CFG/'representatives_v1.json').read_text())['rows'] if r['id']==1)
    for prior in ['ALS','LoD2']:
        run=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';post=run/'post7000'
        if not (post/'score.json').exists():continue
        t=loadz(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');z=loadz(post/'patch_z.npz')
        lt=PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1';e=loadz(lt/'direct_stage1_v2'/f'B173nb_b10__{prior}'/'evaluation.npz')
        baseline_path=lt/'patch_z'/f'B173nb_b10__{prior}__nojudge_{prior}_s0.npz';baseline=loadz(baseline_path)
        s=loadz(run/'model/target_monitor/snapshot_7000.npz');zero=loadz(run/'model/target_monitor/snapshot_0.npz')
        a,b=np.asarray(rep['start']),np.asarray(rep['end']);direction=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a)
        def crop(x):
            q=x[:,:2]-a;dist=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);return dist,(dist>=0)&(dist<=length)&(off<=rep['half_width'])
        dist,mask=crop(t['centre']);mask&=(t['kind']==1)&(t['region']>=0)&e['scoring_allowed']
        gt=t['centre'][:,2]+e['p_gt']*t['normal'][:,2];mvs=t['centre'][:,2]+t['d']*t['normal'][:,2]
        mesh=t['centre'][:,2]+z['z']*t['normal'][:,2];base=t['centre'][:,2]+baseline['z']*t['normal'][:,2]
        bounds=np.concatenate([gt[mask],mvs[mask],t['centre'][mask,2],t['target'][mask,2]]);bounds=bounds[np.isfinite(bounds)]
        limits=[float(bounds.min()-1),float(bounds.max()+1)];fig,axes=plt.subplots(1,3,figsize=(14,4.5))
        for ax in axes:
            ax.scatter(dist[mask],gt[mask],s=8,c='black',label='참값')
            ax.errorbar(dist[mask],t['target'][mask,2],yerr=1.96*t['sigma'][mask]*abs(t['normal'][mask,2]),fmt='.',ms=2,
                c='gray',alpha=.35,label='목표 ±1.96σ')
            ax.set(xlabel='고정 단면 거리 (m)',ylim=limits,xlim=(0,length))
        axes[0].scatter(dist[mask],t['centre'][mask,2],s=5,c='#e6ab42',label='사전 정보')
        axes[0].scatter(dist[mask],mvs[mask],s=4,c='#478ac3',label='MVS')
        dz,mz=crop(zero['xyz']);dz7,m7=crop(s['xyz'])
        for tag,label,col in [(0,'배경','#61a8a7'),(1,'패치','#a94e83'),(2,'풀림','#e09c36')]:
            before=mz&(zero['target_tag']==tag);after=m7&(s['target_tag']==tag)
            if before.any():axes[1].scatter(dz[before],zero['xyz'][before,2],s=9,marker='+',c=col,alpha=.4,label='0회 '+label)
            axes[1].scatter(dz7[after],s['xyz'][after,2],s=3,c=col,label='7,000회 '+label)
        axes[2].scatter(dist[mask],base[mask],s=6,c='#50a27a',label='기존 깊이 기준선 첫 면')
        oldz=loadz(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/post7000/patch_z.npz')
        oldmesh=t['centre'][:,2]+oldz['z']*t['normal'][:,2]
        axes[2].scatter(dist[mask],oldmesh[mask],s=5,c='#888888',label='r4n 7,000회 첫 면')
        axes[2].scatter(dist[mask],mesh[mask],s=6,c='#c95b4f',label='7,000회 메시 첫 면')
        for ax,title in zip(axes,['고정 입력과 목표','초기와 7,000회 중심','채점한 메시의 첫 면']):ax.set_title(title);ax.legend(fontsize=6,loc='upper right')
        axes[0].set_ylabel('지역 높이 (m)');fig.subplots_adjust(top=.81,bottom=.19,wspace=.2)
        val=dict(prior=prior,representative=rep,patches=int(mask.sum()),height_limits_m=limits,
            saved_centres_in_section=int(m7.sum()),saved_centres_outside_height=int((m7&((s['xyz'][:,2]<limits[0])|(s['xyz'][:,2]>limits[1]))).sum()),
            mesh_patch_z_sha256=sha(post/'patch_z.npz'),baseline_patch_z_path=str(baseline_path),baseline_sha256=sha(baseline_path),
            reference='unchanged scorer p_gt; separate from stage0 gt_med',unavailable=['iteration30000','direct_target_mesh'])
        save(fig,f'r6_{prior}_section_comparison',f'B173 날개 · {prior}: 목표, 중심과 메시 첫 면을 같은 단면에 놓았다',val,
            '폭 1.2 m 고정 · 높이 범위는 입력으로 정함 · 첫 면은 사전 패치 법선 채점점 · 30,000회·목표 직접 메시 없음')
        eligible=e['in_eval']&e['scoring_allowed'];fig,axes=plt.subplots(1,3,figsize=(15,5))
        for ax,label,sel in [(axes[0],'r4n 결과',oldz['category']==0),(axes[1],'r6 결과',z['category']==0),(axes[2],'목표 점 자체',abs(t['h']-e['p_gt'])<=e['tau'])]:
            ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],c=np.where(sel[eligible],'#55a577','#c95d55'),s=.7)
            ax.set_aspect('equal');ax.set(title=label,xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)')
        fig.subplots_adjust(top=.8,bottom=.18,wspace=.25)
        save(fig,f'r6_{prior}_within_tau',f'{prior}: 같은 평가 패치에서 결과와 목표의 τ 안 여부를 비교했다',
            json.loads((post/'score.json').read_text())['result_vs_target'],'초록: τ 안 · 빨강: τ 밖 또는 결과 면 없음 · 상세 원값/대체/영역별 넓이는 표에 기록')
        fig,axes=plt.subplots(1,2,figsize=(11,5));attributions=[]
        for ax,revision,folder in [(axes[0],'r4n',OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/post7000'),(axes[1],'r6',post)]:
            a=loadz(folder/'origin_attribution.npz');floating=eligible&(a['category']==1);seen=a['views']>0
            labels=np.full(len(eligible),3,np.int8);f=a['mean_fraction']
            if revision=='r4n':
                labels[seen&(f[:,0]>=.5)]=0;labels[seen&(f[:,2]>=.5)]=1
            else:
                labels[seen&(f[:,0]>=.5)]=0;labels[seen&(f[:,2]>=.5)]=1;labels[seen&(f[:,1]>=.5)]=2
            ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],s=.4,c='#dddddd')
            for label,col,word in [(0,'#61a8a7','배경 우세'),(1,'#a94e83','패치 우세'),(2,'#e09c36','풀림 우세'),(3,'#444444','혼합 또는 확인 불가')]:
                m=floating&(labels==label);ax.scatter(t['centre'][m,0],t['centre'][m,1],s=2,c=col,label=word)
            ax.set_aspect('equal');ax.set(title=revision,xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)');ax.legend(fontsize=6)
            attributions.append(dict(revision=revision,floating_patches=int(floating.sum()),counts={str(k):int((floating&(labels==k)).sum()) for k in range(4)},source_sha256=sha(folder/'origin_attribution.npz')))
        fig.subplots_adjust(top=.81,bottom=.19,wspace=.2)
        save(fig,f'r6_{prior}_floating_origin',f'{prior}: 뜬 면 첫 면의 렌더 기여 출신',attributions,'같은 평가 위치 · 우세: 보이는 영상 평균 렌더 기여 ≥0.5 · 가우시안 최대 기여 화소표와 별개')
    print('SECTION7000_REPORT' ,flush=True)

if __name__=='__main__':main()
