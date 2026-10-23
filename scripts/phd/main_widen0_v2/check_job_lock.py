"""Verify two simultaneous launchers execute one identical numerical job once."""
from pathlib import Path
import multiprocessing as mp
import tempfile
import time
import numpy as np
import u_worker as W
from preflight import dump
root=Path(tempfile.mkdtemp(prefix='job_lock_check_',dir='/out/tmp'));W.U.WORK=root
ctx=mp.get_context('fork');start=ctx.Event()
def fake(site,pset,data,radii,workers,limit):
    with (root/'calls.txt').open('a') as f:f.write('one\n')
    time.sleep(.2)
    np.savez(root/f'gt_{site}_{pset}.npz',status=np.array([0,1],np.int8))
    W.U.jdump(root/f'run_gt_{site}_{pset}.json',dict(patches=2,env=W.U.env()))
W.run=fake
def call():
    start.wait();W.run_locked('lock_test','LoD2','gt',[],1)
ps=[ctx.Process(target=call) for _ in range(2)]
for p in ps:p.start()
start.set()
for p in ps:p.join();assert p.exitcode==0
assert (root/'calls.txt').read_text()=='one\n'
dump('/out/gates/job_lock.json',dict(status='PASS',simultaneous_launchers=2,executions=1,
    test_directory=str(root),scientific_verdict=None))
print('duplicate job lock PASS: two launchers, one execution')
