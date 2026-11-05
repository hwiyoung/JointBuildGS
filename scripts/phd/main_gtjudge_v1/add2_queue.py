"""Shared priority queue; adopts live containers without signalling their processes."""
import concurrent.futures,datetime,traceback
from add2_host import *
Q=O/'queue/addendum2';MUTEX=threading.Lock();POST=threading.Lock();RUNNING=set()
ORDER=[('R1rep_b10',p,a) for a in ['A1','A2'] for p in ['ALS','LoD2']]+[(s,p,'fix') for s,p in [('R1rep_b10','ALS'),('R1rep_b10','LoD2'),('B173nb_b10','LoD2'),('B173nb_b10','ALS'),('B0_b10','LoD2'),('B0_b10','ALS')]]+[(s,p,a) for s,p in [('B173nb_b10','ALS'),('B173nb_b10','LoD2'),('B0_b10','ALS'),('B0_b10','LoD2')] for a in ['A1','A2']]
def runpath(job):
    s,p,a=job;return O/'runs'/s/f'{"fix" if a=="fix" else "gt" if a=="A1" else "gtfs"}_{p}_s0'
def ready(job):
    s,p,a=job
    if a!='fix':return True
    unit=O/'verification/unit_r26.json'
    return unit.exists() and json.loads(unit.read_text())['status']=='PASS' and (O/'addendum2/fix_inputs/ready'/f'{s}__{p}.json').exists() and (p=='ALS' or (Q/'selection_commit.json').exists())
def render(gpu,job,result):
    if result['status']!='TRAINING_COMPLETE_30000':return False
    s,p,a=job
    if (O/'renders'/f'{s}__{p}__{a}'/'receipt.json').exists():return True
    ply=result['attempts'][-1]['model']+'/point_cloud/iteration_30000/point_cloud.ply'
    for attempt in [1,2]:
        with (O/'logs'/f'add2-render-{s}-{p}-{a}-{attempt}.log').open('w') as f:
            rc=subprocess.run(command(gpu,f'jbgs-gtjudge-render-{s}-{p}-{a}','mesh_job.py',[s,p,a,'render',ply],s),stdout=f,stderr=subprocess.STDOUT).returncode
        if not rc:return True
    event('RENDER_ERROR',job=job);return False
def post(job,result,rendered):
    with POST:
        s,p,a=job;mark=Q/'post'/f'{s}__{p}__{a}.json'
        if mark.exists():return
        try:
            if rendered:
                assert mesh(s,p,a)
                assert cpu(f'score-{s}-{p}-{a}','score_new.py',s,p,a)
                assert cpu(f'metrics-{s}-{p}-{a}','add2_scores.py','metrics',s,p)
                if a=='fix':
                    assert cpu(f'fix-detail-{s}-{p}','add2_fix_results.py',s,p)
                    assert cpu(f'fix-figures-{s}-{p}','add2_figures.py',s,p,'fix')
                elif not (D/'figures'/f'{s}__{p}_{a}_mesh_views.png').exists():
                    assert cpu(f'figures-{s}-{p}-{a}','figures.py',s,p,a)
            subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),'run',s,p,a],cwd=R,check=True)
            dump(mark,dict(at=now(),training_status=result['status'],mesh_scored=rendered,scientific_verdict=None));event('POST_FINISHED',job=job)
        except Exception as e:
            event('POST_ERROR',job=job,error=repr(e));traceback.print_exc()
            with (D/'issues.md').open('a') as f:f.write(f'- {now()}: 덧붙임2 후처리 {job} 오류 {e!r}; 다음 학습 계속.\n')
