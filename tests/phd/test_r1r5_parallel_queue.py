"""Resource admission and adopted-container lifecycle checks, without a real GPU."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, '/repo/scripts/phd/r1r5_comparison_v1')
from parallel_queue import Manager, MemorySlots
from resume_parallel import gpu_admissible


class SchedulerTests(unittest.TestCase):
    def test_gpu0_allows_desktop_but_excludes_competing_compute_and_low_memory(self):
        display=['/usr/libexec/gnome-remote-desktop-daemon']
        self.assertTrue(gpu_admissible(24000,40,display,0))
        self.assertTrue(gpu_admissible(24000,40,display+['/usr/share/rustdesk/rustdesk'],0))
        self.assertFalse(gpu_admissible(24000,0,display+['python'],0))
        self.assertFalse(gpu_admissible(22000,0,display,0))
        self.assertFalse(gpu_admissible(24000,30,[],1))
        self.assertTrue(gpu_admissible(24000,0,[],1))

    def test_two_trainers_fit_but_extraction_waits_for_both(self):
        slots = MemorySlots()
        slots.acquire(32)
        entered = threading.Event()
        def extract():
            slots.acquire(56)
            entered.set()
            slots.release(56)
        thread = threading.Thread(target=extract, daemon=True)
        thread.start()
        self.assertFalse(entered.wait(.03))
        slots.release(32)
        self.assertFalse(entered.wait(.03))
        slots.release(32)
        self.assertTrue(entered.wait(1))
        thread.join(1)
        self.assertEqual(slots.used, 0)

    def test_pending_extraction_has_priority_over_new_training(self):
        slots = MemorySlots()
        order = []
        def job(size):
            slots.acquire(size)
            order.append(size)
            slots.release(size)
        extract = threading.Thread(target=job, args=(56,), daemon=True)
        extract.start()
        for _ in range(100):
            with slots.cv:
                if slots.pending:
                    break
            time.sleep(.001)
        train = threading.Thread(target=job, args=(32,), daemon=True)
        train.start()
        slots.release(32)
        extract.join(1)
        train.join(1)
        self.assertEqual(order, [56, 32])

    def test_adopt_waits_for_container_before_retiring_parent_and_extracting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'R3/da3').mkdir(parents=True)
            (root / 'R3/da3/receipt.json').write_text(json.dumps(dict(status='PASS', exit_code=0)))
            manager = Manager.__new__(Manager)
            manager.root = manager.folder = root
            manager.plan = dict(old_unit='old.service', adopted_started_unix=0)
            manager.memory = MemorySlots()
            manager.fail = Mock()
            worker = Mock(records=[])
            events = []
            states = iter([True, False])
            def running():
                value = next(states)
                events.append(('container', value))
                return value
            def command(argv, **kwargs):
                events.append(('command', argv[0]))
                if argv[0] == 'systemctl':
                    self.assertEqual(events[-2], ('container', False))
                    self.assertIn('--kill-who=main', argv)
            manager.container_running = running
            with patch('parallel_queue.subprocess.run', side_effect=command), patch('parallel_queue.time.sleep'):
                manager.finish_adopted(worker)
            self.assertEqual(manager.memory.used, 0)
            self.assertTrue(worker.records[0]['adopted'])
            worker.stage.assert_called_once()
            manager.fail.assert_not_called()

    def test_failed_adopted_stage_never_extracts(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = Manager.__new__(Manager)
            manager.root = manager.folder = Path(temp)
            manager.plan = dict(old_unit='old.service', adopted_started_unix=0)
            manager.memory = MemorySlots()
            manager.container_running = lambda: False
            manager.fail = Mock()
            worker = Mock(records=[])
            with patch('parallel_queue.subprocess.run'):
                manager.finish_adopted(worker)
            worker.stage.assert_not_called()
            self.assertEqual(worker.records[0]['status'], 'FAILED')
            manager.fail.assert_called_once()
            self.assertEqual(manager.memory.used, 0)


if __name__ == '__main__':
    unittest.main()
