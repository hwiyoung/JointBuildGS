"""Durable sequential GPU queue, exact receipts and no automatic failed-run retries."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

TRAIN_IMAGE='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
DA3_IMAGE='sha256:4130d2597c2c3c2804a7cacb8302be948314bc37ba81a1a21383e1c8b7fbba73'
CPU_IMAGE='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'

def read(p): return json.loads(Path(p).read_text())
def atomic(p,obj):
    p=Path(p);t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2,ensure_ascii=False));t.replace(p)

class Queue:
    def __init__(self,attempt):
        self.root=Path(attempt).resolve();self.cfg=read(self.root/'config.json');self.art=Path(self.cfg['artifact_root'])
        self.driver=self.root/'execution/source';self.snapshot=self.root/'snapshot';self.records=[]
        self.base=self.art/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1'
        self.gpu='1';self.region=None;self.job=None
    def status(self,state,**kw):
        atomic(self.root/'execution/status.json',dict(state=state,region=self.region,job=self.job,
            jobs=self.records,updated_unix=time.time(),scientific_verdict=None,**kw))
    def paths(self,region):
        if region=='R1':
            p=self.art/self.cfg['r1_prep_relative'];r=self.art/self.cfg['r1_run_relative']
            return p/'result/input',p/'finalize_20260916T131410Z_ZpnUStaZ/runtime',r/'anchor'
        p=self.root/region
        return p/'preparation/input',p/'runtime',p/'anchor'
    def stage_path(self,region,label):
        return self.root/region/label
    def da3_result_path(self,region):
        return self.root/region/'da3_inference/result'
    def wait_inputs(self,region):
        if region=='R1': return
        while not (self.root/region/'preparation_complete.json').exists():
            if (self.root/'preparation_failure.json').exists():raise RuntimeError('CPU input preparation failed')
            self.status('WAITING_INPUTS');time.sleep(30)
    def available(self,ram_gib,gpu):
        while True:
            mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
            enough=mem>(ram_gib+4)*1024**2
            if gpu:
                row=subprocess.check_output(['nvidia-smi','-i',self.gpu,'--query-gpu=memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
                free,util=map(int,row.split(','));enough=enough and free>=23000 and util<=5
            if enough:return
            self.status('WAITING_RESOURCES');time.sleep(30)
    def docker(self,label,out,mounts,image,argv,*,gpu=False,ram=12,env=None,workdir=None):
        self.job=label;out.mkdir(parents=True,exist_ok=False);self.available(ram,gpu)
        command=['docker','run','--rm','--network','none','--cpus','4' if not gpu else '8','--memory',f'{ram}g',
            '--memory-swap',f'{ram}g','--shm-size','4g','--user',f'{os.getuid()}:{os.getgid()}',
            '-e','PYTHONDONTWRITEBYTECODE=1','-e','OMP_NUM_THREADS=4','-e','OPENBLAS_NUM_THREADS=2']
        command+=['--gpus','device='+self.gpu] if gpu else ['--runtime','runc','-e','NVIDIA_VISIBLE_DEVICES=void']
        if workdir:command+=['--workdir',workdir]
        for k,v in (env or {}).items():command+=['-e',k+'='+v]
        for host,target in mounts:command+=['--mount',f'type=bind,source={host},target={target},readonly']
        command+=['--mount',f'type=bind,source={out},target=/output', '--entrypoint','python',image]+argv
        # Inference expects an empty /out; logs live beside that directory.
        if image==DA3_IMAGE:
            payload=out/'result';payload.mkdir();command[command.index(image):command.index(image)]=[]
            ix=command.index('--entrypoint');command[ix:ix]=['--mount',f'type=bind,source={payload},target=/out']
        atomic(out/'command.json',command);self.status('RUNNING')
        start=time.time()
        with (out/'driver.log').open('x') as log:
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            atomic(out/'process.json',dict(pid=p.pid,started_unix=start,region=self.region,job=label))
            with (out/'host_gpu.csv').open('x') as usage:
                while p.poll() is None:
                    if gpu:subprocess.run(['nvidia-smi','-i',self.gpu,'--query-gpu=timestamp,uuid,memory.used,utilization.gpu','--format=csv,noheader'],stdout=usage,stderr=subprocess.DEVNULL);usage.flush()
                    time.sleep(10)
        row=dict(region=self.region,job=label,exit_code=p.returncode,seconds=time.time()-start,
            output=str(out.relative_to(self.root)),status='PASS' if p.returncode==0 else 'FAILED')
        self.records.append(row);self.status('RUNNING')
        if p.returncode:raise RuntimeError(f'{self.region}/{label} failed; original log retained at {out}')
    def stage(self,region,label,phase,branch='mvs',iteration=None,trained=None,gate=None):
        inputs,runtime,anchor=self.paths(region);out=self.stage_path(region,label)
        source='anchor' if phase in ('verify','anchor') else 'refinement'
        mounts=[(self.driver,'/driver'),(inputs,'/input'),(runtime,'/runtime'),(runtime/(source+'_source'),'/source'),(self.base/'runtime/weights','/weights')]
        if phase in ('preflight','refinement'):mounts.append((anchor/'model/jbgs_complete/iteration_8000','/anchor'))
        if gate:mounts.append((gate,'/gate'))
        if trained:mounts.append((trained,'/trained'))
        if branch=='da3':mounts.append((self.da3_result_path(region),'/da3'))
        if branch=='local_prior0':mounts.append((self.root/region/'masks','/masks'))
        argv=['/driver/phase.py',phase]+(['--iteration',str(iteration)] if iteration else [])
        self.docker(label,out,mounts,TRAIN_IMAGE,argv,gpu=phase!='verify',ram=56 if phase=='extract' else 32 if phase!='verify' else 8,
            env={'LD_PRELOAD':'/opt/geogs/lib/libstdc++.so.6','JBGS_COMPARISON_BRANCH':branch},workdir='/source')
        assert read(out/'receipt.json')['status']=='PASS'
    def da3(self,region):
        inputs,_,_=self.paths(region);root=self.root/region
        self.docker('da3_input',root/'da3_input',[(self.snapshot,'/repo'),(self.driver,'/driver'),(inputs,'/input')],CPU_IMAGE,
            ['/driver/prepare_da3.py'],env={'PYTHONPATH':'/repo'})
        mounts=[(self.driver/'da3','/drivers'),(self.driver/'da3_config.json','/config.json'),
            (self.driver/'da3_policy.json','/batch_policy.json'),(root/'da3_input/split.json','/split.json'),
            (root/'da3_input/batches','/batches'),(self.base/'sources/DA3NESTED-GIANT-LARGE','/model'),
            (self.base/'sources/GeoGS/preprocessing/get_da3_depth_with_colmap.py','/official.py'),
            (self.base/'runtime/da3/acquisition.json','/acquisition.json')]
        self.docker('da3_inference',root/'da3_inference',mounts,DA3_IMAGE,['/drivers/infer.py'],gpu=True,ram=32,
            env={'HF_HOME':'/tmp/hf','MPLCONFIGDIR':'/tmp/mpl'})
        assert read(root/'da3_inference/result/receipt.json')['status']=='PASS_TRAIN_ONLY_DEPTH_GENERATION'
    def refinement(self,region,branch):
        self.stage(region,branch+'_preflight','preflight',branch)
        self.stage(region,branch,'refinement',branch,gate=self.stage_path(region,branch+'_preflight'))
        self.stage(region,'extract_'+branch,'extract',branch,30000,trained=self.stage_path(region,branch))
    def run(self):
        self.status('RUNNING')
        # Fill basic controls before adding the two interventions.
        for region in ['R2','R3','R4','R5']:
            self.region=region;self.wait_inputs(region)
            self.stage(region,'verify','verify');self.stage(region,'anchor','anchor')
            self.refinement(region,'mvs')
            self.stage(region,'extract_anchor','extract',iteration=8000,trained=self.root/region/'anchor')
        for region in self.cfg['regions']:
            self.region=region;(self.root/region).mkdir(exist_ok=True)
            if region=='R1':self.stage(region,'verify','verify')
            self.da3(region);self.refinement(region,'da3')
        # These jobs must never infer a correction label from disagreement alone.
        pending=[]
        for region in self.cfg['regions']:
            self.region=region;mask=self.root/region/'masks/receipt.json'
            if not mask.exists():pending.append(region);continue
            self.refinement(region,'local_prior0')
        self.region=None;self.job=None
        self.status('WAITING_REGION_REVIEW' if pending else 'COMPLETE',pending_local_prior0=pending)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('attempt');a=ap.parse_args();q=Queue(a.attempt)
    try:q.run()
    except Exception:
        q.status('FAILED',error=traceback.format_exc())
        atomic(q.root/'execution/failure.json',dict(region=q.region,job=q.job,error=traceback.format_exc(),scientific_verdict=None))
        raise
if __name__=='__main__':main()
