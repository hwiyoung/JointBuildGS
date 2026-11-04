"""Ordered six-arm execution; first-pair publication is a hard barrier."""
import concurrent.futures as futures
import json,os,subprocess,sys,time,traceback
from pathlib import Path
from gpu_job import R,O,C,D,PH,now,dump,command,train
SCRIPT=R/'scripts/phd/main_finaltrain_v1'

def event(message):
    with (D/'progress.md').open('a') as f:f.write(f'- {now()}: {message}\n')
    print(message,flush=True)

def cpu(tag,script,*args):
    dest=O/'logs'/f'{tag}.log'
    with dest.open('a') as f:
        subprocess.run(['bash',str(SCRIPT/'run_cpu.sh'),tag,script,*map(str,args)],cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True)

def delivered(site,prior):
    marker=O/'delivery'/f'{site}__{prior}.json'
    return marker.exists() and json.loads(marker.read_text()).get('push_verified') is True

def publish(site,prior=None):
    args=[site]+([prior] if prior else [])
    with (O/'logs'/('publish-'+'__'.join(args)+'.log')).open('a') as log:
        subprocess.run([sys.executable,str(SCRIPT/'publish.py'),*args],cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)

def final_views_available(site,prior):
    source=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/defs'/site/'unseen.npz'
    if source.exists():return True
    shared=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1/views'/f'{site}.json'
    fixed=json.loads(shared.read_text())
    assert fixed['views'] and not any(v['virtual'] for v in fixed['views'])
    dump(O/'post'/f'{site}__{prior}.json',dict(at=now(),status='UNAVAILABLE_ORIGINAL_VIRTUAL_VIEWS',
        reason='원래 가상 시점 대상 정의가 없어 공통 학습+가상 시점 최종 메시와 의존 채점·그림은 확인 불가. 시점을 새로 만들거나 학습 시점 메시로 대체하지 않았다.',
        missing_source=str(source),rescore_views=str(shared),training_affected=False,scientific_verdict=None))
    event(f'{site}__{prior}: 원래 가상 시점 입력 없음. 학습 기록·목표를 제출하고 최종 메시 채점은 확인 불가로 남김.')
    return False

def prepare(site):
    budget=O/'outside'/site/'budget_receipt.json'
    if not budget.exists():
        active=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
        if site=='B173nb_b10' and 'jbgs-finaltrain-outside-b173' in active:
            while not budget.exists():
                time.sleep(10)
                if 'jbgs-finaltrain-outside-b173' not in subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines() and not budget.exists():
                    raise RuntimeError('Outside worker exited without receipt')
        else:cpu('outside-'+site,'extend_judgments.py',site)
    rec=json.loads(budget.read_text())
    if rec['status']=='EXECUTION_ERROR':
        failed=budget.parent.with_name(site+'_failed_attempt1');assert not failed.exists();budget.parent.rename(failed)
        event(f'{site} 판단 확장 실행 오류 기록 보존. 같은 설정으로 한 번 다시 실행.')
        cpu('outside-'+site+'-retry','extend_judgments.py',site)
    assert json.loads(budget.read_text())['status'] in ['PASS','TIME_LIMIT_BACKGROUND_FALLBACK']
    if json.loads(budget.read_text())['status']=='PASS' and not (O/'verification'/f'extension_judgments_{site}.json').exists():
        cpu('extension-check-'+site,'inspect_extension.py',site)
    for prior in ['ALS','LoD2']:
        stem=f'{site}__{prior}'
        if not (O/'targets'/f'{stem}.json').exists():cpu('targets-'+stem,'targets.py',site,prior)
        if not (O/'stage1'/stem/'ready.json').exists():cpu('inputs-'+stem,'prepare_inputs.py',site,prior)
        if not (O/'verification'/f'inputs_{stem}.json').exists():cpu('verify-'+stem,'verify_inputs.py',site,prior)
        if not (O/'verification'/f'loaded_{stem}.json').exists():
            with (O/'logs'/f'loaded-{stem}.log').open('a') as f:
                subprocess.run(command(0 if prior=='ALS' else 1,'jbgs-finaltrain-loaded-'+stem,'initialize_check.py',[site,prior],site=site),stdout=f,stderr=subprocess.STDOUT,check=True)
    event(f'{site} 두 사전 정보의 목표·학습 입력 대조 통과. 학습 준비 완료.')

