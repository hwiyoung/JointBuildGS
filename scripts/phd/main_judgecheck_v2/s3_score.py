"""광도 점수 (JUDGEAPPLY-v1 score.py 그대로: 상속 photo_score_reply2.score 의 자르지 않은 판 반복만 뺌, 높이 하나, float64).
카메라만 캠퍼스(WIDEN0 학습 819장, photo_cameras.Cameras). 원본 JPEG, 4 GiB 캐시, NumPy 큰 페이지 요청 끔.  s3_score.py <cuda|cpu> <tile>"""
from common import *
from inherit import functions
import ast, torch, resource, collections
import torch.nn.functional as F
from numpy.core import _multiarray_umath as memory
sys.path.insert(0, str(HERE/'inherited'))
from photo_cameras import Cameras
def main(device, tile):
    assert device in ['cuda', 'cpu']; cfg(); memory._set_madvise_hugepage(False); assert not memory._get_madvise_hugepage()
    root = O/'photo_scores'/tile
    if (root/'complete.json').exists(): return
    lock = json.loads((R/'configs/phd/main_judgecheck_v1/photo_stream.reply2.lock.json').read_text())
    for name in ['photo_score_reply2.py', 'photo_stream_cache_reply2.py', 'photo_cameras.py']: assert sha(HERE/'inherited'/name) == lock['sources'][name]
    pp = O/'photo_prepared'/f'{tile}.npz'
    if not pp.exists(): print('NO_PREPARED', tile); return
    g = loadz(pp); scope = dict(np=np, torch=torch, F=F, time=time, resource=resource, collections=collections, BASE=O, now=now, Path=Path, sha=sha, dump=dump)
    functions('photo_score.py', ['project', 'ncc_vectors'], scope)
    cache, = functions('photo_stream_cache_reply2.py', ['StreamImageCache'], scope); scope.update(ImageCache=cache, Cameras=Cameras)
    p = HERE/'inherited/photo_score_reply2.py'; tree = ast.parse(p.read_text()); node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'score')
    for n in ast.walk(node):
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == 'mode': n.iter = ast.Call(func=ast.Name(id='range', ctx=ast.Load()), args=[ast.Constant(1)], keywords=[])
    node = ast.fix_missing_locations(node); exec(compile(ast.Module(body=[node], type_ignores=[]), str(p), 'exec'), scope)
    root.mkdir(parents=True, exist_ok=True); t0 = time.monotonic()
    result, timing = scope['score'](g, root, device=device, chunk_rows=900000, batch_rows=8192 if device == 'cuda' else 1024)
    assert np.all(g['row_height'] == 0) and np.all(np.diff(g['plane_row_ptr']) <= 1)
    out = dict(point_id=g['point_id'], score=result['best_score'][0], texture=result['texture'][0], texture_by_view=result['texture_by_view'][0], pyramid_levels=result['pyramid_levels'])
    count = np.zeros(2*len(g['point_id']), np.uint8); count[g['row_plane']] = result['valid_image_count'][0]; out['valid_image_count'] = count.reshape(-1, 2)
    savez(root/'scores.npz', **out)
    timing.update(at=now(), tile=tile, device=device, raw_jpeg=True, cache_budget_gib=4, numpy_hugepage_advice=False, height_sweep=False, trimmed_only=True, wall_seconds=time.monotonic()-t0)
    dump(root/'complete.json', timing); print('SCORE_COMPLETE', tile, device, round(timing.get('total_seconds', 0)), flush=True)
if __name__ == '__main__': main(*sys.argv[1:])
