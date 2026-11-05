"""Bounded queue of cached CPU stages, each error gets one identical retry."""
import sys,subprocess,json,concurrent.futures
from gpu_job import R,O,D,dump,now

def cpu(tag,script,*args):
    command=['bash',str(R/'scripts/phd/main_gtjudge_v1/run_cpu.sh'),tag,script,*map(str,args)]
    for attempt in [1,2]:
        rc=subprocess.run(command,cwd=R).returncode
        if not rc:return True
    with (D/'issues.md').open('a') as f:f.write(f'- {now()}: {tag} 같은 설정 2회 실행 오류({rc}); 해당 계산 확인 불가로 기록하고 다음 진행.\n')
    dump(O/'failures'/f'{tag}.json',dict(at=now(),command=command,exit_code=rc,attempts=2,scientific_verdict=None));return False

def mesh(site,prior,family):
    stem=f'{site}__{prior}';root=O/'meshes'/(stem+'__'+family);wd=root/'final_work'
    if (root/'final.json').exists():return True
    for step in ['render','prepare','plan']:
        sentinel={'render':O/'renders'/(stem+'__'+family)/'receipt.json','prepare':wd/'inputs/meta.json','plan':wd/'plan/order.json'}[step]
        if sentinel.exists() and step!='plan':continue
        if not cpu(f'{stem}-{family}-{step}','mesh_job.py',site,prior,family,step):return False
    plan=json.loads((wd/'plan/layout.json').read_text())
    for tile in plan['tiles']:
        k=tile['k']
        if (wd/'tiles'/f'tile{k}.json').exists():continue
        if not cpu(f'{stem}-{family}-tile{k}','mesh_job.py',site,prior,family,f'tile:{k}'):return False
    for step in ['merge','finish']:
        if not cpu(f'{stem}-{family}-{step}','mesh_job.py',site,prior,family,step):return False
    return True

def distance_lane(wait_name,jobs):
    subprocess.run(['docker','wait',wait_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for site,prior in jobs:cpu('distance-'+site+'-'+prior,'stage0.py',site,prior)

def main(mode):
    if mode=='distances':
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            fs=[pool.submit(distance_lane,'jbgs-gtjudge-stage0-R1-LoD2',[('B0_b10','ALS'),('B0_b10','LoD2'),('R1rep_b10','ALS')]),
                pool.submit(distance_lane,'jbgs-gtjudge-stage0-B173-LoD2',[('B173nb_b10','ALS')])]
            for f in fs:f.result()
        cpu('stage0-gate','collect.py','gate')
        dump(O/'queue/stage0_done.json',dict(at=now(),scientific_verdict=None))
    elif mode=='stage1':
        order=[('R1rep_b10','ALS'),('B173nb_b10','LoD2'),('B173nb_b10','ALS'),('R1rep_b10','LoD2'),('B0_b10','ALS'),('B0_b10','LoD2')]
        for site,prior in order:
            if not cpu('target-'+site+'-'+prior,'targets_gt.py',site,prior):continue
            cpu('prepare-'+site+'-'+prior,'prepare_gt.py',site,prior)
            if mesh(site,prior,'gt_judgment_mesh'):cpu('score-gtmesh-'+site+'-'+prior,'score_new.py',site,prior,'gt_judgment_mesh')
            cpu('metrics-'+site+'-'+prior,'collect.py',site,prior)
            cpu('figures01-'+site+'-'+prior,'figures.py',site,prior,'01')
        dump(O/'queue/stage1_done.json',dict(at=now(),scientific_verdict=None))
    else:raise ValueError(mode)
if __name__=='__main__':main(*sys.argv[1:])
