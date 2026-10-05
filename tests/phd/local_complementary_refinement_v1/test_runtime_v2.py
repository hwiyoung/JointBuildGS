"""CPU synthetic identity checks and a bounded fake-resource queue exercise.

No native training, GPU computation, external inputs or evaluation references.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT/'scripts/phd/local_complementary_refinement_v1'
sys.path.insert(0, str(CODE))
import execution_gate_v2 as gate
import run_phase_v2 as worker
import prepare_contract_v2 as preparation
from prepare_source_v2 import payload_hashes
from common import read, record, sha


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contracts, self.source, self.scripts, self.probes = [self.root/name for name in ('contracts', 'source', 'scripts', 'probes')]
        for path in (self.contracts, self.source, self.scripts, self.probes):
            path.mkdir()
        self.cfg = {'schema': 'jbgs.local_complementary_refinement.v2', 'task_id': 'TEST',
                    'scientific_verdict': None, 'runtime': {'image_id': 'test-image', 'allocator': 'native'},
                    'local_weight': {'tau0_m': .5, 'tau1_m': 2.}}
        dump(self.contracts/'experiment_v2.json', self.cfg)
        self.binding = {'status': 'INPUTS_AND_COMMON_THRESHOLDS_FROZEN', 'task_id': 'TEST',
                        'scientific_verdict': None, 'reference_accessed': False,
                        'config': record(self.contracts/'experiment_v2.json'),
                        'tau0_m': .5, 'tau1_m': 2., 'verified_baseline_count': 18,
                        'regions': {'P2': {'checkpoint': {'sha256': 'anchor8k'}}}}
        dump(self.contracts/'input_binding.json', self.binding)
        for filename, status in [('cpu_validation.json', 'PASS'), ('baseline_validation.json', 'PASS_BASELINE_REUSE')]:
            dump(self.contracts/filename, {'status': status, 'scientific_verdict': None,
                                         'config': record(self.contracts/'experiment_v2.json')})
        for name in ('train.py', 'jbgs_state.py', 'jbgs_local_depth.py'):
            (self.source/name).write_text('# fixture '+name+'\n')
        hashes = gate.source_hashes(self.source)
        dump(self.source/'local_source_provenance.json', {
            'schema': 'JBGS_LOCAL_COMPLEMENTARY_SOURCE_v2',
            'prepared_implementation_hashes': hashes,
            'prepared_payload_hashes': payload_hashes(self.source),
            'local_depth_module_sha256': hashes['jbgs_local_depth.py']})
        for name in gate.REQUIRED_HELPERS:
            shutil.copyfile(CODE/name, self.scripts/name)
        self.write_probes()

    def write_probes(self):
        for protection in ('native', 'release'):
            local = {'iteration': 8001, 'tau0': self.binding['tau0_m'], 'tau1': self.binding['tau1_m'],
                     'lambda_prior': .005, 'mode': 'complementary'}
            probe = {'task_id': 'TEST', 'scientific_verdict': None, 'status': 'PASS',
                     'validated_exit_code': 0, 'native_exit_code': 0,
                     'phase': 'probe', 'region': 'P2', 'condition': 'LC_D005_P'+protection,
                     'training_start_iteration': 8000, 'training_end_iteration': 8001,
                     'config_sha256': sha(self.contracts/'experiment_v2.json'),
                     'config': record(self.contracts/'experiment_v2.json'),
                     'input_binding': record(self.contracts/'input_binding.json'),
                     'source_provenance': record(self.source/'local_source_provenance.json'),
                     'implementation_hashes': gate.source_hashes(self.source),
                     'driver': record(self.scripts/'run_phase_v2.py'), 'runtime_image_id': 'test-image',
                     'local_mode': 'complementary', 'tau0_m': self.binding['tau0_m'], 'tau1_m': self.binding['tau1_m'],
                     'anchor': {'sha256': 'anchor8k'},
                     'environment': {'JBGS_LOCAL_DEPTH_MODE': 'complementary',
                                     'JBGS_LOCAL_TAU0': str(self.binding['tau0_m']),
                                     'JBGS_LOCAL_TAU1': str(self.binding['tau1_m']),
                                     'PYTORCH_CUDA_ALLOC_CONF': 'native'},
                     'validation': [{'restore': {'iteration': 8000, 'checkpoint_sha256': 'anchor8k',
                                                 'release': protection == 'release', 'lambda_lod_anchor': .005,
                                                 'restore_equivalence': {'status': 'PASS'}},
                                     'first_local_trace': local, 'last_local_trace': local}]}
            dump(self.probes/gate.DEFAULT_PROBES[protection]/'probe_receipt.json', probe)

    def freeze(self):
        result = gate.freeze(self.contracts, self.source, self.scripts, self.probes)
        for protection, name in gate.DEFAULT_PROBES.items():
            shutil.copyfile(self.probes/name/'probe_receipt.json', self.contracts/f'probe_{protection}_receipt.json')
        return result

    def test_frozen_identity_roundtrip_and_no_overwrite(self):
        frozen = self.freeze()
        verified = gate.verify(self.contracts, self.source, self.scripts, self.probes)
        self.assertEqual(frozen['identity'], verified['identity'])
        gate.verify_runtime(self.contracts, self.source, self.scripts)
        with self.assertRaises(FileExistsError):
            self.freeze()

    def test_runtime_rejects_independent_identity_tampering(self):
        self.freeze()
        targets = [self.contracts/'experiment_v2.json', self.contracts/'input_binding.json',
                   self.source/'local_source_provenance.json', self.source/'train.py',
                   *(self.scripts/name for name in gate.REQUIRED_HELPERS),
                   self.contracts/'probe_native_receipt.json', self.contracts/'probe_release_receipt.json',
                   self.contracts/'cpu_validation.json', self.contracts/'baseline_validation.json']
        for path in targets:
            original = path.read_bytes()
            with self.subTest(path=path.name):
                path.write_bytes(original+b'\n')
                with self.assertRaises(ValueError):
                    gate.verify_runtime(self.contracts, self.source, self.scripts)
                path.write_bytes(original)

    def test_required_cpu_and_baseline_validation_cannot_be_fail_or_another_config(self):
        for filename in ('cpu_validation.json', 'baseline_validation.json'):
            path = self.contracts/filename
            original = read(path)
            for key in ('status', 'config'):
                changed = copy.deepcopy(original)
                if key == 'status':
                    changed['status'] = 'FAIL'
                else:
                    changed['config']['sha256'] = 'another-config'
                dump(path, changed)
                with self.subTest(filename=filename, key=key), self.assertRaises(ValueError):
                    gate.inspect_state(self.contracts, self.source, self.scripts, self.probes, gate.DEFAULT_PROBES)
            dump(path, original)

    def test_gate_rejects_wrong_probe_condition_anchor_allocator_and_release(self):
        p = self.probes/gate.DEFAULT_PROBES['release']/'probe_receipt.json'
        original = read(p)
        cases = [('condition', lambda x: x.update(condition='LC_D0_Prelease')),
                 ('anchor', lambda x: x['anchor'].update(sha256='other-anchor')),
                 ('allocator', lambda x: x['environment'].update(PYTORCH_CUDA_ALLOC_CONF='other')),
                 ('restore_protection', lambda x: x['validation'][0]['restore'].update(release=False)),
                 ('iteration', lambda x: x['validation'][0]['last_local_trace'].update(iteration=8100)),
                 ('native_failure', lambda x: x.update(native_exit_code=1)),
                 ('verdict', lambda x: x.update(scientific_verdict='PASS'))]
        for name, change in cases:
            probe = copy.deepcopy(original)
            change(probe)
            dump(p, probe)
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.inspect_state(self.contracts, self.source, self.scripts, self.probes, gate.DEFAULT_PROBES)
        dump(p, original)

    def test_gate_must_compare_binding_thresholds_to_declared_config(self):
        self.binding['tau1_m'] = 3.
        dump(self.contracts/'input_binding.json', self.binding)
        self.write_probes()
        with self.assertRaises(ValueError):
            gate.inspect_state(self.contracts, self.source, self.scripts, self.probes, gate.DEFAULT_PROBES)

    def test_probe_paths_reject_absolute_traversal_and_symlink_escape(self):
        for value in ('/elsewhere', '../elsewhere', 'ok/../../elsewhere'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.safe_probe_path(self.probes, value)
        (self.probes/'escape').symlink_to(self.root/'source', target_is_directory=True)
        with self.assertRaises(ValueError):
            gate.safe_probe_path(self.probes, 'escape/receipt.json')

    def test_sealed_input_paths_fail_closed(self):
        for value in ('/tmp/data', '../../tmp/data'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preparation.checked(self.root, value)
        (self.root/'escape').symlink_to('/tmp', target_is_directory=True)
        with self.assertRaises(ValueError):
            preparation.checked(self.root, 'escape/anything')
        self.assertEqual(preparation.checked(self.root, 'source/train.py'), self.source/'train.py')


class NativeCommandAndCompleteStateTests(unittest.TestCase):
    def test_normalization_allows_capture_resume_only_preserves_control_differences(self):
        base = ['python', 'train.py', '--lambda_lod_anchor', '0.005', '--dynamic_depth_weight',
                '--jbgs_capture_iterations', '8000', '8100', '30000',
                '--jbgs_input_manifest', '/input/input_manifest.json']
        new = ['python', 'train.py', '--lambda_lod_anchor', '0.005', '--dynamic_depth_weight',
               '--jbgs_capture_iterations', '8001', '--jbgs_input_manifest', '/input/input_manifest.json',
               '--jbgs_resume_full', '/anchor/checkpoint.pth', '--jbgs_stop_after', '8001']
        self.assertEqual(worker.normalized_training_command(base), worker.normalized_training_command(new))
        for changed in [new+['--jbgs_release_protection'], new+['--depth_scale_invariant'],
                        [x if x!='0.005' else '0.0005' for x in new]]:
            self.assertNotEqual(worker.normalized_training_command(base), worker.normalized_training_command(changed))

    def test_complete_receipt_rejects_ply_tamper_and_nontechnical_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary)/'model'
            complete = model/'jbgs_complete/iteration_30000'
            complete.mkdir(parents=True)
            (complete/'checkpoint.pth').write_bytes(b'synthetic complete bytes')
            (complete/'point_cloud.ply').write_bytes(b'synthetic ply bytes')
            receipt = {'schema': 'JBGS_GEOGS_COMPLETE_STATE_v1', 'iteration': 30000,
                       'scientific_verdict': None, 'after_protection_registration': True,
                       'checkpoint_sha256': sha(complete/'checkpoint.pth'),
                       'ply_sha256': sha(complete/'point_cloud.ply')}
            dump(complete/'receipt.json', receipt)
            worker.validate_complete(model, 30000, {}, {})
            (complete/'point_cloud.ply').write_bytes(b'altered ply bytes')
            with self.assertRaises(ValueError):
                worker.validate_complete(model, 30000, {}, {})
            (complete/'point_cloud.ply').write_bytes(b'synthetic ply bytes')
            for key, value in [('scientific_verdict', 'PASS'), ('after_protection_registration', False), ('schema', 'OTHER')]:
                changed = dict(receipt, **{key: value})
                dump(complete/'receipt.json', changed)
                with self.subTest(key=key), self.assertRaises(ValueError):
                    worker.validate_complete(model, 30000, {}, {})


class QueueOrchestrationTests(unittest.TestCase):
    def test_failure_is_preserved_and_remaining_17_are_completed_with_fake_resources(self):
        # Exercise the actual queue shell; fake runner cannot invoke Docker/GPU.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root/'repo'
            scripts = repo/'scripts/phd/local_complementary_refinement_v1'
            scripts.mkdir(parents=True)
            shutil.copyfile(CODE/'run_queue_v2.sh', scripts/'run_queue_v2.sh')
            task = root/'JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1'
            (task/'contracts/main_v2').mkdir(parents=True)
            dump(task/'contracts/main_v2/execution_ready.json', {'synthetic': True})
            fake = root/'fakebin'
            fake.mkdir()
            for name, body in {'nvidia-smi': 'printf "0\\n"', 'awk': 'printf "71\\n"',
                               'df': 'printf "Avail\\n2147483648\\n"'}.items():
                p = fake/name
                p.write_text('#!/usr/bin/env bash\n'+body+'\n')
                p.chmod(0o755)
            runner = '''#!/usr/bin/env bash
set -euo pipefail
region=$1; condition=$2; phase=$3
output="$FAKE_TASK/main_v2/runs/$region/$condition"
mkdir -p "$output"
printf '%s %s %s\n' "$region" "$condition" "$phase" >> "$FAKE_TASK/calls.log"
if [[ "$phase" == train && "$region" == P2 && "$condition" == LC_D005_Pnative ]]; then
    printf '{"status":"FAIL","sentinel":"preserved"}\n' > "$output/train_receipt.json"
    exit 1
fi
if [[ "$phase" != train ]] && grep -q '"status":"FAIL"' "$output/train_receipt.json"; then
    exit 1
fi
printf '{"status":"PASS"}\n' > "$output/${phase}_receipt.json"
'''
            (scripts/'run_phase_v2.sh').write_text(runner)
            env = dict(os.environ, PATH=str(fake)+os.pathsep+os.environ['PATH'], FAKE_TASK=str(task))
            proc = subprocess.run(['bash', str(scripts/'run_queue_v2.sh')], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
            self.assertEqual(proc.returncode, 1, proc.stdout)
            self.assertTrue((task/'main_v2/queue/model_phases_exit_code.txt').exists(), proc.stdout)
            self.assertEqual((task/'main_v2/queue/model_phases_exit_code.txt').read_text().strip(), '1')
            runs = list((task/'main_v2/runs').glob('*/*/train_receipt.json'))
            self.assertEqual(len(runs), 18)
            self.assertEqual(sum(read(path)['status']=='PASS' for path in runs), 17)
            failed = task/'main_v2/runs/P2/LC_D005_Pnative'
            self.assertEqual(read(failed/'train_receipt.json')['sentinel'], 'preserved')
            self.assertFalse((failed/'render_receipt.json').exists())
            self.assertEqual(len(list((task/'main_v2/runs').glob('*/*/metrics_receipt.json'))), 17)
            self.assertIn('ALL_TRAIN_RENDER_METRICS_FINISHED failed=1', (task/'main_v2/queue/events.log').read_text())
            # Re-launch must refuse rather than overwrite failed/completed state.
            second = subprocess.run(['bash', str(scripts/'run_queue_v2.sh')], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(read(failed/'train_receipt.json')['sentinel'], 'preserved')


if __name__ == '__main__':
    unittest.main()
