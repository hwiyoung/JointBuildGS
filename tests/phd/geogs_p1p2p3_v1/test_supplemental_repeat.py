"""Reference-free repetition identity and pre-evaluation completeness fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULES = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
from runtime_layout import RuntimeLayout, sha
from supplemental_repeat import SupplementalRepeat
import seal_candidates as seal


class SupplementalRepeatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.config = self.save('contracts/execution_v1.json', dict(seed=0, scientific_verdict=None,
            conditions=[dict(id='D005_Pnative', lambda_lod_anchor=.005, protection='native')]))
        data = dict(schema='geogs_runtime_layout_v1', revision='allocator_v2', scientific_verdict=None,
                    runs_directory='runs_allocator_v2', parity_directory='parity_allocator_v2', queue_directory='queue_allocator_v2',
                    allocator='backend:native,max_split_size_mb:128', scientific_config_sha256=sha(self.config), anchors={})
        for region in ('P1', 'P2', 'P3'):
            baseline = ('runs' if region=='P1' else 'runs_allocator_v2')+'/'+region+'/D005_Pnative'
            data['anchors'][region] = dict(baseline_directory=baseline,
                checkpoint_directory=baseline+'/model/jbgs_complete/iteration_8000')
        self.layout = RuntimeLayout(self.task, self.save('contracts/runtime_layout_allocator_v2.json', data))
        self.data = dict(schema='GEOGS_SUPPLEMENTAL_NATIVE_REPEAT_v1', repeat_id='native_repeat_1', scientific_verdict=None,
            output_directory='native_repeat_allocator_v2', regions=['P1','P2','P3'], condition_id='D005_Pnative',
            phases=['train','render','metrics','auxiliary'], start_iteration=8000, iterations=30000, seed=0,
            lambda_lod_anchor=.005, protection='native', runtime_image_id='sha256:fixture', allocator=data['allocator'],
            scientific_config_sha256=sha(self.config), runtime_layout_sha256=self.layout.digest,
            anchors={region:dict(checkpoint_directory=value['checkpoint_directory']) for region,value in data['anchors'].items()})
        self.path = self.save('contracts/supplemental_repeat_v1.json', self.data)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, relative, data):
        path = self.task/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def repeat(self):
        return SupplementalRepeat(self.task, self.path, self.layout)

    def test_all_region_paths_are_supplemental_and_use_native_condition(self):
        repeat = self.repeat()
        self.assertEqual(repeat.identifier, 'native_repeat_1')
        self.assertEqual(repeat.run('P2'), self.task/'native_repeat_allocator_v2/P2/D005_Pnative')
        self.assertEqual(self.data['anchors']['P1']['checkpoint_directory'],
                         str(self.layout.anchor_checkpoint('P1').relative_to(self.task)))

    def test_preregistered_repeat_cannot_be_silently_omitted(self):
        with self.assertRaisesRegex(ValueError, 'preregistered explicit'):
            SupplementalRepeat(self.task, None, self.layout)
        with self.assertRaisesRegex(ValueError, 'Repeat contract SHA'):
            self.repeat().require_receipt({})

    def test_changed_seed_controls_anchor_or_allocator_are_rejected(self):
        for field, value in [('seed', 1), ('protection', 'released'), ('allocator', 'different'),
                             ('output_directory', '../outside')]:
            with self.subTest(field=field):
                self.save('contracts/supplemental_repeat_v1.json', dict(self.data, **{field:value}))
                with self.assertRaises(ValueError):
                    self.repeat()
        changed = json.loads(json.dumps(self.data))
        changed['anchors']['P2']['checkpoint_directory'] = self.data['anchors']['P1']['checkpoint_directory']
        self.save('contracts/supplemental_repeat_v1.json', changed)
        with self.assertRaisesRegex(ValueError, 'anchor path'):
            self.repeat()

    def test_native_repeat_starts8000_even_where_primary_native_fullstarts(self):
        repeat = self.repeat()
        receipt = dict(status='PASS', region='P2', condition='D005_Pnative', phase='train',
            config_sha256=sha(self.config), input_manifest_sha256='input', runtime_layout_sha256=self.layout.digest,
            repeat_contract_sha256=repeat.digest, repeat_id=repeat.identifier, supplemental_only=True,
            training_start_iteration=8000, runtime_image_id='sha256:fixture')
        seal.validate_phase_receipt(receipt, 'P2', 'D005_Pnative', 'train', sha(self.config), 'input', self.layout, repeat)
        with self.assertRaises(ValueError):
            seal.validate_phase_receipt(receipt, 'P2', 'D005_Pnative', 'train', sha(self.config), 'input', self.layout)
        for field, value in [('training_start_iteration', 0), ('runtime_image_id', 'wrong'), ('supplemental_only', False)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                repeat.require_run_receipt(dict(receipt, **{field:value}), 'P2')

    def test_every_regional_repeat_is_required_before_reference_evaluation(self):
        repeat = self.repeat()
        candidates = [dict(region=region, condition=repeat.identifier, supplemental_only=True, variant='final', mesh_kind='raw',
            run_directory=str(repeat.run(region).relative_to(self.task))) for region in self.layout.regions]
        manifest = dict(repeat.binding(), candidates=candidates)
        repeat.require_candidates(manifest)
        with self.assertRaisesRegex(ValueError, 'Every declared native repetition'):
            repeat.require_candidates(dict(manifest, candidates=candidates[:2]))
        with self.assertRaisesRegex(ValueError, 'Every declared native repetition'):
            repeat.require_candidates(dict(manifest, candidates=candidates+[candidates[0]]))
        with self.assertRaisesRegex(ValueError, 'path differs'):
            repeat.require_candidates(dict(manifest, candidates=[dict(row, run_directory='runs/primary') for row in candidates]))

    def test_phase_snapshot_and_exact_anchor_gate_bytes_are_bound(self):
        repeat = self.repeat()
        run = repeat.run('P1')
        run.mkdir(parents=True)
        (run/'train_repeat_contract_snapshot.json').write_bytes(self.path.read_bytes())
        (run/'train_repeat_helper_snapshot.py').write_bytes(b'fixture helper')
        anchor_path = self.layout.anchor_checkpoint('P1')/'receipt.json'
        self.save(str(anchor_path.relative_to(self.task)), dict(checkpoint_sha256='checkpoint'))
        gate = self.save('parity_allocator_v2/P1/anchor_gate.json', dict(status='EXACT_COMMON_ANCHOR_VERIFIED',
            region='P1', runtime_layout_sha256=self.layout.digest, checkpoint_sha256='checkpoint'))
        receipt = dict(region='P1', condition='D005_Pnative', phase='train', runtime_layout_sha256=self.layout.digest,
            repeat_contract_sha256=repeat.digest, repeat_id=repeat.identifier, supplemental_only=True,
            training_start_iteration=8000, runtime_image_id='sha256:fixture', repeat_anchor_checkpoint_sha256='checkpoint',
            repeat_anchor_gate_sha256=sha(gate), repeat_helper_sha256=sha(run/'train_repeat_helper_snapshot.py'))
        bound = []
        def bind(path):
            bound.append(path)
            return dict(path=str(path.relative_to(self.task)), sha256=sha(path))
        seal.bind_repeat_provenance(run, receipt, repeat, 'P1', bind, 'train')
        self.assertIn(gate, bound)
        self.assertIn(anchor_path, bound)
        with self.assertRaisesRegex(ValueError, 'exact primary anchor gate'):
            seal.bind_repeat_provenance(run, dict(receipt, repeat_anchor_gate_sha256='other gate'), repeat, 'P1', bind, 'train')
        (run/'train_repeat_helper_snapshot.py').write_bytes(b'changed helper')
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            seal.bind_repeat_provenance(run, receipt, repeat, 'P1', bind, 'train')


if __name__ == '__main__':
    unittest.main()
