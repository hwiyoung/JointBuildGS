"""Seal the requested 7k package first, then the final available-checkpoint package."""
import sys,hashlib,zipfile
from common import *
from package_r7 import stable_bytes
from report_movement_r7 import pc
def read(p):return json.loads(p.read_text())
def main():
    mode=sys.argv[1];assert mode in ['7000','final'];its=[7000] if mode=='7000' else [7000,15000,30000]
    if mode=='final':assert (OUT/'handover/delivery_receipt_r8_7000.json').exists(),'7k package must be delivered first'
    lock=read(CFG/'target_v1.runtime.r8.lock.json');assert sha(CFG/'target_v1.r8.json')==lock['config_sha256']
    for p,h in lock['files'].items():assert sha(REPO/p)==h,p
    for p,h in read(CFG/'fork_r22_base.json')['files'].items():assert sha(REPO/p)==h,p
    assert read(OUT/'r8/verification/unit.json')['status']=='PASS_R8_UNIT'
    assert read(OUT/'r8/verification/runtime.json')['status']=='PASS_R8_SOURCE_AND_INPUTS'
    assert read(OUT/'r8/verification/exclusion.json')['status']=='PASS_INDEPENDENT_SFM_CYLINDERS'
    assert read(OUT/'r8/verification/measurement_sources.json')['status']=='PASS_R8_INHERITED_SCORING_ARITHMETIC'
    rows=[];absent=[];paths=set();training=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8';model=run/'model';assert read(OUT/'r8/verification/initial'/prior/'result.json')['status']=='PASS_R8_INITIALIZATION'
        stop=OUT/'r8'/f'STOP_{prior}.json';receipt=run/'receipt.json'
        training.append(dict(prior=prior,status=read(receipt)['status'] if receipt.exists() else 'RUNNING',stop=read(stop) if stop.exists() else None))
        if mode=='final':assert receipt.exists()
        curves=[json.loads(s) for s in (model/'target_monitor/curve.jsonl').read_text().splitlines()];mem=[json.loads(s) for s in (model/'target_monitor/memory_1000.jsonl').read_text().splitlines()];curve={r['iteration']:r for r in curves}
        for r in mem:
            c=curve[r['iteration']];assert r['gaussians']==c['gaussians'] and r['tags']==c['tags'] and sum(r['tags'].values())==r['gaussians'];assert r['allocated_bytes']<=r['peak_allocated_bytes'] and r['reserved_bytes']<=r['peak_reserved_bytes']
            if r['iteration']>=7000 and r['gaussians']>3*r['count_at_6000']:assert stop.exists()
        provenance=OUT/'r8/baseline_origin'/prior
        assert read(provenance/'verification.json')['status']=='PASS_BASELINE_ORIGIN_JOIN'
        paths.update(provenance.glob('views/*.npz'));paths.add(provenance/'origin_attribution.npz')
        for it in its:
            cp=model/f'jbgs_complete/iteration_{it}/receipt.json'
            if not cp.exists():
                assert stop.exists();absent.append(dict(prior=prior,iteration=it,status='NOT_REACHED_HEALTH_OR_EXECUTION_STOP'));continue
            assert read(run/f'verification{it}.json')['status']=='PASS_R8_SAVED_EVIDENCE_RECOUNT';summary=read(DOC/'tables'/f'r8_{prior}_{it}_summary.json');assert read(run/f'report{it}.json')['status']=='PASS_CHECKPOINT_REPORT';assert read(run/f'diagnostics_report{it}.json')['status']=='PASS_DIAGNOSTIC_FIGURES'
            fs=next(r for r in read(run/'verification_full_state.json')['rows'] if r['iteration']==it);assert fs['status']=='PASS_COMPLETE_STATE'
            for typ in ['gate_coverage','section','section_centres','fixed_render','fixed_height','floating_origin','regions_map','regions_all','regions_original','regions_replaced','failure','release','large_background','counts_memory']+[f'{tag}_movement_{view}' for tag in ['patch','background','released'] for view in ['top','oblique']]:
                f=DOC/'figures'/f'r8_{prior}_{it}_{typ}.json';assert f.exists() and f.with_suffix('.png').exists(),f
            pv=read(run/f'verification_post{it}.json');assert pv['status']=='PASS_POST_RECOUNT_AND_RAYS'
            assert list(summary['geometry_checks'].values())==pv['geometry_checks']
            key=f'r8_{prior}_{it}';meshrows=[]
            for kind in ['current','final']:
                root=OUT/'r8/scoring'/key/kind;v=read(root/'values.json');a=read(root/'verification.json');assert v['status']=='PASS' and a['status']=='PASS_INDEPENDENT_SAVED_ARITHMETIC' and a['mesh_sha256']==v['mesh_sha256'];meshrows.append(dict(kind=kind,sha256=v['mesh_sha256']))
                paths.update(root.glob('dist/*.npz'));paths.add(root/'patch_z.npz')
            rows.append(dict(prior=prior,iteration=it,geometry_status=summary['geometry_status'],geometry_checks=summary['geometry_checks'],score=summary['score'],baseline=summary['baseline'],r7=summary['r7'],health=summary['health'],meshes=meshrows))
            paths.update([model/f'jbgs_complete/iteration_{it}/checkpoint.pth',model/f'point_cloud/iteration_{it}/point_cloud.ply',model/f'target_monitor/snapshot_{it}.npz',run/f'post{it}/merged.ply',OUT/'r8/meshes'/key/'final.ply'])
    if mode=='7000':assert len(rows)+len(absent)==2
    audit=dict(write_scope_exception=read(OUT/'r8/verification/write_scope_exception.json'),at=stamp(),status='PASS_R8_DELIVERY_AUDIT_WITH_RECORDED_SCOPE_EXCEPTION',mode=mode,training=training,rows=rows,unavailable=absent,other_six='NOT_STARTED',r7_ALS='NOT_RESUMED_BY_R8_DECISION',r7_LoD2='REFERENCE_SEPARATE',scientific_verdict=None)
    dump(OUT/'r8'/f'final_audit_{mode}.json',audit);dump(DOC/'tables'/f'r8_final_audit_{mode}.json',audit)
    title='단계1_7000회_점검_r8.md' if mode=='7000' else '최종_채점_r8.md';L=['# r8 '+('7,000회 점검' if mode=='7000' else '학습·채점 기록')+' [이 발주에서 냄]','', 'r8은 기준선 SfM 배경과 배경 목표 화소 무게 1을 사용한다. 패치 입력·목표·무게·다시 붙이기·학습 함수는 r7과 같음이 검증됐다. [구현과 초기 점검](구현과_초기점검_r8.md)에 출처와 바이트 대조를 적었다.','', '| 사전 정보 | 반복 | 뜬 면 | 일치 영역 τ 안 | 면 없음 | 기하 기준 | 건강 |','|---|---:|---:|---:|---:|---|---|']
    for r in rows:L.append(f"| {r['prior']} | {r['iteration']:,} | "+' | '.join(pc(r['score'][k]) for k in ['floating_fraction_cells_0_3','agreement_within_tau_fraction','no_surface_fraction_cells_0_3'])+f" | {r['geometry_status']} | {r['health']['status']} |")
    L +=['','문턱: 같은 사전 정보의 기존 방법 7,000회 대비 뜬 면 +2%p 이하, 일치 영역 τ 안 −2%p 이상, 면 없음 +1%p 이하. 22:20 결정에 따라 기하 기준은 학습 중단에 쓰지 않는다. 건강 중단은 해당 판에만 적용한다.','']
    for r in rows:L +=[f"- [{r['prior']} {r['iteration']:,}회 상세](r8_{r['prior']}_{r['iteration']}_점검.md)"]
    for r in absent:L +=[f"- {r['prior']} {r['iteration']:,}회: 모델 없음. 0점이나 완료로 세지 않음."]
    L +=['','7장 틀: 지금 채점 메시와 최종 메시를 각각 참값 열두 칸으로 나누어 R(τ), P(τ), 양쪽 평균 거리, 뜬 면·면 없음, 두 축, 덩어리를 집계했다. 상세 수와 동반 그림은 `tables/r8/`, `figures/r8_r8_*`에 있다. P와 결과 기준 평균은 기존 AXES71-v2 셈 마(E), A~F와 제외 수는 JSON에 보존했다.','', '기존 r6·기준선·r7과 AXES71-v2 비교 방법은 [이어 학습과 채점](이어학습과채점_r7.md)의 별도 기록을 함께 본다. 나머지 여섯 판은 시작하지 않았다.','', 'scientific_verdict: null.']
    L += ['', '학습 실행 상태:']
    for item in training:L.append('- '+item['prior']+': '+item['status'])
    if (OUT/'r8/STOP_LoD2.json').exists():L += ['- LoD2의 CUDA 메모리 부족 중단·미도달 상태는 [실행 중단 기록](실행중단_r8_LoD2.md)을 본다. 7,000회 건강 통과와 이후 실행 중단을 구분한다.']
    (DOC/title).write_text('\n'.join(L)+'\n')
    assert not (REPO/'report_invalid_placeholder').exists() and not (REPO/'audit_invalid_placeholder').exists()
    L +=['', '쓰기 범위 예외: 작업 중 허용 폴더 밖에 빈 파일 2개를 각각 잘못 만들고 즉시 삭제했다. 기존 입력·코드·결과에 영향은 없으며 `issues.md`에 기록했다.']
    (DOC/title).write_text('\n'.join(L)+'\n')
    combined=DOC/'tables'/f'r8_all_meshes_{mode}.json';assert combined.exists()
    if mode=='7000':
        states=read(combined)['states'];assert len(states)==16 and all(r['status']=='PASS' and r['key'].endswith('_7000') for r in states), 'First package requires all sixteen 7000 comparison meshes'
    if mode=='final':
        states=read(combined)['states'];assert len(states)==36
        assert not any(r['status']=='PENDING' for r in states),'requested earlier readouts remain pending'
        assert read(OUT/'r7_continue/final_audit.json')['status']=='PASS_CONTINUATION_DELIVERY_AUDIT'
        assert (OUT/'handover/delivery_receipt_continue_r7.json').exists()
        for r in states:
            if r['status']=='PASS':
                root=OUT/('r8' if r['key'].startswith('r8_') else 'r7_continue')/'scoring'/r['key']/r['kind']
                assert sha(root/'values.json')==r['sha256']
                assert read(root/'verification.json')['status']=='PASS_INDEPENDENT_SAVED_ARITHMETIC'
    for prior in ['ALS','LoD2']:
        for kind in ['current','final']:
            for metric in ['R_tau','P_tau','gt_mean','res_mean','floating','missing','ge_2.5','ge_10']:
                f=DOC/'figures'/f'r8_compare_{mode}_{prior}_{kind}_{metric}.json';assert f.exists() and f.with_suffix('.png').exists()
    members={}
    for root,prefix in [(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),(DOC,'docs/experiments/phd/main_target_v1'),(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r22','src/phd/forks/GeoGS-conf-guided-v1-r22')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.zip'] and not p.name.startswith('delivery_receipt'):members[prefix+'/'+p.relative_to(root).as_posix()]=stable_bytes(p)
    for p in sorted((OUT/'r8').rglob('*')):
        if p.is_file() and p.suffix in ['.json','.jsonl','.log'] and not any('/'+part+'/' in str(p) for part in ['renders','render','inputs','dist']):members['payload/r8/'+p.relative_to(OUT/'r8').as_posix()]=stable_bytes(p)
    assert not any('/holdout/' in n for n in members)
    external={str(p).replace('/out/','PH/main_target_v1/PHD-MAIN-TARGET-v1/'):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths) if p.exists()}
    manifest=dict(at=stamp(),revision='r8',checkpoint_scope=its,audit=audit,scientific_verdict=None,members=[dict(path=n,bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in members.items()],external_payloads=external,recomputation_boundary='Original S0/S1/UNCERT inputs, frozen r7 targets/maps, the inherited scoring source and Docker image plus external models/meshes/distances are required. ZIP is compact evidence, not a complete data backup. No detailed holdout values included.')
    label='점검r8' if mode=='7000' else '최종점검r8';name='PHD-MAIN-TARGET-v1_'+label+'_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip';dest=OUT/'handover'/name;assert not dest.exists()
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,b in members.items():z.writestr(n,b)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');z.writestr('SHA256SUMS',''.join(f'{m["sha256"]}  {m["path"]}\n' for m in manifest['members']));z.writestr('README.txt','PHD-MAIN-TARGET-v1 r8\n보고서: docs/experiments/phd/main_target_v1/'+title+'\n기하 기준 미달은 기록. 건강 중단은 해당 판에만 적용. 나머지 여섯 판 미시작.\n모델·메시·전체 거리 배열은 외부 manifest 경로에 남음. 원본 자료 없이는 완전 재계산 불가.\nCRC/SHA-256은 무결성 확인이며 과학적 결론이 아님. scientific_verdict: null.\n')
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for m in manifest['members']:assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
    h=sha(dest);dest.with_suffix('.zip.sha256').write_text(h+'  '+name+'\n');receipt=dict(at=stamp(),status='PASS_ARCHIVE_INTEGRITY',zip_name=name,sha256=h,bytes=dest.stat().st_size,mode=mode,members_checked=len(members),crc='PASS',member_sha256='PASS',scientific_verdict=None);dump(OUT/'handover'/f'delivery_receipt_r8_{mode}.json',receipt);dump(DOC/f'delivery_receipt_r8_{mode}.json',receipt);print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
