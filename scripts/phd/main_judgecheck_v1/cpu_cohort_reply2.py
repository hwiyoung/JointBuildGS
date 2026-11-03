"""Two bounded CPU readers around the unchanged, whole-tile-verified score kernel."""
import fcntl,json,sys
from contextlib import contextmanager
import photo_score_reply2 as P
import photo_score_group_reply2 as G
from preflight import C,D,O,Path,sha,dump,now
from record_setting_reply2 import record
BASE=O/'r2'

@contextmanager
def locked(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        yield

def main(action,group,argument=''):
    group=int(group);root=BASE/'cpu_cohorts'/f'group{group}';root.mkdir(parents=True,exist_ok=True)
    if action=='setup':
        # The existing worker has already finished cache preparation. Only its
        # arithmetic continues while the first additional worker starts.
        active_tile=argument
        sources={p.name:sha(p) for p in [Path(P.__file__),Path(G.__file__)]}
        assert json.loads((C/'photo_group.reply2.lock.json').read_text())['sources']==sources
        tiles=(BASE/f'census_group{group}_tiles.txt').read_text().splitlines()
        remaining=[tile for tile in tiles if tile!=active_tile and not (BASE/'photo_scores'/tile/'complete.json').exists() and not (BASE/'photo_scores'/tile/f'group{group}'/'complete.json').exists()]
        setting=dict(workers=2,cpu_quota_each=4,memory_gib_each=28,nice=19,minimum_available_gib_before_launch=36,
            cache_preparation='exclusive task lock; unchanged ImageCache.prepare',
            numerical_kernel='unchanged float64 score and group sources; same 600000/1024 rows',
            order='one prior/kind only; both workers join before judgments; walls require roof commit')
        if group==2:
            assert (BASE/'reports/roof_commit.json').exists()
            assert (C/'photo_stream.reply2.lock.json').exists()
            setting.update(cache_preparation='exclusive lock for level indexing only; read-only JPEG supply in each worker with 4 GiB LRU; no shared image writes',
                           numpy_hugepage_advice=False,stream_lock_sha256=sha(C/'photo_stream.reply2.lock.json'),
                           device_choice='bounded CPU queue selected while another research GPU task is active; choice retained until both workers join')
        record('execution','bounded_cpu_photo_cohort',setting,'Use two bounded CPU workers for independent tiles while another research task uses the GPU. Preserve numerical kernels and completed results. Roofs used serialized NPY preparation; subsequent walls use the verified JPEG cache and process-local memory advice setting, with a short lock around level indexing only')
        dump(root/'plan.json',dict(at=now(),group=group,active_tile_excluded=active_tile,
            assignments=[remaining[::2],remaining[1::2]],kernel_sources=sources,
            wrapper_sha256=sha(Path(__file__)),config_sha256=sha(C/'judgecheck_v1.json'),settings=setting,scientific_verdict=None))
        dump(D/'tables'/f'reply2_cpu_cohort_group{group}.json',json.loads((root/'plan.json').read_text()))
        print('CPU_COHORT_PLAN',group,len(remaining),flush=True);return
    plan=json.loads((root/'plan.json').read_text())
    assert plan['kernel_sources']=={p.name:sha(p) for p in [Path(P.__file__),Path(G.__file__)]}
    if action=='worker':
        if group==2:
            from photo_stream_score_reply2 import install
            assert plan['settings']['stream_lock_sha256']==sha(C/'photo_stream.reply2.lock.json')
            install()
        worker=int(argument);original=P.ImageCache.prepare
        def prepare(cache,levels):
            with locked(BASE/'image_cache/preparation.lock'):return original(cache,levels)
        P.ImageCache.prepare=prepare
        finished=[]
        for tile in plan['assignments'][worker]:
            with locked(BASE/'photo_scores'/tile/f'group{group}.lock'):
                G.main(f'{tile}:{group}','cpu')
            finished.append(tile)
            dump(root/f'worker{worker}.progress.json',dict(at=now(),finished=finished,scientific_verdict=None))
        dump(root/f'worker{worker}.complete.json',dict(at=now(),tiles=finished,scientific_verdict=None))
        print('CPU_COHORT_WORKER_COMPLETE',group,worker,len(finished),flush=True)
    elif action=='verify':
        for tile in sum(plan['assignments'],[]):
            assert (BASE/'photo_scores'/tile/f'group{group}'/'complete.json').exists(),tile
        dump(root/'complete.json',dict(at=now(),status='PASS_CPU_COHORT_COMPLETE',tiles=sum(plan['assignments'],[]),kernel_sources=plan['kernel_sources'],scientific_verdict=None))
        print('CPU_COHORT_COMPLETE',group,flush=True)
    else:raise ValueError(action)

if __name__=='__main__':main(*sys.argv[1:])
