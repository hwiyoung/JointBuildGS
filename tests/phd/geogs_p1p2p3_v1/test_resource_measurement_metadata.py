"""Synthetic reporting-only regression: original rows/numbers stay unchanged."""
import ast
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
MODULES = REPO/'scripts/phd/geogs_p1p2p3_v1/evaluation'
sys.path.insert(0, str(MODULES))
import summarize

OLD_TEXT = 'raw child-phase wall time; shared preprocessing, anchor reuse and failed attempts are separate'
NEW_TEXT = 'recorded driver phase interval; see resource_measurement_scope; shared preprocessing, anchor reuse and failed attempts are separate'
SCOPE = 'resource_measurement_scope'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def before_module():
    source = os.environ.get('RESOURCE_MEASUREMENT_BEFORE')
    if not source:
        raise unittest.SkipTest('A preserved pre-change source is required for the focused equivalence run')
    spec = importlib.util.spec_from_file_location('resource_metadata_before', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReportingOnlyNormalization(ast.NodeTransformer):
    """Remove exactly the authorized metadata delta, then compare the entire AST."""
    def visit_FunctionDef(self, node):
        if node.name == 'resource_measurement_definitions':
            return None
        return self.generic_visit(node)

    def visit_Expr(self, node):
        call = node.value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'dump'
                and len(call.args) == 2 and isinstance(call.args[1], ast.Call)
                and isinstance(call.args[1].func, ast.Name) and call.args[1].func.id == 'resource_measurement_definitions'):
            self.assert_definition_dump = True
            return None
        return self.generic_visit(node)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        node.keywords = [item for item in node.keywords if item.arg != SCOPE]
        return node

    def visit_Dict(self, node):
        node = self.generic_visit(node)
        items = [(key, value) for key, value in zip(node.keys, node.values)
                 if not (isinstance(key, ast.Constant) and key.value == 'resource_measurement_definitions_path')]
        node.keys, node.values = [item[0] for item in items], [item[1] for item in items]
        return node

    def visit_Constant(self, node):
        if node.value == NEW_TEXT:
            return ast.copy_location(ast.Constant(value=OLD_TEXT), node)
        return node


