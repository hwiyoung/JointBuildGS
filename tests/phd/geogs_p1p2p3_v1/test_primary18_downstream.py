"""Prospective primary18 completion scope; synthetic producers and metric headers only."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch

from tests.phd.geogs_p1p2p3_v1.test_control_trajectories import SealedFixture, ct, FinalizationGate, REPO
from tests.phd.geogs_p1p2p3_v1.test_final_preservation import FinalPreservationTest, final
import factor_contrasts as fc


class Primary18Fixture(SealedFixture):
    def setUp(self):
        super().setUp()
        for name in ('evaluation_analysis_v1.json', 'evaluation_completion_v2.json'):
            shutil.copyfile(REPO/'configs/phd/geogs_p1p2p3_v1'/name, self.task/'contracts'/name)
        self.gate = FinalizationGate(self.task)
        repeat = self.gate.repeat
        self.seal.update(status='PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE',
                         supplemental_availability=repeat.supplemental_availability, **repeat.binding())
        self.seal['candidates'] = [row for row in self.seal['candidates'] if not row['supplemental_only']]
        self.seal['extraction_inventory'] = [row for row in self.seal['extraction_inventory'] if row['condition']!='native_repeat_1']
        self.seal['files'] = [row for row in self.seal['files'] if not row['path'].startswith('native_repeat_allocator_v2/')]
        self.seal['completion_decision_evidence'] = [dict(row, bytes=1) for row in repeat.completion.data['failure_evidence']]
        self.seal['files'].extend(self.seal['completion_decision_evidence'])
        self.seal['files'].append(ct.record(self.task, repeat.completion.path))
        # There is no failed/unattempted trace or completed model to accidentally read.
        shutil.rmtree(self.task/'native_repeat_allocator_v2')
        self.write_seal()


class Primary18ControlAndFactorTests(Primary18Fixture):
    def test_exact_primary18_inventory_excludes_all_failed_unattempted_trace_reads(self):
        access = ct.inventory(self.task)
        self.assertEqual(len(access['jobs']), 18)
        self.assertEqual(len({job[field]['path'] for job in access['jobs'] for field in ('trace','train_receipt')}), 36)
        self.assertTrue(all(not row['supplemental_only'] for row in access['jobs']))
        self.assertEqual(access['evaluable_repeat_regions'], [])
        self.assertEqual(len(access['supplemental_availability']), 3)
        self.assertEqual(access['completion_contract_sha256'], self.gate.repeat.completion.digest)
        self.seal['candidates'].pop()
        self.write_seal()
        with self.assertRaisesRegex(ValueError, 'omits or duplicates'):
            ct.inventory(self.task)

    def test_primary_control_values_unchanged_no_fake_repeat_curve_or_table(self):
        access = ct.inventory(self.task)
        output = self.task/'primary18_controls'
        plotted = []
        def plot(output, region, rows, cfg, supplemental):
            self.assertFalse(supplemental)
            plotted.append(region)
            return dict(region=region, supplemental=False)
        with patch.object(ct, 'plot_region', side_effect=plot):
            result = ct.extract(self.task, output, access, self.cfg)
        self.assertEqual(result['completed_runs'], 18)
        self.assertEqual(result['primary_samples'], 4120)
        self.assertEqual(result['supplemental_samples'], 0)
        self.assertEqual(plotted, ['P1','P2','P3'])
        self.assertFalse((output/'native_repeat_control_samples.csv').exists())
        state = ct.read(output/'supplemental_control_status.json')
        self.assertEqual(state['completed_repeat_curves'], 0)
        self.assertFalse(state['failed_or_unattempted_trace_payloads_opened'])

    def test_factor_gate_retains_two_fixed_primary_csvs_and_completion_contract(self):
        summary = self.task/'evaluation/summary'
        summary.mkdir(parents=True)
        files = []
        for name in ('geometry_primary_1024.csv', 'render_all_images.csv'):
            path = summary/name
            path.write_text('SYNTHETIC_HEADER_ONLY\n')
            files.append(fc.file_record(self.task, path))
        fc.dump(summary/'receipt.json', dict(status='TABLES_AND_ACTUAL_VIEWER_DATA_READY', scientific_verdict=None,
            candidate_seal_sha256=fc.sha(self.task/'contracts/candidates_sealed_v1.json'),
            config_sha256=fc.sha(self.task/'contracts/execution_v1.json'),
            analysis_config_sha256=fc.sha(self.task/'contracts/evaluation_analysis_v1.json'),
            regions=['P1','P2','P3'], primary_condition_count=6, supplemental_in_primary_tables_or_case_ranking=False,
            summary_files=files, **self.gate.layout.binding(), **self.gate.repeat.binding(), **self.gate.resource.binding()))
        result = fc.input_gate(self.task)
        self.assertEqual(len(result['summary_csv_files']), 2)
        self.assertEqual(len(result['contract_files']), 7)
        self.assertEqual(result['evaluation_scope'], 'PRIMARY18_SUPPLEMENTAL_INCOMPLETE')
        (summary/'geometry_primary_1024.csv').write_text('TAMPERED')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            fc.input_gate(self.task)


class Primary18PreservationBindingTests(FinalPreservationTest):
    def test_primary18_preservation_gate_retains_explicit_contract_binding(self):
        value, path = self.seal()
        contract = self.task/'contracts/evaluation_completion_v2.json'
        shutil.copyfile(REPO/'configs/phd/geogs_p1p2p3_v1/evaluation_completion_v2.json', contract)
        value.update(status='PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE',
                     completion_contract_sha256=final.sha(contract), evaluation_scope='PRIMARY18_SUPPLEMENTAL_INCOMPLETE')
        path.write_text(json.dumps(value))
        factory = self.gate_factory(value, path)
        def scoped_factory(task):
            gate = factory(task)
            gate.resource = SimpleNamespace(repeat=SimpleNamespace(completion=True))
            return gate
        final.seal_gate(self.task, self.output, scoped_factory)
        final.require_gate(self.task, self.output)
        contract.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'completion contract changed'):
            final.require_gate(self.task, self.output)
