"""Publish the six regional conditions only after their actual receipts pass."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time
import traceback
import numpy as np
from plyfile import PlyData
import legacy_publish as export

root=Path('/out');run=Path('/run');audit=Path('/audit');root.mkdir(exist_ok=True)
export.root=root
# The legacy R1 exporter keeps geometry above the MVS-derived camera-fit bounds.
# Capture its actual crop before per-region exports change export.box.
R1_DISPLAY_BOX=export.box.copy()
roles=['prior','mvs','anchor','mvs_geogs','da3_geogs','local_prior0']
labels=dict(prior='Existing ALS prior',mvs='현재 MVS',anchor='Anchor · 8,000회',
    mvs_geogs='MVS–GeoGS · prior 0.005',da3_geogs='DA3–GeoGS · prior 0.005',local_prior0='MVS–GeoGS · 보정 구역 prior 0')
def read(p):return json.loads(Path(p).read_text())
def rebase(v):
    if isinstance(v,dict):return {k:(s.replace('/data/','/data/r1legacy/',1) if k in ('url',) and isinstance(s,str) and s.startswith('/data/') else rebase(s)) for k,s in v.items()}
    if isinstance(v,list):return [rebase(s) for s in v]
    return v
def links(region):
    items=[]
    source=run/region/'audit/result'
    for name,label in [('full_input_atlas.png','전체 입력 관계'),('rgb_plan.png','MVS 평면도'),('views_1.png','원영상 1'),('views_2.png','원영상 2'),('views_3.png','원영상 3'),('inspection_views.json','검토 영상 목록')]:
        p=source/name
        if p.exists():
            dest=root/'review'/region/name;dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copyfile(p,dest)
            items.append(dict(url=f'/data/review/{region}/{name}',label=label))
    for name,label in [('whole_area_judgment.png','전체 구역 판단'),('zone_judgments.csv','구역별 표')]:
        p=run/region/'review'/name
        display=run/region/'review_display_v3'
        if name=='whole_area_judgment.png' and (display/'receipt.json').exists():
            receipt=read(display/'receipt.json');assert receipt['status']=='PASS_DISPLAY_ONLY'
            name='whole_area_judgment_v3.png';p=display/name;assert export.sha(p)==receipt['output_sha256']
        if p.exists():
            dest=root/'review'/region/name;dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copyfile(p,dest)
            items.insert(0,dict(url=f'/data/review/{region}/{name}',label=label))
    return items
def main():
    cfg=read(audit/'config.json');fused=PlyData.read('/fused.ply',mmap='r')['vertex'].data
    base={};regions_cfg=cfg['regions'];completed=0
    for r in regions_cfg[1:]:
        rid=r['id'];ref=np.load(audit/f'{rid}_reference_points.npz');rows=ref['source_rows'];rgb=np.column_stack([fused[k][rows] for k in ('red','green','blue')])
        xyz=ref['xyz'];bounds=dict(min=[r['u_m'][0],-r['v_m'][1],float(xyz[:,2].min())],max=[r['u_m'][1],-r['v_m'][0],float(xyz[:,2].max())])
        export.box=np.array([bounds['min'],bounds['max']]);base[rid]=(bounds,
            export.candidate('mvs','융합 MVS · 원본 RGB','mvs',export.cache(rid+'_mvs',lambda d:export.points(xyz,rgb,d,'FUSED_MVS_POINTS',dict(kind='NATIVE_MVS_RGB',label='MVS 원본 RGB')))))
    while True:
        try:
            records=[];completed=0;q=read(run/'execution/status.json') if (run/'execution/status.json').exists() else dict(state='PREPARING')
            overrides=read(run/'execution/artifact_overrides.json') if (run/'execution/artifact_overrides.json').exists() else {}
            legacy=read('/r1legacy/manifest.json');r1=rebase(legacy['regions'][0]);r1['review_links']=[dict(url='/data/r1legacy/judgment/R1_whole_area_judgment.png',label='R1 전체 구역 판단'),dict(url='/data/r1legacy/judgment/zone_judgments.csv',label='구역별 표')]
            r1['review_links'] += [dict(url=f'/data/r1legacy/judgment/zone_review_{i}.png',label=f'구역별 원영상 검토 {i}') for i in range(1,5)]
            sky=root/'review/R1/R1_sky_comparison.png'
            if sky.exists():r1['review_links'].append(dict(url='/data/review/R1/R1_sky_comparison.png',label='MVS·DA3 하늘 깊이 비교'))
            for r in regions_cfg:
                rid=r['id'];status=root/'review'/rid
                if rid=='R1':
                    entry=copy.deepcopy(r1);items=entry['candidates'];bounds=entry['bounds'];completed+=1
                else:
                    bounds,mvs=base[rid];entry=dict(id=rid,bounds=bounds,frame='객체축 u / -v / local z · m',review_links=links(rid));items=[copy.deepcopy(mvs)]
                    prep=run/rid/'preparation';receipt=prep/'receipt.json'
                    if receipt.exists() and read(receipt)['status']=='PASS_CPU_INPUT_PREPARATION':
                        p=prep/'input/initialization/sample_membership.npz';samples=np.load(p)['sample_xyz'];export.box=np.array([bounds['min'],bounds['max']])
                        items.insert(0,export.candidate('prior','ALS prior 표본 · 회색','prior',export.cache(rid+'_prior_'+export.sha(p)[:12],lambda d:export.points(samples,np.tile([180,190,198],(len(samples),1)),d,'ALS_PRIOR_POINTS',dict(kind='CONSTANT_NEUTRAL',label='회색 · 기하 확인용')))))
                export.box=R1_DISPLAY_BOX.copy() if rid=='R1' else np.array([bounds['min'],bounds['max']])
                display_crop=dict(min=export.box[0].tolist(),max=export.box[1].tolist())
                entry['display_crop_bounds']=display_crop
                # A changed crop must not reuse the previous immutable geometry buffers.
                crop_key='_crop_'+hashlib.sha256(json.dumps(display_crop,sort_keys=True).encode()).hexdigest()[:12] if rid=='R1' else ''
                jp=run/rid/'review/judgments.npz'
                if rid!='R1' and jp.exists() and (run/rid/'review/receipt.json').exists():
                    ev=np.load(run/rid/'audit/result/surface_evidence.npz');jud=np.load(jp)['mvs_judgment'];palette=np.array([[154,157,163],[39,135,186],[230,160,26],[154,89,181],[71,123,85]])
                    items.append(export.candidate('judgment','현재 표면 · 판단 초안','mvs',export.cache(rid+'_judgment_'+export.sha(jp)[:12],lambda d:export.points(ev['mvs_xyz'],palette[jud],d,'INPUT_JUDGMENT_POINTS',dict(kind='JUDGMENT_CATEGORIES',label='입력 기반 후보 · 보정은 가설')))))
                for name,role,it in [('anchor','anchor',8000),('mvs','mvs_geogs',30000),('da3','da3_geogs',30000),('local_prior0','local_prior0',30000)]:
                    if rid=='R1' and name in ('anchor','mvs'):continue
                    folder=run/overrides.get(rid,{}).get(name,f'{rid}/{name}');p=folder/'receipt.json'
                    if p.exists() and read(p)['status']=='PASS':
                        rec=read(p);digest=rec['checkpoint']['ply_sha256'];ply=folder/'model/jbgs_complete'/f'iteration_{it}'/'point_cloud.ply'
                        key=rid+'_'+name+'_'+digest[:12]+crop_key
                        def points(d,p=ply,h=digest):assert export.sha(p)==h;return export.geometry(p,d)
                        items.append(export.candidate(name+'_centers',labels[role]+' · Gaussian 중심',role,export.cache(key,points)))
                        meshroot=run/overrides.get(rid,{}).get('extract_'+name,f'{rid}/extract_{name}');er=meshroot/'receipt.json'
                        if er.exists() and read(er)['status']=='PASS':
                            m=read(er)['surfaces']['fuse.ply'];mp=meshroot/m['path'];key=rid+'_mesh_'+name+'_'+m['sha256'][:12]+crop_key
                            def mesh(d,p=mp,h=m['sha256']):assert export.sha(p)==h;return export.geometry(p,d,True)
                            items.append(export.candidate(name+'_mesh',labels[role]+' · RGB 표면',role,export.cache(key,mesh)))
                            if name!='anchor':completed+=1
                    else:
                        failed=(q.get('state')=='FAILED' and q.get('region')==rid and name in str(q.get('job',''))) or any(f['region']==rid and f['branch']==name for f in q.get('failures',[]))
                        reason='보정 구역 검토·마스크 준비 후 실행' if name=='local_prior0' and not (run/rid/'masks/receipt.json').exists() else '백그라운드 실행 대기 · 완료 후 자동 표시'
                        if failed:reason='실행 실패 · 상태 기록에서 원인 확인'
                        items.append(export.candidate(name+'_pending',labels[role],role,reason=reason,status='failed' if failed else 'pending'))
                for role in roles:
                    if not any(c['group']==role for c in items):items.append(export.candidate(role+'_pending',labels[role],role,reason='입력 준비 중'))
                mask_receipt=run/rid/'masks/receipt.json'
                if mask_receipt.exists():
                    mr=read(mask_receipt);support={k:mr[k] for k in ['region','total_pixels','contributing_views','policy','outside_multiplier','inside_multiplier','base_prior_weight','native_protection_retained']}
                    support.update(scientific_verdict=None,receipt_sha256=export.sha(mask_receipt),per_view=[dict(name=x['name'],pixels=x['pixels']) for x in mr['masks'] if x['pixels']])
                    summary=root/'review'/rid/'weight_support.json';summary.parent.mkdir(parents=True,exist_ok=True);export.atomic(summary,support)
                    note=f"prior 해제: {mr['contributing_views']}장 · 합계 {mr['total_pixels']:,}픽셀"
                    for c in items:
                        if c['group']=='local_prior0':
                            c['label']+=' · '+note;c['local_weight_support']=support
                            c['links']=[dict(label='실제 가중치 적용 범위',url=f'/data/review/{rid}/weight_support.json')]
                            if c['status']=='pending':c['reason']=note+' · 같은 Anchor에서 학습 예정'
                entry.update(candidates=items,description=r['label_ko'],default_candidates={role:next(c['id'] for c in reversed(items) if c['group']==role) for role in roles})
                entry['default_candidates']['mvs']='mvs';records.append(entry)
                if rid=='R1':
                    for z in legacy['regions'][1:]:
                        records.append(dict(entry,id='R1_'+z['id'],bounds=z['bounds'],frame=z['frame']))
                zones=run/rid/'review_zones.json'
                if zones.exists():
                    for z in read(zones)['zones']:
                        if z['id']=='Z00':continue
                        p=np.array(z['polygon']);lo=p.min(0);hi=p.max(0)
                        records.append(dict(entry,id=rid+'_'+z['id'],bounds=dict(min=[float(lo[0]),float(-hi[1]),bounds['min'][2]],max=[float(hi[0]),float(-lo[1]),bounds['max'][2]]),frame=z['name']))
            text={'RUNNING':'백그라운드 실행 중','COMPLETE':'학습·표면 추출 완료','FAILED':'실행 실패 · 기록 확인','WAITING_REGION_REVIEW':'국소 보정 구역 검토 대기','WAITING_RESOURCES':'자원 대기','WAITING_INPUTS':'입력 준비 중'}.get(q['state'],'준비 중')
            if q['state']=='COMPLETE_WITH_FAILURES':text='대기 큐 종료 · 일부 조건 실패, 기록 확인'
            elif q.get('failures'):text+=f" · 실패 {len(q['failures'])}조건 별도 기록"
            if q.get('region'):text+=' · '+q['region']+' / '+str(q.get('job') or '')
            export.atomic(root/'status.json',dict(execution=q,preparation=read(run/'preparation_status.json'),audit=read(run/'audit_status.json') if (run/'audit_status.json').exists() else None,scientific_verdict=None))
            export.atomic(root/'manifest.json',dict(schema='geogs_rgb_comparison_v1',scientific_verdict=None,built_at=time.time(),regions=records,
                run_status=dict(queue_status=text,completed=completed,total=15),report='/data/status.json'))
        except Exception:
            export.atomic(root/'publication_failure.json',dict(status='FAIL',error=traceback.format_exc(),scientific_verdict=None))
            with (root/'publication_errors.log').open('a') as f:f.write(traceback.format_exc()+'\n')
        time.sleep(45)
if __name__=='__main__':main()
