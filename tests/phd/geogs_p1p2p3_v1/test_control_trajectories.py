"""Synthetic trace/clock/figure checks and actual all21 metadata-gate tests."""
import ast
import copy
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io

REPO = Path(__file__).resolve().parents[3]
BASE = REPO/'scripts/phd/geogs_p1p2p3_v1'
for directory in (BASE/'analysis', BASE, BASE/'evaluation', BASE/'runtime'):
    sys.path.insert(0, str(directory))
import control_trajectories as ct
from finalization_control import FinalizationGate


def trace_text(start=0, finish=300, protected=10, prior=.005):
    return ''.join(json.dumps(dict(iteration=iteration, gaussians=1000+iteration,
        protected=protected, lod_weight=.08 if iteration <= 8000 else prior,
        da_weight=.05*(.95**((iteration-start)//1000)), elapsed_seconds=2.+(iteration-start)/10,
        camera='SYNTHETIC_PHOTO_NOT_EXPORTED', rgb_loss={'ignored_quality':'sentinel'},
        lod_loss='SYNTHETIC_LOSS_NOT_EXPORTED', da_loss=-999999,
        peak_cuda_allocated_bytes=42, peak_cuda_reserved_bytes=84, peak_rss_bytes=168))+'\n'
        for iteration in range(start+100, finish+1, 100))


def job(start=0, condition='D005_Pnative', supplemental=False):
    return dict(region='P1', condition=condition, scientific_condition='D005_Pnative' if supplemental else condition,
        supplemental_only=supplemental, training_start_iteration=start,
        declared_refinement_prior_weight=.005, protection='native', anchor_checkpoint_directory='synthetic/anchor',
        trace=dict(path='synthetic/model/jbgs_trace.jsonl', sha256='a'*64),
        train_receipt=dict(path='synthetic/train_receipt.json', sha256='b'*64))


class TraceSemanticsTests(unittest.TestCase):
    def test_global_iteration_and_cumulative_clock_not_per_step(self):
        rows = ct.parse_trace(trace_text(8000, 8300), job(8000), iterations=8300)
        self.assertEqual([row['global_iteration'] for row in rows], [8100, 8200, 8300])
        self.assertEqual([row['iterations_since_execution_start'] for row in rows], [100, 200, 300])
        self.assertEqual(rows[0]['process_elapsed_seconds'], 12.)
        self.assertIsNone(rows[0]['elapsed_since_previous_logged_sample_seconds'])
        self.assertEqual(rows[1]['elapsed_since_previous_logged_sample_seconds'], 10.)
        self.assertEqual(rows[1]['logged_iteration_gap'], 100)
        self.assertTrue(all(row['per_step_seconds'] is None for row in rows))

    def test_quality_fields_camera_and_memory_are_not_exported(self):
        rows = ct.parse_trace(trace_text(), job(), iterations=300)
        encoded = json.dumps(rows, allow_nan=False)
        for forbidden in ('rgb_loss', 'lod_loss', 'da_loss', 'SYNTHETIC_LOSS', 'SYNTHETIC_PHOTO', 'peak_cuda', 'peak_rss'):
            self.assertNotIn(forbidden, encoded)

    def test_phase_not_inferred_from_constant_or_changing_weight(self):
        rows = ct.parse_trace(trace_text(8000, 10000), job(8000), iterations=10000)
        self.assertGreater(len({row['da3_weight'] for row in rows}), 1)
        self.assertTrue(all(row['da_controller_phase'] is None
                            and row['da_controller_phase_status']=='NOT_RECORDED_IN_PINNED_TRACE' for row in rows))

    def test_zero_prior_and_released_protection_are_actual_values(self):
        rows = ct.parse_trace(trace_text(8000, 8200, protected=0, prior=0), job(8000, 'D0_Prelease'), iterations=8200)
        self.assertTrue(all(row['prior_weight']==0 and row['protected_gaussians']==0 for row in rows))

    def test_missing_duplicate_and_reset_trace_fail_without_gap_fill(self):
        lines = trace_text().splitlines()
        cases = [lines[:-1], lines[:1]+lines[2:], lines+lines[-1:], [lines[1], lines[0], lines[2]]]
        reset = [json.loads(line) for line in lines]
        reset[1]['elapsed_seconds'] = 0
        cases.append([json.dumps(row) for row in reset])
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                ct.parse_trace('\n'.join(changed), job(), iterations=300)

    def test_nonfinite_negative_counts_and_noninteger_iteration_fail(self):
        for field, value in (('gaussians', -1), ('protected', 99999), ('iteration', 100.5),
                             ('lod_weight', -1), ('da_weight', float('nan')), ('elapsed_seconds', -1)):
            row = json.loads(trace_text(finish=100))
            row[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                ct.parse_trace(json.dumps(row), job(), iterations=100)

    def test_different_same_rule_realized_weights_remain_distinct(self):
        first = trace_text(8000, 8200)
        changed = [json.loads(line) for line in first.splitlines()]
        changed[-1]['da_weight'] = .025
        second = '\n'.join(json.dumps(row) for row in changed)
        a = ct.parse_trace(first, job(8000), iterations=8200)
        b = ct.parse_trace(second, job(8000, 'D0005_Pnative'), iterations=8200)
        self.assertNotEqual(a[-1]['da3_weight'], b[-1]['da3_weight'])
        self.assertEqual(a[-1]['da_controller_phase_status'], b[-1]['da_controller_phase_status'])

    def test_actual_instrumentation_ast_supports_reported_semantics(self):
        path = BASE/'jbgs_state.py'
        self.assertEqual(ct.sha(path), ct.STATE_SHA)
        tree = ast.parse(path.read_text())
        after = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name=='after_step')
        row_node = next(node for node in ast.walk(after) if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id=='row' for target in node.targets))
        fields = {key.value for key in row_node.value.keys}
        self.assertTrue({'iteration', 'gaussians', 'protected', 'lod_weight', 'da_weight', 'elapsed_seconds'} <= fields)
        self.assertNotIn('da_phase', fields)
        self.assertNotIn('da_controller_phase', fields)
        source = path.read_text()
        self.assertLess(source.index("f.write(json.dumps(row"), source.index("torch.save(state"))
        self.assertIn('STARTED = time.monotonic()', source)


class SealedFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        contracts = self.task/'contracts'
        contracts.mkdir()
        for name in ('experiment_v1.json', 'runtime_layout_allocator_v2.json', 'supplemental_repeat_v1.json', 'extraction_resource_v3.json'):
            shutil.copyfile(REPO/'configs/phd/geogs_p1p2p3_v1'/name, contracts/('execution_v1.json' if name=='experiment_v1.json' else name))
        self.gate = FinalizationGate(self.task)
        self.cfg = self.gate.cfg
        self.binding = dict(config_sha256=ct.sha(contracts/'execution_v1.json'), **self.gate.layout.binding(),
                            **self.gate.repeat.binding(), **self.gate.resource.binding())
        self.seal = dict(schema='JBGS_GEOGS_CANDIDATES_SEALED_v2',
            status='ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED', reference_accessed=False,
            scientific_verdict=None, **self.binding, candidates=[], extraction_inventory=[], files=[])
        for region in self.cfg['regions']:
            for condition in [row['id'] for row in self.cfg['conditions']]+[self.gate.repeat.identifier]:
                repeated = condition == self.gate.repeat.identifier
                scientific = 'D005_Pnative' if repeated else condition
                run = self.gate.repeat.run(region) if repeated else self.gate.layout.run(region, condition)
                (run/'model').mkdir(parents=True)
                start = 8000 if repeated or self.gate.layout.starts_from_anchor(region, condition) else 0
                control = next(row for row in self.cfg['conditions'] if row['id']==scientific)
                (run/'model/jbgs_trace.jsonl').write_text(trace_text(start, 30000,
                    protected=0 if control['protection']=='released' else 10, prior=control['lambda_lod_anchor']))
                receipt = dict(region=region, condition=scientific, phase='train', status='PASS',
                    scientific_verdict=None, native_exit_code=0, validated_exit_code=0, runtime_image_id=ct.IMAGE,
                    training_start_iteration=start, wall_seconds=4.+(30000-start)/10,
                    implementation_hashes={'jbgs_state.py':ct.STATE_SHA, 'train.py':ct.TRAIN_SHA}, **self.binding)
                if repeated:
                    receipt.update(repeat_id='native_repeat_1', supplemental_only=True)
                ct.dump(run/'train_receipt.json', receipt)
                for path in (run/'model/jbgs_trace.jsonl', run/'train_receipt.json'):
                    self.seal['files'].append(ct.record(self.task, path))
                for variant in self.gate.resource.variant_inventory(region, scientific, self.gate.repeat.identifier if repeated else None):
                    self.seal['extraction_inventory'].append(dict(region=region, condition=condition,
                        variant=variant['name'], **{key:variant[key] for key in ('iteration', 'mesh_res', 'required', 'export_images')},
                        status='PASS' if variant['required'] else 'TECHNICAL_RESOURCE_UNAVAILABLE'))
                for variant in ['final', 'mesh_512']+(['anchor_512'] if condition=='D005_Pnative' else []):
                    for kind in ('raw', 'post'):
                        self.seal['candidates'].append(dict(region=region, condition=condition, variant=variant,
                            mesh_kind=kind, supplemental_only=repeated, run_directory=str(run.relative_to(self.task)),
                            anchor_provenance=dict(checkpoint=dict(sha256=self.gate.repeat.data['anchors'][region].get('checkpoint_sha256')))))
        self.write_seal()

    def write_seal(self):
        (self.task/'contracts/candidates_sealed_v1.json').write_text(json.dumps(self.seal))


class ProvenanceGateTests(SealedFixture):
    def test_inventory_only_reads_contracts_even_when_trace_payload_is_absent(self):
        for item in self.seal['files']:
            (self.task/item['path']).unlink()
        access = ct.inventory(self.task)
        self.assertEqual(len(access['jobs']), 21)
        self.assertEqual(sum(job['supplemental_only'] for job in access['jobs']), 3)
        self.assertEqual(len(access['jobs'])*2, 42)
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            ct.verify_inputs(self.task, access)

    def test_incomplete_all21_gate_fails_before_any_trace_access(self):
        self.seal['candidates'] = [row for row in self.seal['candidates']
                                   if not (row['condition']=='native_repeat_1' and row['region']=='P3')]
        self.write_seal()
        for item in self.seal['files']:
            (self.task/item['path']).unlink()
        with self.assertRaisesRegex(ValueError, 'Every declared native repetition'):
            ct.inventory(self.task)

    def test_unbound_trace_requires_independent_receipt_instead_of_self_hash(self):
        self.seal['files'] = self.seal['files'][1:]
        self.write_seal()
        with self.assertRaisesRegex(ValueError, 'UNBOUND_CONTROL_INPUT.*separately reviewed post-seal'):
            ct.inventory(self.task)

    def test_duplicate_missing_size_and_changed_trace_are_rejected(self):
        original = copy.deepcopy(self.seal)
        self.seal['files'].append(self.seal['files'][0])
        self.write_seal()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            ct.inventory(self.task)
        self.seal = copy.deepcopy(original)
        self.seal['files'][0].pop('bytes')
        self.write_seal()
        with self.assertRaisesRegex(ValueError, 'exact sealed SHA'):
            ct.inventory(self.task)
        self.seal = original
        self.write_seal()
        access = ct.inventory(self.task)
        path = self.task/access['jobs'][-1]['trace']['path']
        path.write_bytes(path.read_bytes().replace(b'1000', b'1001', 1))
        with patch.object(ct, 'parse_trace') as parser, self.assertRaisesRegex(ValueError, 'bytes changed'):
            ct.extract(self.task, self.task/'results', access, self.cfg)
        parser.assert_not_called()

    def test_native_resume_and_start0_modes_are_preserved(self):
        access = ct.inventory(self.task)
        native = {item['region']:item['training_start_iteration'] for item in access['jobs'] if item['condition']=='D005_Pnative'}
        self.assertEqual(native, dict(P1=8000, P2=0, P3=0))
        self.assertTrue(all(item['training_start_iteration']==8000 for item in access['jobs'] if item['supplemental_only']))

    def test_source_semantics_and_native_receipt_start_cannot_drift(self):
        access = ct.inventory(self.task)
        item = access['jobs'][0]
        rows = ct.parse_trace((self.task/item['trace']['path']).read_text(), item)
        path = self.task/item['train_receipt']['path']
        original = ct.read(path)
        wrong = copy.deepcopy(original)
        wrong['implementation_hashes']['jbgs_state.py'] = 'x'*64
        path.write_text(json.dumps(wrong))
        with self.assertRaisesRegex(ValueError, 'Trace producer source differs'):
            ct.run_summary(self.task, item, rows, access)
        wrong = copy.deepcopy(original)
        wrong['training_start_iteration'] = 0
        path.write_text(json.dumps(wrong))
        with self.assertRaisesRegex(ValueError, 'starting state differs'):
            ct.run_summary(self.task, item, rows, access)

    def test_clocks_preserve_origins_scope_and_unavailable_per_step(self):
        access = ct.inventory(self.task)
        for item in (access['jobs'][0], next(row for row in access['jobs'] if row['region']=='P2' and row['condition']=='D005_Pnative')):
            rows = ct.parse_trace((self.task/item['trace']['path']).read_text(), item)
            summary = ct.run_summary(self.task, item, rows, access)
            self.assertEqual(summary['driver_phase_wall_minus_last_trace_elapsed_seconds'], 2.)
            self.assertEqual(summary['training_driver_wall_source_field'], 'wall_seconds')
            self.assertEqual(summary['training_driver_phase_wall_seconds'], 4.+(30000-item['training_start_iteration'])/10)
            self.assertIsNone(summary['per_step_seconds'])
            self.assertIsNone(summary['full_pipeline_seconds'])
            if item['training_start_iteration']==8000:
                self.assertIsNone(summary['step8000_logged_process_elapsed_seconds'])
            else:
                self.assertEqual(summary['step8000_logged_process_elapsed_seconds'], 802.)

    def test_inventory_cli_and_changed_seal_between_stages(self):
        attempt = self.task/'attempt'
        attempt.mkdir()
        with patch.object(sys, 'argv', ['control_trajectories.py', '--mode', 'inventory',
                                       '--task', str(self.task), '--attempt', str(attempt)]), redirect_stdout(io.StringIO()):
            ct.main()
        mounted = (attempt/'mount_relative_paths.txt').read_text().splitlines()
        self.assertEqual(len(mounted), 42)
        self.assertTrue(all(path.endswith(('model/jbgs_trace.jsonl', 'train_receipt.json')) for path in mounted))
        original = ct.read(attempt/'input_gate.json')
        self.assertEqual(original, ct.inventory(self.task))
        # Valid seal metadata with different bytes must invalidate the earlier access gate.
        self.seal['synthetic_changed_after_gate'] = True
        self.write_seal()
        with patch.object(sys, 'argv', ['control_trajectories.py', '--mode', 'extract',
                                       '--task', str(self.task), '--attempt', str(attempt)]), patch.object(ct, 'parse_trace') as parser:
            with self.assertRaisesRegex(ValueError, 'changed between Docker stages'):
                ct.main()
        parser.assert_not_called()


class SyntheticPlotsAndExportTests(SealedFixture):
    def test_full_export_has_separate_primary_repeat_tables_and_real_plot_files(self):
        access = ct.inventory(self.task)
        output = self.task/'results'
        plot_cfg = dict(self.cfg, synthetic_fixture_only=True)
        result = ct.extract(self.task, output, access, plot_cfg)
        self.assertEqual(result['completed_runs'], 21)
        self.assertEqual(result['primary_samples'], 4120)
        self.assertEqual(result['supplemental_samples'], 660)
        self.assertEqual(result['figures'], 6)
        self.assertFalse(result['loss_quality_fields_exported'])
        self.assertFalse(result['checkpoint_loaded'])
        with (output/'primary_control_samples.csv').open() as stream:
            primary = list(csv.DictReader(stream))
        with (output/'native_repeat_control_samples.csv').open() as stream:
            repeated = list(csv.DictReader(stream))
        self.assertTrue(all(row['supplemental_only']=='False' for row in primary))
        self.assertTrue(all(row['supplemental_only']=='True' and row['condition']=='native_repeat_1' for row in repeated))
        figures = ct.read(output/'figure_index.json')['figures']
        self.assertTrue(all(item['synthetic_fixture_only'] for item in figures))
        self.assertTrue(all('start '+str(series['training_start_iteration']) in series['label']
                            for item in figures for series in item['plotted_series']))
        self.assertTrue(all(min(series['source_iterations']) > 8000 for item in figures
                            for series in item['plotted_series'] if series['panel']==1))
        self.assertTrue(all(len(item['plotted_series']) == (12 if item['figure_family']=='native_repeat_diagnostic' else 36) for item in figures))
        for item in result['files']:
            self.assertEqual(ct.record(output, output/item['path']), item)
        from PIL import Image
        for region in self.cfg['regions']:
            for family in ('primary_six_conditions', 'native_repeat_diagnostic'):
                with Image.open(output/(region+'_'+family+'.png')) as image:
                    self.assertEqual(image.size, (2080, 1600))
                    self.assertGreater(len(image.convert('RGB').getcolors(10_000_000)), 1000)
                self.assertTrue((output/(region+'_'+family+'.pdf')).read_bytes().startswith(b'%PDF'))
        # Keep one inspected synthetic image only when the isolated validation harness requests it.
        if Path('/out').is_dir():
            for name in ('P2_primary_six_conditions.png', 'P2_native_repeat_diagnostic.png'):
                shutil.copyfile(output/name, Path('/out')/('synthetic_'+name))
        with self.assertRaises(FileExistsError):
            ct.extract(self.task, output, access, plot_cfg)


if __name__ == '__main__':
    unittest.main()
