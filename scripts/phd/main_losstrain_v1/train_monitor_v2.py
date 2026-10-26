"""Authorized continuation: fresh dynamic GT, then soft/current arms and remaining units."""
import argparse,concurrent.futures,fcntl,json,subprocess,time
import train_full as F
P,OUT,REPO,save,sha,now=F.P,F.OUT,F.REPO,F.save,F.sha,F.now

def stopped():return F.STOP.is_set() or (OUT/'checks/full_monitor_v2_STOP.json').exists()

def mark_stop(run,attempt,reason):
    F.STOP.set();row=dict(run=run,attempt=attempt,reason=reason,at=now(),scientific_verdict=None)
    save(F.root_of(run)/f'STOP_attempt_{attempt}.json',row)
    save(OUT/'checks/full_monitor_v2_STOP.json',row)

F.mark_stop=mark_stop

def wait_fixed():
    fixed=OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0'
    while not (fixed/'post_PASS.json').exists():
        if stopped():return False
        for p in [fixed/'post_attempt_1_receipt.json',fixed/'run_attempt_1_receipt.json']:
            if p.exists() and json.loads(p.read_text())['exit_code']:
                mark_stop(dict(site='B173nb_b10',prior='ALS',variant='lt_fixgt'),1,'inflight fixed postprocessing failure')
                return False
        time.sleep(5)
    return True

def gates(batch):
    F.C.gates()
    root=OUT/'checks/monitor_v2';approval=json.loads((root/'approval.json').read_text())
    assert approval['status']=='AUTHORIZED' and not approval['nojudge_retraining']
    for p,h in approval['superseded_stops'].items():assert sha(OUT/p)==h
    assert json.loads((root/'validation.json').read_text())['status']=='PASS'
    assert json.loads((root/'gpu_probe/model/monitor/monitor_v2_probe.json').read_text())['status']=='PASS'
    assert (root/'commit.json').exists()
    assert not stopped()
    if batch!='first':assert json.loads((OUT/'checks/interim.json').read_text())['status']=='PASS'
    if batch=='optional':assert all((F.root_of(r)/'post_PASS.json').exists() for r in F.runs_for('remaining'))
    return json.loads((OUT/'checks/lambda_selection.json').read_text())['selected_lambda']

def run(r,gpu,lam):
    if stopped():return
    unit=F.root_of(r)
    if (unit/'post_PASS.json').exists():return
    first=0
    if unit.exists():
        assert r==dict(site='B173nb_b10',prior='ALS',variant='lt_dyngt')
        assert (unit/'STOP_attempt_1.json').exists() and not (unit/'attempt_2').exists()
        first=2
    else:unit.mkdir(parents=True)
    for attempt in [first,first+1]:
        if stopped():return
        sub=unit/f'attempt_{attempt}';sub.mkdir();mode,validity=F.MODES[r['variant']]
        key=r['site']+'__'+r['prior']
        args=P.train_args(r['site'],r['prior'],P.to_container(sub/'model'),sw_off=['judgment'])
        args+=['--jbgs_sw_depth_loss',mode,'--jbgs_vfile_dir','/o/direct_stage1_v2/'+key,
            '--jbgs_vfile_vprior',validity,'--jbgs_depth_lambda',str(lam),
            '--jbgs_lt_monitor','1','--jbgs_lt_monitor_v2','1',
            '--jbgs_lt_nojudge_inventory','/o/checks/monitor_v2/nojudge/'+key+'.json',
            '--jbgs_lt_diagnostic_cells','/o/direct_stage1_v2/'+key+'/evaluation.npz',*P.RECORDS]
        command=P.docker('jbgs-lt-v2-full-'+str(gpu),gpu,'r17',r['site'],['train.py',*args]);command[2:2]=['--memory','48g']
        binding=dict(source_sha256={p:sha(P.SRC['r17']/p) for p in ['train.py','jbgs_judgment.py']},
            config_sha256=sha(REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json'))
        save(sub/'start_binding.json',dict(**binding,at=now(),scientific_verdict=None));save(sub/'command.json',command)
        start=time.monotonic();stamp=now();peak=0.
        with (sub/'run.log').open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            while process.poll() is None:
                q=subprocess.run(['nvidia-smi','-i',str(gpu),'--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
                try:peak=max(peak,float(q.stdout.strip()))
                except ValueError:pass
                time.sleep(5)
        rc=process.returncode
        save(sub/'receipt.json',dict(run=r,gpu=gpu,attempt=attempt,exit_code=rc,started_at=stamp,finished_at=now(),
            seconds=time.monotonic()-start,gpu_peak_total_MiB=peak,lambda_depth=lam,**binding,scientific_verdict=None))
        print(unit.name,'attempt',attempt,'training exit',rc,flush=True)
        if rc:
            oom='out of memory' in (sub/'run.log').read_text().lower()
            if oom and attempt==first:continue
            mark_stop(r,attempt,'OOM twice: NO RESULT' if oom else 'execution or monitor-v2 health error');return
        assert (sub/'model/point_cloud/iteration_30000/point_cloud.ply').is_file()
        save(unit/'PASS.json',dict(attempt=attempt,model=str(sub/'model'),at=now(),monitor_policy='v2',scientific_verdict=None))
        # The old fixed process predates the file lock, so let its post finish first.
        if not wait_fixed():return
        with (OUT/'checks/tsdf.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if not stopped():F.post(r,gpu,unit)
        return

def lane(gpu,runs,lam):
    for r in runs:
        if stopped():return
        run(r,gpu,lam)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('batch',choices=['first','remaining','optional']);a=ap.parse_args()
    lam=gates(a.batch);root=OUT/'checks/monitor_v2';start=root/f'batch_{a.batch}_start.json'
    assert not start.exists();runs=F.runs_for(a.batch)
    save(start,dict(at=now(),runs=runs,lambda_depth=lam,scientific_verdict=None))
    if a.batch=='first':
        run(runs[1],1,lam)
        if not stopped() and wait_fixed():
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                for future in [pool.submit(run,runs[2],0,lam),pool.submit(run,runs[3],1,lam)]:future.result()
    else:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            for future in [pool.submit(lane,g,runs[g::2],lam) for g in [0,1]]:future.result()
    if stopped():raise SystemExit('monitor-v2 batch stopped; checks/full_monitor_v2_STOP.json')
    assert all((F.root_of(r)/'post_PASS.json').exists() for r in runs)
    save(OUT/f'checks/batch_{a.batch}_PASS.json',dict(at=now(),completed=len(runs),monitor_policy='v2',scientific_verdict=None))

if __name__=='__main__':main()
