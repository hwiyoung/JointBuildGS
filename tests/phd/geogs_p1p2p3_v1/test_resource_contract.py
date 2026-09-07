"""Contract ownership and optional-OOM evidence admission, without reference data."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
BASE = REPO/'scripts/phd/geogs_p1p2p3_v1'
for path in (BASE,BASE/'evaluation'):
    sys.path.insert(0,str(path))
from resource_contract import ResourceContract, RESOURCE_SHA, sha
import run_auxiliary_resource_v3 as driver


class ResourceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)
        self.resource = object.__new__(ResourceContract)
        self.resource.task = self.task
        self.resource.path = None
        self.resource.digest = RESOURCE_SHA
        self.resource.data = json.loads((REPO/'configs/phd/geogs_p1p2p3_v1/extraction_resource_v3.json').read_text())
        self.resource.layout = SimpleNamespace(regions=('P1','P2','P3'))
        self.resource.repeat = None

    def tearDown(self):
        self.temp.cleanup()

    def planned(self, required=False):
        return dict(name='mesh_512' if required else 'mesh_2048', iteration=30000,
                    mesh_res=512 if required else 2048, required=required, export_images=False,source_kind='final_complete')

    def test_common_anchor_has_one_primary_native_owner_and_repeat_has_no_anchor(self):
        native = self.resource.variant_inventory('P1','D005_Pnative')
        self.assertEqual([row['name'] for row in native],['anchor_512','anchor','mesh_512','mesh_2048'])
        self.assertEqual([row['required'] for row in native],[True,False,True,False])
        repeated = self.resource.variant_inventory('P2','D005_Pnative','native_repeat_1')
        self.assertEqual([row['name'] for row in repeated],['mesh_512','mesh_2048'])
        self.assertNotEqual(self.resource.aux_run('P2','D005_Pnative'), self.resource.aux_run('P2','D005_Pnative','native_repeat_1'))

    def proof(self, required=False):
        planned = self.planned(required)
        root = self.task/planned['name']
        root.mkdir()
        cap = 32*1024**3
        before = dict(memory_max=str(cap),memory_events={'oom_kill':0})
        after = dict(memory_max=str(cap),memory_events={'oom_kill':1})
        (root/'memory.jsonl').write_text(json.dumps(before)+'\n'+json.dumps(after)+'\n')
        (root/'render.log').write_text('Synthetic native process killed after allocation\n')
        value = dict(resource_contract_sha256=RESOURCE_SHA,scientific_verdict=None,
                     **{k:planned[k] for k in ('iteration','mesh_res','required','export_images','source_kind')},
                     variant=planned['name'],status='TECHNICAL_RESOURCE_UNAVAILABLE',native_exit_code=-9,
                     cgroup_memory_limit_bytes=cap,cgroup_oom_kill_delta=1,memory_before=before,memory_after=after,
                     memory_trace=dict(path='memory.jsonl',sha256=sha(root/'memory.jsonl')),
                     source_log=dict(path='render.log',sha256=sha(root/'render.log')))
        return root,planned,value

    def test_optional_requires_matching_native_sigkill_cgroup_event_and_trace(self):
        root,planned,value = self.proof()
        self.resource.validate_variant(value,planned,root)
        for key,other in [('native_exit_code',-11),('cgroup_oom_kill_delta',0),('cgroup_memory_limit_bytes',48*1024**3)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.resource.validate_variant(dict(value,**{key:other}),planned,root)
        altered = copy.deepcopy(value)
        altered['memory_after']['memory_events']['oom_kill'] = 2
        altered['cgroup_oom_kill_delta'] = 2
        with self.assertRaisesRegex(ValueError,'trace/cap'):
            self.resource.validate_variant(altered,planned,root)

    def test_required_oom_and_modified_proof_fail_closed(self):
        root,planned,value = self.proof(required=True)
        with self.assertRaisesRegex(ValueError,'Required'):
            self.resource.validate_variant(value,planned,root)
        (root/'memory.jsonl').write_text('changed')
        with self.assertRaisesRegex(ValueError,'hash differs'):
            self.resource.validate_variant(value,planned,root)

    def test_optional_driver_records_oom_and_keeps_exact_official_sensitivity_command(self):
        source = self.task/'source.ply'
        cfg_args = self.task/'cfg_args'
        source.write_bytes(b'synthetic exact source')
        cfg_args.write_text('synthetic cfg namespace')
        cap = 32*1024**3
        before = dict(unix=1.,memory_max=str(cap),memory_events={'oom_kill':0},
                      host_mem_available_bytes=64*1024**3,memory_current_bytes=1,memory_peak_bytes=1)
        after = dict(before,unix=2.,memory_events={'oom_kill':1})
        seen = []
        def popen(command,**kwargs):
            seen.append(command)
            kwargs['stdout'].write('Synthetic cgroup OOM native process\n')
            kwargs['stdout'].flush()
            return SimpleNamespace(pid=321,returncode=None)
        common = dict(region='P1',condition='D005_Pnative',scientific_verdict=None,resource_contract_sha256=RESOURCE_SHA)
        with mock.patch.object(driver,'memory',side_effect=[before,before,after]), \
             mock.patch.object(driver.subprocess,'Popen',side_effect=popen), \
             mock.patch.object(driver.os,'wait4',return_value=(321,9,SimpleNamespace(ru_maxrss=1024))):
            row = driver.native_variant(self.task,self.planned(),source,cfg_args,common,self.resource,
                {'extraction':{'num_cluster':50}},None)
        self.assertEqual(row['status'],'TECHNICAL_RESOURCE_UNAVAILABLE')
        self.assertEqual(seen[0][-6:],['--iteration','30000','--mesh_res','2048','--skip_train','--skip_test'])
        receipt = json.loads((self.task/row['receipt_path']).read_text())
        self.assertEqual(receipt['source_complete_ply_sha256'],sha(source))
        self.assertEqual(receipt['cgroup_oom_kill_delta'],1)


if __name__ == '__main__':
    unittest.main()
