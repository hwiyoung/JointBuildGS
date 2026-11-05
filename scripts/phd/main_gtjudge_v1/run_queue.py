"""One durable ordered two-GPU queue. Observe only health-7000 and finished arms."""
import sys,json,time,subprocess,threading,concurrent.futures,traceback
from pathlib import Path
from gpu_job import R,O,D,command,train,dump,now
from cpu_queue import cpu,mesh
from publish_add1 import main as publish
ORDER={0:[('R1rep_b10','ALS'),('B173nb_b10','ALS'),('B0_b10','ALS')],1:[('B173nb_b10','LoD2'),('R1rep_b10','LoD2'),('B0_b10','LoD2')]}
EVENT_LOCK=threading.Lock();POST_LOCK=threading.Lock()
def event(**v):
    with EVENT_LOCK:
        with (O/'queue/events.jsonl').open('a') as f:f.write(json.dumps(dict(at=now(),**v),ensure_ascii=False)+'\n')
def watch_health(stop):
    seen=set()
    while not stop.wait(60):
        for p in (O/'runs').glob('*/*/attempt*/model/target_monitor/health_7000.json'):
            if str(p) in seen:continue
            try:value=json.loads(p.read_text())
            except (OSError,ValueError):continue
            seen.add(str(p));event(event='HEALTH_7000',path=str(p),health=value)

def post(site,prior,arm):
    with POST_LOCK:
        try:
            if mesh(site,prior,arm):
                cpu('score-'+site+'-'+prior+'-'+arm,'score_new.py',site,prior,arm)
                cpu('metrics-'+site+'-'+prior+'-'+arm,'collect.py',site,prior)
                if (O/'scenes'/f'{site}__{prior}'/'preservation_features.npz').exists():cpu('strata-'+site+'-'+prior+'-'+arm,'preservation.py',site,prior,'tables')
                cpu('figures-'+site+'-'+prior+'-'+arm,'figures.py',site,prior,arm)
            publish('',site,prior,arm)
        except Exception as e:
            event(event='POST_ERROR',site=site,prior=prior,arm=arm,error=repr(e));traceback.print_exc()
            with (D/'issues.md').open('a') as f:f.write(f'- {now()}: {site}/{prior}/{arm} 후처리 오류 {e!r}; 학습 대기열 계속.\n')

def lane(gpu,postpool):
    pending=[]
    for site,prior in ORDER[gpu]:
        for arm in ['A1','A2']:
            result=train(gpu,site,prior,arm);event(event='TRAINING_FINISHED',site=site,prior=prior,arm=arm,status=result['status'])
            if result['status']=='TRAINING_COMPLETE_30000':
                ply=result['attempts'][-1]['model']+'/point_cloud/iteration_30000/point_cloud.ply'
                args=[site,prior,arm,'render',ply];rc=None
                for attempt in [1,2]:
                    logfile=O/'logs'/f'render-{site}-{prior}-{arm}-attempt{attempt}.log'
                    with logfile.open('w') as log:rc=subprocess.run(command(gpu,f'jbgs-gtjudge-render-{site}-{prior}-{arm}','mesh_job.py',args,site),stdout=log,stderr=subprocess.STDOUT).returncode
                    if rc==0:break
                if rc==0:pending.append(postpool.submit(post,site,prior,arm))
                else:
                    with (D/'issues.md').open('a') as f:f.write(f'- {now()}: {site}/{prior}/{arm} 모델 렌더 2회 오류; 메시·채점 확인 불가, 다음 학습 진행.\n')
                    publish('',site,prior,arm)
            else:publish('',site,prior,arm)
    for future in pending:future.result()

def stage2():
    for site,prior in [x for lane in ORDER.values() for x in lane]:
        if cpu('preservation-'+site+'-'+prior,'preservation.py',site,prior):cpu('samples-'+site+'-'+prior,'figures.py',site,prior,'2')
    publish('단계2');dump(O/'queue/stage2_done.json',dict(at=now(),scientific_verdict=None))

def main():
    (O/'queue').mkdir(exist_ok=True);dump(O/'queue/launched.json',dict(at=now(),order=ORDER,scientific_verdict=None))
    while not (O/'stage0_decision.json').exists():time.sleep(30)
    if not (O/'queue/stage1_done.json').exists():subprocess.run([sys.executable,str(R/'scripts/phd/main_gtjudge_v1/cpu_queue.py'),'stage1'],cwd=R,check=True)
    publish('단계01')
    stop=threading.Event();observer=threading.Thread(target=watch_health,args=(stop,),daemon=True);observer.start()
    with concurrent.futures.ThreadPoolExecutor(2) as postpool,concurrent.futures.ThreadPoolExecutor(3) as pool:
        jobs=[pool.submit(lane,gpu,postpool) for gpu in [0,1]]
        featurejob=pool.submit(stage2)
        for job in jobs:job.result()
        featurejob.result()
    stop.set();dump(O/'queue/stage3_done.json',dict(at=now(),scientific_verdict=None))
    # The optional exact-r23 / baseline seed-1 queue is a separate final stage;
    # it never takes either GPU before the 12 diagnostic arms finish.
    optional=R/'scripts/phd/main_gtjudge_v1/seed1_queue.py'
    if optional.exists():subprocess.run([sys.executable,str(optional)],cwd=R,check=True)
    publish('');dump(O/'queue/complete.json',dict(at=now(),scientific_verdict=None))
if __name__=='__main__':main()
