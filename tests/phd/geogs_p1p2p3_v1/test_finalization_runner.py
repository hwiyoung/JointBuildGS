"""Reference-free command routing and partial-output admission checks."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

REPO = Path(__file__).resolve().parents[3]
BASE = REPO/'scripts/phd/geogs_p1p2p3_v1'
for directory in (BASE, BASE/'evaluation', BASE/'runtime'):
    sys.path.insert(0, str(directory))
from finalization_control import FinalizationGate


class FinalizationCommandsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = subprocess.check_output(['bash', str(BASE/'runtime/finalize_after_all21.sh'), '--dry-run'], text=True)
        cls.commands = [shlex.split(line) for line in output.splitlines()]

    def test_fixed_nine_commands_bind_layout_repeat_and_readonly_model_task(self):
        self.assertEqual(len(self.commands), 9)
        for command in self.commands:
            self.assertEqual(command[:3], ['docker', 'run', '--rm'])
            self.assertEqual(command[command.index('--runtime-layout')+1], '/task/contracts/runtime_layout_allocator_v2.json')
            self.assertEqual(command[command.index('--repeat-contract')+1], '/task/contracts/supplemental_repeat_v1.json')
            self.assertEqual(command[command.index('--resource-contract')+1], '/task/contracts/extraction_resource_v3.json')
            self.assertTrue(any('dst=/task,readonly' in arg for arg in command))
            self.assertFalse(any('docker.sock' in arg for arg in command))
        self.assertIn('/audit/seal_candidates.py', self.commands[0])
        self.assertIn('/audit/case_figures.py', self.commands[-1])
        self.assertIn('--viewer-manifest-v2', self.commands[-1])

    def test_raw_reference_mounts_only_matching_regional_geometry_commands(self):
        count = 0
        for command in self.commands:
            reference = [arg for arg in command if 'dst=/reference/' in arg]
            geometry = '--stage' in command and command[command.index('--stage')+1] == 'geometry'
            self.assertEqual(bool(reference), geometry)
            if geometry:
                region = command[command.index('--region')+1]
                self.assertEqual(len(reference), 1)
                self.assertIn('/run/'+region+'/reference.npz,dst=/reference/'+region+'/reference.npz,readonly', reference[0])
                count += 1
        self.assertEqual(count, 3)


class FinalizationStageAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.gate = object.__new__(FinalizationGate)
        self.gate.task = self.task
        self.gate.cfg = dict(regions={'P1':{'expected_test':2}}, conditions=[dict(id='D005_Pnative')])
        self.gate.layout = SimpleNamespace(require_receipt=lambda value: None)
        self.gate.repeat = SimpleNamespace(identifier='native_repeat_1', require_receipt=lambda value: None)
        self.gate.candidate_seal = lambda: ({}, 'a'*64)

    def tearDown(self):
        self.temp.cleanup()

    def render_receipt(self, condition, stage):
        path = self.task/'evaluation/renders/P1'/condition/stage/'receipt.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(status='PASS_RENDER_QUALITY_EVALUATION', scientific_verdict=None,
            region='P1', condition=condition, stage=stage, expected_evaluation_views=2,
            sealed_render_manifest_sha256='a'*64)))

    def test_partial_render_stage_refuses_automatic_rerun_of_successful_prefix(self):
        self.assertEqual(self.gate.decide('renders:P1')[0], 'RUN')
        self.render_receipt('D005_Pnative', 'final')
        with self.assertRaises(FileNotFoundError):
            self.gate.decide('renders:P1')
        for condition in ('D005_Pnative', 'native_repeat_1'):
            for stage in ('final', 'anchor'):
                self.render_receipt(condition, stage)
        self.assertEqual(self.gate.decide('renders:P1')[0], 'SKIP')

    def test_partial_geometry_and_wrong_seal_render_receipt_fail_closed(self):
        (self.task/'evaluation/geometry/P1').mkdir(parents=True)
        with self.assertRaises(FileNotFoundError):
            self.gate.decide('geometry:P1')
        for condition in ('D005_Pnative', 'native_repeat_1'):
            for stage in ('final', 'anchor'):
                self.render_receipt(condition, stage)
        path = self.task/'evaluation/renders/P1/native_repeat_1/anchor/receipt.json'
        value = json.loads(path.read_text())
        value['sealed_render_manifest_sha256'] = 'b'*64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'different candidate seal'):
            self.gate.decide('renders:P1')

    def test_resource_render_inventory_uses_shared_anchor512_without_fake_repeat_anchor(self):
        self.gate.resource = SimpleNamespace(data={'revision':'resource_v3'},require_receipt=lambda value:None)
        candidates = [dict(region='P1',condition=condition,variant=stage,render_records=[{'synthetic':True}])
                      for condition,stage in (('D005_Pnative','final'),('D005_Pnative','anchor_512'),('native_repeat_1','final'))]
        self.gate.candidate_seal = lambda: ({'candidates':candidates},'a'*64)
        for row in candidates:
            self.render_receipt(row['condition'],row['variant'])
        self.assertEqual(self.gate.decide('renders:P1')[0],'SKIP')
        self.assertFalse((self.task/'evaluation/renders/P1/native_repeat_1/anchor').exists())


if __name__ == '__main__':
    unittest.main()
