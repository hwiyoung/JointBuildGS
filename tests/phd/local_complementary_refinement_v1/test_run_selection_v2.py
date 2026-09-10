"""Synthetic failure lineage checks; no reference geometry or model payloads."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/phd/local_complementary_refinement_v1'))
import run_selection_v2 as rs


class RunSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.cfg=dict(task_id='synthetic',runtime=dict(image_id='image'),regions=['P1','P2','P3'],
            conditions=[dict(id=f'LC_D{d}_P{p}') for d in ['005','0005','0'] for p in ['native','release']])
        self.region='P3';self.condition='LC_D0005_Pnative'
        self.retry=f'retries/{self.region}_{self.condition}_attempt2'
        for region in self.cfg['regions']:
            for condition in self.cfg['conditions']:
                self.write_run(region,condition['id'],f"runs/{region}/{condition['id']}")
        self.write_run(self.region,self.condition,self.retry)
        old=self.root/f'runs/{self.region}/{self.condition}'
        receipt=rs.read(old/'train_receipt.json');receipt['status']='FAIL'
        self.write(old/'train_receipt.json',receipt)
        (old/'train.log').write_text('torch.cuda.OutOfMemoryError: synthetic capacity failure\n')
        self.selection=rs.make_selection(self.root,self.cfg,'cfg','binding',{(self.region,self.condition):self.retry})
        self.path=self.root/'selection.json'

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

    def write_run(self,region,condition,relative):
        for phase in ['train','render','metrics']:
            receipt=dict(status='PASS',region=region,condition=condition,phase=phase,task_id='synthetic',
                scientific_verdict=None,runtime_image_id='image',config_sha256='cfg',input_binding=dict(sha256='binding'),
                command=['python','train.py'],environment=dict(allocator='native'),anchor=dict(sha256='anchor'),
                source_provenance=dict(sha256='source'),driver=dict(sha256='driver'),training_start_iteration=8000,
                training_end_iteration=30000)
            self.write(self.root/relative/(phase+'_receipt.json'),receipt)

    def bind(self,path,expected=None):
        value=rs.digest(path)
        if expected is not None and value!=expected:raise ValueError('Digest differs')
        return value

    def load(self,selection=None):
        self.write(self.path,self.selection if selection is None else selection)
        return rs.load_selection(self.path,self.root,self.cfg,'cfg','binding',self.bind)

    def retry_row(self):
        return next(x for x in self.selection['runs'] if x['relative_path']==self.retry)

    def test_full18_includes_bound_retry_and_preserves_failure(self):
        selected=self.load();self.assertEqual(len(selected),18)
        self.assertEqual(selected[self.region,self.condition],self.root/self.retry)
        self.assertEqual(rs.read(self.root/f'runs/{self.region}/{self.condition}/train_receipt.json')['status'],'FAIL')

    def test_wrong_config_binding_image_or_verdict_fails(self):
        for key,value in [('config_sha256','other'),('input_binding_sha256','other'),('scientific_verdict','pass'),('selection_uses_quality_metrics',True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                altered=copy.deepcopy(self.selection);altered[key]=value;self.load(altered)

    def test_missing_duplicate_unknown_identity_fails(self):
        for mode in ['missing','duplicate','unknown']:
            altered=copy.deepcopy(self.selection)
            if mode=='missing':altered['runs'].pop()
            elif mode=='duplicate':altered['runs'][-1]=altered['runs'][0]
            else:altered['runs'][0]['region']='P4'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.load(altered)

    def test_path_escape_different_identity_and_alias_fail(self):
        for relative in ['../outside','runs/P1/LC_D0005_Pnative','retries/P3_LC_D0005_Pnative_attempt1']:
            with self.subTest(relative=relative),self.assertRaises(ValueError):rs.safe_run(self.root,self.region,self.condition,relative)
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):rs.safe_run(self.root,self.region,self.condition,'alias/'+self.retry)

    def test_symlinked_run_directory_fails(self):
        path=self.root/'retries/P1_LC_D0_Pnative_attempt2';path.symlink_to(self.root/'runs/P1/LC_D0_Pnative',target_is_directory=True)
        with self.assertRaises(ValueError):rs.safe_run(self.root,'P1','LC_D0_Pnative',str(path.relative_to(self.root)))

    def test_attempt10_path_is_allowed(self):
        relative='retries/P1_LC_D0_Pnative_attempt10'
        self.assertEqual(rs.safe_run(self.root,'P1','LC_D0_Pnative',relative),self.root/relative)

    def test_failed_or_changed_selected_phase_fails(self):
        path=self.root/self.retry/'metrics_receipt.json';r=rs.read(path);r['status']='FAIL';self.write(path,r)
        with self.assertRaises(ValueError):self.load()
        self.retry_row()['phase_receipt_sha256']['metrics']=rs.digest(path)
        with self.assertRaises(ValueError):self.load()

    def test_failed_history_must_be_complete_and_ordered(self):
        row=self.retry_row();row['failed_attempts']=[]
        with self.assertRaises(ValueError):self.load()

    def test_successful_previous_attempt_cannot_be_discarded(self):
        row=self.retry_row();old=self.root/row['failed_attempts'][0]['relative_path']/'train_receipt.json'
        r=rs.read(old);r['status']='PASS';self.write(old,r);row['failed_attempts'][0]['train_receipt_sha256']=rs.digest(old)
        with self.assertRaises(ValueError):self.load()

    def test_oom_evidence_cannot_be_absent_or_changed(self):
        row=self.retry_row();log=self.root/row['failed_attempts'][0]['relative_path']/'train.log';log.write_text('different error')
        with self.assertRaises(ValueError):self.load()
        row['failed_attempts'][0]['train_log_sha256']=rs.digest(log)
        with self.assertRaises(ValueError):self.load()

    def test_training_policy_change_fails_even_with_updated_hash(self):
        path=self.root/self.retry/'train_receipt.json';original=rs.read(path)
        for key in ['command','environment','anchor','source_provenance','driver','training_start_iteration','training_end_iteration']:
            r=dict(original);r[key]='changed';self.write(path,r);self.retry_row()['phase_receipt_sha256']['train']=rs.digest(path)
            with self.subTest(key=key),self.assertRaises(ValueError):self.load()

    def test_evaluation_source_is_fixed_by_its_receipt(self):
        row=self.retry_row();evaluation=dict(selected_run_sources=[row])
        self.assertEqual(rs.run_from_evaluation(self.root,self.region,self.condition,evaluation,self.bind),self.root/self.retry)
        evaluation['selected_run_sources'].append(row)
        with self.assertRaises(ValueError):rs.run_from_evaluation(self.root,self.region,self.condition,evaluation,self.bind)

    def test_legacy_evaluation_stays_on_original_run(self):
        result=rs.run_from_evaluation(self.root,'P1','LC_D0_Pnative',{},self.bind)
        self.assertEqual(result,self.root/'runs/P1/LC_D0_Pnative')

    def test_evaluation_source_digest_failure(self):
        row=copy.deepcopy(self.retry_row());row['phase_receipt_sha256']['train']='wrong'
        with self.assertRaises(ValueError):rs.run_from_evaluation(self.root,self.region,self.condition,dict(selected_run_sources=[row]),self.bind)


if __name__=='__main__':unittest.main()
