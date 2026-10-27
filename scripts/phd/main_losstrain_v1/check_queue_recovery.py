"""Exercise scheduler failures with recorded monitors, without launching training."""
import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
OUT = Path('/out')


def function(filename, name, scope):
    tree = ast.parse((HERE / filename).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), scope)
    return scope[name]


class Recovery(unittest.TestCase):
    def test_first_batch_reaches_scores_and_figures_before_new_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            runs=[dict(run=i) for i in range(24)]
            policy={'enabled':True}
            schedule=function('continue_resource_v1.py','readout_schedule',
                              dict(ROOT=root,RUNS=runs,read=lambda p,*a: policy if p.name=='first_batch_priority.json' else {}))
            # A mesh-ready first arm must be scored before the next TSDF.
            state=schedule(runs[1:],runs[:1])
            self.assertTrue(state['active'])
            self.assertFalse(state['post_may_start'])
            self.assertEqual(state['post'],runs[1:4])
            self.assertEqual(state['measure'],runs[:1])
            # First-batch figures still need RAM after all four scores complete.
            state=schedule(runs[4:],[])
            self.assertTrue(state['active'])
            self.assertEqual(state['post'],[])
            # A generated interim releases all remaining authorized work.
            (root/'interim_report_generated.json').write_text('{}')
            state=schedule(runs[4:],[])
            self.assertFalse(state['active'])
            self.assertEqual(state['post'],runs[4:])

    def test_no_priority_policy_preserves_original_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            runs=[dict(run=i) for i in range(24)]
            state=function('continue_resource_v1.py','readout_schedule',
                           dict(ROOT=Path(directory),RUNS=runs,read=lambda *a:{}))(runs,runs[:1])
            self.assertFalse(state['active'])
            self.assertEqual(state['post'],runs)
            self.assertTrue(state['post_may_start'])

    def test_handoff_preserves_new_error_during_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stop = root / 'training_STOP.json'
            stop.write_text('{"status":"OPERATIONAL_QUEUE_HANDOFF"}')
            reads = []
            def read(path):
                if path.name == 'validation.json': return {'status': 'PASS'}
                if path.name == 'state.json': return {'gpu_jobs': {}, 'cpu_measurement': None}
                if path.name == 'training_STOP.json':
                    reads.append(path)
                    if len(reads) == 2: path.write_text('{"reason":"new nonfinite failure"}')
                    return json.loads(path.read_text())
                raise AssertionError(path)
            scope = dict(Q=SimpleNamespace(ROOT=root, OUT=root, read=read),
                         fcntl=SimpleNamespace(flock=lambda *a: None, LOCK_EX=1, LOCK_NB=2))
            with self.assertRaises(AssertionError):
                function('resume_tiled_when_idle.py', 'main', scope)()
            self.assertEqual(json.loads(stop.read_text()), {'reason': 'new nonfinite failure'})
            self.assertFalse((root / 'history').exists())

    def test_old_post_admission_does_not_release_new_training(self):
        record = dict(status='ADMITTED', required_GiB=64, required_stable_seconds=60, attempt=2)
        scope = dict(F=SimpleNamespace(root_of=lambda r: Path('/unit')),
                     next_post_mode=lambda u: 'post', next_attempt=lambda u,m: 4,
                     OUT=Path('/out'),policy_for=lambda root:dict(host_available_GiB=64),
                     read=lambda *args: record)
        admitted = function('continue_resource_v1.py', 'post_admitted', scope)
        self.assertFalse(admitted({}))
        record['attempt'] = 4
        self.assertTrue(admitted({}))
        record['status'] = 'WAITING_FOR_MEMORY'
        self.assertFalse(admitted({}))

    def classify(self, stop):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit = root / 'unit'
            monitor = unit / 'attempt_0/model/monitor'
            monitor.mkdir(parents=True)
            (monitor / 'losstrain_health_v2.jsonl').write_text(json.dumps(stop) + '\n')
            written = {}
            calls = []
            scope = dict(json=json, ROOT=root, F=SimpleNamespace(root_of=lambda r: unit, now=lambda: 'test'),
                         next_training_attempt=lambda u: 0, cuda_oom_attempt=lambda s: False,
                         train_attempt=lambda *args: calls.append(args) or False,
                         save=lambda p, d: written.update({p.name: d}))
            function('continue_resource_v1.py', 'train', scope)({}, 0, .0025)
            self.assertEqual(len(calls), 1)
            return written

    def test_recorded_opacity_stop_preserved_without_stopping_other_arms(self):
        path = OUT / 'runs/B173nb_b10/lt_fixgt_LoD2_s0/attempt_0/model/monitor/losstrain_health_v2.jsonl'
        row = json.loads(path.read_text().splitlines()[-1])
        self.assertEqual(row['iteration'], 3100)
        self.assertLess(row['whole_opacity_median'], .05)
        result = self.classify(row)
        self.assertIn('training_health_STOP.json', result)
        self.assertNotIn('training_STOP.json', result)
        self.assertEqual(result['training_health_STOP.json']['criterion_record'], row)

    def test_psnr_stop_preserved(self):
        result = self.classify({'stop': 'training PSNR more than 3 dB below same-iteration nojudge'})
        self.assertIn('training_health_STOP.json', result)
        self.assertNotIn('training_STOP.json', result)

    def test_unknown_error_still_stops_queue(self):
        result = self.classify({'stop': 'nonfinite loss'})
        self.assertIn('training_STOP.json', result)
        self.assertNotIn('training_health_STOP.json', result)

    def test_reporter_survives_stale_idle_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saves = []
            sleeps = []
            def sleep(seconds):
                sleeps.append(seconds)
                (root / 'PARTIAL_NO_RESULT.json').write_text('{}')
            scope = dict(ROOT=root, RUNS=[{}], F=SimpleNamespace(now=lambda: 'test', root_of=lambda r: root / 'unit'),
                         fcntl=SimpleNamespace(flock=lambda *a: None, LOCK_EX=1, LOCK_NB=2),
                         read=lambda *a: {'stops': ['training_STOP.json'], 'gpu_jobs': {}, 'cpu_measurement': None},
                         save=lambda p,d: saves.append(p.name), memory_available_gib=lambda: 0,
                         refresh=lambda: None, time=SimpleNamespace(sleep=sleep))
            function('watch_resource_reports.py', 'main', scope)()
            self.assertEqual(sleeps, [30])
            self.assertEqual(saves.count('reporter_state.json'), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
