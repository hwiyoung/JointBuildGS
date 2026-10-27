"""A proposed lower admission gate must remain inactive without user approval."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

def module(name):
    spec=importlib.util.spec_from_file_location(name,Path('/repo/scripts/phd/main_losstrain_v1')/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

P=module('post_memory_policy');A=module('post_admission')


class MemoryPolicy(unittest.TestCase):
    def test_no_approval_retains_original_policy(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(P.policy_for(d),P.DEFAULT)
            self.assertEqual(P.policy_for(d)['host_available_GiB'],64)

    def test_incomplete_approval_cannot_enable_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'checks/post_memory_56_40_v1/authorization.json';p.parent.mkdir(parents=True)
            p.write_text(json.dumps(dict(status='PROPOSED_NOT_ACTIVE',policy=P.PROPOSED,user_instruction='')))
            with self.assertRaises(AssertionError):P.policy_for(d)

    def test_exact_approved_profile_preserves_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'checks/post_memory_56_40_v1/authorization.json';p.parent.mkdir(parents=True)
            p.write_text(json.dumps(dict(status='AUTHORIZED',policy=P.PROPOSED,user_instruction='synthetic unit-test approval')))
            r=P.policy_for(d)
            self.assertEqual(r['host_available_GiB']-r['container_limit_GiB'],16)
            self.assertEqual(r['stable_seconds'],60)

    def test_admission_restarts_stable_window_after_memory_dip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'checks').mkdir()
            now=[0];values=iter([57,57,55,57,57,57,57,57,57,57])
            def sleep(seconds):now[0]+=seconds
            with A.admit(root/'admission.json',root=root,minimum_gib=56,stable_seconds=60,
                         read_memory=lambda:next(values),sleep=sleep,clock=lambda:now[0]):
                r=json.loads((root/'admission.json').read_text())
                self.assertEqual(r['status'],'ADMITTED')
                self.assertEqual(r['wait_seconds'],90)
                self.assertEqual(r['stable_seconds'],60)


if __name__=='__main__':unittest.main()
