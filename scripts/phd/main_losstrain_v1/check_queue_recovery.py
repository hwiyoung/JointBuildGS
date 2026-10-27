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
