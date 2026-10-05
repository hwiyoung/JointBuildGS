"""Receipt-aware continuation after scheduler failure; display-aware GPU admission."""
import argparse
import fcntl
import hashlib
from pathlib import Path
import subprocess
import threading
import time
import traceback
from parallel_queue import Manager, MemorySlots, Worker
from run_queue import read, atomic


def gpu_admissible(free_mib, utilization, processes, gpu):
    if free_mib < 23000:
        return False
    if str(gpu) == '0':
        return all(p in ['/usr/libexec/gnome-remote-desktop-daemon', '/usr/share/rustdesk/rustdesk'] for p in processes)
    return utilization <= 5 and not processes


class ResumeWorker(Worker):
    def stage_path(self, region, label):
        return self.root/self.manager.plan.get('artifact_overrides',{}).get(region,{}).get(label,f'{region}/{label}')

    def available(self, ram_gib, gpu):
        while True:
            mem=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))
            enough=mem>(ram_gib+4)*1024**2
            if gpu:
                row=subprocess.check_output(['nvidia-smi','-i',self.gpu,
                    '--query-gpu=memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
                free,util=map(int,row.split(','))
                processes=subprocess.check_output(['nvidia-smi','-i',self.gpu,
                    '--query-compute-apps=process_name','--format=csv,noheader'],text=True).splitlines()
                enough=enough and gpu_admissible(free,util,processes,self.gpu)
            if enough:return
            self.status('WAITING_RESOURCES');time.sleep(30)

    def run_condition(self, region, branch):
        self.region=region
        try:
            trained=self.stage_path(region,branch)
            if not (trained/'receipt.json').exists():
                if branch=='da3':self.da3(region)
                else:assert read(self.root/region/'masks/receipt.json')['status']=='PASS'
                gate=self.stage_path(region,branch+'_preflight')
                if (gate/'receipt.json').exists():assert read(gate/'receipt.json')['status']=='PASS'
                else:self.stage(region,branch+'_preflight','preflight',branch)
                self.stage(region,branch,'refinement',branch,gate=gate)
            assert read(trained/'receipt.json')['status']=='PASS'
            extraction=self.stage_path(region,'extract_'+branch)
            assert not extraction.exists(), 'This continuation never overwrites a stage'
            self.stage(region,'extract_'+branch,'extract',branch,30000,trained=trained)
        except Exception:self.manager.fail(self,branch,traceback.format_exc())


class ResumeManager(Manager):
    def run(self):
        lockfile=(self.root/'execution/parallel_scheduler.lock').open('a')
        fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name,digest in read(self.folder/'source_hashes.json').items():
            assert hashlib.sha256((self.folder/'source'/name).read_bytes()).hexdigest()==digest
        self.failures=[f for f in self.previous.get('failures',[]) if f['branch']!='scheduler']
        self.memory=MemorySlots(adopted=0)
        self.workers={str(g):ResumeWorker(self,g) for g in [1,0]}
        threads=[threading.Thread(target=w.run,name='gpu'+g) for g,w in self.workers.items()]
        for t in threads:t.start()
        for t in threads:t.join()
        self.state='COMPLETE_WITH_FAILURES' if self.failures else 'COMPLETE'
        self.update(self.workers['0'],'COMPLETE')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('attempt');ap.add_argument('recovery');a=ap.parse_args()
    manager=ResumeManager(a.attempt,a.recovery)
    try:manager.run()
    except Exception:
        atomic(manager.folder/'scheduler_failure.json',dict(status='FAILED',error=traceback.format_exc(),scientific_verdict=None));raise