class ResourceMeasurementMetadataTests(unittest.TestCase):
    def comparable(self, rows):
        values = copy.deepcopy(rows)
        for row in values:
            row.pop(SCOPE, None)
            if row.get('cost_interpretation') == NEW_TEXT:
                row['cost_interpretation'] = OLD_TEXT
        return values

    def fixture(self, task, start=8000, repeated=False, amended=False):
        files = {}
        def save(relative, value, trace=False):
            path = task/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(''.join(json.dumps(row)+'\n' for row in value) if trace else json.dumps(value))
            files[relative] = dict(path=relative, bytes=path.stat().st_size, sha256=sha(path))
            return path
        layout = SimpleNamespace(
            run=lambda region, condition: task/f'runs_allocator_v2/{region}/{condition}',
            starts_from_anchor=lambda region, condition: start == 8000,
            anchor_checkpoint=lambda region: task/f'anchors/{region}/iteration_8000',
            binding=lambda: dict(runtime_layout_sha256='layout'), require_receipt=lambda receipt: None)
        repeat = SimpleNamespace(identifier='native_repeat_1',
            run=lambda region: task/f'native_repeat_allocator_v2/{region}/D005_Pnative',
            binding=lambda: dict(repeat_contract_sha256='repeat'), require_run_receipt=lambda receipt, region: None)
        resource = SimpleNamespace(
            aux_run=lambda region, condition, repeat_id: task/f'extraction_resource_v3/{repeat_id or "primary"}/{region}/{condition}',
            binding=lambda: dict(resource_contract_sha256='resource'),
            validate_receipt=lambda receipt, region, condition, repeat_id: None)
        condition = repeat.identifier if repeated else 'D005_Pnative'
        run = repeat.run('P1') if repeated else layout.run('P1', condition)
        for index, phase in enumerate(('train', 'render', 'metrics', 'auxiliary')):
            parent = resource.aux_run('P1', 'D005_Pnative', repeat.identifier if repeated else None) if amended and phase == 'auxiliary' else run
            save(str((parent/(phase+'_receipt.json')).relative_to(task)), dict(status='PASS',
                wall_seconds=19.125+index, child_peak_rss_bytes=1024*(index+9), training_start_iteration=start,
                resource_scheduling=dict(wait_seconds=2.25 if phase in ('render','auxiliary') else 0.0,
                                         serialized_extraction=phase in ('render','auxiliary'))))
        trace = [dict(iteration=iteration, elapsed_seconds=elapsed, peak_cuda_allocated_bytes=allocated,
                      peak_cuda_reserved_bytes=reserved, peak_rss_bytes=rss, gaussians=50, protected=11)
                 for iteration, elapsed, allocated, reserved, rss in
                 ([(8000, 5.5, 100, 900, 4096)] if start == 0 else [])+
                 [(8100, 7.5, 300, 800, 8192), (30000, 17.0, 200, 1200, 4096)]]
        save(str((run/'model/jbgs_trace.jsonl').relative_to(task)), trace, trace=True)
        return dict(task=task, region='P1', condition=condition, layout=layout, sealed_files=files,
                    repeat=repeat if repeated else None, resource=resource if amended else None)

    def test_entire_original_ast_is_unchanged_after_removing_only_metadata(self):
        previous = before_module()
        before = ast.parse(Path(previous.__file__).read_text())
        after = ReportingOnlyNormalization().visit(ast.parse(Path(summarize.__file__).read_text()))
        self.assertEqual(ast.dump(before, include_attributes=False), ast.dump(after, include_attributes=False))

    def test_original_phase_and_trace_values_preserved_for_both_start_intervals(self):
        before = before_module()
        for start in (0, 8000):
            with self.subTest(start=start), tempfile.TemporaryDirectory() as temporary:
                arguments = self.fixture(Path(temporary), start=start)
                original, current = before.resource_records(**arguments), summarize.resource_records(**arguments)
                self.assertEqual(self.comparable(current), original)
                self.assertEqual(len(current), 5)
                self.assertTrue(all(row[SCOPE] == 'regional_driver_phase_v1' for row in current[:4]))
                self.assertEqual(current[-1][SCOPE], 'training_process_trace_v1')
                self.assertEqual(current[-1]['peak_cuda_allocated_bytes'], 300)
                self.assertEqual(current[-1]['child_peak_rss_bytes'], 8192)
                self.assertTrue(all(row['full_pipeline_wall_seconds'] is None for row in current))

    def test_resource_v3_parent_and_repeat_rows_keep_their_original_numbers_and_identity(self):
        before = before_module()
        for repeated in (False, True):
            with self.subTest(repeated=repeated), tempfile.TemporaryDirectory() as temporary:
                arguments = self.fixture(Path(temporary), repeated=repeated, amended=True)
                original, current = before.resource_records(**arguments), summarize.resource_records(**arguments)
                self.assertEqual(self.comparable(current), original)
                self.assertEqual(current[3][SCOPE], 'resource_v3_auxiliary_phase_v1')
                self.assertEqual(current[4][SCOPE], 'training_process_trace_v1')
                self.assertTrue(all(row['supplemental_only'] == repeated for row in current))
                if repeated:
                    self.assertTrue(all(row['cost_category'].startswith('SUPPLEMENTAL_REPEAT_') for row in current))

    def test_shared_anchor_and_failed_source_rows_remain_separate_and_nonadditive(self):
        before = before_module()
        from tests.phd.geogs_p1p2p3_v1.test_runtime_layout import RuntimeRevisionTests
        fixture = RuntimeRevisionTests()
        fixture.setUp()
        try:
            layout, anchor = fixture.prepare_anchor()
            original = before.anchor_resource_records(fixture.task, 'P1', anchor, layout)
            current = summarize.anchor_resource_records(fixture.task, 'P1', anchor, layout)
            self.assertEqual(self.comparable(current), original)
            self.assertEqual([row[SCOPE] for row in current], ['shared_anchor_trace_prefix_v1', 'failed_anchor_source_phase_v1'])
            self.assertTrue(all(row['additive_to_final_phase_totals'] is False for row in current))
            self.assertIsNone(current[0]['wall_seconds'])
        finally:
            fixture.tearDown()

    def test_definitions_distinguish_device_allocator_rss_and_cgroup_boundaries(self):
        definitions = summarize.resource_measurement_definitions()
        json.dumps(definitions, allow_nan=False)
        self.assertIsNone(definitions['scientific_verdict'])
        self.assertFalse(definitions['raw_device_gpu_evidence']['read_by_this_summary'])
        self.assertFalse(definitions['raw_device_gpu_evidence']['final_regional_csv_device_peak_exported'])
        self.assertFalse(definitions['memory_peaks_are_additive'])
        scopes = definitions['scopes']
        self.assertEqual(len(scopes), 6)
        ordinary = scopes['regional_driver_phase_v1']['child_peak_rss_bytes']
        self.assertFalse(ordinary['is_native_pid_only'])
        self.assertFalse(ordinary['parent_driver_validation_rss_included'])
        trace = scopes['training_process_trace_v1']
        self.assertFalse(trace['child_peak_rss_bytes']['is_driver_children_measurement'])
        self.assertFalse(trace['child_peak_rss_bytes']['final_after_trace_peak_guaranteed'])
        self.assertIn('Counters as observed', trace['cuda_peak_scope'])
        variant = scopes['resource_v3_auxiliary_variant_v1']
        self.assertFalse(variant['sampled_peak_memory_current_bytes']['is_continuous_peak'])
        self.assertFalse(variant['sampled_peak_memory_current_bytes']['is_gpu_memory'])
        self.assertFalse(variant['raw_cgroup_lifetime_peak']['before_after_difference_is_variant_peak'])
        self.assertFalse(variant['raw_cgroup_lifetime_peak']['current_variant_post_validation_included'])
        self.assertFalse(variant['additive_to_phase_totals'])
        self.assertIn('host-headroom wait', variant['wall_seconds']['excludes'])
        self.assertIn('per-variant host headroom waits', scopes['resource_v3_auxiliary_phase_v1']['wall_seconds']['includes'])

    def test_real_summary_entrypoint_preserves_all_csv_rows_and_binds_definitions(self):
        before = before_module()
        from tests.phd.geogs_p1p2p3_v1 import test_resource_evaluation as fixtures
        original_inventory = fixtures.inventory
        def inventory(*args, **kwargs):
            row = original_inventory(*args, **kwargs)
            row.update(wall_seconds=31.125, child_peak_rss_bytes=3210,
                sampled_peak_memory_current_bytes=654321, cgroup_memory_limit_bytes=32*1024**3,
                cgroup_oom_kill_delta=1 if row['status'] == 'TECHNICAL_RESOURCE_UNAVAILABLE' else 0,
                host_headroom_wait_seconds=1.75)
            return row
        def execute(module):
            captured = {}
            original_main = module.main
            def main():
                original_main()
                task = Path(sys.argv[sys.argv.index('--task')+1])
                summary = task/'evaluation/summary'
                captured['csv'] = {str(path.relative_to(summary)):path.read_bytes() for path in sorted(summary.rglob('*.csv'))}
                captured['receipt'] = json.loads((summary/'receipt.json').read_text())
                captured['manifest'] = (task/'evaluation/viewer/manifest.json').read_bytes()
                path = summary/'resource_measurement_definitions.json'
                if path.exists():
                    captured['definitions'] = dict(path='evaluation/summary/'+path.name, bytes=path.stat().st_size, sha256=sha(path))
                    captured['definition_bytes'] = path.read_bytes()
            fixture = fixtures.ResourceSummaryWorkflowTests('test_three_region_primary_matrix_survives_optional_oom_and_emits_two_resolution_families')
            with patch.object(fixtures, 'summarize', module), patch.object(fixtures, 'inventory', side_effect=inventory), patch.object(module, 'main', side_effect=main):
                result = unittest.TestResult()
                fixture.run(result)
                self.assertTrue(result.wasSuccessful(), result.errors+result.failures)
            return captured
        original, current = execute(before), execute(summarize)
        self.assertEqual(set(original['csv']), set(current['csv']))
        counts = {}
        for name in original['csv']:
            with self.subTest(csv=name):
                old_rows = list(csv.DictReader(io.StringIO(original['csv'][name].decode())))
                new_rows = list(csv.DictReader(io.StringIO(current['csv'][name].decode())))
                self.assertEqual(self.comparable(new_rows), old_rows)
                counts[name] = len(new_rows)
                if name != 'extraction_attempt_resources.csv':
                    self.assertEqual(original['csv'][name], current['csv'][name])
                else:
                    self.assertTrue(new_rows and all(row[SCOPE] == 'resource_v3_auxiliary_variant_v1' for row in new_rows))
                    self.assertTrue(all(row['additive_to_phase_totals'] == 'False' for row in new_rows))
                    self.assertTrue(any(row['status'] == 'TECHNICAL_RESOURCE_UNAVAILABLE' for row in new_rows))
                    self.assertTrue(any(row['supplemental_only'] == 'True' for row in new_rows))
        self.assertEqual(original['manifest'], current['manifest'])
        self.assertEqual(current['receipt']['resource_measurement_definitions_path'], current['definitions']['path'])
        self.assertEqual([row for row in current['receipt']['summary_files'] if row['path'] == current['definitions']['path']], [current['definitions']])
        for key in original['receipt']:
            if key != 'summary_files':
                self.assertEqual(original['receipt'][key], current['receipt'][key])
        report = os.environ.get('RESOURCE_MEASUREMENT_TEST_OUTPUT')
        if report:
            output = Path(report)
            output.mkdir(parents=True, exist_ok=True)
            (output/'resource_measurement_definitions.json').write_bytes(current['definition_bytes'])
            (output/'extraction_resources_before.csv').write_bytes(original['csv']['extraction_attempt_resources.csv'])
            (output/'extraction_resources_after.csv').write_bytes(current['csv']['extraction_attempt_resources.csv'])
            (output/'summary_receipt_synthetic.json').write_text(json.dumps(current['receipt'], indent=2))
            (output/'csv_equivalence.json').write_text(json.dumps(dict(scientific_verdict=None,
                status='ALL_ORIGINAL_CSV_ROWS_AND_FIELDS_PRESERVED_EXCEPT_AUTHORIZED_METADATA', row_counts=counts,
                unchanged_viewer_manifest=True, definition_receipt_binding=current['definitions']), indent=2))


if __name__ == '__main__':
    unittest.main()
