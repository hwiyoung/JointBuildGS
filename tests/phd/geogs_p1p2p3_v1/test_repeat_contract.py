import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

REPO = Path(__file__).resolve().parents[3]
MODULE = REPO / 'scripts/phd/geogs_p1p2p3_v1/repeat_contract.py'
spec = importlib.util.spec_from_file_location('geogs_repeat_contract', MODULE)
repeat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repeat)
CONFIG = REPO / 'configs/phd/geogs_p1p2p3_v1/experiment_v1.json'
LAYOUT = REPO / 'configs/phd/geogs_p1p2p3_v1/runtime_layout_allocator_v2.json'
CONTRACT = REPO / 'configs/phd/geogs_p1p2p3_v1/supplemental_repeat_v1.json'


class SupplementalRepeatTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CONFIG.read_text())
        self.layout = json.loads(LAYOUT.read_text())
        self.contract = json.loads(CONTRACT.read_text())

    def validate(self, contract=None, region='P1', condition='D005_Pnative', phase='train'):
        repeat.validate_contract(contract or self.contract, self.cfg, repeat.sha(CONFIG), self.layout,
                                 repeat.sha(LAYOUT), region, condition, phase,
                                 self.contract['runtime_image_id'], self.contract['allocator'])

    def test_three_native_repeats_keep_all_four_frozen_phases(self):
        for region in ('P1', 'P2', 'P3'):
            for phase in ('train', 'render', 'metrics', 'auxiliary'):
                with self.subTest(region=region, phase=phase):
                    self.validate(region=region, phase=phase)

    def test_changed_scientific_or_runtime_controls_are_rejected(self):
        for field, value in (('seed', 1), ('lambda_lod_anchor', 0.0005), ('protection', 'released'),
                             ('start_iteration', 0), ('iterations', 8100), ('output_directory', 'runs_allocator_v2'),
                             ('scientific_config_sha256', 'changed'), ('runtime_layout_sha256', 'changed'),
                             ('allocator', 'backend:cudaMallocAsync'), ('runtime_image_id', 'another-image'),
                             ('scientific_verdict', 'PASS'), ('reference_accessed_for_this_decision', True)):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.contract)
                changed[field] = value
                with self.assertRaises(ValueError):
                    self.validate(changed)

    def test_changed_condition_parity_or_anchor_path_is_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(condition='D0005_Pnative')
        with self.assertRaises(ValueError):
            self.validate(phase='parity')
        changed = copy.deepcopy(self.contract)
        changed['anchors']['P2']['checkpoint_directory'] = 'a/new/anchor'
        with self.assertRaises(ValueError):
            self.validate(changed)

    def fixture(self, directory, region='P1'):
        root = Path(directory)
        anchor = root/'anchor'
        anchor.mkdir()
        digest = self.contract['anchors'][region]['checkpoint_sha256'] or 'a'*64
        (anchor/'receipt.json').write_text(json.dumps(dict(iteration=8000, after_protection_registration=True,
                                                        checkpoint_sha256=digest)))
        gate = root/'gate.json'
        gate.write_text(json.dumps(dict(region=region, status='EXACT_COMMON_ANCHOR_VERIFIED',
                        runtime_layout_sha256=repeat.sha(LAYOUT), checkpoint_sha256=digest)))
        environment = dict(JBGS_RUNTIME_IMAGE_ID=self.contract['runtime_image_id'],
                           PYTORCH_CUDA_ALLOC_CONF=self.contract['allocator'],
                           JBGS_REPEAT_ID=self.contract['repeat_id'],
                           JBGS_REPEAT_CONTRACT_SHA256=repeat.sha(CONTRACT))
        return dict(config_path=CONFIG, layout_path=LAYOUT, region=region, condition='D005_Pnative', phase='train',
                    contract_path=CONTRACT, anchor_root=anchor, gate_path=gate, environment=environment)

    def test_mounted_binding_records_exact_primary_gate_and_resolved_anchor(self):
        for region in ('P1', 'P2', 'P3'):
            with self.subTest(region=region), tempfile.TemporaryDirectory() as directory:
                args = self.fixture(directory, region)
                binding = repeat.load_repeat_binding(**args)
                self.assertEqual(binding['repeat_id'], 'native_repeat_1')
                self.assertEqual(binding['repeat_contract_sha256'], repeat.sha(CONTRACT))
                self.assertEqual(binding['repeat_anchor_gate_sha256'], repeat.sha(args['gate_path']))
                self.assertTrue(binding['supplemental_only'])

    def test_wrong_anchor_gate_cannot_validate_a_repeat(self):
        for field, value in (('checkpoint_sha256', 'another-anchor'), ('runtime_layout_sha256', 'changed'),
                             ('region', 'P3'), ('status', 'FAIL')):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                args = self.fixture(directory)
                gate = json.loads(args['gate_path'].read_text())
                gate[field] = value
                args['gate_path'].write_text(json.dumps(gate))
                with self.assertRaises(ValueError):
                    repeat.load_repeat_binding(**args)

    def test_contract_environment_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory)
            args['environment']['JBGS_REPEAT_CONTRACT_SHA256'] = 'changed'
            with self.assertRaises(ValueError):
                repeat.load_repeat_binding(**args)

    def test_primary_and_repeat_prerequisites_cannot_be_mixed(self):
        binding = dict(repeat_id='native_repeat_1', repeat_contract_sha256='a'*64)
        repeat.require_repeat_receipt({}, None)
        repeat.require_repeat_receipt(binding, binding)
        with self.assertRaises(ValueError):
            repeat.require_repeat_receipt(binding, None)
        with self.assertRaises(ValueError):
            repeat.require_repeat_receipt({}, binding)

    def test_missing_contract_does_not_change_primary_behavior_or_accept_repeat_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory)
            args.update(contract_path=Path(directory)/'absent.json', environment={})
            self.assertIsNone(repeat.load_repeat_binding(**args))
            args['environment'] = {'JBGS_REPEAT_ID': 'native_repeat_1'}
            with self.assertRaises(ValueError):
                repeat.load_repeat_binding(**args)

    def test_readiness_requires_every_primary_phase_and_rejects_failure_or_repeat_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for region in self.cfg['regions']:
                for condition in self.cfg['conditions']:
                    for phase in ('train', 'render', 'metrics', 'auxiliary'):
                        path = root/region/condition['id']/(phase+'_receipt.json')
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(dict(status='PASS', region=region, condition=condition['id'],
                            phase=phase, config_sha256=repeat.sha(CONFIG), runtime_layout_sha256=repeat.sha(LAYOUT))))
            self.assertEqual(repeat.validate_primary_readiness(root, self.cfg, repeat.sha(CONFIG), repeat.sha(LAYOUT)), 72)
            target = root/'P3/D0_Prelease/auxiliary_receipt.json'
            failed = json.loads(target.read_text())
            failed['status'] = 'FAIL'
            target.write_text(json.dumps(failed))
            with self.assertRaises(ValueError):
                repeat.validate_primary_readiness(root, self.cfg, repeat.sha(CONFIG), repeat.sha(LAYOUT))
            failed.update(status='PASS', repeat_id='native_repeat_1')
            target.write_text(json.dumps(failed))
            with self.assertRaises(ValueError):
                repeat.validate_primary_readiness(root, self.cfg, repeat.sha(CONFIG), repeat.sha(LAYOUT))

    def production_command(self, region, supplemental):
        """Stop the real phase driver at Popen; no child/CUDA operation runs.

        Synthetic file metadata exercises its actual command construction. The
        production repeat-contract validation itself is covered above.
        """
        with mock.patch.object(sys, 'path', [str(MODULE.parent), *sys.path]):
            module_spec = importlib.util.spec_from_file_location('repeat_phase_driver_test', MODULE.parent/'run_regional_phase.py')
            driver = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(driver)
        class CommandCaptured(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('input', 'output', 'source', 'anchor'):
                (root/name).mkdir()
            (root/'.dockerenv').touch()
            (root/'config.json').write_bytes(CONFIG.read_bytes())
            (root/'runtime_layout.json').write_bytes(LAYOUT.read_bytes())
            (root/'repeat_contract.json').write_bytes(CONTRACT.read_bytes())
            (root/'anchor/checkpoint.pth').write_bytes(b'synthetic checkpoint identity for command construction only')
            (root/'anchor/receipt.json').write_text(json.dumps(dict(iteration=8000,
                checkpoint_sha256=repeat.sha(root/'anchor/checkpoint.pth'))))
            (root/'input/input_manifest.json').write_text(json.dumps(dict(status='INPUTS_SEALED_FOR_EXECUTION',
                region=region, config_sha256=repeat.sha(CONFIG), files=[],
                training_paths=dict(prior_depth='prior', da3_depth='da3', protection_pcd='initialization/lod2_pcd.ply'))))
            mapped = {'/.dockerenv', '/input', '/output', '/source', '/anchor', '/config.json',
                      '/runtime_layout.json', '/repeat_contract.json', '/reference', '/artifacts'}
            def isolated_path(value):
                text = str(value)
                if any(text == base or text.startswith(base+'/') for base in mapped):
                    return root/text.lstrip('/')
                return Path(value)
            binding = dict(repeat_id='native_repeat_1', repeat_contract_sha256=repeat.sha(CONTRACT),
                           supplemental_only=True) if supplemental else None
            environment = dict(JBGS_RUNTIME_REVISION='allocator_v2',
                               PYTORCH_CUDA_ALLOC_CONF=self.contract['allocator'],
                               JBGS_RUNTIME_IMAGE_ID=self.contract['runtime_image_id'])
            with mock.patch.object(driver, 'Path', isolated_path), \
                 mock.patch.object(driver, 'load_repeat_binding', return_value=binding), \
                 mock.patch.object(driver.subprocess, 'check_output', return_value=b'["native",134217728]'), \
                 mock.patch.object(driver.subprocess, 'Popen', side_effect=CommandCaptured) as captured, \
                 mock.patch.dict(driver.os.environ, environment, clear=True), \
                 mock.patch.object(sys, 'argv', ['run_regional_phase.py', '--config', '/config.json',
                    '--region', region, '--condition', 'D005_Pnative', '--phase', 'train']):
                with self.assertRaises(CommandCaptured):
                    driver.main()
                return captured.call_args.args[0]

    def test_real_phase_driver_forces_repeat_p2_p3_to_8000_without_changing_controls(self):
        for region in ('P2', 'P3'):
            with self.subTest(region=region):
                command = self.production_command(region, True)
                self.assertTrue(command[command.index('--jbgs_resume_full')+1].endswith('/anchor/checkpoint.pth'))
                for flag, value in (('--iterations', '30000'), ('--stage_switch_iter', '8000'),
                                    ('--lambda_lod_init', '0.08'), ('--lambda_lod_anchor', '0.005')):
                    self.assertEqual(command[command.index(flag)+1], value)
                self.assertIn('--protect_bldg', command)
                self.assertNotIn('--jbgs_release_protection', command)

    def test_real_phase_driver_preserves_primary_p2_full_start(self):
        command = self.production_command('P2', False)
        self.assertNotIn('--jbgs_resume_full', command)


if __name__ == '__main__':
    unittest.main()
