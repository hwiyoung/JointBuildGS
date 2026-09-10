"""Semantic reporting checks using explicit synthetic accounting, no raw GT."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

CODE=Path(__file__).resolve().parents[3]/'scripts/phd/local_complementary_refinement_v1'
sys.path.insert(0,str(CODE))
import summarize_results_v2 as report
from evaluation_utils_v2 import write_json,write_csv,sha,three_way_rows,paired_rows


def fixture():
    parents=['D005_Pnative','D005_Prelease','D0005_Pnative','D0005_Prelease','D0_Pnative','D0_Prelease']
    conditions=[dict(id='LC_'+name,parent_condition=name,lambda_p=.005 if index<2 else .0005 if index<4 else 0.,
                     protection='native' if index%2==0 else 'release') for index,name in enumerate(parents)]
    cfg=dict(task_id='SYNTHETIC_TEST_ONLY',regions=['P1','P2','P3'],conditions=conditions,scientific_verdict=None,
             evaluation={'thresholds_m':[.1,.2,.25,.5,1.,2.]})
    def geom(name,precision=.8,recall=.5):
        return dict(region='P2',candidate=name,mesh_kind='raw',mesh_res=512,threshold_m=.5,
            reference_count=8,surface_samples=10,status='ASSESSED_DEVELOPMENT_ONLY',
            precision=precision,recall=recall,f1=2*precision*recall/(precision+recall))
    local=conditions[0]['id'];parent=parents[0]
    geometry=[geom('ANCHOR'),*[geom(name) for name in parents],geom(local,.4,.75)]
    def pair(candidate,comparator,gain=2,damage=2,retained=2,remaining=2):
        return dict(region='P2',candidate=candidate,comparator=comparator,mesh_kind='raw',threshold_m=.5,
            cohort='ALL_REFERENCE',reference_count=8,corrected_count=gain,damaged_count=damage,
            retained_near_count=retained,remaining_far_count=remaining)
    pairs=[*[pair(name,'ANCHOR') for name in parents],pair(local,'ANCHOR',4,2,2,0),pair(local,parent,3,1,3,1)]
    cells=[dict(region='P2',candidate=local,comparator=parent,mesh_kind='raw',threshold_m=.5,cell_id=0,reference_count=4,corrected_count=2,damaged_count=1),
           dict(region='P2',candidate=local,comparator=parent,mesh_kind='raw',threshold_m=.5,cell_id=1,reference_count=4,corrected_count=1,damaged_count=0)]
    # Anchor/G/LC states: 000=0,001=2,010=0,011=2,100=1,101=1,110=1,111=1.
    joint=dict(region='P2',candidate=local,parent_condition=parent,mesh_kind='raw',threshold_m=.5,
        cohort='ALL_REFERENCE',reference_count=8,global_corrected_count=2,global_damaged_count=2,
        global_correction_retained_by_local_count=2,global_correction_lost_by_local_count=0,
        global_damage_recovered_by_local_count=1,additional_local_damage_count=1,
        additional_local_correction_count=2,global_damage_remaining_in_local_count=1,
        anchor_valid_retained_by_both_count=1,anchor_far_remaining_far_in_both_count=0)
    joint.update({f'anchor_global_local_near_{state:03b}_count':count for state,count in enumerate([0,2,0,2,1,1,1,1])})
    appearance=[]
    for domain in ('full_frame','fixed_prism_projected_bbox'):
        for index,name in enumerate(('photo_a','photo_b')):
            full=domain=='full_frame'
            appearance.append(dict(region='P2',candidate=local,parent_condition=parent,domain=domain,name=name,
                status='ASSESSED',pixel_count=100,psnr_native_db=20.+index if full else None,
                psnr_cpu_float64_db=22.+index,ssim_native=.7 if full else None,lpips_vgg_native_01=.3 if full else None,
                parent_psnr_native_db=18.+index,parent_ssim_native=.6,parent_lpips_vgg_native_01=.4))
    return cfg,geometry,pairs,cells,[joint],appearance


class SummaryAccountingTests(unittest.TestCase):
    def test_reference_recall_can_improve_while_f1_worsens(self):
        cfg,geometry,pairs,cells,joint,_=fixture()
        rows,methods=report.pair_summary(geometry,pairs,cells,joint,cfg,False)
        row=rows[0]
        self.assertGreater(row['delta_recall'],0.)
        self.assertLess(row['delta_precision'],0.)
        self.assertLess(row['delta_f1'],0.)
        self.assertEqual(row['local_corrected_vs_global'],3)
        self.assertEqual(row['local_damaged_vs_global'],1)
        self.assertEqual(row['same_cell_both_count'],1)
        self.assertEqual(len([r for r in methods if r['method']=='G']),6)
        self.assertEqual(row['global_corrected_vs_anchor'],2)
        self.assertEqual(row['additional_local_damage_count'],1)

    def test_same_cell_counts_cannot_hide_lost_reference_membership(self):
        cfg,geometry,pairs,cells,joint,_=fixture();cells[0]['reference_count']=3
        with self.assertRaisesRegex(ValueError,'Same-cell reference'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_netted_only_counts_are_rejected(self):
        cfg,geometry,pairs,cells,joint,_=fixture();cells[0]['corrected_count']=1;cells[0]['damaged_count']=0
        with self.assertRaisesRegex(ValueError,'gains/damage'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_recall_and_point_transition_denominators_must_agree(self):
        cfg,geometry,pairs,cells,joint,_=fixture();geometry[-1]['recall']=.9
        with self.assertRaisesRegex(ValueError,'recall does not reconcile'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_original_comparators_cannot_be_selected_away(self):
        cfg,geometry,pairs,cells,joint,_=fixture();geometry.pop(5)
        with self.assertRaisesRegex(ValueError,'original G comparator'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_complete_report_cannot_accept_one_condition(self):
        cfg,geometry,pairs,cells,joint,_=fixture()
        with self.assertRaisesRegex(ValueError,'full18'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,True)

    def test_duplicate_geometry_identity_rejected(self):
        cfg,geometry,pairs,cells,joint,_=fixture();geometry.append(dict(geometry[-1]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_three_way_state_counts_must_partition_same_points(self):
        cfg,geometry,pairs,cells,joint,_=fixture();joint[0]['anchor_global_local_near_111_count']=0
        with self.assertRaisesRegex(ValueError,'Three-way classes'):
            report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_forged_named_counts_rejected_despite_valid_eight_point_partition(self):
        for field,value in [('global_correction_lost_by_local_count',999),
                            ('global_damage_recovered_by_local_count',888),
                            ('additional_local_damage_count',777)]:
            with self.subTest(field=field):
                cfg,geometry,pairs,cells,joint,_=fixture();joint[0][field]=value
                self.assertEqual(sum(joint[0][f'anchor_global_local_near_{s:03b}_count'] for s in range(8)),8)
                with self.assertRaisesRegex(ValueError,'Three-way named count'):
                    report.pair_summary(geometry,pairs,cells,joint,cfg,False)

    def test_every_named_count_is_derived_and_checked(self):
        _,_,pairs,_,joint,_=fixture()
        expected=report.validate_three_way_accounting(joint[0],8,pairs[0],pairs[-2],pairs[-1])
        self.assertEqual(len(expected),10)
        for field in expected:
            with self.subTest(field=field):
                forged=dict(joint[0]);forged[field]+=1
                with self.assertRaisesRegex(ValueError,'Three-way named count'):
                    report.validate_three_way_accounting(forged,8,pairs[0],pairs[-2],pairs[-1])

    def test_all_three_pair_projections_reject_valid_sum_mismatches(self):
        for index,label in enumerate(('Anchor->G','Anchor->LC','G->LC')):
            with self.subTest(projection=label):
                _,_,pairs,_,joint,_=fixture()
                projected=copy.deepcopy([pairs[0],pairs[-2],pairs[-1]])
                projected[index]['corrected_count']-=1;projected[index]['remaining_far_count']+=1
                self.assertEqual(sum(projected[index][key] for key in
                    ('corrected_count','damaged_count','retained_near_count','remaining_far_count')),8)
                with self.assertRaisesRegex(ValueError,'Three-way projection differs from '+label):
                    report.validate_three_way_accounting(joint[0],8,*projected)

    def test_binary_order_matches_actual_producer_for_all_eight_states(self):
        states=np.arange(8);a=np.where(states&4,.1,1.);g=np.where(states&2,.1,1.);lc=np.where(states&1,.1,1.)
        cohorts={'ALL_REFERENCE':np.ones(8,dtype=bool)}
        row=three_way_rows('P2','LC','G','raw',a,g,lc,cohorts,[.5])[0]
        self.assertEqual([row[f'anchor_global_local_near_{s:03b}_count'] for s in states],[1]*8)
        projections=[paired_rows('P2',after,before,'raw',old,new,cohorts,[.5],1e-9)[0]
            for after,before,old,new in [('G','ANCHOR',a,g),('LC','ANCHOR',a,lc),('LC','G',g,lc)]]
        derived=report.validate_three_way_accounting(row,8,*projections)
        self.assertEqual(derived['global_corrected_count'],2)
        self.assertEqual(derived['global_damaged_count'],2)
        self.assertTrue(all(value==1 for key,value in derived.items() if key not in
            ('global_corrected_count','global_damaged_count')))

    def test_cell_cannot_contain_more_changed_points_than_reference(self):
        cfg,g,p,c,j,_=fixture();c[0]['reference_count']=2;c[1]['reference_count']=6
        with self.assertRaisesRegex(ValueError,'exceed its reference count'):
            report.pair_summary(g,p,c,j,cfg,False)

    def test_anchor_recall_must_reconcile_with_three_way_projection(self):
        cfg,g,p,c,j,_=fixture();g[0]['recall']=.625
        with self.assertRaisesRegex(ValueError,'Anchor reference recall'):
            report.pair_summary(g,p,c,j,cfg,False)

    def test_appearance_uses_identical_pairs_and_does_not_copy_roi_ssim(self):
        cfg,*_,appearance=fixture();candidate=cfg['conditions'][0]['id']
        appearance[1]['ssim_native']=None
        summary=report.appearance_summary(appearance,{('P2',candidate):['photo_a','photo_b']})
        full_ssim=next(r for r in summary if r['metric']=='ssim' and r['domain']=='full_frame')
        roi_ssim=next(r for r in summary if r['metric']=='ssim' and r['domain']!='full_frame')
        full_psnr=next(r for r in summary if r['metric']=='psnr' and r['domain']=='full_frame')
        self.assertEqual(full_ssim['finite_pair_count'],1)
        self.assertEqual(full_ssim['expected_camera_count'],2)
        self.assertAlmostEqual(full_psnr['mean_paired_delta'],2.)
        self.assertEqual(roi_ssim['finite_pair_count'],0)
        self.assertIsNone(roi_ssim['mean_local'])

    def test_missing_appearance_camera_fails(self):
        cfg,*_,appearance=fixture();candidate=cfg['conditions'][0]['id'];appearance.pop()
        with self.assertRaisesRegex(ValueError,'camera identity membership'):
            report.appearance_summary(appearance,{('P2',candidate):['photo_a','photo_b']})

    def test_partial_report_has_no_outcome_direction_count(self):
        cfg,g,p,c,j,a=fixture();paired,methods=report.pair_summary(g,p,c,j,cfg,False)
        appearance=report.appearance_summary(a,{('P2',cfg['conditions'][0]['id']):['photo_a','photo_b']})
        text=report.korean_report(cfg,paired,methods,appearance,False,[], 'a'*64)
        self.assertIn('중간 관측',text)
        self.assertNotIn('F1 수치는 상승',text)
        self.assertIn('scientific_verdict: null',text)
        self.assertIn('평균 배율 전역 대조·controller replay가 없어',text)

    def test_all_thresholds_and_post_required(self):
        cfg,g,*_=fixture()
        with self.assertRaisesRegex(ValueError,'both raw/post'):
            report.validate_geometry_grid(g,cfg)

    def test_paired_and_three_way_grids_reject_missing_or_duplicate_thresholds(self):
        cfg,_,pairs,_,joint,_=fixture()
        for three_way,rows in [(False,pairs),(True,joint)]:
            grid=[dict(row,mesh_kind=k,threshold_m=t) for row in rows for k in ('raw','post')
                  for t in cfg['evaluation']['thresholds_m']]
            report.validate_paired_grids(grid,cfg,three_way)
            with self.subTest(three_way=three_way),self.assertRaisesRegex(ValueError,'both raw/post'):
                report.validate_paired_grids(grid[:-1],cfg,three_way)
            with self.subTest(three_way=three_way),self.assertRaisesRegex(ValueError,'Duplicate paired'):
                report.validate_paired_grids(grid+[grid[0]],cfg,three_way)


class SealedSummaryTests(unittest.TestCase):
    def setup_attempt(self,root,full=False):
        cfg,g,p,c,j,a=fixture();config=root/'experiment_v2.json';write_json(config,cfg)
        identities=[('P2',cfg['conditions'][0]['id'])]
        if full:
            template_g,template_p,template_c,template_j,template_a=g,p,c,j,a
            g=[];p=[];c=[];j=[];a=[];identities=[]
            for region in cfg['regions']:
                g.extend(dict(r,region=region) for r in template_g[:-1])
                p.extend(dict(r,region=region) for r in template_p[:-2])
                for condition in cfg['conditions']:
                    candidate,parent=condition['id'],condition['parent_condition']
                    g.append(dict(template_g[-1],region=region,candidate=candidate))
                    p.extend([dict(template_p[-2],region=region,candidate=candidate),
                              dict(template_p[-1],region=region,candidate=candidate,comparator=parent)])
                    c.extend(dict(r,region=region,candidate=candidate,comparator=parent) for r in template_c)
                    j.extend(dict(r,region=region,candidate=candidate,parent_condition=parent) for r in template_j)
                    a.extend(dict(r,region=region,candidate=candidate,parent_condition=parent) for r in template_a)
                    identities.append((region,candidate))
        evaluation=root/'evaluation';evaluation.mkdir()
        full_geometry=[dict(row,mesh_kind=kind,threshold_m=t) for row in g for kind in ('raw','post') for t in cfg['evaluation']['thresholds_m']]
        full_pairs=[dict(row,mesh_kind=kind,threshold_m=t) for row in p for kind in ('raw','post') for t in cfg['evaluation']['thresholds_m']]
        full_joint=[dict(row,mesh_kind=kind,threshold_m=t) for row in j for kind in ('raw','post') for t in cfg['evaluation']['thresholds_m']]
        data={'geometry_metrics':full_geometry,'paired_transitions':full_pairs,'same_cell_changes':c,
              'anchor_global_local_transitions':full_joint,'appearance_per_image':a,'coverage':[],
              'postprocessing_effect':[],'compute':[],'missing_runs':[] if full else [{'status':'PENDING','condition':'remaining17'}]}
        for name,rows in data.items():write_csv(evaluation/(name+'.csv'),rows)
        for region,candidate in identities:
            identity=evaluation/region/candidate/'render_identity.json'
            write_json(identity,{'records':[{'name':'photo_a'},{'name':'photo_b'}]})
        manifest=[dict(path=str(path.relative_to(evaluation)),bytes=path.stat().st_size,sha256=sha(path))
                  for path in evaluation.rglob('*') if path.is_file()]
        write_json(evaluation/'receipt.json',dict(schema='jbgs.local_complementary_evaluation.v2',scientific_verdict=None,
            reference_used_for_training_or_parameter_selection=False,
            status='COMPLETE_DEVELOPMENT_EVALUATION' if full else 'PARTIAL_DEVELOPMENT_EVALUATION',
            run_count=18 if full else 1,expected_full_run_count=18,missing=data['missing_runs'],
            inputs=[{'path':str(config),'sha256':sha(config)}],outputs=manifest))
        return config,evaluation

    def test_full18_report_retains_all_baselines_and_all_harm(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,evaluation=self.setup_attempt(root,full=True)
            attempt,receipt=report.summarize(evaluation,config,root/'summary')
            self.assertEqual(receipt['status'],'COMPLETE_18_DEVELOPMENT_SUMMARY')
            self.assertEqual(receipt['report_revision'],'v2.2_three_way_accounting')
            with (attempt/'paired_summary.csv').open() as stream:paired=list(csv.DictReader(stream))
            with (attempt/'all_methods_raw512_0.5m.csv').open() as stream:methods=list(csv.DictReader(stream))
            self.assertEqual(len(paired),18)
            self.assertEqual(sum(r['method']=='G' for r in methods),18)
            self.assertEqual(sum(r['method']=='LC' for r in methods),18)
            text=(attempt/'RESULT_ko_v2.md').read_text()
            self.assertIn('하락 18조건',text)
            self.assertIn('작은 차이의 재현성',text)

    def test_explicit_partial_delivery_and_digest_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,evaluation=self.setup_attempt(root)
            with self.assertRaisesRegex(ValueError,'Full18'):
                report.summarize(evaluation,config,root/'summary')
            attempt,receipt=report.summarize(evaluation,config,root/'summary',True)
            self.assertEqual(receipt['status'],'PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION')
            self.assertFalse(receipt['raw_gt_or_model_loaded'])
            self.assertTrue((attempt/'RESULT_ko_v2.md').is_file())
            for entry in receipt['outputs']:self.assertEqual(sha(attempt/entry['path']),entry['sha256'])

    def test_mutated_csv_cannot_be_summarized(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,evaluation=self.setup_attempt(root)
            with (evaluation/'same_cell_changes.csv').open('a') as stream:stream.write('\n')
            with self.assertRaisesRegex(ValueError,'Changed evaluation output'):
                report.summarize(evaluation,config,root/'summary',True)

    def test_summary_cannot_write_into_evaluation_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,evaluation=self.setup_attempt(root)
            with self.assertRaisesRegex(ValueError,'separate'):
                report.summarize(evaluation,config,evaluation/'summary',True)

    def test_explicit_evaluation_only_false_is_required(self):
        for invalid in ('ABSENT',True,None,0,'false'):
            with self.subTest(value=invalid),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);config,evaluation=self.setup_attempt(root)
                receipt_path=evaluation/'receipt.json';receipt=json.loads(receipt_path.read_text())
                if invalid=='ABSENT':receipt.pop('reference_used_for_training_or_parameter_selection')
                else:receipt['reference_used_for_training_or_parameter_selection']=invalid
                receipt_path.unlink();write_json(receipt_path,receipt)
                with self.assertRaisesRegex(ValueError,'Explicit evaluation-only'):
                    report.summarize(evaluation,config,root/'summary',True)
                self.assertFalse((root/'summary').exists())

    def test_sealed_missing_paired_grid_is_still_rejected(self):
        for name in ('paired_transitions','anchor_global_local_transitions'):
            with self.subTest(table=name),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);config,evaluation=self.setup_attempt(root)
                path=evaluation/(name+'.csv')
                with path.open() as stream:rows=list(csv.DictReader(stream))
                path.unlink();write_csv(path,rows[:-1]);self.reseal(evaluation,path)
                with self.assertRaisesRegex(ValueError,'both raw/post'):
                    report.summarize(evaluation,config,root/'summary',True)
                self.assertFalse((root/'summary').exists())

    def test_nonprimary_post_threshold_named_count_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config,evaluation=self.setup_attempt(root)
            path=evaluation/'anchor_global_local_transitions.csv'
            with path.open() as stream:rows=list(csv.DictReader(stream))
            target=next(r for r in rows if r['mesh_kind']=='post' and float(r['threshold_m'])==2.)
            target['global_correction_lost_by_local_count']=999
            path.unlink();write_csv(path,rows);self.reseal(evaluation,path)
            with self.assertRaisesRegex(ValueError,'Three-way named count'):
                report.summarize(evaluation,config,root/'summary',True)
            self.assertFalse((root/'summary').exists())

    @staticmethod
    def reseal(evaluation,path):
        receipt_path=evaluation/'receipt.json';receipt=json.loads(receipt_path.read_text())
        entry=next(r for r in receipt['outputs'] if r['path']==path.name)
        entry.update(bytes=path.stat().st_size,sha256=sha(path));receipt_path.unlink();write_json(receipt_path,receipt)


if __name__=='__main__':unittest.main()
