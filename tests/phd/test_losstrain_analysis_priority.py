"""Priority changes must never restart training, omit arms, or hide new stops."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

SCRIPTS = Path('/repo/scripts/phd/main_losstrain_v1')


def load(name, function, scope):
    tree = ast.parse((SCRIPTS/name).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    exec(compile(ast.Module(body=[node], type_ignores=[]), name, 'exec'), scope)
    return scope[function]


class Priority(unittest.TestCase):
    def test_pending_priority_preserves_membership_and_variant_order(self):
        runs = [dict(site=s, prior=p, variant=v) for s in ['B0_b10','R1rep_b10']
                for p in ['LoD2','ALS'] for v in ['fixed','gt','soft','now']]
        function = load('continue_resource_v1.py','prioritize_training',{})
        original = list(runs)
        ordered = function(runs, dict(site='R1rep_b10',prior='ALS'))
        self.assertEqual(ordered[:4], runs[-4:])
        self.assertEqual(ordered[4:], runs[:-4])
        self.assertEqual(runs, original)
        self.assertEqual(function(runs,None),original)

    def test_request_refuses_existing_real_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); queue=root/'queue';queue.mkdir()
            (queue/'training_STOP.json').write_text('{"error":"nonfinite"}')
            scope=dict(ROOT=root/'driver', Q=SimpleNamespace(ROOT=queue),
                       MARKERS=['training_STOP.json','post_STOP.json'])
            with self.assertRaises(AssertionError):
                load('priority_analysis_delivery.py','request',scope)()
            self.assertEqual(json.loads((queue/'training_STOP.json').read_text()),{'error':'nonfinite'})
            self.assertFalse((queue/'post_STOP.json').exists())

    def test_next_unit_finishes_scoring_before_unrelated_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            runs=[dict(site='R1',prior='ALS',variant=v) for v in ['fixed','gt','soft','now']]
            unrelated=dict(site='R1',prior='LoD2',variant='now')
            def unit(r):return root/(r['prior']+'_'+r['variant'])
            def read(p,*args):return dict(enabled=True,site='R1',prior='ALS') if p.name=='next_analysis_priority.json' else {}
            scope=dict(ROOT=root,RUNS=runs+[unrelated],F=SimpleNamespace(root_of=unit),read=read)
            schedule=load('continue_resource_v1.py','readout_schedule',scope)
            state=schedule([],[])
            self.assertEqual(state['training_scope'],runs)
            self.assertNotIn(unrelated,state['training_scope'])
            self.assertFalse(state['post_may_start'])
            for r in runs:
                unit(r).mkdir();(unit(r)/'PASS.json').touch()
            state=schedule(runs+[unrelated],[])
            self.assertTrue(state['active']);self.assertEqual(state['post'],runs)
            state=schedule(runs[1:]+[unrelated],runs[:1])
            self.assertFalse(state['post_may_start']);self.assertEqual(state['measure'],runs[:1])
            for r in runs:(unit(r)/'measure_PASS.json').touch()
            state=schedule([unrelated],[])
            self.assertFalse(state['active']);self.assertEqual(state['post'],[unrelated])

    def test_handoff_does_not_clear_new_failure_after_inflight_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);queue=root/'queue';queue.mkdir()
            expected={'status':'OPERATIONAL_ANALYSIS_DELIVERY_HANDOFF'}
            (root/'request.json').write_text(json.dumps(expected))
            (queue/'state.json').write_text(json.dumps(dict(gpu_jobs={},cpu_measurement=None,
                                                           stops=['training_STOP.json','post_STOP.json'])))
            (queue/'training_STOP.json').write_text('{"error":"new nonfinite"}')
            (queue/'post_STOP.json').write_text(json.dumps(expected))
            cfg=root/'cfg.json';cfg.write_text('{}')
            scope=dict(ROOT=root,CONFIG=cfg,MARKERS=['training_STOP.json','post_STOP.json'],STATUS=expected['status'],
                       Q=SimpleNamespace(ROOT=queue,read=lambda p:json.loads(p.read_text())),
                       fcntl=SimpleNamespace(flock=lambda *a:None,LOCK_EX=1,LOCK_NB=2))
            with self.assertRaises(AssertionError):
                load('priority_analysis_delivery.py','run',scope)()
            self.assertEqual(json.loads((queue/'training_STOP.json').read_text()),{'error':'new nonfinite'})
            self.assertFalse((queue/'history').exists())

    def test_validation_failure_preserves_handoff_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);queue=root/'queue';queue.mkdir()
            expected={'status':'OPERATIONAL_ANALYSIS_DELIVERY_HANDOFF'}
            markers=['training_STOP.json','post_STOP.json']
            (root/'request.json').write_text(json.dumps(expected))
            (queue/'state.json').write_text(json.dumps(dict(gpu_jobs={},cpu_measurement=None,stops=markers)))
            for name in markers:(queue/name).write_text(json.dumps(expected))
            cfg=root/'cfg.json';cfg.write_text('{}')
            def reject(epoch):raise RuntimeError('source differs from locked training')
            scope=dict(ROOT=root,CONFIG=cfg,MARKERS=markers,STATUS=expected['status'],
                       Q=SimpleNamespace(ROOT=queue,read=lambda p:json.loads(p.read_text()),validate=reject),
                       fcntl=SimpleNamespace(flock=lambda *a:None,LOCK_EX=1,LOCK_NB=2))
            with self.assertRaisesRegex(RuntimeError,'source differs'):
                load('priority_analysis_delivery.py','run',scope)()
            self.assertTrue(all((queue/name).exists() for name in markers))
            self.assertFalse((queue/'history').exists())


if __name__ == '__main__':
    unittest.main()
