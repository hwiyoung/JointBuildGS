"""Resource admission only: serialize photo readouts and wait for host RAM."""
from contextlib import ExitStack, contextmanager
import fcntl
import json
from pathlib import Path
import time


def memory_available_gib():
    fields=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(fields['MemAvailable'].split()[0])/1024**2


@contextmanager
def admit(record,root=Path('/o'),minimum_gib=52,read_memory=memory_available_gib,sleep=time.sleep):
    start=time.monotonic()
    with ExitStack() as stack:
        for gpu in [0,1]:
            lock=stack.enter_context((root/'checks'/f'photo_gpu_{gpu}.lock').open('a'))
            fcntl.flock(lock,fcntl.LOCK_EX)
        while True:
            available=read_memory()
            state=dict(status='ADMITTED' if available>=minimum_gib else 'WAITING_FOR_MEMORY',
                available_GiB=available,required_GiB=minimum_gib,wait_seconds=time.monotonic()-start,
                effect='execution scheduling only; no postprocessing parameter change',scientific_verdict=None)
            record.write_text(json.dumps(state,indent=2)+'\n')
            if available>=minimum_gib:break
            sleep(10)
        yield
