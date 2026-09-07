"""CPU synthetic archive checks; no live task, GPU, model deserialization or reference."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
RUNTIME = REPO / 'scripts/phd/geogs_p1p2p3_v1/runtime'
CONFIG = REPO / 'configs/phd/geogs_p1p2p3_v1/native_repeat_retry_v1.json'
spec = importlib.util.spec_from_file_location('failed_archive', RUNTIME / 'verify_failed_repeat_archive.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class FailedArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.destination = self.root / 'preserved_failed_run'
        self.evidence = self.root / 'metadata'
        self.source.mkdir()
        self.evidence.mkdir()
        self.cfg = json.loads(CONFIG.read_text())
        self.region = 'P1'
        target = self.cfg['targets'][self.region]
        self.source_host = self.cfg['task_root'] + '/' + target['relative_directory']
        self.archive_host = self.cfg['task_root'] + '/runtime/native_repeat_retry_v1/P1/attempt.SYN001/preserved_failed_run'
        self.invocation = dict(task_id=self.cfg['task_id'], region='P1', condition='D005_Pnative', phase='train',
            repeat_id='native_repeat_1', supplemental_only=True, training_start_iteration=8000,
            config_sha256=self.cfg['scientific_config_sha256'], runtime_layout_sha256=self.cfg['runtime_layout_sha256'],
            repeat_contract_sha256=self.cfg['repeat_contract_sha256'], runtime_image_id=self.cfg['runtime_image_id'],
            runtime_revision='allocator_v2', input_manifest_sha256=target['input_manifest_sha256'],
            repeat_anchor_checkpoint_sha256=target['anchor_checkpoint_sha256'], repeat_anchor_gate_sha256=target['anchor_gate_sha256'],
            scientific_verdict=None, prior_initialization_and_anchor_retained=True, image_only=False,
            environment=self.cfg['environment'], command=['python', 'train.py', '--synthetic-fixture-only'],
            started_unix=100, implementation_hashes={f'synthetic_{index}.py': f'{index:064x}' for index in range(45)})
        self.receipt = dict(self.invocation, status='FAIL', native_exit_code=1, validated_exit_code=1,
                            wall_seconds=123.125, child_peak_rss_bytes=876543)
        self.write_failure()
        checkpoint = self.source / 'model/jbgs_complete/iteration_8100'
        checkpoint.mkdir(parents=True)
        (checkpoint / 'checkpoint.pth').write_bytes(b'SYNTHETIC opaque checkpoint bytes; never deserialize\x00\xff')
        (checkpoint / 'point_cloud.ply').write_bytes(b'SYNTHETIC opaque PLY fixture; never parse')
        (self.source / 'model/empty/nested').mkdir(parents=True)
        (self.source / 'train.log').write_bytes(b'SYNTHETIC failure stdout retained verbatim\n')
        self.config_path = self.evidence / 'config.json'
        self.config_path.write_text(json.dumps(self.cfg))

    def tearDown(self):
        self.temporary.cleanup()

    def write_failure(self):
        for name, value, key in [('train_invocation.json', self.invocation, 'failed_invocation_sha256'),
                                 ('train_receipt.json', self.receipt, 'failed_receipt_sha256')]:
            path = self.source / name
            path.write_text(json.dumps(value))
            self.cfg['targets'][self.region][key] = archive.sha(path)

    def preflight(self):
        # Lower-level byte/metadata functions use synthetic pins; the production
        # CLI separately validates hard-coded original pins in validate_config.
        return archive.preflight(self.source, self.evidence, self.config_path, self.cfg,
                                 self.region, self.source_host, self.archive_host)

    def move_fixture(self):
        self.source.rename(self.destination)
        (self.evidence / 'mv_exit_code.txt').write_text('0\n')
        (self.evidence / 'source_absence_postcheck.txt').write_text('PASS_SOURCE_ABSENT\n')

    def post(self):
        return archive.post(self.destination, self.evidence, self.config_path, self.cfg,
                            self.region, self.source_host, self.archive_host)

    def test_checked_in_config_accepts_only_exact_two_original_failures(self):
        cfg = json.loads(CONFIG.read_text())
        archive.validate_config(cfg)
        mutations = [lambda c: c['targets']['P1'].update(failed_receipt_sha256='f' * 64),
                     lambda c: c['targets']['P2'].update(failed_invocation_sha256='a' * 64),
                     lambda c: c.update(maximum_additional_attempts_per_region=2),
                     lambda c: c.update(seed=1),
                     lambda c: c.update(targets={**c['targets'], 'P3': c['targets']['P2']}),
                     lambda c: c['targets']['P1'].update(gpu_lock_index=1)]
        for mutate in mutations:
            changed = copy.deepcopy(cfg)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                archive.validate_config(changed)

    def test_8100_opaque_payloads_and_empty_directories_survive_once(self):
        pre = self.preflight()
        self.assertFalse(pre['moved'])
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.source.stat().st_ino, pre['root_identity']['inode'])
        (self.evidence / 'post_stdout.log').write_text('OPEN STREAM')
        (self.evidence / 'post_stderr.log').write_text('')
        self.move_fixture()
        result = self.post()
        self.assertEqual(result['status'], 'PASS_ORIGINAL_FAILURE_ARCHIVED_BYTE_IDENTICALLY')
        self.assertIn('model/empty/nested', result['empty_directories'])
        self.assertFalse(result['retry_launched'])
        self.assertFalse(self.source.exists())
        self.assertEqual(archive.read(self.evidence / 'before_manifest.json'), archive.read(self.evidence / 'after_manifest.json'))
        inventory = archive.read(self.evidence / 'closed_metadata_inventory.json')
        self.assertNotIn('post_stdout.log', {row['path'] for row in inventory['files']})
        (self.evidence / 'post_stdout.log').write_text('CLOSED STREAM WITH NEW OUTPUT')
        for item in inventory['files']:
            archive.checked(self.evidence, item)
        with self.assertRaises(FileNotFoundError):
            self.preflight()

    def test_changed_original_receipt_is_rejected_before_manifest(self):
        (self.source / 'train_receipt.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'exact original failed receipt'):
            self.preflight()
        self.assertFalse((self.evidence / 'before_manifest.json').exists())

    def test_changed_invocation_is_rejected(self):
        (self.source / 'train_invocation.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'exact original failed invocation'):
            self.preflight()

    def test_success_or_wrong_identity_rejected_even_with_synthetic_digest_binding(self):
        for key, value in [('status', 'PASS'), ('native_exit_code', 0), ('validated_exit_code', 0),
                           ('repeat_id', 'different_repeat'), ('region', 'P2'), ('scientific_verdict', 'PASS')]:
            saved = dict(self.receipt)
            self.receipt[key] = value
            self.write_failure()
            with self.subTest(key=key), self.assertRaises(ValueError):
                archive.validate_failure(self.source, self.cfg, self.region)
            self.receipt = saved

    def test_later_failed_retry_cannot_reuse_original_admission_hashes(self):
        original = copy.deepcopy(self.cfg)
        self.invocation['started_unix'] = 200
        self.receipt = dict(self.receipt, started_unix=200, wall_seconds=130)
        self.write_failure()
        with self.assertRaisesRegex(ValueError, 'no repeated retry'):
            archive.validate_failure(self.source, original, self.region)

    def test_symlink_and_final_artifact_markers_rejected(self):
        link = self.source / 'model/external'
        link.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'Symlink prohibited'):
            archive.tree_manifest(self.source)
        link.unlink()
        for relative in ['model/jbgs_complete/iteration_30000', 'model/point_cloud/iteration_30000',
                         'model/train', 'complete.json', 'render_receipt.json', 'model/results.json']:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'Final/completed artifact'):
                archive.tree_manifest(self.source)
            path.unlink()

    def test_unapproved_or_escaping_source_destination_rejected(self):
        for source, destination in [(self.source_host.replace('/P1/', '/P2/'), self.archive_host),
                                    (self.source_host, self.archive_host.replace('/P1/', '/P2/')),
                                    (self.source_host, self.archive_host.replace('attempt.SYN001', '../attempt.SYN001')),
                                    (self.source_host, self.archive_host.replace('preserved_failed_run', 'replacement'))]:
            with self.subTest(source=source, destination=destination), self.assertRaises(ValueError):
                archive.mapping(self.cfg, self.region, source, destination)

    def test_post_detects_changed_file_bytes(self):
        self.preflight()
        self.move_fixture()
        (self.destination / 'model/jbgs_complete/iteration_8100/checkpoint.pth').write_bytes(b'TAMPERED')
        with self.assertRaisesRegex(ValueError, 'Archive files/bytes/modes/directories differ'):
            self.post()
        self.assertFalse((self.evidence / 'archive_receipt.json').exists())

    def test_post_detects_removed_empty_directory(self):
        self.preflight()
        self.move_fixture()
        (self.destination / 'model/empty/nested').rmdir()
        with self.assertRaisesRegex(ValueError, 'Archive files/bytes/modes/directories differ'):
            self.post()

    def test_post_detects_changed_mode(self):
        self.preflight()
        self.move_fixture()
        path = self.destination / 'train.log'
        path.chmod(stat.S_IMODE(path.stat().st_mode) ^ stat.S_IXUSR)
        with self.assertRaisesRegex(ValueError, 'Archive files/bytes/modes/directories differ'):
            self.post()

    def test_post_requires_preflight_hashes_and_host_source_absence(self):
        self.preflight()
        self.move_fixture()
        (self.evidence / 'source_absence_postcheck.txt').unlink()
        with self.assertRaises(FileNotFoundError):
            self.post()
        (self.evidence / 'source_absence_postcheck.txt').write_text('PASS_SOURCE_ABSENT\n')
        (self.evidence / 'before_manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Closed evidence hash/bytes changed'):
            self.post()

    def test_failed_preflight_cannot_reach_host_mv_in_real_shell_wrapper(self):
        repo = self.root / 'fixture_repo'
        runtime = repo / 'scripts/phd/geogs_p1p2p3_v1/runtime'
        runtime.mkdir(parents=True)
        scripts = ['archive_failed_repeat.sh', 'verify_failed_repeat_archive.py']
        for name in scripts:
            shutil.copyfile(RUNTIME / name, runtime / name)
        config = repo / 'configs/phd/geogs_p1p2p3_v1/native_repeat_retry_v1.json'
        config.parent.mkdir(parents=True)
        shutil.copyfile(CONFIG, config)
        task = self.root / 'JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1'
        source = task / 'native_repeat_allocator_v2/P1/D005_Pnative'
        source.mkdir(parents=True)
        (source / 'SYNTHETIC_FAILURE_UNCHANGED').write_bytes(b'Never move after failed preflight')
        (task / 'queue_allocator_v2/locks').mkdir(parents=True)
        binaries = self.root / 'mock_bin'
        binaries.mkdir()
        for name, text in {
            'docker': '#!/bin/sh\nif test "$1" = ps; then exit 0; fi\nexit 73\n',
            'git': '#!/bin/sh\nprintf "synthetic_git_head\\n"\n',
            'mv': '#!/bin/sh\nprintf "BAD_MV_REACHED\\n" >&2\nexit 99\n'}.items():
            path = binaries / name
            path.write_text(text)
            path.chmod(0o755)
        result = subprocess.run(['bash', str(runtime / scripts[0]), 'P1'],
                                env=dict(os.environ, PATH=str(binaries) + ':' + os.environ['PATH']), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('BAD_MV_REACHED', result.stderr)
        self.assertEqual((source / 'SYNTHETIC_FAILURE_UNCHANGED').read_bytes(), b'Never move after failed preflight')
        attempts = list((task / 'runtime/native_repeat_retry_v1/P1').glob('attempt.*'))
        self.assertEqual(len(attempts), 1, result.stdout + result.stderr)
        self.assertEqual((attempts[0] / 'metadata/preflight_exit_code.txt').read_text().strip(), '73')
        self.assertFalse((attempts[0] / 'metadata/move_command.sh').exists())
        self.assertFalse((attempts[0] / 'preserved_failed_run').exists())


if __name__ == '__main__':
    unittest.main()
