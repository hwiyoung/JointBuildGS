"""Synthetic resource-availability and matched-resolution evaluation checks."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULES = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
import resource_support as resource
import summarize
import seal_candidates as seal
import case_figures as cases
from runtime_layout import RuntimeLayout
from supplemental_repeat import SupplementalRepeat


def inventory(region='P1', condition='D005_Pnative', status='PASS', required=False, variant='mesh_2048'):
    return dict(region=region, condition=condition, scientific_condition='D005_Pnative', variant=variant,
        mesh_res=2048, iteration=30000, required=required, supplemental_only=condition=='native_repeat_1',
        status=status, producer_directory='extraction_resource_v3/fixture',
        receipt=dict(path='fixture/receipt.json', sha256='f'*64))


class ResourceAvailabilityTests(unittest.TestCase):
    def test_memcg_oom_is_not_zero_f1_reference_absence_or_reconstruction_failure(self):
        row = resource.inventory_availability({'extraction_inventory': [inventory(status=resource.UNAVAILABLE)]})[0]
        self.assertIsNone(row['precision'])
        self.assertIsNone(row['recall'])
        self.assertIsNone(row['f1'])
        self.assertIsNone(row['surface_distances'])
        self.assertIsNone(row['far_from_observed_reference_area_estimate_m2'])
        self.assertFalse(row['is_reference_absence'])
        self.assertFalse(row['is_reconstruction_failure'])
        self.assertEqual(row['metric_status'], 'NOT_ASSESSED_TECHNICAL_RESOURCE_UNAVAILABLE')
        json.dumps(row, allow_nan=False)

    def test_required_oom_and_unknown_errors_cannot_be_terminal_inventory(self):
        for row in [inventory(required=True, status=resource.UNAVAILABLE), inventory(status='FAIL'), inventory(status='pending')]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                resource.inventory_availability({'extraction_inventory':[row]})

    def test_optional_aggregate_requires_every_region_condition_and_repeat(self):
        regions, conditions = ['P1', 'P2'], ['D005_Pnative', 'changed', 'native_repeat_1']
        rows = [inventory(region, condition) for region in regions for condition in conditions]
        self.assertTrue(resource.optional_final_inventory_complete({'extraction_inventory': rows}, regions, conditions))
        rows[-1]['status'] = resource.UNAVAILABLE
        self.assertFalse(resource.optional_final_inventory_complete({'extraction_inventory': rows}, regions, conditions))
        for changed in [rows[:-1], rows+rows[:1]]:
            with self.assertRaises(ValueError):
                resource.optional_final_inventory_complete({'extraction_inventory': changed}, regions, conditions)

    def test_actual_contract_cannot_be_silently_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            task = Path(temporary)
            self.assertIsNone(resource.make_resource(task, None, None, None))
            (task/'contracts').mkdir()
            (task/'contracts/extraction_resource_v3.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'explicit --resource-contract'):
                resource.make_resource(task, None, None, None)
        with self.assertRaises(ValueError):
            resource.require(None, {'resource_contract_sha256':'a'*64})


class MatchedAnchor512Tests(unittest.TestCase):
    def metric(self, candidate, value, **changes):
        row = dict(region='P1', candidate=candidate, sensitivity='sample0.1_reference0.1',
            surface_kind='triangle_surface', threshold_m=.5, status='ASSESSED_DEVELOPMENT_ONLY')
        row.update({key:value for key in summarize.GEOMETRY_METRICS})
        row.update(changes)
        return row

    def test_main1024_values_do_not_enter_matched512_anchor_difference(self):
        rows = [self.metric('D005_Pnative.anchor_512.raw', .8),
                self.metric('D005_Pnative.anchor.raw', 900), self.metric('D005_Pnative.final.raw', 1000),
                self.metric('changed.mesh_512.raw', .3)]
        paired = summarize.anchor_refinement_pairs(rows, rows)
        self.assertEqual(len(paired), len(summarize.GEOMETRY_METRICS))
        self.assertTrue(all(abs(row['anchor_minus_final']-.5)<1e-12 and row['mesh_res']==512 for row in paired))

    def test_shared_anchor_matches_each_condition_and_repetition_without_fake_anchor_repeat(self):
        anchor = [self.metric('D005_Pnative.anchor_512.raw', .8)]
        finals = [self.metric('changed.mesh_512.raw', .3),
                  self.metric('native_repeat_1.mesh_512.raw', .4, supplemental_only=True)]
        rows = summarize.anchor_refinement_pairs(anchor, finals)
        self.assertEqual({row['condition'] for row in rows}, {'changed', 'native_repeat_1'})
        self.assertTrue(all(row['shared_anchor'] for row in rows))
        self.assertTrue(all(row['supplemental_only'] for row in rows if row['condition']=='native_repeat_1'))

    def test_wrong_estimator_density_or_mesh_kind_cannot_be_paired(self):
        anchor = [self.metric('D005_Pnative.anchor_512.raw', .8)]
        for after in [self.metric('changed.mesh_512.post', .3),
                      self.metric('changed.mesh_512.raw', .3, surface_kind='pointset'),
                      self.metric('changed.mesh_512.raw', .3, sensitivity='sample0.2_reference0.1')]:
            with self.assertRaises(ValueError):
                summarize.anchor_refinement_pairs(anchor, [after])

    def test_actual_reconstruction_failure_remains_distinct_from_resource_unavailability(self):
        rows = summarize.anchor_refinement_pairs([self.metric('D005_Pnative.anchor_512.raw', .8)],
            [self.metric('changed.mesh_512.raw', None, status='RECONSTRUCTION_FAILURE')])
        by_metric = {row['metric']: row for row in rows}
        self.assertEqual(by_metric['f1']['final_value'], 0.)
        self.assertEqual(by_metric['ref2candidate_mean_m']['difference_status'], 'NEGATIVE_INFINITY')
        json.dumps(rows, allow_nan=False)


class ResourceProducerBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.task = Path(self.temporary.name)
        self.root, self.run = self.task/'aux', self.task/'run'
        self.root.mkdir(); self.run.mkdir()
        config_snapshot = self.write(self.root/'auxiliary_config_snapshot.json', b'synthetic scientific configuration')
        resource_snapshot = self.write(self.root/'auxiliary_resource_contract_snapshot.json', b'synthetic resource contract')
        layout_snapshot = self.write(self.root/'auxiliary_runtime_layout_snapshot.json', b'synthetic runtime layout')
        self.config_sha, self.resource_sha = seal.sha(config_snapshot), seal.sha(resource_snapshot)
        self.planned = dict(name='mesh_2048', iteration=30000, mesh_res=2048, required=False, export_images=False)
        self.source = self.write(self.run/'model/point_cloud.ply', b'exact frozen model')
        self.cfg = self.write(self.run/'model/cfg_args', b'exact renderer args')
        directory = self.root/'auxiliary/mesh_2048'
        copied = self.write(directory/'model/point_cloud/iteration_30000/point_cloud.ply', b'exact frozen model')
        self.write(directory/'model/cfg_args', b'exact renderer args')
        log = self.write(directory/'render.log', b'synthetic native log; no real output read')
        memory = self.write(directory/'memory.jsonl', b'synthetic proof validated by shared contract in production')
        self.value = dict(region='P1', condition='D005_Pnative', variant='mesh_2048', iteration=30000,
            mesh_res=2048, status=resource.UNAVAILABLE, native_exit_code=-9, command=['native', 'fixture'],
            config_sha256=self.config_sha, resource_contract_sha256=self.resource_sha,
            source_complete_ply_sha256=seal.sha(self.source), copied_ply_sha256=seal.sha(copied),
            render_cfg_args_sha256=seal.sha(self.cfg),
            memory_trace=dict(path='memory.jsonl', sha256=seal.sha(memory)),
            source_log=dict(path='render.log', sha256=seal.sha(log)))
        self.receipt_path = self.write(directory/'receipt.json', json.dumps(self.value).encode())
        self.write(directory/'invocation.json', json.dumps(self.value).encode())
        producer = self.write(self.root/'auxiliary_driver_snapshot.py', b'exact executed driver snapshot')
        variants = [dict(name='mesh_2048', status=resource.UNAVAILABLE,
            receipt_path='auxiliary/mesh_2048/receipt.json', receipt_sha256=seal.sha(self.receipt_path))]
        manifest = self.write(self.root/'auxiliary_manifest.json', json.dumps(dict(status='PASS', variants=variants)).encode())
        outer = dict(input_manifest_sha256='i'*64, driver_sha256=seal.sha(producer),
            config_sha256=self.config_sha, resource_contract_sha256=self.resource_sha,
            runtime_layout_sha256=seal.sha(layout_snapshot), variants=variants,
            validation=[dict(path='auxiliary_manifest.json', exists_nonempty=True, bytes=manifest.stat().st_size, sha256=seal.sha(manifest))],
            producer_files=[dict(path=str(path.relative_to(self.root)), sha256=seal.sha(path), bytes=path.stat().st_size)
                            for path in self.root.glob('*') if path.is_file()])
        self.write(self.root/'auxiliary_receipt.json', json.dumps(outer).encode())
        self.contract = SimpleNamespace(task=self.task, digest=self.resource_sha,
            data={'scientific_config_sha256':self.config_sha}, validate_receipt=lambda *args: None,
            variant_inventory=lambda *args:[self.planned], binding=lambda:{'resource_contract_sha256':self.resource_sha},
            require_receipt=lambda value: self.assertEqual(value['resource_contract_sha256'], self.resource_sha))

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); return path

    def bind(self, path):
        return dict(path=str(path.relative_to(self.task)), bytes=path.stat().st_size, sha256=seal.sha(path))

    def execute(self):
        return seal.bind_resource_auxiliary(self.contract, self.root, self.run, 'P1', 'D005_Pnative',
            'D005_Pnative', None, 'i'*64, {}, self.bind(self.source), self.bind)

    def test_unavailable_variant_binds_exact_source_and_failure_receipt_without_surface(self):
        result = self.execute()
        self.assertEqual(result[0]['status'], resource.UNAVAILABLE)
        self.assertEqual(result[0]['source_complete_point_cloud']['sha256'], seal.sha(self.source))
        self.assertEqual(result[0]['receipt']['sha256'], seal.sha(self.receipt_path))

    def test_source_substitution_and_changed_executed_helper_are_rejected(self):
        self.execute()
        source_bytes = self.source.read_bytes(); self.source.write_bytes(b'other frozen model')
        with self.assertRaisesRegex(ValueError, 'model/renderer'):
            self.execute()
        self.source.write_bytes(source_bytes)
        (self.root/'auxiliary_driver_snapshot.py').write_bytes(b'changed driver')
        with self.assertRaisesRegex(ValueError, 'producer differs'):
            self.execute()


class ResourceSummaryWorkflowTests(unittest.TestCase):
    def test_three_region_primary_matrix_survives_optional_oom_and_emits_two_resolution_families(self):
        self.summary_workflow(primary18=False)

    def test_primary18_summary_keeps_matrix_and_reports_failed_unattempted_supplemental(self):
        self.summary_workflow(primary18=True)

    def summary_workflow(self, primary18):
        """Real summary entrypoint, synthetic metrics only, no reference arrays."""
        with tempfile.TemporaryDirectory() as temporary:
            task = Path(temporary)
            def save(relative, data):
                path = task/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data))
                return path
            config_root = MODULES.parents[3]/'configs/phd/geogs_p1p2p3_v1'
            contract_files = {'experiment_v1.json':'execution_v1.json',
                'runtime_layout_allocator_v2.json':'runtime_layout_allocator_v2.json',
                'supplemental_repeat_v1.json':'supplemental_repeat_v1.json',
                'extraction_resource_v3.json':'extraction_resource_v3.json'}
            if primary18:
                contract_files['evaluation_completion_v2.json'] = 'evaluation_completion_v2.json'
                contract_files['evaluation_analysis_v1.json'] = 'evaluation_analysis_v1.json'
            (task/'contracts').mkdir()
            for source, target in contract_files.items():
                (task/'contracts'/target).write_bytes((config_root/source).read_bytes())
            config = json.loads((task/'contracts/execution_v1.json').read_text())
            layout_path, repeat_path, resource_path = [task/'contracts'/name for name in
                ('runtime_layout_allocator_v2.json','supplemental_repeat_v1.json','extraction_resource_v3.json')]
            layout = RuntimeLayout(task, layout_path, config['regions'])
            repeat = SupplementalRepeat(task, repeat_path, layout)
            contract = resource.make_resource(task, resource_path, layout, repeat)
            bindings = dict(layout.binding(), **repeat.binding(), **contract.binding())
            analysis = task/'contracts/evaluation_analysis_v1.json' if primary18 else save('contracts/evaluation_analysis_v1.json', dict(scientific_verdict=None))
            all_conditions = [row['id'] for row in config['conditions']]+([repeat.identifier] if repeat.evaluable_regions else [])
            candidates, inventory_rows = [], []
            for region in config['regions']:
                for condition in all_conditions:
                    repeated = condition == repeat.identifier
                    scientific = 'D005_Pnative' if repeated else condition
                    variants = [('final', 1024, 30000), ('mesh_512', 512, 30000)]
                    for item in contract.variant_inventory(region, scientific, repeat.identifier if repeated else None):
                        # All optional anchors and2048 surfaces unavailable except one
                        # high-resolution surface: no aggregate may use that survivor.
                        available = item['required'] or region == 'P2' and condition == 'D005_Pnative' and item['name']=='mesh_2048'
                        entry = inventory(region, condition, 'PASS' if available else resource.UNAVAILABLE,
                                          item['required'], item['name'])
                        entry.update(mesh_res=item['mesh_res'], iteration=item['iteration'], scientific_condition=scientific)
                        inventory_rows.append(entry)
                        if available and item['name'] != 'mesh_512':
                            variants.append((item['name'], item['mesh_res'], item['iteration']))
                    for variant, resolution, iteration in variants:
                        for kind in ('raw','post'):
                            candidates.append(dict(region=region, condition=condition, variant=variant,
                                mesh_kind=kind, iteration=iteration, mesh_res=resolution,
                                supplemental_only=repeated, run_directory=str((repeat.run(region) if repeated else layout.run(region,condition)).relative_to(task)),
                                anchor_provenance={'checkpoint':{'sha256':layout.data['anchors'][region].get('checkpoint_sha256')}},
                                render_records=[{'synthetic':True}] if kind=='raw' and variant in ('final','anchor_512') else []))
            completion_fields = {}
            completion_files = []
            if primary18:
                completion_fields = dict(supplemental_availability=repeat.supplemental_availability,
                    completion_decision_evidence=[dict(row, bytes=1) for row in repeat.completion.data['failure_evidence']])
                completion_files = completion_fields['completion_decision_evidence'] + [dict(
                    path='contracts/evaluation_completion_v2.json', bytes=repeat.completion.path.stat().st_size, sha256=repeat.completion.digest)]
            seal_path = save('contracts/candidates_sealed_v1.json', dict(status=resource.seal_status(contract),
                scientific_verdict=None, config_sha256=seal.sha(task/'contracts/execution_v1.json'),
                files=completion_files, candidates=candidates, extraction_inventory=inventory_rows, **bindings, **completion_fields))
            fixture = MatchedAnchor512Tests()
            for region in config['regions']:
                rows, index = [], []
                for candidate in [value for value in candidates if value['region']==region]:
                    identifier = '.'.join(candidate[key] for key in ('condition','variant','mesh_kind'))
                    rows.append(fixture.metric(identifier, .4, region=region, supplemental_only=candidate['supplemental_only']))
                    if candidate['mesh_res'] not in (512,1024):
                        continue
                    relative = f'evaluation/geometry/{region}/{identifier}/{summarize.PRIMARY}.json'
                    metric = save(relative, dict(status='ASSESSED_DEVELOPMENT_ONLY', **bindings))
                    metric.with_suffix('.npz').write_bytes(b'synthetic hash fixture; no geometric coordinates')
                    role = 'anchor' if candidate['iteration']==8000 else ('native_repetition' if candidate['supplemental_only'] else 'vanilla' if candidate['condition']=='D005_Pnative' else 'changed')
                    index.append(dict(id=identifier, role=role, metrics_relative=relative,
                        data_url=identifier+'.json', surface_kind='triangle_surface', source_path='synthetic/'+identifier,
                        section_url=identifier+'.png', distance_url=identifier+'.distance.png'))
                save(f'evaluation/geometry/{region}/receipt.json', dict(status='PASS_GEOMETRY_EVALUATION', candidate_seal_sha256=seal.sha(seal_path), **bindings))
                summarize.csv_write(task/f'evaluation/geometry/{region}/geometry_metrics.csv', rows)
                save(f'evaluation/geometry/{region}/viewer_index.json', dict(candidates=index, reference_points=0))
                for candidate in candidates:
                    if candidate['region'] != region or not candidate['render_records']:
                        continue
                    condition, stage = candidate['condition'], candidate['variant']
                    optical = []
                    for domain in ('full_frame','fixed_prism_projected_bbox'):
                        optical.append(dict(region=region, condition=condition, name='synthetic.png', stage=stage,
                            domain=domain, status='ASSESSED', pixel_count=100, evaluation_index=0, image_id=1,
                            camera_id=1, photo_sha256='p'*64, seed=0, roi_x0=0, roi_y0=0, roi_x1=10, roi_y1=10,
                            psnr_native_db=20., psnr_positive_infinity=False, ssim_native=.9,
                            lpips_vgg_native_01=.2, lpips_vgg_signed_11=.3, montage='synthetic.png'))
                    save(f'evaluation/renders/{region}/{condition}/{stage}/receipt.json',
                         dict(status='PASS_RENDER_QUALITY_EVALUATION', rows=optical,
                              sealed_render_manifest_sha256=seal.sha(seal_path), **bindings))
            (task/'evaluation/viewer').mkdir()
            argv = ['summarize.py','--task',str(task),'--analysis-config',str(analysis),
                '--runtime-layout',str(layout_path),'--repeat-contract',str(repeat_path),'--resource-contract',str(resource_path)]
            with patch.object(sys, 'argv', argv), patch.object(summarize, 'relation_rows', return_value=([],[],[])), \
                 patch.object(summarize, 'anchor_resource_records', return_value=[]), \
                 patch.object(summarize, 'resource_records', return_value=[]):
                summarize.main()
            def read(relative):
                with (task/'evaluation/summary'/relative).open() as stream:
                    return list(csv.DictReader(stream))
            primary = read('geometry_primary_1024.csv')
            self.assertEqual({row['region'] for row in primary}, {'P1','P2','P3'})
            self.assertEqual({row['candidate'].split('.')[0] for row in primary}, set(all_conditions)-{repeat.identifier})
            self.assertTrue(all('.final.' in row['candidate'] for row in primary))
            paired = read('anchor_to_refinement_512_pairs.csv')
            self.assertEqual({row['condition'] for row in paired}, set(all_conditions))
            self.assertTrue(all('.anchor_512.' in row['anchor_candidate'] and '.mesh_512.' in row['final_candidate'] for row in paired))
            self.assertFalse((task/'evaluation/summary/geometry_optional_2048_region_macro.csv').exists())
            optional = json.loads((task/'evaluation/summary/optional_extraction_interpretation.json').read_text())
            self.assertEqual(optional['aggregate_status'], 'NOT_AGGREGATED_INCOMPLETE_RESOURCE_INVENTORY')
            if primary18:
                self.assertFalse((task/'evaluation/summary/supplemental_repeat/geometry_primary_minus_repeat.csv').exists())
                availability = read('supplemental_repeat/availability.csv')
                self.assertEqual([row['region'] for row in availability], ['P1','P2','P3'])
                self.assertEqual([row['status'] for row in availability], ['TRAINING_FAILED_CUDA_OOM', 'TRAINING_FAILED_CUDA_OOM', 'NOT_ATTEMPTED_AFTER_CONTROLLER_FAILURE'])
                self.assertTrue(all(row['quality_metrics']=='' and row['is_reference_absence']=='False'
                                    and row['is_reconstruction_failure']=='False' for row in availability))
                costs = read('supplemental_repeat/failed_attempt_resources.csv')
                self.assertEqual([row['region'] for row in costs], ['P1','P2'])
                self.assertEqual([float(row['wall_seconds']) for row in costs],
                                 [row['train_wall_seconds'] for row in repeat.supplemental_availability if row['attempted']])
            else:
                differences = read('supplemental_repeat/geometry_primary_minus_repeat.csv')
                self.assertEqual({row['variant'].split('.')[0] for row in differences}, {'final','mesh_512'})
            viewer = json.loads((task/'evaluation/viewer/manifest.json').read_text())
            self.assertEqual([row['mesh_res'] for row in viewer['resolution_modes']], [1024,512])
            for region in viewer['regions']:
                anchor = next(row for row in region['candidates'] if row['id']=='D005_Pnative.anchor.raw')
                self.assertEqual(anchor['status'], 'failed')
                self.assertIn('TECHNICAL_RESOURCE_UNAVAILABLE', anchor['reason'])
                self.assertTrue(any(row['id']=='D005_Pnative.anchor_512.raw' and row['status']=='available' for row in region['candidates']))
                self.assertTrue(all(row['condition_id']=='native_repeat_1' for row in region['sections'] if row['id'].startswith('native_repeat_1.')))
                if primary18:
                    repeated = region['supplemental_availability'][0]
                    self.assertFalse(repeated['completed'])
                    self.assertIsNone(repeated['quality_metrics'])
                    self.assertTrue(any(repeated['status'] in note and 'Quality not assessed' in note for note in region['notes']))
                    self.assertFalse(any(row['id']==repeat.identifier for row in region['conditions']))
                    self.assertFalse(any(row.get('condition_id')==repeat.identifier for row in region['candidates']))


class ResourceCaseFigureWorkflowTests(unittest.TestCase):
    def test_primary1024_and_shared_anchor512_sections_are_separate_with_same_case_and_reference(self):
        from tests.phd.geogs_p1p2p3_v1 import test_case_figures as case_fixtures
        import numpy as np
        fixture = case_fixtures.SealedCaseEndToEndTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        task = fixture.task
        contract_path = fixture.save_json('contracts/extraction_resource_v3.json', {'synthetic_fixture_only':True})
        digest = seal.sha(contract_path)
        contract = SimpleNamespace(path=contract_path, digest=digest, binding=lambda:dict(resource_contract_sha256=digest))
        seal_data = json.loads(fixture.seal_path.read_text())
        seal_data.update(status=resource.RESOURCE_SEAL_STATUS, resource_contract_sha256=digest)
        fixture.seal_path.write_text(json.dumps(seal_data))
        candidate_digest = seal.sha(fixture.seal_path)
        evaluated = []
        for record in fixture.evaluated:
            path = task/record['path']
            if path.suffix == '.json':
                metric = json.loads(path.read_text())
                metric.update(resource_contract_sha256=digest, candidate_seal_sha256=candidate_digest)
                path.write_text(json.dumps(metric))
            evaluated.append(fixture.record(path))
        for identifier in ('D005_Pnative.anchor_512.raw', 'D005_Pnative.mesh_512.raw', 'changed.mesh_512.raw'):
            path = task/f'evaluation/geometry/P1/{identifier}/{cases.PRIMARY}.npz'
            path.parent.mkdir(parents=True)
            np.savez(path, prediction_surface_samples=fixture.reference+[0,0,.2],
                reference_points=fixture.reference, reference_original_indices=np.arange(len(fixture.reference)))
            metric = fixture.save_json(str(path.with_suffix('.json').relative_to(task)),
                dict(status='ASSESSED_DEVELOPMENT_ONLY', surface_kind='triangle_surface',
                     resource_contract_sha256=digest, candidate_seal_sha256=candidate_digest))
            evaluated.extend([fixture.record(path), fixture.record(metric)])
        selected_path = task/'evaluation/summary/selected_cases.json'
        selected = json.loads(selected_path.read_text())
        selected['resource_contract_sha256'] = digest
        selected['cases'][0].update(cell_x=0, cell_y=0)
        selected_path.write_text(json.dumps(selected))
        summary = json.loads(fixture.summary.read_text())
        summary.update(resource_contract_sha256=digest, candidate_seal_sha256=candidate_digest,
            case_figure_input_files=evaluated,
            summary_files=[fixture.record(selected_path), fixture.record(task/'evaluation/viewer/manifest.json')])
        fixture.summary.write_text(json.dumps(summary))
        output = task/'evaluation/cases_v1'
        with patch.object(cases.resources, 'make_resource', return_value=contract):
            result = cases.run(task, output, viewer_manifest_v2=True, resource_contract=contract_path)
        item = result['cases'][0]
        metadata = json.loads((output/item['metadata_url']).read_text())
        self.assertEqual(len(metadata['sections']), 8)
        self.assertEqual(len(metadata['anchor_refinement512_sections']), 10)
        self.assertTrue(all('.anchor.' not in row['id'] and '.anchor_512.' not in row['id'] for row in metadata['column_sources']))
        paired_ids = {row['id'] for row in metadata['anchor_refinement512_column_sources']}
        self.assertEqual(paired_ids, {'prior_mesh','mvs_points','D005_Pnative.anchor_512.raw',
                                     'D005_Pnative.mesh_512.raw','changed.mesh_512.raw'})
        self.assertTrue((output/item['paired_section_url']).is_file())
        self.assertIn('no512 reranking', metadata['case_selection_source'])
        self.assertFalse(result['raw_reference_accessed'])
        viewer = json.loads((task/'evaluation/viewer/manifest_v2.json').read_text())
        self.assertEqual({row['comparison_family'] for row in viewer['regions'][0]['sections']},
                         {'primary_1024','anchor_refinement_512'})
        self.assertTrue(all(row['case_id']=='changed.0.0.synthetic_fixture_case' for row in viewer['regions'][0]['sections']))


if __name__ == '__main__':
    unittest.main()
