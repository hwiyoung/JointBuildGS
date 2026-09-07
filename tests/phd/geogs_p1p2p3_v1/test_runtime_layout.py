"""Runtime-only revision and exact mixed-origin anchor provenance fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULES = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
from runtime_layout import RuntimeLayout, sha
import seal_candidates as seal
import summarize


class RuntimeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.config = self.save('contracts/execution_v1.json', {'scientific_verdict':None})
        self.data = dict(schema='geogs_runtime_layout_v1', revision='allocator_v2', scientific_verdict=None,
                         runs_directory='runs_allocator_v2', parity_directory='parity_allocator_v2', queue_directory='queue_allocator_v2',
                         allocator='backend:native,max_split_size_mb:128', scientific_config_sha256=sha(self.config), anchors={})
        for region in ('P1', 'P2', 'P3'):
            baseline = ('runs' if region=='P1' else 'runs_allocator_v2')+'/'+region+'/D005_Pnative'
            self.data['anchors'][region] = dict(baseline_directory=baseline,
                checkpoint_directory=baseline+'/model/jbgs_complete/iteration_8000', native_final_starts_from_anchor=region=='P1')
        self.path = self.save('contracts/runtime_layout_allocator_v2.json', self.data)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, relative, value):
        path = self.task/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def bind(self, path):
        return dict(path=str(path.relative_to(self.task)), sha256=sha(path), bytes=path.stat().st_size)

    def test_explicit_revision_routes_all_finals_and_mixed_anchors(self):
        layout = RuntimeLayout(self.task, self.path)
        layout.require_scientific_config(self.config)
        for region in ('P1','P2','P3'):
            self.assertEqual(layout.run(region, 'D005_Pnative'), self.task/f'runs_allocator_v2/{region}/D005_Pnative')
        self.assertEqual(layout.anchor_checkpoint('P1'), self.task/'runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000')
        self.assertEqual(layout.anchor_checkpoint('P2'), self.task/'runs_allocator_v2/P2/D005_Pnative/model/jbgs_complete/iteration_8000')
        self.assertTrue(layout.starts_from_anchor('P1', 'D005_Pnative'))
        self.assertFalse(layout.starts_from_anchor('P2', 'D005_Pnative'))
        self.assertTrue(layout.starts_from_anchor('P3', 'changed'))

    def test_legacy_default_does_not_implicitly_select_new_layout(self):
        legacy = RuntimeLayout(self.task)
        self.assertEqual(legacy.run('P1', 'D005_Pnative'), self.task/'runs/P1/D005_Pnative')
        with self.assertRaisesRegex(ValueError, 'exact explicit'):
            legacy.require_receipt({'runtime_layout_sha256':sha(self.path)})

    def test_changed_contract_bytes_or_scientific_config_are_rejected(self):
        before = RuntimeLayout(self.task, self.path)
        self.data['reason'] = 'different operational revision bytes'
        self.save('contracts/runtime_layout_allocator_v2.json', self.data)
        after = RuntimeLayout(self.task, self.path)
        with self.assertRaises(ValueError):
            after.require_receipt(before.binding())
        self.config.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'unchanged scientific'):
            after.require_scientific_config(self.config)

    def test_escaping_paths_wrong_region_or_wrong_iteration_are_rejected(self):
        for update in ('escape', 'region', 'iteration'):
            changed = json.loads(json.dumps(self.data))
            if update=='escape':
                changed['runs_directory'] = '../other_task'
            elif update=='region':
                changed['anchors']['P1']['baseline_directory'] = 'runs/P2/D005_Pnative'
            else:
                changed['anchors']['P1']['checkpoint_directory'] = 'runs/P1/D005_Pnative/model/jbgs_complete/iteration_8100'
            self.save('contracts/runtime_layout_allocator_v2.json', changed)
            with self.assertRaises(ValueError):
                RuntimeLayout(self.task, self.path)

    def test_phase_start_iteration_is_bound_for_resumed_native(self):
        layout = RuntimeLayout(self.task, self.path)
        receipt = dict(status='PASS', region='P1', condition='D005_Pnative', phase='train',
                       config_sha256=sha(self.config), input_manifest_sha256='i'*64,
                       runtime_layout_sha256=layout.digest, training_start_iteration=8000)
        seal.validate_phase_receipt(receipt, 'P1', 'D005_Pnative', 'train', sha(self.config), 'i'*64, layout)
        with self.assertRaisesRegex(ValueError, 'start iteration'):
            seal.validate_phase_receipt(dict(receipt, training_start_iteration=0), 'P1', 'D005_Pnative', 'train', sha(self.config), 'i'*64, layout)

    def prepare_anchor(self):
        layout = RuntimeLayout(self.task, self.path)
        directory = layout.anchor_checkpoint('P1')
        directory.mkdir(parents=True)
        (directory/'checkpoint.pth').write_bytes(b'synthetic state bytes; not a real torch checkpoint')
        (directory/'point_cloud.ply').write_bytes(b'synthetic exact anchor PLY identity')
        self.save(str((directory/'receipt.json').relative_to(self.task)), dict(iteration=8000, after_protection_registration=True,
            checkpoint_sha256=sha(directory/'checkpoint.pth'), ply_sha256=sha(directory/'point_cloud.ply')))
        baseline = layout.anchor_baseline('P1')
        self.save(str((baseline/'train_receipt.json').relative_to(self.task)), dict(region='P1', condition='D005_Pnative', phase='train',
            config_sha256=sha(self.config), input_manifest_sha256='i'*64, status='FAIL', wall_seconds=99999))
        trace = baseline/'model/jbgs_trace.jsonl'
        trace.write_text(json.dumps(dict(iteration=8000, elapsed_seconds=20))+'\n'+json.dumps(dict(iteration=14700, elapsed_seconds=400))+'\n')
        return layout, seal.bind_anchor(layout, 'P1', sha(self.config), 'i'*64, self.bind)

    def test_failed_source_run_keeps_complete_anchor_and_separate_cost(self):
        layout, anchor = self.prepare_anchor()
        self.assertEqual(anchor['source_run_status'], 'FAIL')
        rows = summarize.anchor_resource_records(self.task, 'P1', anchor, layout)
        prefix, failed = rows
        self.assertEqual(prefix['anchor_prefix_elapsed_seconds'], 20)
        self.assertIsNone(prefix['wall_seconds'])
        self.assertEqual(failed['raw_phase_wall_seconds'], 99999)
        self.assertEqual(failed['cost_category'], 'FAILED_ATTEMPT_NOT_ANCHOR_COST')
        self.assertFalse(failed['additive_to_final_phase_totals'])

    def test_new_auxiliary_anchor_must_copy_old_exact_ply(self):
        layout, anchor = self.prepare_anchor()
        run = layout.run('P1', 'D005_Pnative')
        point = run/'auxiliary/anchor/model/point_cloud/iteration_8000/point_cloud.ply'
        point.parent.mkdir(parents=True)
        point.write_bytes((self.task/anchor['point_cloud']['path']).read_bytes())
        self.save(str((run/'auxiliary/anchor/receipt.json').relative_to(self.task)), dict(status='PASS', iteration=8000,
            config_sha256=sha(self.config), runtime_layout_sha256=layout.digest,
            source_complete_ply_sha256=anchor['point_cloud']['sha256'], copied_ply_sha256=sha(point)))
        result = seal.bind_auxiliary_anchor(run, anchor, layout, sha(self.config), self.bind)
        self.assertIn('runs_allocator_v2/P1', result['copied_point_cloud']['path'])
        point.write_bytes(b'wrong anchor')
        with self.assertRaisesRegex(ValueError, 'copy changed'):
            seal.bind_auxiliary_anchor(run, anchor, layout, sha(self.config), self.bind)

    def test_resumed_resource_walltime_is_not_reported_as_full_pipeline(self):
        layout = RuntimeLayout(self.task, self.path)
        run = layout.run('P1', 'D005_Pnative')
        files = {}
        for phase in ('train', 'render', 'metrics', 'auxiliary'):
            path = self.save(str((run/(phase+'_receipt.json')).relative_to(self.task)), dict(status='PASS',
                runtime_layout_sha256=layout.digest, training_start_iteration=8000 if phase=='train' else None,
                wall_seconds=100, child_peak_rss_bytes=1024))
            record = self.bind(path)
            files[record['path']] = record
        trace = run/'model/jbgs_trace.jsonl'
        trace.parent.mkdir(parents=True)
        trace.write_text(json.dumps(dict(iteration=30000, elapsed_seconds=95, peak_cuda_allocated_bytes=100,
            peak_cuda_reserved_bytes=200, peak_rss_bytes=1024, gaussians=10, protected=5))+'\n')
        record = self.bind(trace)
        files[record['path']] = record
        rows = summarize.resource_records(self.task, 'P1', 'D005_Pnative', layout, files)
        self.assertTrue(rows[0]['shared_anchor'])
        self.assertEqual(rows[0]['raw_phase_wall_seconds'], 100)
        self.assertTrue(all(row['full_pipeline_wall_seconds'] is None for row in rows))
        self.assertIsNone(rows[-1]['anchor_prefix_elapsed_seconds'])
        self.assertEqual(rows[-1]['post_anchor_instrumented_interval_seconds'], 95)

    def extraction(self, resolution=1024, depth=80.):
        return dict(schema='GEOGS_BOUNDED_TSDF_LOG_PARAMETERS_v1', mesh_res=resolution, num_cluster=50,
                    depth_trunc_m=depth, voxel_size_m=depth/resolution, sdf_trunc_m=5*depth/resolution,
                    source_log_sha256='l'*64, parser_sha256='p'*64, tsdf_block_count=1,
                    numeric_relationship_policy='EXACT_FLOAT_EQUALITY_FOR_ROUNDTRIP_LOGGED_VALUES')

    def validate_extraction(self, value, seen, region='P1'):
        return seal.validate_realized_extraction(value, dict(sha256='l'*64), dict(sha256='p'*64),
                                                 region, value['mesh_res'], 50, seen)

    def test_extraction_same_camera_tuple_across_arms_anchor_and_resolutions(self):
        seen = {}
        for resolution in (1024, 512, 2048, 1024):
            self.validate_extraction(self.extraction(resolution), seen)
        self.assertEqual(len(seen), 3)
        self.validate_extraction(self.extraction(depth=90.), seen, region='P2')
        with self.assertRaisesRegex(ValueError, 'tuple differs'):
            self.validate_extraction(self.extraction(depth=81.), seen)
        with self.assertRaisesRegex(ValueError, 'across extraction resolutions'):
            self.validate_extraction(self.extraction(4096, depth=81.), seen)

    def test_extraction_rejects_wrong_log_parser_nonfinite_and_default_algebra(self):
        for key, value in [('source_log_sha256', 'bad'), ('parser_sha256', 'bad'),
                           ('depth_trunc_m', float('nan')), ('sdf_trunc_m', .4), ('num_cluster', 49)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate_extraction(dict(self.extraction(), **{key:value}), {})

    def test_auxiliary_extraction_binds_actual_inputs_log_and_parser(self):
        layout = RuntimeLayout(self.task, self.path)
        run = layout.run('P1', 'D005_Pnative')
        directory = run/'auxiliary/mesh_512'
        directory.mkdir(parents=True)
        for name, content in [('render.log', b'fixture log'), ('parse_extraction_snapshot.py', b'fixture parser'),
                              ('model/cfg_args', b'fixture namespace'),
                              ('model/point_cloud/iteration_30000/point_cloud.ply', b'fixture ply'),
                              ('model/train/ours_30000/fuse.ply', b'fixture raw mesh'),
                              ('model/train/ours_30000/fuse_post.ply', b'fixture post mesh')]:
            path = directory/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        point_sha = sha(directory/'model/point_cloud/iteration_30000/point_cloud.ply')
        realized = dict(self.extraction(512), source_log_sha256=sha(directory/'render.log'),
                        parser_sha256=sha(directory/'parse_extraction_snapshot.py'))
        invocation = dict(config_sha256=sha(self.config), runtime_layout_sha256=layout.digest, iteration=30000,
                          mesh_res=512, command=['render fixture'], source_complete_ply_sha256=point_sha,
                          copied_ply_sha256=point_sha, render_cfg_args_sha256=sha(directory/'model/cfg_args'))
        receipt = dict(invocation, status='PASS', realized_extraction=realized,
                       extraction_helper_snapshot=dict(sha256=realized['parser_sha256']),
                       files=[dict(path=f'model/train/ours_30000/{name}', exists=True,
                                   sha256=sha(directory/f'model/train/ours_30000/{name}'))
                              for name in ('fuse.ply', 'fuse_post.ply')])
        for filename, value in [('invocation.json', invocation), ('receipt.json', receipt)]:
            self.save(str((directory/filename).relative_to(self.task)), value)
        source = dict(sha256=point_sha)
        result = seal.bind_auxiliary_extraction(run, 'mesh_512', 30000, 512, sha(self.config), layout,
                                               'P1', 50, {}, source, self.bind)
        self.assertEqual(result['depth_trunc_m'], 80.)
        for filename in ('fuse.ply', 'fuse_post.ply'):
            mesh_path = directory/f'model/train/ours_30000/{filename}'
            original = mesh_path.read_bytes()
            mesh_path.write_bytes(b'X'*len(original))
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, 'producer hash'):
                seal.bind_auxiliary_extraction(run, 'mesh_512', 30000, 512, sha(self.config), layout,
                                              'P1', 50, {}, source, self.bind)
            mesh_path.write_bytes(original)
        (directory/'model/cfg_args').write_bytes(b'changed namespace')
        with self.assertRaisesRegex(ValueError, 'cfg_args identity'):
            seal.bind_auxiliary_extraction(run, 'mesh_512', 30000, 512, sha(self.config), layout,
                                          'P1', 50, {}, source, self.bind)


if __name__ == '__main__':
    unittest.main()
