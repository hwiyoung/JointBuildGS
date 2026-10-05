import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

MODULE = Path(__file__).resolve().parents[3] / 'scripts/phd/geogs_p1p2p3_v1/resource_schedule.py'
spec = importlib.util.spec_from_file_location('geogs_resource_schedule', MODULE)
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


class ResourceSchedulingTests(unittest.TestCase):
    def test_non_extraction_never_opens_lock(self):
        for phase in ('train', 'parity', 'metrics'):
            handle, receipt = scheduler.acquire_extraction_lock(phase, '/missing/task/lock')
            self.assertIsNone(handle)
            self.assertFalse(receipt['serialized_extraction'])
            self.assertEqual(receipt['wait_seconds'], 0.0)

    @unittest.skipUnless(os.environ.get('JBGS_TEST_SHARED_LOCK'), 'Actual read-only bind lock required')
    def test_readonly_shared_inode_blocks_then_releases_another_process(self):
        path = Path(os.environ['JBGS_TEST_SHARED_LOCK'])
        before = path.read_bytes()
        held, _ = scheduler.acquire_extraction_lock('auxiliary', path)
        program = ('import json,sys; from resource_schedule import acquire_extraction_lock; '
                   'print("READY", flush=True); '
                   'handle,receipt=acquire_extraction_lock("render",sys.argv[1]); '
                   'print(json.dumps(receipt),flush=True)')
        env = dict(os.environ, PYTHONPATH=str(MODULE.parent))
        child = subprocess.Popen([sys.executable, '-c', program, str(path)], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'READY')
            time.sleep(.2)
            self.assertIsNone(child.poll(), 'Second extraction bypassed the held lock')
            fcntl.flock(held.fileno(), fcntl.LOCK_UN)
            held.close()
            output, error = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, error)
            receipt = json.loads(output)
            self.assertGreaterEqual(receipt['wait_seconds'], .15)
            self.assertTrue(receipt['wait_excluded_from_native_phase_wall_seconds'])
            self.assertEqual(receipt['lock_open_mode'], 'rb')
        finally:
            if not held.closed:
                held.close()
            if child.poll() is None:
                child.kill()
                child.communicate()
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
