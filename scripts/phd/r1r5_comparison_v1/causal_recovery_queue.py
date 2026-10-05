"""Recover R2 and run a same-device R1 keep/release pair in immutable outputs."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import threading
import time
import traceback

from parallel_queue import Manager, MemorySlots, Worker
from resume_parallel import ResumeWorker
from run_queue import read, atomic, TRAIN_IMAGE, CPU_IMAGE


def receipt_name(condition):
    return '_'.join([condition['region'],condition['branch'],condition['tag']])+'_receipt.json'


class CausalWorker(ResumeWorker):
    condition = None

    def stage_path(self, region, label):
        return self.root / region / (label + '_' + self.condition['tag'])

    def da3_result_path(self, region):
        assert region == 'R2'
        return self.root / self.manager.plan['da3_input']

    def docker(self, label, out, mounts, image, argv, **kwargs):
        if image == TRAIN_IMAGE:
            env = dict(kwargs.get('env', {}))
            env.update(JBGS_LOCAL_PRIOR_INSIDE=str(self.condition['inside_multiplier']),
                       JBGS_MEMORY_RASTER=str(int(self.condition['memory_raster'])),
                       JBGS_RASTER_TRACE='/output/raster_memory_trace.jsonl',
                       JBGS_EXTRA_CAPTURES=','.join(map(str,self.condition['captures'])))
            if self.region == 'R1':env['JBGS_CAUSAL_PROBES']='/driver/r1_probes.json'
            kwargs['env'] = env
        return super().docker(label, out, mounts, image, argv, **kwargs)

    def run(self):
        for condition in self.manager.plan['workers'][self.gpu]:
            self.condition = condition
            self.region = region = condition['region'];branch=condition['branch']
            self.manager.pending.get_nowait()
            try:
                if branch == 'da3':
                    assert read(self.da3_result_path(region)/'receipt.json')['status']=='PASS_TRAIN_ONLY_DEPTH_GENERATION'
                self.stage(region,branch+'_preflight','preflight',branch)
                gate=self.stage_path(region,branch+'_preflight')
                self.stage(region,branch,'refinement',branch,gate=gate)
                trained=self.stage_path(region,branch)
                self.stage(region,'extract_'+branch,'extract',branch,30000,trained=trained)
                atomic(self.manager.folder/receipt_name(condition),dict(status='PASS',
                    condition=condition,trained=str(trained.relative_to(self.root)),
                    extracted=str(self.stage_path(region,'extract_'+branch).relative_to(self.root)),
                    scientific_verdict=None))
                if region=='R2':self.manager.publish_recovery(self,branch)
            except Exception:
                self.manager.fail(self,branch+'_'+condition['tag'],traceback.format_exc())
        if self.gpu=='0':
            paired=[c for c in self.manager.plan['workers']['0'] if c['region']=='R1']
            if all((self.manager.folder/receipt_name(c)).exists() for c in paired):
                try:
                    self.region='R1'
                    self.docker('paired_summary',self.manager.folder/'r1_pair_summary',
                                [(self.driver,'/driver'),(self.root,'/run')],CPU_IMAGE,
                                ['/driver/summarize_causal_pair.py'],ram=4)
                except Exception:self.manager.fail(self,'paired_summary',traceback.format_exc())
        self.region=self.job=None;self.status('COMPLETE')


class CausalManager(Manager):
    def publish_recovery(self,worker,branch):
        with self.lock:
            path=self.root/'execution/artifact_overrides.json';overrides=read(path)
            for name in [branch,branch+'_preflight','extract_'+branch]:
                overrides.setdefault('R2',{})[name]=str(worker.stage_path('R2',name).relative_to(self.root))
            atomic(path,overrides)
            resolved=[f for f in self.failures if f['region']=='R2' and f['branch']==branch]
            atomic(self.folder/('resolved_R2_'+branch+'.json'),dict(status='RECOVERED',
                   previous_failures=resolved,condition=worker.condition,scientific_verdict=None))
            self.failures=[f for f in self.failures if f not in resolved]
            self.update(worker,'RECOVERED')

    def run_owned(self):
        for name,digest in read(self.folder/'source_hashes.json').items():
            assert hashlib.sha256((self.folder/'source'/name).read_bytes()).hexdigest()==digest,name
        qa=read(self.folder/'raster_validation_v2/receipt.json')
        assert qa['status']=='PASS_NATIVE_STRIP_OUTPUT_GRADIENT_PARITY'
        assert qa['source_sha256']==hashlib.sha256((self.folder/'source/memory_raster.py').read_bytes()).hexdigest()
        self.memory=MemorySlots(adopted=0)
        self.workers={str(g):CausalWorker(self,g) for g in [0,1]}
        threads=[threading.Thread(target=w.run,name='gpu'+g) for g,w in self.workers.items()]
        for t in threads:t.start()
        for t in threads:t.join()
        self.state='COMPLETE_WITH_FAILURES' if self.failures else 'COMPLETE'
        self.update(self.workers['0'],'COMPLETE')
        receipts=[self.folder/receipt_name(c) for jobs in self.plan['workers'].values() for c in jobs]
        atomic(self.folder/'receipt.json',dict(status='PASS' if all(p.exists() and read(p)['status']=='PASS' for p in receipts) else 'PARTIAL',
            conditions=[read(p) for p in receipts if p.exists()],scientific_verdict=None))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('attempt',type=Path);parser.add_argument('folder',type=Path);args=parser.parse_args()
    root=args.attempt.resolve();folder=args.folder.resolve()
    atomic(folder/'status.json',dict(state='WAITING_PREVIOUS_QUEUE',scientific_verdict=None,updated_unix=time.time()))
    with (root/'execution/parallel_scheduler.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous=read(root/'execution/status.json')
        assert previous['state'] in ('COMPLETE','COMPLETE_WITH_FAILURES'),previous['state']
        with (folder/'previous_status.json').open('x') as f:json.dump(previous,f,indent=2)
        manager=CausalManager(root,folder)
        try:manager.run_owned()
        except Exception:
            atomic(folder/'scheduler_failure.json',dict(status='FAIL',error=traceback.format_exc(),scientific_verdict=None));raise


if __name__=='__main__':main()
