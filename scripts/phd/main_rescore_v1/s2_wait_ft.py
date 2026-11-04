"""Wait for FINALTRAIN completion receipts via inotify, with no repeated status queries."""
from common import *
import ctypes,os,select,struct,sys
from s2_ft_paths import model_path
site=sys.argv[1];ft=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
lib=ctypes.CDLL('libc.so.6',use_errno=True);lib.inotify_init1.argtypes=[ctypes.c_int];lib.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
fd=lib.inotify_init1(os.O_CLOEXEC);assert fd>=0
pending=set(['ALS','LoD2']);watches={}
for prior in sorted(pending):
    root=ft/'runs'/site/f'ft_{prior}_s0';assert root.is_dir()
    wd=lib.inotify_add_watch(fd,os.fsencode(root),0x00000008|0x00000080)
    assert wd>=0;watches[wd]=prior
def check(prior):
    p=ft/'runs'/site/f'ft_{prior}_s0/receipt.json'
    if not p.exists():return False
    try:r=json.loads(p.read_text())
    except json.JSONDecodeError:return False
    if r.get('status') in ['HEALTH_STOP','NO_RESULT']:
        dump(O/'arrival'/f'{site}__{prior}.json',dict(at=now(),status=r['status'],receipt=str(p),receipt_sha256=sha(p),event_source='inotify terminal receipt; no status polling',scientific_verdict=None))
        print('UNAVAILABLE',site,prior,r['status'],flush=True);return True
    if r.get('status')!='TRAINING_COMPLETE_30000':return False
    model=model_path(r,site,prior)/'point_cloud/iteration_30000/point_cloud.ply'
    assert model.is_file()
    dump(O/'arrival'/f'{site}__{prior}.json',dict(at=now(),status=r['status'],receipt=str(p),receipt_sha256=sha(p),model=str(model),event_source='inotify close_write/moved_to; no status polling',scientific_verdict=None))
    print('READY',site,prior,flush=True);return True
try:
    for prior in list(pending):
        if check(prior):pending.remove(prior)
    while pending:
        select.select([fd],[],[])
        data=os.read(fd,65536);offset=0
        while offset<len(data):
            wd,mask,cookie,n=struct.unpack_from('iIII',data,offset);offset+=16
            name=data[offset:offset+n].split(b'\0',1)[0].decode();offset+=n
            prior=watches.get(wd)
            if name=='receipt.json' and prior in pending and check(prior):pending.remove(prior)
finally:os.close(fd)