def post(site,prior,gpu):
    from scope_policy import training_only
    if training_only(site):
        cpu('training-report-'+site+'__'+prior,'training_report.py',site,prior)
        publish(site,prior)
        return
    stem=f'{site}__{prior}';run=O/'runs'/site/f'ft_{prior}_s0';rec=json.loads((run/'receipt.json').read_text())
    if rec['status']=='TRAINING_COMPLETE_30000' and final_views_available(site,prior):
        event(f'{stem} 30,000회 완료. 다른 판과 독립적으로 최종 메시·채점·제출 시작.')
        if not (O/'meshes'/stem/'render/receipt.json').exists():
            with (O/'logs'/f'render-{stem}.log').open('a') as f:subprocess.run(command(gpu,'jbgs-finaltrain-render-'+stem,'render_final.py',[site,prior],site=site),stdout=f,stderr=subprocess.STDOUT,check=True)
        wd=O/'meshes'/stem/'final_work'
        if not (wd/'inputs/meta.json').exists():cpu('mesh-prep-'+stem,'mesh.py','prepare',site,prior)
        if not (wd/'order/order.json').exists():cpu('mesh-plan-'+stem,'mesh.py','plan',site,prior)
        layout=json.loads((wd/'plan/layout.json').read_text())
        for tile in layout['tiles']:
            k=tile['k']
            if not (wd/'tiles'/f'tile{k}.json').exists():cpu(f'mesh-tile-{stem}-{k}','mesh.py','tile',site,prior,k)
        if not (wd/'merged.json').exists():cpu('mesh-merge-'+stem,'mesh.py','merge',site,prior)
        if not (wd.parent/'final.json').exists():cpu('cleanup-'+stem,'rescore_bridge.py','cleanup',site,prior)
        if not (O/'scores'/stem/'binding.json').exists():cpu('score-'+stem,'rescore_bridge.py','score',site,prior)
    elif rec['status']!='TRAINING_COMPLETE_30000':event(f'{stem}: {rec["status"]}. 결과 없음 기록과 건강 점검을 제출.')
    cpu('report-'+stem,'report.py',site,prior)
    publish(site,prior)

def arm(site,prior,gpu):
    if delivered(site,prior):return
    run=O/'runs'/site/f'ft_{prior}_s0'
    if not (run/'receipt.json').exists():train(str(gpu),site,prior)
    post(site,prior,gpu)

def main():
    previous=O/'QUEUE_FAILURE.json'
    if previous.exists():
        archive=O/'queue_history'/f'failure_{time.time_ns()}.json';archive.parent.mkdir(exist_ok=True);previous.rename(archive)
    state=O/'QUEUE.json';dump(state,dict(at=now(),pid=os.getpid(),state='RUNNING',scientific_verdict=None))
    for site in ['B173nb_b10','B0_b10','R1rep_b10']:
        if all(delivered(site,p) for p in ['ALS','LoD2']):continue
        dump(state,dict(at=now(),pid=os.getpid(),state='PREPARING',site=site,scientific_verdict=None))
        prepare(site)
        dump(state,dict(at=now(),pid=os.getpid(),state='TRAINING_AND_DELIVERING',site=site,scientific_verdict=None))
        with futures.ThreadPoolExecutor(max_workers=2) as pool:
            tasks=[pool.submit(arm,site,p,g) for g,p in [(0,'ALS'),(1,'LoD2')]]
            for job in futures.as_completed(tasks):job.result()
        assert all((O/'delivery'/f'{site}__{p}.json').exists() for p in ['ALS','LoD2'])
    cpu('all-report','report.py','all')
    publish('all')
    partial=any((O/'post').glob('*.json'))
    dump(state,dict(at=now(),pid=os.getpid(),state='COMPLETE_WITH_UNAVAILABLE_OUTPUTS' if partial else 'COMPLETE',scientific_verdict=None))

if __name__=='__main__':
    try:main()
    except BaseException as error:
        dump(O/'QUEUE_FAILURE.json',dict(at=now(),error=str(error),traceback=traceback.format_exc(),scientific_verdict=None))
        dump(O/'QUEUE.json',dict(at=now(),pid=os.getpid(),state='FAILED',error=str(error),scientific_verdict=None))
        event('실행 오류: '+str(error));raise
