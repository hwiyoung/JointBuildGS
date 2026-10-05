"""Unattended completion rejects missing, partial, or mismatched evidence chains."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/phd/local_complementary_refinement_v1'))
from automation_state_v2 import full_completion, logged_value, sha, derivative


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.task=Path(self.tmp.name)/'main_v2';self.batch=self.task/'automation_v2'/'analysis_full'
        self.batch.mkdir(parents=True);self.out=self.task/'automation_v2'/'completion.json'
        self.ev=self.task/'evaluation'/'attempt_eval';self.roots={}
        self.rows=[dict(region=r,condition=f'LC_D{d}_P{m}',relative_path=f'runs/{r}/LC_D{d}_P{m}',
            phase_receipt_sha256=dict(train='a',render='b',metrics='c'),failed_attempts=[])
            for r in ['P1','P2','P3'] for d in ['005','0005','0'] for m in ['native','release']]
        self.rows[0]['failed_attempts']=[{'relative_path':'failed-original'}]
        self.selection=self.task/'run_selection_v2.json'
        self.save(self.selection,dict(runs=self.rows,selection_uses_quality_metrics=False,config_sha256='config',input_binding_sha256='binding'))
        self.save(self.ev/'receipt.json',dict(status='COMPLETE_DEVELOPMENT_EVALUATION',run_count=18,expected_full_run_count=18,missing=[],
            selected_run_sources=deepcopy(self.rows),run_selection={'sha256':sha(self.selection)}))
        evhash=sha(self.ev/'receipt.json')
        self.stage('summary','summary',dict(status='COMPLETE_18_DEVELOPMENT_SUMMARY',observed_condition_count=18,expected_condition_count=18),[evhash],'/summary')
        self.stage('maps','maps',dict(status='PASS_STATIC_MAPS',case_count=18),[evhash])
        self.fig=self.task/'figures'/'attempt_figures'
        self.save(self.fig/'receipt.json',dict(status='PASS_MATCHED_FIGURES_WRITTEN_REQUIRES_VISUAL_REVIEW',records=self.rows,inputs=[{'sha256':evhash}]))
        self.stage('figure_qa','figures_review',dict(status='PASS_NATIVE_PIXEL_PSNR_AND_BAND_QA',run_count=18,matrix_status='FULL18'),[evhash,sha(self.fig/'receipt.json')])
        self.stage('map_qa','maps_review',dict(status='PASS_EXACT_ORIGINAL_DISTANCES_AND_ALL_CELLS',run_count=18,matrix_status='FULL18'),[evhash,sha(self.roots['maps']/'receipt.json')])
        self.stage('strata','strata_diagnostic',dict(status='PASS',matrix_status='COMPLETE_MATRIX',producer_completed_run_count=18,producer_expected_run_count=18),[evhash])
        self.stage('matrix','matrix_figures',dict(status='PASS_COMPLETE_18_MATRIX_FIGURES',observed_condition_count=18,expected_condition_count=18,not_plotted_condition_count=0),[sha(self.roots['summary']/'receipt.json')])
        self.stage('photo_cases','photo_case_summary',dict(status='PASS_FULL18_CASE_COMPARISON',run_count=18,case_count=6,paired_rows=72),[evhash],'/out')
        self.stage('attempt_costs','attempt_costs',dict(status='PASS_FULL18_ATTEMPT_COSTS',selected_conditions=18,selected_training_attempts=18,failed_training_attempts=1),[sha(self.selection)],'/output')
        self.trace=self.task/'trace_monitor'/'attempt_trace'/'runtime_receipt.json'
        self.save(self.trace,dict(status='PASS',matrix_status='COMPLETE_MATRIX',analyzer_status_counts={'PASS':18},paired_iterations=3960,
            run_selection={'sha256':sha(self.selection)},config_sha256='config',input_binding_sha256='binding'))
        (self.batch/'trace.log').write_text('Trace attempt: /media/external/task/main_v2/trace_monitor/attempt_trace\n')
        self.packet=self.task/'review_site'/'packets'/'packet_test'
        bundle=dict(regions=['P1','P2','P3'],figures=str(self.fig.relative_to(self.task)),
            **{k:str(self.roots[k].relative_to(self.task)) for k in ['summary','maps','figure_qa','map_qa']})
        self.save(self.packet/'sources.json',{'bundles':[bundle]})
        self.save(self.packet/'receipt.json',dict(status='PASS_REVIEW_PACKET',evaluated_conditions=18,outputs=[dict(path='sources.json',sha256=sha(self.packet/'sources.json'))]))
        self.save(self.task/'review_site'/'current.json',dict(packet='packets/packet_test',receipt_sha256=sha(self.packet/'receipt.json')))
        (self.batch/'publish.log').write_text(json.dumps({'packet':'/site/packets/packet_test'})+'\n')
        self.packet_3d=self.task/'review_3d'/'packets'/'packet_3d'
        self.save(self.packet_3d/'manifest.json',dict(evaluated_conditions=18,source_review_receipt_sha256=sha(self.packet/'receipt.json'),source_review_packet='packets/packet_test'))
        self.save(self.packet_3d/'receipt.json',dict(status='PASS_3D_EXPORT_BROWSER_REVIEW_REQUIRED',evaluated_conditions=18,source_review_packet='packets/packet_test',source_review_receipt_sha256=sha(self.packet/'receipt.json'),
            records=[dict(region=r['region'],condition=r['condition'],kind=kind) for r in self.rows for kind in ['raw','post']],
            inputs=[dict(sha256=sha(self.packet/'receipt.json'))],outputs=[dict(path='manifest.json',sha256=sha(self.packet_3d/'manifest.json'))]))
        self.save(self.task/'review_3d'/'current.json',dict(packet='packets/packet_3d',receipt_sha256=sha(self.packet_3d/'receipt.json')))
        (self.batch/'publish_3d.log').write_text(json.dumps({'packet':'/site/packets/packet_3d'})+'\n')
        self.browser=self.task/'review_3d/browser_qa/attempt_browser/receipt.json'
        self.save(self.browser,dict(status='PASS_ACTUAL_3D_MATCHED_CONDITIONS_RAW_POST',evaluated_conditions=18,
            manifest_sha256=sha(self.packet_3d/'manifest.json'),export_receipt_sha256=sha(self.packet_3d/'receipt.json'),
            source_review_receipt_sha256=sha(self.packet/'receipt.json'),source_review_packet='packets/packet_test',
            checks=[dict(name=name,**{'pass':True},detail=dict(region=r['region'],condition=r['condition'],surface=kind))
                for name in ['Matched G follows LC coefficient and protection','LC actual selected candidate','Six cameras synchronized']
                for r in self.rows for kind in ['raw','post']]))
        (self.batch/'browser_3d_qa.log').write_text('/media/external/task/main_v2/review_3d/browser_qa/attempt_browser/receipt.json\n')

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(dict(scientific_verdict=None,**value)))

    def stage(self,stage,kind,value,hashes,prefix=None):
        root=self.task/kind/('attempt_'+stage);self.roots[stage]=root
        self.save(root/'receipt.json',dict(value,inputs=[{'sha256':x} for x in hashes]))
        (self.batch/(stage+'.log')).write_text(json.dumps({'output':(prefix or '/task/main_v2/'+kind)+'/'+root.name})+'\n')

    def mutate(self,path,**changes):
        value=json.loads(path.read_text());value.update(changes);path.write_text(json.dumps(value))

    def complete(self):full_completion(self.task,self.ev,self.out,self.batch)

    def test_full18_chain_seals_once_with_bound_receipts(self):
        self.complete();receipt=json.loads(self.out.read_text())
        self.assertEqual(receipt['status'],'PASS_UNATTENDED_FULL18_ANALYSIS')
        self.assertIsNone(receipt['scientific_verdict'])
        self.assertEqual(receipt['run_selection_sha256'],sha(self.selection))
        self.assertGreater(len(receipt['inputs']),20)
        with self.assertRaises(FileExistsError):self.complete()

    def test_partial_trace_cannot_complete_even_when_wrapper_passed(self):
        self.mutate(self.trace,matrix_status='PARTIAL_MATRIX',analyzer_status_counts={'PASS':17,'PARTIAL':1})
        with self.assertRaisesRegex(ValueError,'complete refinement traces'):self.complete()
        self.assertFalse(self.out.exists())

    def test_missing_trace_samples_cannot_complete(self):
        self.mutate(self.trace,paired_iterations=3959)
        with self.assertRaisesRegex(ValueError,'complete refinement traces'):self.complete()

    def test_trace_from_another_selection_cannot_complete(self):
        self.mutate(self.trace,run_selection={'sha256':'other'})
        with self.assertRaisesRegex(ValueError,'Trace selection'):self.complete()

    def test_summary_from_another_evaluation_cannot_complete(self):
        self.mutate(self.roots['summary']/'receipt.json',inputs=[{'sha256':'other'}])
        with self.assertRaisesRegex(ValueError,'Summary binds'):self.complete()

    def test_failed_attempt_costs_must_include_original_failure(self):
        self.mutate(self.roots['attempt_costs']/'receipt.json',failed_training_attempts=0)
        with self.assertRaisesRegex(ValueError,'failed attempt costs'):self.complete()

    def test_auxiliary_receipt_is_required(self):
        (self.roots['photo_cases']/'receipt.json').unlink()
        with self.assertRaises(FileNotFoundError):self.complete()

    def test_packet_must_be_this_batch_publication(self):
        self.mutate(self.task/'review_site'/'current.json',packet='packets/packet_other')
        with self.assertRaisesRegex(ValueError,'this batch publication'):self.complete()

    def test_packet_receipt_hash_must_match_pointer(self):
        self.mutate(self.packet/'receipt.json',extra='changed after publication')
        with self.assertRaisesRegex(ValueError,'hash-bound review'):self.complete()

    def test_full_packet_cannot_mix_another_region_summary(self):
        source=json.loads((self.packet/'sources.json').read_text());source['bundles'][0]['summary']='summary/attempt_other'
        (self.packet/'sources.json').write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError,'Published source policy hash'):self.complete()

    def test_3d_cannot_bind_a_different_static_packet(self):
        self.mutate(self.packet_3d/'receipt.json',source_review_packet='packets/packet_other')
        self.mutate(self.task/'review_3d'/'current.json',receipt_sha256=sha(self.packet_3d/'receipt.json'))
        with self.assertRaisesRegex(ValueError,'3D packet source review'):self.complete()

    def test_3d_must_include_every_condition_in_raw_and_post(self):
        receipt=json.loads((self.packet_3d/'receipt.json').read_text());receipt['records'][-1]=receipt['records'][0]
        (self.packet_3d/'receipt.json').write_text(json.dumps(receipt))
        self.mutate(self.task/'review_3d'/'current.json',receipt_sha256=sha(self.packet_3d/'receipt.json'))
        with self.assertRaisesRegex(ValueError,'All36 unique 3D'):self.complete()

    def test_3d_manifest_cannot_change_after_export(self):
        self.mutate(self.packet_3d/'manifest.json',evaluated_conditions=17)
        with self.assertRaisesRegex(ValueError,'3D manifest hash'):self.complete()

    def test_3d_browser_qa_must_bind_this_export(self):
        self.mutate(self.browser,export_receipt_sha256='other')
        with self.assertRaisesRegex(ValueError,'3D browser QA binds different'):self.complete()

    def test_3d_browser_qa_pass_label_requires_complete_condition_coverage(self):
        browser=json.loads(self.browser.read_text());browser['checks']=browser['checks'][:-1]
        self.browser.write_text(json.dumps(browser))
        with self.assertRaisesRegex(ValueError,'misses condition/surface'):self.complete()

    def test_ambiguous_stage_log_and_escaped_path_fail_closed(self):
        log=self.batch/'summary.log';original=log.read_text();log.write_text(original+original)
        with self.assertRaisesRegex(ValueError,'Expected one output'):self.complete()
        log.write_text(json.dumps({'output':'/summary/attempt_ok/../../outside'}))
        with self.assertRaisesRegex(ValueError,'Unexpected summary'):self.complete()

    def test_duplicate_evaluated_identity_cannot_complete(self):
        actual=deepcopy(self.rows);actual[-1]=actual[0]
        self.mutate(self.ev/'receipt.json',selected_run_sources=actual)
        with self.assertRaisesRegex(ValueError,'Evaluation membership'):self.complete()


if __name__=='__main__':unittest.main()
