"""Synthetic preservation failures only; no regional/reference payload access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3]/'scripts/phd/geogs_p1p2p3_v1/preservation/verify_final.py'
spec = importlib.util.spec_from_file_location('final_preservation', SCRIPT)
final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final)


class FinalPreservationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo, self.task, self.output = [self.root/name for name in ('repo','task','out')]
        for path in (self.repo,self.task,self.output):
            path.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def baseline(self):
        rows = []
        for name in ('historical/data.bin','scripts/phd/geogs_p1p2p3_v1/preexisting.py'):
            path = self.repo/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'original')
            rows.append(dict(path=name,bytes=path.stat().st_size,sha256=final.sha(path)))
        return dict(files=rows)

    def seal(self):
        source = self.task/'producer.bin'
        source.write_bytes(b'producer')
        value = dict(schema='JBGS_GEOGS_CANDIDATES_SEALED_v2',
                     status='ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED',
                     reference_accessed=False, scientific_verdict=None,
                     files=[final.record(self.task,source)], candidates=[dict(synthetic=True)],
                     extraction_inventory=[dict(synthetic=True)], config_sha256='config',
                     runtime_layout_sha256='layout',repeat_contract_sha256='repeat',resource_contract_sha256='resource')
        path = self.task/'contracts/candidates_sealed_v1.json'
        path.parent.mkdir()
        final.dump(path,value)
        return value,path

    def gate_factory(self, value, path):
        class Gate:
            def candidate_seal(self):
                return value,final.sha(path)
        return lambda task:Gate()

    def test_all_original_members_hashed_even_inside_current_task_prefix(self):
        baseline = self.baseline()
        rows = final.hash_baseline(self.repo,baseline,2,self.output)
        self.assertEqual([row['status'] for row in rows],['PASS_BYTES','PASS_BYTES'])
        self.assertTrue(all(row['current_sha256'] == row['baseline_sha256'] for row in rows))

    def test_same_size_tamper_and_missing_are_both_reported(self):
        baseline = self.baseline()
        (self.repo/baseline['files'][0]['path']).write_bytes(b'modified')
        (self.repo/baseline['files'][1]['path']).unlink()
        rows = final.hash_baseline(self.repo,baseline,2,self.output)
        self.assertEqual([row['status'] for row in rows],['CHANGED_BYTES_OR_DURING_CHECK','MISSING_OR_UNREADABLE'])
        self.assertEqual(len((self.output/'baseline_file_checks.jsonl').read_text().splitlines()),2)

    def test_missing_gate_prevents_any_baseline_hashing(self):
        with patch.object(final,'hash_baseline',side_effect=AssertionError('payload access before seal')) as hashing:
            with self.assertRaises(FileNotFoundError):
                final.final_check(self.repo,self.task,self.output)
            hashing.assert_not_called()
        self.assertFalse((self.output/'baseline_file_checks.jsonl').exists())

    def test_gate_rejects_sealed_producer_tamper(self):
        value,path = self.seal()
        (self.task/'producer.bin').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'Sealed producer bytes changed'):
            final.seal_gate(self.task,self.output,self.gate_factory(value,path))
        self.assertFalse((self.output/'candidate_seal_gate.json').exists())

    def test_gate_rejects_noncomplete_or_changed_seal(self):
        value,path = self.seal()
        value['status']='PARTIAL'
        with self.assertRaisesRegex(ValueError,'Actual resource-amended candidate seal'):
            final.seal_gate(self.task,self.output,self.gate_factory(value,path))
        value['status']='ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED'
        final.seal_gate(self.task,self.output,self.gate_factory(value,path))
        final.require_gate(self.task,self.output)
        path.write_text(path.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'Candidate seal changed'):
            final.require_gate(self.task,self.output)

    def test_unknown_document_metadata_and_omitted_symlink_reconciliation(self):
        target = '../unchanged_target'
        link = self.repo/'omitted_link'
        link.symlink_to(target,target_is_directory=True)
        unknown = self.repo/'unknown.md'
        unknown.write_text('not read by reconciliation')
        info=unknown.stat()
        reconciliation=dict(baseline_snapshot_omitted_symlink=dict(path='omitted_link',current_target=target,
            head_target=target,head_entry='120000 blob hash\tomitted_link',baseline_limitation='omitted directory symlink'),
            new_observed_outside_scope=dict(path='unknown.md',bytes=info.st_size,mtime_ns=info.st_mtime_ns,git_status='?? unknown.md'))
        def git(repo,*args):
            return {'show':target,'ls-tree':'120000 blob hash\tomitted_link','status':'?? unknown.md'}[args[0]].encode()
        with patch.object(final,'git',side_effect=git):
            symlink,observed,known,outside=final.reconcile_paths(self.repo,dict(files=[]),reconciliation,
                {'omitted_link','unknown.md','unexplained.md'})
            self.assertEqual(symlink['status'],'PASS_HEAD_SYMLINK_TARGET')
            self.assertEqual(observed['status'],'PASS_OBSERVED_METADATA_ONLY')
            self.assertFalse(observed['content_read'])
            self.assertEqual(outside,['unexplained.md'])
            unknown.write_text('changed size')
            self.assertEqual(final.reconcile_paths(self.repo,dict(files=[]),reconciliation,set())[1]['status'],
                             'DIFFERENCE_REQUIRES_REVIEW')


if __name__ == '__main__':
    unittest.main()
