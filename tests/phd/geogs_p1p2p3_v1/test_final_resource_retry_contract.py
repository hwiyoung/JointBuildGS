"""Finite resource retry gates reject scope drift and preserve earlier history."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / 'scripts/phd/geogs_p1p2p3_v1/no_anchor_v1'
sys.path.insert(0, str(SCRIPTS))
import seal_memory_attempt as seal
import run_phase as driver


class FinalResourceRetryContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        self.source = self.task / 'source'
        self.source.mkdir()
        for name in ('train.py', 'jbgs_memory_recovery.py', 'jbgs_pinned_storage.py',
                     'jbgs_memory_recovery_v1_base.py'):
            (self.source / name).write_text('# fixture ' + name + '\n')
        before = seal.source_map(self.source)
        self.parent = dict(status='PASS_MEMORY_RECOVERY_RUNTIME_PREPARED', storage_version=2,
                           destination_python_sha256=before, original_source_python_sha256={'train.py': 'original'})
        self.write(self.source / 'jbgs_memory_recovery_v2_receipt.json', self.parent)
        (self.source / 'jbgs_memory_recovery_v2_base.py').write_bytes((self.source / 'jbgs_memory_recovery.py').read_bytes())
        (self.source / 'jbgs_memory_recovery.py').write_text('# v3 fixture adapter\n')
        (self.source / 'jbgs_stream_ply.py').write_text('# v3 fixture writer\n')
        actual = seal.source_map(self.source)
        self.runtime = dict(status='PASS_MEMORY_RECOVERY_RUNTIME_PREPARED', scientific_verdict=None,
            science_config_unchanged=True, storage_version=2, resource_recovery_version=3,
            destination_python_sha256=actual, script_sha256='generator',
            adapter_source_sha256=actual['jbgs_memory_recovery.py'],
            added_module_source_sha256={name: value for name, value in actual.items() if name != 'train.py'},
            v2_destination_python_sha256=before,
            v2_runtime_receipt_sha256=seal.sha(self.source / 'jbgs_memory_recovery_v2_receipt.json'),
            original_source_python_sha256=self.parent['original_source_python_sha256'],
            train_py_identical_to_memory_recovery_v2=True, early_parameter_gradient_release=True,
            stream_ply=True, checkpoint_resume_supported=False)
        self.proof = dict(status='PASS_CUDA_RUNTIME_FIXTURE', scientific_verdict=None,
            resource_recovery_version=3, storage_version=2, device='cuda:0', synthetic_optimizer_steps=8,
            maximum_cuda_allocated_bytes=4096, prepared_source_python_sha256=actual,
            early_gradient_release_verified=True, ply_serialization_byte_equal=True,
            validation_sources_sha256={'prepare_runtime.py': 'generator',
                'runtime_adapter.py': actual['jbgs_memory_recovery.py'],
                'stream_ply.py': actual['jbgs_stream_ply.py'], 'verify_runtime.py': seal.V3_VERIFIER_SHA})

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return dict(path=str(path.relative_to(self.task)), bytes=path.stat().st_size, sha256=seal.sha(path))

    def test_v3_exact_source_cuda_and_native_parent_pass(self):
        version, mapping = seal.validate_runtime(self.source, self.runtime, self.proof)
        self.assertEqual(version, 2)
        self.assertEqual(mapping, self.runtime['destination_python_sha256'])

    def test_v3_rejects_cpu_incomplete_proof_and_source_drift(self):
        for field, value in [('status', 'PASS_CPU_RUNTIME_FIXTURE'), ('device', 'cpu'),
                             ('early_gradient_release_verified', False), ('ply_serialization_byte_equal', False),
                             ('synthetic_optimizer_steps', 7), ('resource_recovery_version', 2)]:
            with self.subTest(field=field):
                changed = dict(self.proof, **{field: value})
                with self.assertRaises(ValueError): seal.validate_runtime(self.source, self.runtime, changed)
        (self.source / 'train.py').write_text('# changed native arithmetic\n')
        with self.assertRaises(ValueError): seal.validate_runtime(self.source, self.runtime, self.proof)

    def test_v2_legacy_proof_still_passes(self):
        old = dict(status='PASS_MEMORY_RECOVERY_RUNTIME_PREPARED', scientific_verdict=None,
            science_config_unchanged=True, storage_version=2, script_sha256='v2-generator',
            adapter_source_sha256=self.runtime['adapter_source_sha256'],
            added_module_source_sha256={'jbgs_pinned_storage.py': self.runtime['destination_python_sha256']['jbgs_pinned_storage.py']},
            destination_python_sha256=seal.source_map(self.source))
        proof = dict(status='PASS_CUDA_RUNTIME_FIXTURE', scientific_verdict=None,
            prepared_source_python_sha256=seal.source_map(self.source),
            validation_sources_sha256={'prepare_runtime.py': old['script_sha256'],
                'runtime_adapter.py': old['adapter_source_sha256'],
                'pinned_storage.py': old['added_module_source_sha256']['jbgs_pinned_storage.py']})
        self.assertEqual(seal.validate_runtime(self.source, old, proof)[0], 2)

    def test_frozen_policy_forbids_wrong_region_attempt_or_config(self):
        path = ROOT / 'configs/phd/geogs_p1p2p3_v1/sfm_final_resource_retry_v1.json'
        args = [path, seal.FINAL_POLICY_SHA, 'P1', seal.RETRY_ATTEMPTS['P1'], seal.PREDECESSORS['P1'], seal.SCIENCE_CONFIG_SHA]
        seal.validate_final_policy(*args)
        for index, value in [(1, 'changed'), (3, seal.RETRY_ATTEMPTS['P2']), (4, seal.PREDECESSORS['P2']), (5, 'other-config')]:
            changed = args.copy(); changed[index] = value
            with self.assertRaises(ValueError): seal.validate_final_policy(*changed)

    def predecessor(self):
        amendment = dict(attempt_id=seal.PREDECESSORS['P1'], region='P1', storage_version=2,
            original_config_sha256=seal.SCIENCE_CONFIG_SHA, scientific_verdict=None, status='SEALED_BEFORE_RETRY')
        receipt = dict(status='FAIL', native_exit_code=1, validated_exit_code=1, region='P1', phase='train',
            iteration=None, condition_id='SFM_noanchor_D005_Pnative', scientific_verdict=None,
            config_sha256=seal.SCIENCE_CONFIG_SHA, attempt_id=seal.PREDECESSORS['P1'],
            started_unix=10., finished_unix=20., wall_seconds=10., command=['python', 'train.py'])
        first = dict(status='PASS_FIRST_STEP_DIRECT_REFINEMENT', iteration=1, anchor_iterations_executed=0,
                     pretrained_optimizer_loaded=False, scientific_verdict=None)
        return receipt, first, amendment

    def test_only_closed_training_resource_failure_qualifies(self):
        receipt, first, amendment = self.predecessor()
        def check(r=receipt, f=first, log='torch.cuda.OutOfMemoryError: fixture'):
            return seal.validate_predecessor(r, f, log, amendment, 'P1', seal.SCIENCE_CONFIG_SHA, seal.PREDECESSORS['P1'])
        check()
        for changes in ({'status': 'TRAINING'}, {'status': 'PASS', 'native_exit_code': 0},
                        {'native_exit_code': -15, 'validated_exit_code': -15}, {'finished_unix': None},
                        {'validated_exit_code': 91}, {'command': ['train.py', '--jbgs_resume_full', 'old']}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): check(dict(receipt, **changes))
        with self.assertRaises(ValueError): check(f={})
        with self.assertRaises(ValueError): check(log='Killed')
        check(log='RuntimeError: PINNED_HOST_BUDGET_EXCEEDED: bounded resource refusal')

    def test_cgroup_sigkill_requires_kernel_and_exact_container_proof(self):
        container = 'a' * 64
        receipt, first, amendment = self.predecessor()
        receipt.update(native_exit_code=-9, validated_exit_code=-9)
        proof = dict(schema='GEOGS_NATIVE_RESOURCE_FAILURE_v1', scientific_verdict=None, region='P1',
            condition_id='SFM_noanchor_D005_Pnative', native_exit_code=-9, cause='CGROUP_OOM_KILL',
            kernel_oom_confirmed=True, producer_receipt_sha256='receipt-sha', container_id=container,
            cgroup_path='/system.slice/docker-' + container + '.scope', victim_pid=12, limit_bytes=32 << 30)
        texts = dict(kernel_journal='constraint=CONSTRAINT_MEMCG ' + proof['cgroup_path'] +
            ' task=python,pid=12, Memory cgroup out of memory: Killed process 12 (python)\n'
            'memory: usage 33554432kB, limit 33554432kB', docker_inspect='{"Id":"' + container + '"}',
            docker_inspect_command='docker inspect jbgs-geogs-' + seal.PREDECESSORS['P1'] + '-P1-train')
        def check(p=proof, t=texts):
            return seal.validate_cgroup_failure(p, t, receipt, 'receipt-sha', 'P1', seal.PREDECESSORS['P1'])
        self.assertTrue(check())
        for changes in ({'producer_receipt_sha256': 'wrong'}, {'victim_pid': 13}, {'limit_bytes': 64 << 30},
                        {'kernel_oom_confirmed': False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): check(dict(proof, **changes))
        with self.assertRaises(ValueError): check(t=dict(texts, kernel_journal='Killed'))
        with self.assertRaises(ValueError): check(t=dict(texts, docker_inspect_command='docker inspect unrelated'))
        seal.validate_predecessor(receipt, first, 'Killed', amendment, 'P1', seal.SCIENCE_CONFIG_SHA,
                                 seal.PREDECESSORS['P1'], cgroup_oom=True)

    def test_cgroup_full_evidence_list_preserves_extra_observations_without_using_them_as_cause(self):
        policy = self.task / 'contracts/policy.json'; policy.parent.mkdir()
        policy.write_bytes((ROOT / 'configs/phd/geogs_p1p2p3_v1/sfm_final_resource_retry_v1.json').read_bytes())
        folder = self.task / seal.PREDECESSORS['P1']; folder.mkdir()
        (folder / 'config.json').write_bytes((ROOT / 'configs/phd/geogs_p1p2p3_v1/no_anchor_sfm_v1.json').read_bytes())
        run = folder / 'runs/P1/SFM_noanchor_D005_Pnative'
        receipt, first, amendment = self.predecessor()
        self.write(folder / 'amendment.json', amendment)
        receipt.update(native_exit_code=-9, validated_exit_code=-9,
            memory_recovery_amendment_sha256=seal.sha(folder / 'amendment.json'),
            memory_recovery_amendment_path=seal.PREDECESSORS['P1'] + '/amendment.json')
        self.write(run / 'receipt.json', receipt)
        self.write(run / 'model/jbgs_no_anchor/first_step.json', first)
        (run / 'native.log').write_text('Killed\n')
        container = 'b' * 64
        proof = dict(schema='GEOGS_NATIVE_RESOURCE_FAILURE_v1', scientific_verdict=None, region='P1',
            condition_id='SFM_noanchor_D005_Pnative', native_exit_code=-9, cause='CGROUP_OOM_KILL',
            kernel_oom_confirmed=True, producer_receipt_sha256=seal.sha(run / 'receipt.json'), container_id=container,
            cgroup_path='/system.slice/docker-' + container + '.scope', victim_pid=23, limit_bytes=32 << 30, evidence=[])
        values = [('kernel_journal', 'kernel', 'constraint=CONSTRAINT_MEMCG ' + proof['cgroup_path'] +
            ' task=python,pid=23, Memory cgroup out of memory: Killed process 23 (python)\n'
            'memory: usage 33554432kB, limit 33554432kB'), ('docker_inspect', 'inspect', container),
            ('docker_inspect_command', 'command', 'docker inspect jbgs-geogs-' + seal.PREDECESSORS['P1'] + '-P1-train'),
            ('unavailable_observation', 'empty1', ''), ('unavailable_observation', 'empty2', '')]
        for role, name, text in values:
            path = self.task / (name + '.txt'); path.write_text(text)
            proof['evidence'].append(dict(role=role, **seal.evidence_record(path, self.task)))
        self.write(self.task / 'resource.json', proof)
        args = (self.task, seal.PREDECESSORS['P1'], 'contracts/policy.json', seal.FINAL_POLICY_SHA,
                'P1', seal.RETRY_ATTEMPTS['P1'], seal.SCIENCE_CONFIG_SHA, 'resource.json')
        result, _, _ = seal.final_retry_evidence(*args)
        self.assertEqual(len(result['resource_failure_evidence']), 3)
        (self.task / 'empty2.txt').write_text('changed even though not cause evidence')
        with self.assertRaisesRegex(ValueError, 'Cgroup evidence source changed'): seal.final_retry_evidence(*args)

    def test_driver_requires_exact_bundle_and_inherited_history(self):
        receipt, first, predecessor = self.predecessor()
        predecessor.update(original_failed_run_receipt={'path': 'original/receipt.json', 'sha256': 'original'},
                           original_failed_log={'path': 'original/native.log', 'sha256': 'log'},
                           prior_resource_attempts=[{'fixture_old_cost': 10}])
        evidence = self.task / 'bundle'; evidence.mkdir()
        policy = (ROOT / 'configs/phd/geogs_p1p2p3_v1/sfm_final_resource_retry_v1.json').read_bytes()
        (evidence / 'policy.json').write_bytes(policy)
        self.write(evidence / 'predecessor_amendment.json', predecessor)
        receipt['memory_recovery_amendment_sha256'] = seal.sha(evidence / 'predecessor_amendment.json')
        self.write(evidence / 'predecessor_training_receipt.json', receipt)
        self.write(evidence / 'predecessor_first_step.json', first)
        self.write(evidence / 'runtime_validation.json', self.proof)
        (evidence / 'predecessor_native_log.log').write_text('torch.cuda.OutOfMemoryError: fixture')
        records = {}; meta = dict(region='P1', predecessor_attempt_id=seal.PREDECESSORS['P1'], attempt_index=1,
            max_attempts=1, fresh_only=True, resume=False, automatic_further_retry=False,
            resource_recovery_version=3, storage_version=2)
        for path in evidence.iterdir():
            key = path.stem
            record = dict(filename=path.name, bytes=path.stat().st_size, sha256=seal.sha(path))
            records[key] = record
            if key != 'runtime_validation': meta[key] = dict(path='canonical/' + path.name, **record)
        amendment = dict(resource_recovery_version=3, attempt_id=seal.RETRY_ATTEMPTS['P1'],
            final_resource_retry=meta, final_retry_evidence_bundle=records,
            validation={'sha256': seal.sha(evidence / 'runtime_validation.json')})
        for key in ('original_failed_run_receipt', 'original_failed_log', 'prior_resource_attempts'):
            amendment[key] = predecessor[key]
        args = (amendment, self.runtime, self.source, evidence, 'P1', seal.SCIENCE_CONFIG_SHA)
        driver.validate_v3_bundle(*args)
        amendment['prior_resource_attempts'] = []
        with self.assertRaisesRegex(ValueError, 'earlier failure history'): driver.validate_v3_bundle(*args)


if __name__ == '__main__': unittest.main()
