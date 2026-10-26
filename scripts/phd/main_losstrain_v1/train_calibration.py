"""Host stdlib: four prescribed 3000-step calibrations, two GPU lanes.

Checks all six current/mask gates. Only OOM gets one identical-config retry.
No GT geometry or evaluation score enters strength selection.
"""
import concurrent.futures
import datetime
import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path
import check_current_gpu as C
P=C.P;OUT=C.OUT;REPO=C.REPO
STOP=threading.Event()
RUNS=[dict(name='lt_cal_dyn_x1',mode='dynamic',mult=1.,gpu=0),
      dict(name='lt_cal_current',mode='current',mult=1.,gpu=1),
      dict(name='lt_cal_dyn_xthird',mode='dynamic',mult=1/3,gpu=0),
      dict(name='lt_cal_dyn_x3',mode='dynamic',mult=3.,gpu=1)]
SCHEDULE=['--iterations','3000','--test_iterations','3000','--save_iterations','3000',
    '--jbgs_log_interval','100','--jbgs_readout_interval','3000','--jbgs_snapshot_iterations','3000','--jbgs_dump_iterations','3000']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def now():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()

def gates():
    for s,p in P.UNITS6:
        assert json.loads((OUT/f'checks/current_direct_v1/comparison_{s}_{p}.json').read_text())['status']=='PASS'
        assert json.loads((OUT/f'checks/depth_direct_v2/{s}_{p}/probe/depth_masks.json').read_text())['status']=='PASS'
    assert json.loads((OUT/'direct_stage1_v2/gates.json').read_text())['gate']=='PASS'
    assert json.loads((OUT/'checks/loss_cpu.json').read_text())['gate']=='PASS'
    assert json.loads((OUT/'checks/direct_stage1/monitor_check.json').read_text())['status']=='PASS'
    cfg=REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json'
    assert sha(cfg)==json.loads(cfg.with_suffix('.lock.json').read_text())['sha256']
    return sha(cfg)

def run(r):
    if STOP.is_set():return
    site='B173nb_b10';prior='ALS';unit=OUT/'runs'/site/(r['name']+'_ALS_s0')
    unit.mkdir(parents=True,exist_ok=False)
    for attempt in [0,1]:
        sub=unit/f'attempt_{attempt}';sub.mkdir()
        model=P.to_container(sub/'model')
        args=P.train_args(site,prior,model,sw_off=['judgment'],schedule=SCHEDULE)
        args+=['--jbgs_sw_depth_loss',r['mode'],'--jbgs_vfile_dir','/o/direct_stage1_v2/B173nb_b10__ALS',
            '--jbgs_vfile_vprior','gt','--jbgs_depth_lambda',str(.0025*r['mult']),
            '--jbgs_lt_monitor','1','--jbgs_lt_gradient_from','2901','--jbgs_lt_gradient_to','3000',*P.RECORDS]
        name='jbgs-lt-'+r['name'].replace('_','-')+f'-a{attempt}'
        command=P.docker(name,r['gpu'],'r17',site,['train.py',*args]);command[2:2]=['--memory','48g']
        save(sub/'command.json',command);start=time.monotonic();stamp=now();peak=0
        with (sub/'run.log').open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            while process.poll() is None:
                smi=subprocess.run(['nvidia-smi','-i',str(r['gpu']),'--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
                try:peak=max(peak,float(smi.stdout.strip()))
                except ValueError:pass
                time.sleep(5)
        rc=process.returncode
        receipt=dict(run=r,attempt=attempt,exit_code=rc,started_at=stamp,finished_at=now(),seconds=time.monotonic()-start,
            gpu_peak_total_MiB=peak,config_sha256=gates(),
            source_sha256={f:sha(P.SRC['r17']/f) for f in ['jbgs_judgment.py','train.py']},scientific_verdict=None)
        save(sub/'receipt.json',receipt);print(r['name'],'exit',rc,'seconds',round(receipt['seconds'],1),flush=True)
        if rc:
            oom=(sub/'model/monitor/oom_record.json').exists() or 'out of memory' in (sub/'run.log').read_text().lower()
            if oom and attempt==0:continue
            STOP.set();save(OUT/'checks/calibration_STOP.json',dict(run=r,attempt=attempt,reason='OOM twice' if oom else 'execution/health error',path=str(sub),at=now(),scientific_verdict=None))
            return
        ply=sub/'model/point_cloud/iteration_3000/point_cloud.ply'
        assert ply.is_file(),'completed training checkpoint missing'
        # Post-training all-view observation: fixed mode only loads the shared
        # sigma/maps; no optimizer and no protection/re-read changes to PLY.
        readargs=P.train_args(site,prior,P.to_container(sub/'readout_init'),sw_off=['judgment'],schedule=P.SP.SCHEDULE_PROBE)
        readargs+=['--jbgs_sw_depth_loss','fixed','--jbgs_vfile_dir','/o/direct_stage1_v2/B173nb_b10__ALS','--jbgs_vfile_vprior','now',*P.RECORDS]
        entry=['/repo/scripts/phd/main_losstrain_v1/calibration_readout.py','--readout_ply',P.to_container(ply),
            '--readout_json',P.to_container(sub/'metrics.json'),'--',*readargs]
        cmd=P.docker(name+'-readout',r['gpu'],'r17',site,entry);cmd[2:2]=['--memory','48g'];save(sub/'readout_command.json',cmd)
        with (sub/'readout.log').open('w') as log:rc2=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        if rc2:
            STOP.set();save(OUT/'checks/calibration_STOP.json',dict(run=r,reason='readout error',path=str(sub),at=now(),scientific_verdict=None));return
        save(unit/'PASS.json',dict(attempt=attempt,model=str(sub/'model'),metrics=str(sub/'metrics.json'),receipt=str(sub/'receipt.json'),scientific_verdict=None))
        return

def lane(gpu):
    for r in RUNS:
        if r['gpu']==gpu:run(r)

if __name__=='__main__':
    cfg=gates()
    assert not (OUT/'checks/calibration_start.json').exists()
    save(OUT/'checks/calibration_start.json',dict(at=now(),config_sha256=cfg,runs=RUNS,
        source_sha256={str(f.relative_to(REPO)):sha(f) for f in [Path(__file__),Path(__file__).with_name('calibration_readout.py'),Path(__file__).with_name('select_lambda.py'),P.SRC['r17']/'train.py',P.SRC['r17']/'jbgs_judgment.py']},scientific_verdict=None))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        for f in [pool.submit(lane,gpu) for gpu in [0,1]]:f.result()
    if STOP.is_set():raise SystemExit('calibration stopped; see checks/calibration_STOP.json')
    print('four calibration trainings and readouts complete',flush=True)
