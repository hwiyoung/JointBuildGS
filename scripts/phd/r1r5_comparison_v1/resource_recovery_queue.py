"""One allocator-only R2 retry, then independent remaining conditions once each."""
import argparse
import hashlib
from pathlib import Path
import traceback
from run_queue import Queue, TRAIN_IMAGE, atomic, read


class ResourceRecovery(Queue):
    def __init__(self, root, recovery):
        super().__init__(root)
        self.recovery=Path(recovery).resolve();self.driver=self.recovery/'source'
        self.plan=read(self.recovery/'plan.json')
        self.records=read(self.recovery/'previous_status.json')['jobs'];self.failures=[]

    def stage_path(self,region,label):
        return self.root/self.plan['artifact_overrides'].get(region,{}).get(label,f'{region}/{label}')

    def da3_result_path(self,region):
        if region=='R2':return self.root/'R2/da3_inference_recovery_20260918T010840Z/result'
        return super().da3_result_path(region)

    def status(self,state,**kw):
        super().status(state,recovery=str(self.recovery.relative_to(self.root)),
                       failures=self.failures,**kw)
        atomic(self.recovery/'status.json',read(self.root/'execution/status.json'))

    def docker(self,label,out,mounts,image,argv,**kw):
        if image==TRAIN_IMAGE and kw.get('gpu'):
            kw['env']={**kw.get('env',{}),'PYTORCH_CUDA_ALLOC_CONF':'backend:cudaMallocAsync',
                       'JBGS_CUDA_ALLOCATOR_OVERRIDE':'backend:cudaMallocAsync'}
        return super().docker(label,out,mounts,image,argv,**kw)

    def run(self):
        for branch,regions in [('da3',['R2','R3','R4','R5']),
                               ('local_prior0',['R1','R2','R3','R4','R5'])]:
            for region in regions:
                self.region=region
                try:
                    if branch=='da3' and region!='R2':self.da3(region)
                    if branch=='local_prior0':assert read(self.root/region/'masks/receipt.json')['status']=='PASS'
                    self.refinement(region,branch)
                except Exception:
                    failure=dict(region=region,branch=branch,job=self.job,error=traceback.format_exc())
                    self.failures.append(failure)
                    atomic(self.recovery/f'{region}_{branch}_failure.json',dict(**failure,scientific_verdict=None))
                    self.status('RUNNING')
        self.region=self.job=None
        self.status('COMPLETE_WITH_FAILURES' if self.failures else 'COMPLETE')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('attempt');ap.add_argument('recovery');a=ap.parse_args()
    q=ResourceRecovery(a.attempt,a.recovery)
    for name,digest in read(q.recovery/'source_hashes.json').items():
        assert hashlib.sha256((q.driver/name).read_bytes()).hexdigest()==digest
    try:q.run()
    except Exception:
        q.status('FAILED',error=traceback.format_exc());raise