def adopt(entry):
    name=entry['name'];root=Path(entry['attempt_root']);job=tuple(entry['job']);started=json.loads((root/'launch.json').read_text())['at']
    response=subprocess.run(['docker','wait',name],capture_output=True,text=True)
    done=root/'TRAINING_COMPLETE.json';stop=root/'model/target_monitor/STOP.json'
    rc=int(response.stdout.strip()) if response.returncode==0 and response.stdout.strip().isdigit() else 0 if done.exists() else 1
    health=json.loads(stop.read_text()) if stop.exists() else None;status='TRAINING_COMPLETE_30000' if rc==0 and done.exists() else 'HEALTH_STOP' if health else 'EXECUTION_ERROR'
    finished=json.loads(done.read_text())['at'] if done.exists() else now();seconds=(datetime.datetime.fromisoformat(finished)-datetime.datetime.fromisoformat(started)).total_seconds()
    a=int(root.name.removeprefix('attempt'));rec=dict(at=finished,attempt=a,status=status,model='/gtjudge/'+str((root/'model').relative_to(O)),exit_code=rc,seconds=seconds,health=health,adopted=True,scientific_verdict=None);dump(root/'receipt.json',rec)
    if status=='EXECUTION_ERROR':return train(entry['gpu'],*job)
    final=dict(at=finished,site=job[0],prior=job[1],arm=job[2],status=status,attempts=[rec],scientific_verdict=None);dump(root.parent/'receipt.json',final);return final
def worker(gpu,entry,pool):
    if entry:
        job=tuple(entry['job']);result=adopt(entry);event('TRAINING_FINISHED',job=job,status=result['status'],adopted=True)
        rendered=render(gpu,job,result);pool.submit(post,job,result,rendered)
        with MUTEX:RUNNING.discard(job)
    while True:
        with MUTEX:
            remaining=[j for j in ORDER if not (runpath(j)/'receipt.json').exists()]
            possible=[j for j in remaining if j not in RUNNING and ready(j)]
            if possible:job=possible[0];RUNNING.add(job)
            else:job=None
            done=not remaining
        if done:return
        if job is None:time.sleep(15);continue
        event('TRAINING_STARTED',gpu=gpu,job=job)
        result=fix_train(gpu,job[0],job[1]) if job[2]=='fix' else train(gpu,*job)
        event('TRAINING_FINISHED',gpu=gpu,job=job,status=result['status']);rendered=render(gpu,job,result);pool.submit(post,job,result,rendered)
        with MUTEX:RUNNING.discard(job)
def health(stop):
    seen=set()
    while not stop.wait(60):
        for p in (O/'runs').glob('*/*/attempt*/model/target_monitor/health_7000.json'):
            if str(p) not in seen:
                seen.add(str(p));event('HEALTH_7000',path=str(p),value=json.loads(p.read_text()))
def main():
    Q.mkdir(parents=True,exist_ok=True);entries=[]
    handoff=json.loads((Q/'handoff.json').read_text())
    for c in handoff['active_containers']:
        name=c['Names']
        for p in (O/'runs').glob('*/*/attempt*/command.json'):
            cmd=json.loads(p.read_text())
            if '--name' in cmd and cmd[cmd.index('--name')+1]==name:
                l=json.loads(p.with_name('launch.json').read_text());job=(l['site'],l['prior'],l['arm']);entries.append(dict(name=name,attempt_root=str(p.parent),gpu=l['gpu'],job=job));RUNNING.add(job)
    dump(Q/'adopted.json',dict(at=now(),entries=entries,order=ORDER,scientific_verdict=None))
    stop=threading.Event();threading.Thread(target=health,args=(stop,),daemon=True).start()
    with concurrent.futures.ThreadPoolExecutor(2) as posts,concurrent.futures.ThreadPoolExecutor(2) as workers:
        fs=[workers.submit(worker,gpu,next((e for e in entries if e['gpu']==gpu),None),posts) for gpu in [0,1]]
        for f in fs:f.result()
    stop.set();dump(Q/'training_done.json',dict(at=now(),scientific_verdict=None))
    subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/add2_publish.py'),'fixed'],cwd=R,check=True)
    # Optional seed trials only after all diagnostic and fixed training finishes.
    subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/seed1_queue.py')],cwd=R,check=True)
    dump(Q/'complete.json',dict(at=now(),scientific_verdict=None))
if __name__=='__main__':main()
