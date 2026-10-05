import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.phd.geogs_mvs_pgsr_v1.viewer.surface_selection import resolve_surface


class SurfaceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        self.parameters = dict(mesh_res=512, num_cluster=50, voxel_size_m=.3, sdf_trunc_m=1.5, depth_trunc_m=150.)
        self.args = dict(region='P1', mode='mvs', prior=.005,
                         training_relative='train/P1/mvs_0.005/attempt.training', ply_sha='a'*64,
                         config_sha='b'*64, source_sha='c'*64, input_manifest_sha='d'*64,
                         expected_extraction=self.parameters, runtime_image_id='sha256:'+'e'*64)

    def make(self, tier='evaluation', attempt='attempt.a', raw_sha='1'*64, **job_changes):
        identifier = 'P1.mvs.D005_Pnative'
        folder = self.task / tier / attempt / 'extractions' / identifier
        folder.mkdir(parents=True)
        record = dict(path='model/train/ours_30000/fuse.ply', sha256=raw_sha, bytes=4)
        raw = folder / record['path']; raw.parent.mkdir(parents=True); raw.write_bytes(b'mesh')
        job = dict(id=identifier, region='P1', mode='mvs', prior=.005,
                   training_relative=self.args['training_relative'], config_sha256=self.args['config_sha'],
                   source_provenance_sha256=self.args['source_sha'], input_manifest_sha256=self.args['input_manifest_sha'],
                   files=[dict(path=self.args['training_relative']+'/model/point_cloud/iteration_30000/point_cloud.ply',
                               sha256=self.args['ply_sha'], bytes=10)], scientific_verdict=None)
        job.update(job_changes)
        receipt = dict(status='PASS', scientific_verdict=None, exit_code=0, job=job,
                       runtime_image_id=self.args['runtime_image_id'], realized_extraction=self.parameters.copy(),
                       surfaces=dict(raw=record))
        self.save(folder / 'receipt.json', receipt)
        if tier == 'matched_comparison_v1':
            self.save(folder.parent.parent / 'receipt.json', dict(status='PASS_MATCHED_COMPARISON', scientific_verdict=None))
            self.save(folder.parent.parent / 'plan.json', dict(runs=[copy.deepcopy(job)], scientific_verdict=None))
        return folder, receipt

    def save(self, path, value):
        path.write_text(json.dumps(value))

    def resolve(self):
        return resolve_surface(self.task, **self.args)

    def test_pending_is_none(self):
        self.assertIsNone(self.resolve())
        folder, receipt = self.make(); receipt['status'] = 'FAIL'; self.save(folder/'receipt.json', receipt)
        self.assertIsNone(self.resolve())

    def test_exact_run_and_raw_record_return(self):
        folder, receipt = self.make()
        self.assertEqual(self.resolve(), (folder, receipt['surfaces']['raw'], 'canonical_finalization'))

    def test_other_training_run_is_skipped(self):
        self.make(training_relative='train/P1/mvs_0.005/attempt.other', config_sha256='wrong')
        self.assertIsNone(self.resolve())

    def test_same_run_bad_provenance_raises(self):
        folder, receipt = self.make()
        for key in ('region', 'mode', 'prior', 'id', 'config_sha256', 'source_provenance_sha256', 'input_manifest_sha256'):
            with self.subTest(key=key):
                changed = copy.deepcopy(receipt); changed['job'][key] = 'wrong'; self.save(folder/'receipt.json', changed)
                with self.assertRaisesRegex(ValueError, 'job mismatch'):
                    self.resolve()

    def test_exact_ply_path_and_hash_are_required(self):
        folder, receipt = self.make()
        for change in (dict(sha256='f'*64), dict(path='other/model/point_cloud/iteration_30000/point_cloud.ply')):
            changed = copy.deepcopy(receipt); changed['job']['files'][0].update(change)
            self.save(folder/'receipt.json', changed)
            with self.assertRaisesRegex(ValueError, 'final PLY'):
                self.resolve()

    def test_extraction_parameters_and_runtime_must_match(self):
        folder, receipt = self.make()
        for key in self.parameters:
            changed = copy.deepcopy(receipt); changed['realized_extraction'][key] += .01
            self.save(folder/'receipt.json', changed)
            with self.assertRaisesRegex(ValueError, 'parameter mismatch'):
                self.resolve()
        changed = copy.deepcopy(receipt); changed['runtime_image_id'] = 'wrong'; self.save(folder/'receipt.json', changed)
        with self.assertRaisesRegex(ValueError, 'runtime image'):
            self.resolve()

    def test_scientific_null_explicit_at_job_and_receipt(self):
        folder, receipt = self.make()
        for where in ('receipt', 'job'):
            changed = copy.deepcopy(receipt)
            target = changed if where == 'receipt' else changed['job']
            del target['scientific_verdict']; self.save(folder/'receipt.json', changed)
            with self.assertRaisesRegex(ValueError, 'scientific_verdict null'):
                self.resolve()

    def test_canonical_precedes_conflicting_matched(self):
        folder, receipt = self.make()
        self.make('matched_comparison_v1', raw_sha='2'*64, config_sha256='wrong')
        self.assertEqual(self.resolve(), (folder, receipt['surfaces']['raw'], 'canonical_finalization'))

    def test_matched_requires_completed_root_and_exact_job(self):
        folder, receipt = self.make('matched_comparison_v1')
        self.assertEqual(self.resolve()[2], 'matched_comparison')
        root = folder.parent.parent
        completion = root / 'receipt.json'; completion.unlink()
        self.assertIsNone(self.resolve())
        self.save(completion, dict(status='PASS_MATCHED_COMPARISON', scientific_verdict=None))
        plan = json.loads((root/'plan.json').read_text()); plan['runs'][0]['files'][0]['sha256'] = 'wrong'
        self.save(root/'plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'exact extraction job'):
            self.resolve()

    def test_same_tier_identical_hash_deduplicates_and_conflict_fails(self):
        for tier in ('evaluation', 'matched_comparison_v1'):
            with self.subTest(tier=tier), tempfile.TemporaryDirectory() as temporary:
                self.task = Path(temporary)
                first, _ = self.make(tier, 'attempt.a')
                second, receipt = self.make(tier, 'attempt.b')
                self.assertEqual(self.resolve()[0], first)
                receipt['surfaces']['raw']['sha256'] = '2'*64; self.save(second/'receipt.json', receipt)
                with self.assertRaisesRegex(ValueError, 'different SHA256'):
                    self.resolve()

    def test_raw_path_traversal_and_symlink_escape_fail(self):
        folder, receipt = self.make()
        for relative in ('../../outside.ply', '/tmp/outside.ply'):
            changed = copy.deepcopy(receipt); changed['surfaces']['raw']['path'] = relative
            self.save(folder/'receipt.json', changed)
            with self.assertRaisesRegex(ValueError, 'contained relative path'):
                self.resolve()
        raw = folder / receipt['surfaces']['raw']['path']; raw.unlink()
        outside = self.task / 'outside.ply'; outside.write_bytes(b'mesh'); raw.symlink_to(outside)
        self.save(folder/'receipt.json', receipt)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.resolve()

    def test_helper_does_not_claim_payload_hash_verification(self):
        folder, receipt = self.make()
        (folder / receipt['surfaces']['raw']['path']).write_bytes(b'different bytes')
        self.assertIsNotNone(self.resolve())  # The builder factory must check the actual SHA before export.


if __name__ == '__main__':
    unittest.main()
