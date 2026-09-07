"""Prospective completion scope, using frozen configs and synthetic metadata only."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT/'scripts/phd/geogs_p1p2p3_v1'
sys.path[:0] = [str(CODE/'evaluation'), str(CODE/'runtime'), str(CODE)]
import supplemental_repeat as supplemental
from runtime_layout import RuntimeLayout, sha
import seal_candidates
import resource_support
import finalization_control


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        (self.task/'contracts').mkdir()
        for name in ('execution_v1', 'runtime_layout_allocator_v2', 'supplemental_repeat_v1',
                     'extraction_resource_v3', 'evaluation_analysis_v1', 'evaluation_completion_v2'):
            source = 'experiment_v1' if name == 'execution_v1' else name
            shutil.copyfile(ROOT/'configs/phd/geogs_p1p2p3_v1'/f'{source}.json', self.task/'contracts'/f'{name}.json')
        self.layout = RuntimeLayout(self.task, self.task/'contracts/runtime_layout_allocator_v2.json')
        self.repeat = self.load()

    def load(self):
        return supplemental.SupplementalRepeat(self.task, self.task/'contracts/supplemental_repeat_v1.json', self.layout)

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def record(self, path):
        return dict(path=str(path.relative_to(self.task)), sha256=sha(path), bytes=path.stat().st_size)

    def manifest(self):
        evidence = [dict(row, bytes=123) for row in self.repeat.completion.data['failure_evidence']]
        return dict(self.repeat.binding(), supplemental_availability=self.repeat.supplemental_availability,
                    completion_decision_evidence=evidence, candidates=[],
                    files=[self.record(self.repeat.completion.path), *evidence])

    def test_exact_contract_loads_without_failed_payloads_and_binds_scope(self):
        self.assertEqual(self.repeat.evaluable_regions, [])
        self.assertFalse(self.repeat.evaluation_enabled('P1'))
        self.assertEqual(self.repeat.completion.digest, supplemental.COMPLETION_SHA)
        self.assertEqual(resource_support.seal_status(SimpleNamespace(repeat=self.repeat)),
                         'PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE')
        with self.assertRaisesRegex(ValueError, 'amendment binding'):
            self.repeat.require_receipt(dict(repeat_contract_sha256=self.repeat.digest))
        self.repeat.require_candidates(self.manifest())
        self.assertFalse(self.repeat.run('P1').exists())

    def test_changed_completion_bytes_fail_closed_and_absent_contract_retains_all21(self):
        path = self.repeat.completion.path
        path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'amendment SHA'):
            self.load()
        path.unlink()
        legacy = self.load()
        self.assertEqual(legacy.evaluable_regions, ['P1', 'P2', 'P3'])
        self.assertNotIn('evaluation_scope', legacy.binding())
        with self.assertRaisesRegex(ValueError, 'Every declared native repetition'):
            legacy.require_candidates(dict(legacy.binding(), candidates=[]))

    def test_availability_inventory_or_deferred_candidate_substitution_rejected(self):
        for mutation in ('availability', 'missing_evidence', 'repeat', 'disguised_repeat'):
            manifest = self.manifest()
            if mutation == 'availability':
                manifest['supplemental_availability'][0]['status'] = 'REFERENCE_ABSENT'
            elif mutation == 'missing_evidence':
                manifest['files'].pop()
            else:
                manifest['candidates'] = [dict(condition='native_repeat_1', supplemental_only=mutation == 'repeat')]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.repeat.require_candidates(manifest)

    def synthetic_failures(self):
        data = copy.deepcopy(self.repeat.completion.data)
        for row in data['supplemental_availability'][:2]:
            region = row['region']
            input_path = self.task/'inputs'/region/'input_manifest.json'
            self.save(input_path, {'synthetic': True})
            invocation = dict(region=region, condition='D005_Pnative', phase='train',
                config_sha256=data['scientific_config_sha256'], input_manifest_sha256=sha(input_path),
                runtime_layout_sha256=self.layout.digest, repeat_contract_sha256=self.repeat.digest,
                repeat_id=self.repeat.identifier, supplemental_only=True, training_start_iteration=8000,
                runtime_image_id=self.repeat.data['runtime_image_id'], scientific_verdict=None,
                command=['python','train.py','--jbgs_resume_full','/anchor/checkpoint.pth'])
            run = self.repeat.run(region)
            self.save(run/'train_invocation.json', invocation)
            self.save(run/'train_receipt.json', dict(invocation, status='FAIL', native_exit_code=1,
                      validated_exit_code=1, wall_seconds=row['train_wall_seconds']))
            (run/'train.log').write_text('synthetic CUDA OOM evidence; no actual loss values\n')
            (run/'train_gpu.csv').write_text('synthetic device metadata\n')
        for item in data['failure_evidence']:
            item['sha256'] = sha(self.task/item['path'])
        self.save(self.repeat.completion.path, data)
        with patch.object(supplemental, 'COMPLETION_SHA', sha(self.repeat.completion.path)):
            self.repeat = self.load()

    def test_sealer_binds_eight_closed_files_and_rejects_changed_bytes_or_p3_presence(self):
        self.synthetic_failures()
        metadata = seal_candidates.bind_completion_amendment(self.repeat, self.record)
        self.assertEqual(len(metadata['completion_decision_evidence']), 8)
        self.repeat.run('P3').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'remain absent'):
            seal_candidates.bind_completion_amendment(self.repeat, self.record)
        self.repeat.run('P3').rmdir()
        with (self.repeat.run('P1')/'train.log').open('a') as stream:
            stream.write('changed')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            seal_candidates.bind_completion_amendment(self.repeat, self.record)

    def test_primary72_readiness_requires_every_primary_phase_without_repeat_reads(self):
        gate = object.__new__(finalization_control.FinalizationGate)
        gate.task, gate.layout, gate.repeat = self.task, self.layout, self.repeat
        gate.cfg = json.loads((self.task/'contracts/execution_v1.json').read_text())
        self.save(self.task/'contracts/evaluation_sources_v1.json', {'synthetic': True})
        gate.resource = SimpleNamespace(data={'synthetic': True}, path=None,
            aux_run=lambda region, condition, repeat: self.layout.run(region, condition),
            validate_receipt=lambda *args: None, binding=lambda: {})
        for region in gate.cfg['regions']:
            input_path = self.task/'inputs'/region/'input_manifest.json'
            self.save(input_path, {'synthetic': True})
            self.assertEqual(len(gate.condition_ids(region)), 6)
            for condition in gate.cfg['conditions']:
                for phase in ('train', 'render', 'metrics', 'auxiliary'):
                    start = 8000 if self.layout.starts_from_anchor(region, condition['id']) else 0
                    path = self.layout.run(region, condition['id'])/(phase+'_receipt.json')
                    self.save(path, dict(status='PASS', region=region, condition=condition['id'], phase=phase,
                        config_sha256=finalization_control.CONFIG_SHA, input_manifest_sha256=sha(input_path),
                        runtime_layout_sha256=self.layout.digest, training_start_iteration=start,
                        native_exit_code=0, validated_exit_code=0, runtime_image_id=finalization_control.IMAGE,
                        scientific_verdict=None))
        result = gate.readiness()
        self.assertEqual(result['phase_receipts'], 72)
        self.assertEqual(result['status'], 'PRIMARY18_REQUIRED_PHASES_PASS_SUPPLEMENTAL_INCOMPLETE')
        self.assertFalse(any('native_repeat_allocator_v2' in row['path'] for row in result['files']))
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            gate.readiness()

    def test_seal_stage_reuse_rechecks_all_failed_evidence_bytes(self):
        manifest = self.manifest()
        self.save(self.task/'contracts/candidates_sealed_v1.json', manifest)
        gate = object.__new__(finalization_control.FinalizationGate)
        gate.task = self.task
        gate.candidate_seal = lambda: (manifest, 'synthetic-seal')
        seen = []
        with patch.object(finalization_control, 'checked', side_effect=lambda task, row: seen.append(row)):
            self.assertEqual(gate.decide('seal')[0], 'SKIP')
        self.assertEqual(seen, manifest['files'])

    def test_explicit_stage_input_mode_retains_complete_seal_gate_without_bulk_rehash(self):
        manifest = self.manifest()
        self.save(self.task/'contracts/candidates_sealed_v1.json', manifest)
        gate = object.__new__(finalization_control.FinalizationGate)
        gate.task = self.task
        gate.stage_input_verification = True
        calls = []
        gate.candidate_seal = lambda: (calls.append('complete-inventory-gate') or manifest, 'synthetic-seal')
        with patch.object(finalization_control, 'checked', side_effect=AssertionError('Unexpected bulk payload read')):
            self.assertEqual(gate.decide('seal')[0], 'SKIP')
        self.assertEqual(calls, ['complete-inventory-gate'])

    def test_stage_mode_rejects_missing_or_misbound_consumed_input_proof(self):
        gate = object.__new__(finalization_control.FinalizationGate)
        gate.task, gate.layout, gate.repeat = self.task, self.layout, self.repeat
        gate.stage_input_verification = True
        path = self.task/'synthetic_geometry_receipt.json'
        input_record = dict(path='inputs/P1/surface/als_surface.ply', bytes=123, sha256='a'*64)
        manifest = dict(files=[input_record], candidates=[dict(region='P1', surface=input_record)])
        gate.candidate_seal = lambda: (manifest, 'synthetic-seal')
        receipt = dict(status='PASS_GEOMETRY_EVALUATION', scientific_verdict=None,
                       region='P1', candidate_seal_sha256='synthetic-seal',
                       **self.layout.binding(), **self.repeat.binding())
        self.save(path, receipt)
        with self.assertRaisesRegex(ValueError, 'consumed-input verification'):
            gate.bound_receipt(path, 'PASS_GEOMETRY_EVALUATION', 'synthetic-seal', region='P1')
        receipt['input_verification'] = dict(policy='REGIONAL_CONSUMED_INPUTS_v1', stage='geometry',
            region='P1', candidate_seal_sha256='synthetic-seal', files_count=1, verified_bytes=123,
            files=[input_record], manifest_sha256=hashlib.sha256(json.dumps([input_record], sort_keys=True,
                separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest(), scientific_verdict=None)
        self.save(path, receipt)
        gate.bound_receipt(path, 'PASS_GEOMETRY_EVALUATION', 'synthetic-seal', region='P1')
        receipt['input_verification']['files'] = []
        self.save(path, receipt)
        with self.assertRaisesRegex(ValueError, 'exact regional scoring inventory'):
            gate.bound_receipt(path, 'PASS_GEOMETRY_EVALUATION', 'synthetic-seal', region='P1')
        receipt['input_verification']['files'] = [input_record]
        receipt['input_verification']['manifest_sha256'] = 'changed'
        self.save(path, receipt)
        with self.assertRaisesRegex(ValueError, 'exact regional scoring inventory'):
            gate.bound_receipt(path, 'PASS_GEOMETRY_EVALUATION', 'synthetic-seal', region='P1')
        receipt['input_verification']['region'] = 'P2'
        self.save(path, receipt)
        with self.assertRaisesRegex(ValueError, 'consumed-input verification'):
            gate.bound_receipt(path, 'PASS_GEOMETRY_EVALUATION', 'synthetic-seal', region='P1')


if __name__ == '__main__':
    unittest.main()
