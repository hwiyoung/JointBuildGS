"""Single-height, clipped-only scoring using the verified float64 GPU/CPU kernel."""
from common import *
from cameras import Cameras
from inherit import functions
import ast,torch,resource,collections
import torch.nn.functional as F
from numpy.core import _multiarray_umath as memory
def main(device,site):
    assert device in ['cuda','cpu'];c=cfg();memory._set_madvise_hugepage(False);assert not memory._get_madvise_hugepage()
    upstream=R/'configs/phd/main_judgecheck_v1/photo_stream.reply2.lock.json';lock=json.loads(upstream.read_text())
    for name in ['photo_score_reply2.py','photo_stream_cache_reply2.py','photo_cameras.py']:
        assert sha(HERE/'inherited'/name)==lock['sources'][name]
    g=loadz(O/'photo_prepared'/f'{site}.npz');scope=dict(np=np,torch=torch,F=F,time=time,resource=resource,collections=collections,BASE=O,now=now,Path=Path,sha=sha,dump=dump)
    functions('photo_score.py',['project','ncc_vectors'],scope)
    cache,=functions('photo_stream_cache_reply2.py',['StreamImageCache'],scope);scope.update(ImageCache=cache,Cameras=lambda:Cameras(site))
    p=HERE/'inherited/photo_score_reply2.py';tree=ast.parse(p.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='score')
    # Remove only the untrimmed comparison, explicitly cancelled by order 0.2.
    for n in ast.walk(node):
        if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='mode':n.iter=ast.Call(func=ast.Name(id='range',ctx=ast.Load()),args=[ast.Constant(1)],keywords=[])
    node=ast.fix_missing_locations(node);exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),scope)
    root=O/'photo_scores'/site;root.mkdir(parents=True,exist_ok=True)
    result,timing=scope['score'](g,root,device=device,chunk_rows=900000,batch_rows=8192 if device=='cuda' else 1024)
    # Every represented candidate has exactly one height, zero relative to its
    # r-shifted prior or fitted MVS plane. No maximum over distinct heights.
    assert np.all(g['row_height']==0) and np.all(np.diff(g['plane_row_ptr'])<=1)
    out=dict(point_id=g['point_id'],score=result['best_score'][0],texture=result['texture'][0],texture_by_view=result['texture_by_view'][0],pyramid_levels=result['pyramid_levels'])
    count=np.zeros(2*len(g['point_id']),np.uint8);count[g['row_plane']]=result['valid_image_count'][0];out['valid_image_count']=count.reshape(-1,2)
    savez(root/'scores.npz',**out)
    timing.update(at=now(),site=site,device=device,gpu_wait_seconds=0,raw_jpeg=True,cache_budget_gib=4,numpy_hugepage_advice=False,height_sweep=False,trimmed_only=True,upstream_stream_lock_sha256=sha(upstream),output_sha256=sha(root/'scores.npz'))
    dump(root/'complete.json',timing);dump(O/'timing'/f'{site}_photo_score.json',timing)
    progress(f'{site} 광도 일관성 점수 완료: {device}, {timing["total_seconds"]:.1f}초, 사진 읽기 {timing["decode_seconds"]:.1f}초, GPU 대기 0초.')
    print('SCORE_COMPLETE',json.dumps(timing),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
