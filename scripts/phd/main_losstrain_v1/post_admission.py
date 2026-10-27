"""Resource admission only: serialize photo readouts and wait for host RAM."""
from contextlib import ExitStack, contextmanager
import fcntl
import json
import os
from pathlib import Path
import time


def memory_available_gib():
    fields=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(fields['MemAvailable'].split()[0])/1024**2


@contextmanager
def admit(record,root=Path('/o'),minimum_gib=64,stable_seconds=60,read_memory=memory_available_gib,sleep=time.sleep,clock=time.monotonic):
    start=clock();stable_since=None
    with ExitStack() as stack:
        for gpu in [0,1]:
            lock=stack.enter_context((root/'checks'/f'photo_gpu_{gpu}.lock').open('a'))
            fcntl.flock(lock,fcntl.LOCK_EX)
        while True:
            available=read_memory()
            if available<minimum_gib:stable_since=None
            elif stable_since is None:stable_since=clock()
            stable=0 if stable_since is None else clock()-stable_since
            admitted=available>=minimum_gib and stable>=stable_seconds
            state=dict(status='ADMITTED' if admitted else 'WAITING_FOR_MEMORY',
                attempt=int(os.environ['JBGS_LT_POST_ATTEMPT']) if 'JBGS_LT_POST_ATTEMPT' in os.environ else None,
                available_GiB=available,required_GiB=minimum_gib,wait_seconds=clock()-start,
                stable_seconds=stable,required_stable_seconds=stable_seconds,
                effect='execution scheduling only; no postprocessing parameter change',scientific_verdict=None)
            record.write_text(json.dumps(state,indent=2)+'\n')
            if admitted:break
            sleep(10)
        yield
