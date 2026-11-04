"""Install the verified pixel cache around the unchanged photo arithmetic."""
import json,sys
import photo_score_reply2 as P
import photo_score_group_reply2 as G
import photo_stream_cache_reply2 as S
from numpy.core import _multiarray_umath as memory
from preflight import C,O,Path,sha,dump,now
from record_setting_reply2 import record

def sources():
    return {p.name:sha(p) for p in [Path(P.__file__),Path(G.__file__),Path(S.__file__),Path(__file__),Path(__file__).with_name('photo_cameras.py')]}

def setup():
    verification=O/'r2/stream_verification/complete.json';v=json.loads(verification.read_text())
    assert v['status']=='PASS_STREAM_CACHE_200_POINT_SCORE_PARITY'
    assert v['numpy_hugepage_advice'] is False
    assert v['memory_gate_sha256']==sha(O/'r2/array_memory_benchmark.json')
    current=sources()
    for name in ['photo_score_reply2.py','photo_stream_cache_reply2.py','photo_cameras.py']:
        assert current[name]==v['sources'][name],name
    value=dict(policy='read compact original JPEG on cache miss; identical grayscale/pyramid bytes and unchanged float64 score; 4 GiB process LRU reused between tiles',
               numerical_kernel_changed=False,numpy_hugepage_advice=False,host_kernel_configuration_changed=False,
               memory_gate_sha256=v['memory_gate_sha256'],verification_sha256=sha(verification),sources=current,
               timing='JPEG decode is deferred to get() and included in upload_seconds; cache preparation only indexes requested levels',
               completed_results='retain all completed scores; apply only to pending tiles')
    record('execution','stream_photo_cache',value,'Eight images showed large NPY read/copy overhead; a separate same-byte copy probe also isolated process-local NumPy huge-page advice overhead (on/off/off/on 10.839/0.068/0.061/0.552s). Use compact JPEG and disable only this process advice, preserving completed results and float64 math; 200-point all-curve parity passed with both changes before adoption')
    dump(C/'photo_stream.reply2.lock.json',dict(at=now(),sources=current,verification_sha256=sha(verification),config_sha256=sha(C/'judgecheck_v1.json'),scientific_verdict=None))
    print('STREAM_CACHE_LOCKED',flush=True)

def install():
    lock=json.loads((C/'photo_stream.reply2.lock.json').read_text());assert lock['sources']==sources()
    assert lock['verification_sha256']==sha(O/'r2/stream_verification/complete.json')
    memory._set_madvise_hugepage(False)
    assert not memory._get_madvise_hugepage()
    P.ImageCache=S.StreamImageCache
    original=P.score
    def score(*args,**kwargs):
        result,timing=original(*args,**kwargs)
        timing.update(image_supply='original JPEG with 4 GiB process LRU',numpy_hugepage_advice=False,stream_lock_sha256=sha(C/'photo_stream.reply2.lock.json'),
                      stream_sources=lock['sources'],image_supply_timing='decode included in upload_seconds; prepare is level indexing only')
        return result,timing
    P.score=score

def main(arg,device='cuda'):
    if arg=='setup':setup();return
    install();G.main(arg,device)

if __name__=='__main__':main(*sys.argv[1:])
