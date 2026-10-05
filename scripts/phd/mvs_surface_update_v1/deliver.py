"""Inspectable stage-by-stage results and mobile figures from frozen probes."""
import argparse
import hashlib
import json
import shutil
import textwrap
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def write(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
def metric(name,value,unit=''): return dict(name=name,value=value,unit=unit)


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True);ap.add_argument('--font',type=Path,required=True);ap.add_argument('--name',default='review');a=ap.parse_args()
    out=a.attempt/a.name;out.mkdir(exist_ok=False)
    prep=a.attempt/'prepare_v2';cases=read(prep/'cases.json');parent=read(prep/'receipt.json')
    assert sha(prep/'cases.json')==parent['cases_sha256']
    for record in parent['outputs']:
        assert sha(prep/record['path'])==record['sha256'],record['path']
    data=dict(task_id=cases['task_id'],scientific_verdict=None,
        summary='같은 7×7 표본의 불일치 → 두 3D 가설 → 동일 이웃의 보임·사진·깊이곡선 → 국소 Gaussian 수정 → 주변 영향. 고정 Anchor8k의 기술 비교입니다.',
        regions=[],receipts=[dict(label='사례·입력 계보',path='../prepare_v2/receipt.json'),dict(label='고정 판정·수정 정책',path='../prepare_v2/config.json')])
    allrows=[];pdfpages=[];walkthrough=[];fnt=ImageFont.truetype(str(a.font),28);small=ImageFont.truetype(str(a.font),21)
    roles={'best_supported_candidate_or_abstain':'수정 근거 후보','ambiguous_candidate':'모호성·유보 사례','agree_control':'깊이 일치 대조'}
    for region in cases['regions']:
        rid=region['id'];probe=a.attempt/'probe'/rid;receipt=read(probe/'receipt.json')
        assert receipt['status']=='PASS_BOUNDED_INFERENCE_DIAGNOSTIC' and receipt['cases_sha256']==sha(prep/'cases.json')
        for rel,digest in receipt['output_sha256'].items():
            assert sha(probe/rel)==digest,rel
        data['receipts'].append(dict(label=rid+' 실제 Gaussian 비교 기록',path=f'../probe/{rid}/receipt.json'))
        reference_dir=a.attempt/'reference'/rid
        reference_receipt=None
        if (reference_dir/'receipt.json').exists():
            reference_receipt=read(reference_dir/'receipt.json')
            assert reference_receipt['status']=='PASS_REFERENCE_DIAGNOSTIC'
            assert reference_receipt['scientific_verdict'] is None
            assert reference_receipt['cases_sha256']==sha(prep/'cases.json')
            assert reference_receipt['probe_receipt_sha256']==sha(probe/'receipt.json')
            for rel,digest in reference_receipt['output_sha256'].items():
                assert sha(reference_dir/rel)==digest,rel
            data['receipts'].append(dict(label=rid+' 현재 UAS 평가 계보',path=f'../reference/{rid}/receipt.json'))
        rr=dict(id=rid,cases=[])
        for c in region['cases']:
            cid=c['id'];result=read(probe/cid/'result.json');folder=out/cid;folder.mkdir()
            baseprefix=f'../prepare_v2/{cid}/';proberel=f'../probe/{rid}/{cid}/'
            checks=c['checks'];fail=c['reason_codes'];stats=c['profile_stats'];ev=c['neighbor_evidence']
            fig,ax=plt.subplots(figsize=(10,5));ax.axis('off')
            table=[[k,'YES' if v else 'NO'] for k,v in checks.items()]
            table.append(['both hypotheses inside regional XY','NO' if 'different_surface_or_outside_region_xy' in fail else 'YES'])
            artist=ax.table(cellText=table,colLabels=['Frozen technical admission check','Result'],loc='center',cellLoc='left',colWidths=[.8,.2]);artist.auto_set_font_size(False);artist.set_fontsize(10);artist.scale(1,1.65)
            ax.set_title(c['decision']+'\nNot a calibrated source-authority or temporal-change verdict');fig.tight_layout();fig.savefig(folder/'06_decision.png',dpi=140);plt.close(fig)
            with np.load(probe/cid/'association_and_intervention.npz') as f: assoc={k:f[k] for k in f.files}
            before=assoc['xyz_before'];after=assoc['xyz_after'];origin=np.array(c['prior_xyz_world']);candidate=assoc['candidate_xyz_before']
            fig=plt.figure(figsize=(10,4));ax=fig.add_subplot(121,projection='3d')
            if len(candidate):
                q=candidate-origin;ax.scatter(q[:,0],q[:,1],q[:,2],color='gray',s=12,label='association candidates')
            for points,color,label in [(np.asarray(c['prior_patch_world'],float),'#2563eb','Prior patch'),(np.asarray(c['mvs_patch_world'],float),'#d97706','MVS patch'),(before,'black','GS before'),(after,'red','GS after')]:
                if len(points):q=points-origin;ax.scatter(q[:,0],q[:,1],q[:,2],c=color,s=14,label=label)
            ax.set(xlabel='local X offset (m)',ylabel='local Y offset (m)',zlabel='local Z offset (m)');ax.legend(fontsize=7)
            ax=fig.add_subplot(122)
            if len(before):
                delta=after-before;ax.bar(np.arange(len(delta)),np.linalg.norm(delta,axis=1),color='#008c83');ax.set_ylim(0,.11)
            else:ax.text(.5,.5,'NO GAUSSIAN UPDATE',ha='center',va='center',transform=ax.transAxes)
            ax.set(xlabel='applied Gaussian order (exact IDs in NPZ)',ylabel='actual displacement (m)',title=f'{result["changed_ids"]} changed / {result["selected_ids"]} associated')
            fig.suptitle('Actual immutable-checkpoint Gaussian association and bounded center change');fig.tight_layout();fig.savefig(folder/'07_gaussians.png',dpi=140);plt.close(fig)
            rawpath=probe/cid/'view_00/raw.npz'
            with np.load(rawpath) as f: raw={k:f[k] for k in f.files}
            x0,y0,x1,y1=c['display_bbox'];crop=np.s_[y0:y1,x0:x1];target=raw['target_mask'][crop]
            fig,axes=plt.subplots(2,3,figsize=(11,7))
            photo=raw['photo'];rgb0=raw['rgb_before'];rgb1=raw['rgb_after'];e=np.mean(np.abs(rgb1-photo),2)-np.mean(np.abs(rgb0-photo),2)
            for ax,arr,title in zip(axes[0],[photo,rgb0,rgb1],['Current photo','GS before','GS after']):
                ax.imshow(np.clip(arr[crop],0,1));ax.contour(target.astype(float),levels=[.5],colors=['lime'],linewidths=.6);ax.set_title(title);ax.axis('off')
            d0,d1=raw['depth_before'],raw['depth_after'];valid=(raw['alpha_before']>=.5)&(raw['alpha_after']>=.5)&(d0>0)&(d1>0)
            for ax,arr,limit,title in [(axes[1,0],e,.02,'Photo error change: blue improves / red worsens'),(axes[1,1],np.where(valid,d1-d0,np.nan),.1,'Expected depth change (m)'),(axes[1,2],raw['alpha_after']-raw['alpha_before'],.1,'Alpha change')]:
                im=ax.imshow(arr[crop],vmin=-limit,vmax=limit,cmap='coolwarm');ax.contour(target.astype(float),levels=[.5],colors=['lime'],linewidths=.6);ax.set_title(title,fontsize=9);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.04)
            fig.suptitle(f'{cid}: {result["status"]}; 7x7 fixed target marked green');fig.tight_layout();fig.savefig(folder/'08_before_after.png',dpi=150);plt.close(fig)
            fig,axes=plt.subplots(1,2,figsize=(11,4))
            for domain,color in [('target','#008c83'),('surrounding','#b95b14'),('outside','#677580')]:
                photo_d=[v['metrics'][domain].get('photo_mae_delta',np.nan) for v in result['views']]
                depth_d=[v['metrics'][domain].get('depth_abs_change_max_m') for v in result['views']]
                axes[0].plot(range(len(photo_d)),photo_d,'o-',label=domain,color=color)
                axes[1].plot(range(len(depth_d)),[x if x is not None else np.nan for x in depth_d],'o-',label=domain,color=color)
            axes[0].axhline(0,c='black',lw=.5);axes[0].set(xlabel='view ID (0 reference)',ylabel='after minus before RGB MAE',title='All fixed views; negative improves')
            axes[1].set(xlabel='view ID (0 reference)',ylabel='max paired depth change (m)',title='Change is not independent geometry accuracy')
            for ax in axes:ax.legend()
            fig.tight_layout();fig.savefig(folder/'08_all_views.png',dpi=140);plt.close(fig)
            stages=[
                dict(title='불일치 후보',summary=f'같은 RGB 광선의 두 깊이 차이입니다. 확대 그림의 녹색 7×7 패치만 이 사례의 관측 근거입니다. Prior {c["prior_depth"]:.3f}m / MVS {c["mvs_depth"]:.3f}m.',images=[dict(src=baseprefix+'01_inputs.png',label='원사진·두 깊이·깊이차')],metrics=[metric('Prior−MVS',c['prior_depth']-c['mvs_depth'],'m')]),
                dict(title='두 3D 표면 가설',summary='같은 픽셀에 대한 두 원자료 가설입니다. 강제로 한 표면으로 합치지 않았습니다. 위치·기울기 차이와 영역 밖 대응을 확인합니다.',images=[dict(src=baseprefix+'02_surfaces.png',label='실제 7×7 패치의 3D 점과 X–Z 투영')]),
                dict(title='가시성·비교 가능 관측',summary='Prior 자체와 MVS 자체의 깊이 앞뒤 관계와 일치를 각각 검사합니다. 실제 가시성을 확정하는 검사는 아닙니다. Prior→MVS는 별도 충돌 정보이며 Prior 배제 기준으로 사용하지 않습니다. 같은 이웃 ID에서 사진·가시성·비용곡선·시차 지원을 모읍니다.',images=[dict(src=baseprefix+'03_visibility.png',label='이웃별 원 상태 코드')],metrics=[metric('결박 이웃 수',len(ev)),metric('동일 이웃에서 비교 가능한 관측',sum(x['admitted'] for x in ev))]),
                dict(title='다중 시점 사진 지지',summary='동일한 원패치와 원픽셀을 비교합니다. MVS를 반대하는 비교 가능 이웃도 비용곡선 계산에 남겼습니다. 사진 비용은 정확도 확정값이 아닙니다.',images=[dict(src=baseprefix+'04_patches.png',label='이웃별 원패치와 두 가설 재투영')],metrics=[metric('MVS 방향 지지 이웃',sum(x['supports_mvs'] for x in ev)),metric('MVS 방향 반대 이웃',sum(x['opposes_mvs'] for x in ev))]),
                dict(title='대응 모호성',summary='검사를 통과한 같은 이웃들로 비용곡선을 다시 계산했습니다. 검정선이 최종 관측 곡선입니다. 폭 0은 한 깊이 격자점이며, 격자 간격과 탐색 끝까지 함께 확인합니다.',images=[dict(src=baseprefix+'05_profile.png',label='이웃별 비용과 재계산한 깊이 비용곡선')],metrics=[metric('최저 사진 비용',stats['cost']),metric('낮은 비용 구간 폭',stats['width'],'m'),metric('깊이 격자 간격',stats['spacing'],'m'),metric('낮은 비용 구간 수',stats['modes']),metric('최저점 깊이',stats['best'],'m')]),
                dict(title='국소 표면 패치의 종합 판정',summary='개발용 국소 시험을 허용할지 판정한 결과입니다. 실제 변화·기하 정확도 또는 전체 지붕의 수정 허가를 뜻하지 않습니다. 일치 대조도 독립적으로 올바른 표면이라는 뜻은 아닙니다.',images=[dict(src=f'{cid}/06_decision.png',label='각 기준의 통과·미통과와 최종 동작')],metrics=[metric('판정',c['decision']),metric('유보/미충족 이유',fail)]),
                dict(title='실제 Gaussian 연결과 수정',summary='고정 Anchor8k의 깊이와 실제 렌더링 기여로 연결 가능성을 검사했습니다. '+('관련 Gaussian을 수정하지 않고 동일한 상태를 비교했습니다.' if result['changed_ids']==0 else '선택된 중심만 최대 0.1m 이동한 별도 상태입니다. 다른 Gaussian도 함께 렌더링해 가림과 주변 영향을 측정했습니다.')+' 원본 checkpoint와 중심 이외 파라미터는 그대로입니다.',images=[dict(src=f'{cid}/07_gaussians.png',label='표면 가설·실제 Gaussian·이동량'),dict(src=proberel+'selected_contribution.png',label='선택 Gaussian의 수정 전 실제 영상 기여')],metrics=[metric('기하·기여 후보 수',result['geometric_and_contribution_candidates']),metric('국소 연결 Gaussian 수',result['selected_ids']),metric('실제 바뀐 Gaussian 수',result['changed_ids']),metric('대상 alpha 기여 비율',result['selected_target_alpha_fraction']),metric('최대 실제 이동',result['actual_max_displacement_m'],'m'),metric('연결 단계 유보 이유',result['association_reasons'])]),
                dict(title='수정 전후 형상·영상·주변 영향',summary='동일 checkpoint와 동일한 대상·주변·외부 측정 창을 비교했습니다. 모든 결박 이웃의 결과를 표시합니다. 색척도 밖 변화는 포화되며 원수치는 그대로 저장했습니다. 영상 개선만으로 수정안을 자동 채택하지 않습니다.',images=[dict(src=f'{cid}/08_before_after.png',label='기준 영상: 실제 수정 전후와 차이'),dict(src=f'{cid}/08_all_views.png',label='모든 시점: 대상·주변·외부 영향')],metrics=[])]
            ref=result['views'][0]['metrics'];sf=ref['surrounding'];tf=ref['target'];outside=ref['outside']
            metrics=[metric('대상 사진 MAE 전',tf['photo_mae_before']),metric('대상 사진 MAE 후',tf['photo_mae_after']),metric('대상 사진 MAE 변화',tf['photo_mae_delta']),metric('주변 사진 MAE 변화',sf.get('photo_mae_delta')),metric('주변 깊이 최대 변화',sf.get('depth_abs_change_max_m'),'m'),metric('외부 깊이 최대 변화',outside.get('depth_abs_change_max_m'),'m'),metric('대상 alpha 피복 손실',tf['alpha_coverage_lost_pixels'],'pixels'),metric('비선택 Gaussian XYZ 동일',result['nonselected_xyz_exact'])]
            stages[-1]['metrics']=metrics
            reference_path=a.attempt/'reference'/rid/cid/'summary.json'
            if reference_path.exists():
                assert reference_receipt is not None,'Unsealed reference summary'
                score=read(reference_path)
                for domain,label in [('target','대상'),('surrounding','주변')]:
                    sd=score['domains'][domain]
                    metrics.extend([metric(label+' 고정 UAS 표본',sd['frozen_reference_count']),
                        metric(label+' 전후 모두 비교 가능한 UAS 표본',sd['paired_valid']),
                        metric(label+' UAS 깊이 절대 오차 평균 전',sd['paired_before_absolute_camera_z_error_m']['mean'],'m'),
                        metric(label+' UAS 깊이 절대 오차 평균 후',sd['paired_after_absolute_camera_z_error_m']['mean'],'m'),
                        metric(label+' UAS 깊이 절대 오차 p95 전',sd['paired_before_absolute_camera_z_error_m']['p95'],'m'),
                        metric(label+' UAS 깊이 절대 오차 p95 후',sd['paired_after_absolute_camera_z_error_m']['p95'],'m'),
                        metric(label+' UAS 피복 손실',sd['lost_after'],'pixels')])
                stages[-1]['summary']+=' UAS는 결과 고정 뒤 평가에만 사용했습니다. 같은 원본 UAS ID를 전후 비교하며, 픽셀당 관측된 전면 점을 사용합니다. UAS 점 결손에 따른 가림 모호성·픽셀 반올림·기존 좌표계와 수직 기준의 한계가 남습니다. 오차 통계는 전후 모두 유효한 표본 기준이며 피복 손실은 따로 표시합니다.'
                data['receipts'].append(dict(label=cid+' 현재 UAS 평가 원수치',path=f'../reference/{rid}/{cid}/summary.json'))
            if result['changed_ids']==0:
                stages[-1]['summary']='이 사례는 실제 수정이 유보되어 전후가 같습니다. 변화 0을 수정 후 구조 보존 성공으로 해석하지 않습니다. '+stages[-1]['summary']
            rr['cases'].append(dict(id=cid,label=roles[c['label']],decision=c['decision'],reason_codes=fail,stages=stages,
                probe=dict(status=result['status'],summary=f'{result["changed_ids"]}개 중심 수정 · {result["actual_max_displacement_m"]:.4f}m 최대 이동 · '+('실제 수정 없이 동일 상태를 비교함' if result['changed_ids']==0 else '자동 채택하지 않음'),metrics=metrics)))
            allrows.append(dict(region=rid,case=cid,role=c['label'],decision=c['decision'],probe_status=result['status'],changed_gaussians=result['changed_ids'],
                maximum_displacement_m=result['actual_max_displacement_m'],reference_view_metrics=ref,views=result['views'],scientific_verdict=None))
            # Compact mobile summary, retaining actual render differences and quantitative context.
            card=Image.new('RGB',(840,1550),'white');draw=ImageDraw.Draw(card);y=20
            for line in [f'{rid} · {roles[c["label"]]}',f'실제 수정: {result["changed_ids"]}개 Gaussian / 최대 {result["actual_max_displacement_m"]:.3f}m',
                         f'대상 사진 MAE: {tf["photo_mae_before"]:.5f} → {tf["photo_mae_after"]:.5f}',
                         f'주변 사진 MAE 변화: {sf.get("photo_mae_delta",0):+.6f}']:
                draw.text((24,y),line,font=fnt,fill='#173b48');y+=43
            for imgpath in [folder/'07_gaussians.png',folder/'08_before_after.png',folder/'08_all_views.png']:
                im=Image.open(imgpath).convert('RGB');height=round(im.height*792/im.width);card.paste(im.resize((792,height)),(24,y));y+=height+10
            for line in ['관측·연결 근거가 부족한 사례는 업데이트 유보.', '사진 적합도와 형상 변화는 독립 정확도 확정이 아닙니다.']:
                draw.text((24,y),line,font=small,fill='#855b16');y+=33
            card=card.crop((0,0,840,min(y+18,card.height)));card.save(folder/'mobile.png');pdfpages.append(card)
            if c['label']=='best_supported_candidate_or_abstain':
                for si,stage in enumerate(stages):
                    page=Image.new('RGB',(840,1188),'white');dd=ImageDraw.Draw(page);yy=24
                    dd.text((24,yy),f'{rid} · {si+1}단계 · {stage["title"]}',font=fnt,fill='#173b48');yy+=55
                    for line in textwrap.wrap(stage['summary'],width=46):dd.text((24,yy),line,font=small,fill='#425763');yy+=32
                    if stage.get('images'):
                        rel=stage['images'][0]['src'];im=Image.open(out/rel).convert('RGB');im.thumbnail((792,700));page.paste(im,(24,yy));yy+=im.height+12
                    for m in stage.get('metrics',[])[:5]:
                        value=m['value'];value='미산출' if value is None else str(value)
                        dd.text((24,yy),f'{m["name"]}: {value[:64]} {m.get("unit", "")}',font=small,fill='#173b48');yy+=30
                    walkthrough.append(page)
        data['regions'].append(rr)
    shutil.copy2('/repo/src/apps/mvs_surface_update_v1/index.html',out/'index.html')
    (out/'data.js').write_text('window.SURFACE_UPDATE='+json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':'))+';\n')
    write(out/'summary.json',allrows)
    pdfpages[0].save(out/'all_cases_mobile.pdf',save_all=True,append_images=pdfpages[1:],resolution=110.)
    walkthrough[0].save(out/'P1_P2_P3_eight_stages.pdf',save_all=True,append_images=walkthrough[1:],resolution=110.)
    write(out/'receipt.json',dict(task_id=cases['task_id'],status='PASS_REVIEW_BUILD',scientific_verdict=None,
          cases_sha256=sha(prep/'cases.json'),script_sha256=sha(__file__),font_sha256=sha(a.font),
          outputs=[dict(path=str(p.relative_to(out)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*')) if p.is_file()]))
    print(json.dumps(dict(status='PASS_REVIEW_BUILD',cases=len(allrows),out=str(out))))


if __name__=='__main__':main()
