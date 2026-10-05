"""Resume only uncompleted branches after the diagnosed DA3 dtype check failure."""
import argparse
import hashlib
import json
from pathlib import Path
import traceback
from run_queue import Queue, DA3_IMAGE, read, atomic


class RecoveryQueue(Queue):
    def __init__(self, attempt, recovery):
        super().__init__(attempt)
        self.recovery = Path(recovery).resolve()
        self.driver = self.recovery / 'source'
        self.records = read(self.recovery / 'previous_status.json')['jobs']
        self.retry = self.root / 'R2' / ('da3_inference_' + self.recovery.name)

    def status(self, state, **kw):
        super().status(state, recovery=str(self.recovery.relative_to(self.root)), **kw)
        atomic(self.recovery / 'status.json', read(self.root / 'execution/status.json'))

    def docker(self, label, out, mounts, image, argv, **kw):
        old = self.root / 'R2/da3_inference/result'
        mounts = [(self.retry / 'result' if Path(p) == old else p, target)
                  for p, target in mounts]
        return super().docker(label, out, mounts, image, argv, **kw)

    def r2_inference(self):
        region = 'R2'
        mounts = [(self.driver/'da3', '/drivers'), (self.driver/'da3_config.json', '/config.json'),
                  (self.driver/'da3_policy.json', '/batch_policy.json'),
                  (self.root/region/'da3_input/split.json', '/split.json'),
                  (self.root/region/'da3_input/batches', '/batches'),
                  (self.base/'sources/DA3NESTED-GIANT-LARGE', '/model'),
                  (self.base/'sources/GeoGS/preprocessing/get_da3_depth_with_colmap.py', '/official.py'),
                  (self.base/'runtime/da3/acquisition.json', '/acquisition.json')]
        for label, out, extra in [
            ('da3_pose_preflight', self.recovery/'R2_pose_preflight', ['--batch-id', '10']),
            ('da3_inference_recovery', self.retry, [])
        ]:
            self.docker(label, out, mounts, DA3_IMAGE, ['/drivers/infer.py']+extra,
                        gpu=True, ram=32, env={'HF_HOME':'/tmp/hf','MPLCONFIGDIR':'/tmp/mpl'})
            receipt = read(out/'result/receipt.json')
            assert receipt['status'] == 'PASS_TRAIN_ONLY_DEPTH_GENERATION'
            assert receipt['full_region'] is (not extra)

    def run(self):
        self.region = 'R2'
        self.r2_inference()
        self.refinement('R2', 'da3')
        for region in ['R3', 'R4', 'R5']:
            self.region = region
            self.da3(region)
            self.refinement(region, 'da3')
        for region in ['R1', 'R2', 'R3', 'R4', 'R5']:
            self.region = region
            assert read(self.root/region/'masks/receipt.json')['status'] == 'PASS'
            self.refinement(region, 'local_prior0')
        self.region = self.job = None
        self.status('COMPLETE')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt')
    parser.add_argument('recovery')
    args = parser.parse_args()
    q = RecoveryQueue(args.attempt, args.recovery)
    for relative, digest in read(q.recovery/'source_hashes.json').items():
        assert hashlib.sha256((q.driver/relative).read_bytes()).hexdigest() == digest
    try:
        q.run()
    except Exception:
        q.status('FAILED', error=traceback.format_exc())
        atomic(q.recovery/'failure.json', dict(region=q.region, job=q.job,
               error=traceback.format_exc(), scientific_verdict=None))
        raise


if __name__ == '__main__':
    main()
