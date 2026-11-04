"""Consume the existing completion watcher's receipts; no training-status polling."""
from common import *
import ctypes, select, struct, sys

site=sys.argv[1]
root=O/'arrival';root.mkdir(exist_ok=True)
lib=ctypes.CDLL('libc.so.6',use_errno=True)
lib.inotify_init1.argtypes=[ctypes.c_int]
lib.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
fd=lib.inotify_init1(os.O_CLOEXEC);assert fd>=0
assert lib.inotify_add_watch(fd,os.fsencode(root),0x8|0x80)>=0
pending={'ALS','LoD2'}
def ready(prior):
    p=root/f'{site}__{prior}.json'
    if not p.exists():return False
    try:r=json.loads(p.read_text())
    except json.JSONDecodeError:return False
    status=r['status']
    if status not in ['TRAINING_COMPLETE_30000','HEALTH_STOP','NO_RESULT']:return False
    print('READY' if status=='TRAINING_COMPLETE_30000' else 'UNAVAILABLE',site,prior,flush=True)
    return True
try:
    for prior in sorted(pending):
        if ready(prior):pending.remove(prior)
    while pending:
        select.select([fd],[],[])
        data=os.read(fd,65536);offset=0
        while offset<len(data):
            wd,mask,cookie,n=struct.unpack_from('iIII',data,offset);offset+=16
            name=data[offset:offset+n].split(b'\0',1)[0].decode();offset+=n
            for prior in sorted(pending):
                if name==f'{site}__{prior}.json' and ready(prior):pending.remove(prior)
finally:os.close(fd)
