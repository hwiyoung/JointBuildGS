"""Evaluation-only truth positions on new ALS normals and unchanged LoD2 axes."""
import json,time,zipfile,multiprocessing as mp,sys
import numpy as np
from scipy.spatial import cKDTree
from preflight import C,O,Path,sha,dump,now
from geometry import loadz,savez
from prepare import array
import ring_kernel as K
import ring_context as U
BASE=O/'r2';INPUT=O/'r1'

def chunk(ids):return [(int(i),K.one_patch(int(i))[0]) for i in ids]

def cells(d,gt,status):
    prior='ALS' if 'old_normal' in d else 'LoD2';tau=.1266 if prior=='ALS' else .2
    out=np.full(len(gt),6,np.int8);usable=(status==0)&np.isfinite(gt)&np.isfinite(d['prior_height_m'])&np.isfinite(d['normal']).all(1)
    p=abs(d['prior_height_m']-gt)<=tau;m=(d['n']>=4)&np.isfinite(d['mvs_mean_m']);v=abs(d['mvs_mean_m']-gt)<=tau
    out[usable&m&p&v]=0;out[usable&m&~p&v]=1;out[usable&m&p&~v]=2;out[usable&m&~p&~v]=3
    out[usable&~m&p]=4;out[usable&~m&~p]=5
    # Missing prior height/normal is excluded, not relabeled reference absence.
    out[~np.isfinite(d['prior_height_m'])|~np.isfinite(d['normal']).all(1)]=9
    return out

def main(tile_arg=None):
    assert sha(C/'judgecheck_v1.json')==json.loads((C/'judgecheck_v1.reply2.lock.json').read_text())['config_sha256']
    lock=C/'truth.reply2.lock.json'
    if not lock.exists():dump(lock,dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),Path(K.__file__),Path(__file__).parent/'u_core.py']},
        purpose='evaluation cells and target type3 only; never geometry calibration, view selection, thresholds or honest judgment',
        ALS='unchanged UNCERT GT face, minimum support, LMedS validity and median axis position on new normal; original patch RNG index',
        LoD2='reuse original GT positions because core and normal are unchanged',scientific_verdict=None))
    for p in sorted((INPUT/'geometry').glob(f'{tile_arg or "*"}__*.npz')):
        dest=BASE/'truth'/p.name
        if dest.exists():continue
        d=loadz(p);tile,prior=p.stem.split('__');started=time.monotonic();N=len(d['patch_id']);old=loadz(INPUT/'evaluation_inputs'/p.name)
        assert np.array_equal(d['patch_id'],old['patch_id'])
        if prior=='LoD2':gt=old['gt_p'].astype(float);status=old['gt_status'];details={}
        else:
            X=np.load(U.PTS/tile/'gt_xyz.npy').astype(float);tree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False)
            with zipfile.ZipFile(U.W/'holdout/internal/patch_geometry'/f'{tile}_{prior}.npz') as z:ids=array(z,'patch_id')
            lookup={pid:i for i,pid in enumerate(ids)};original=np.array([lookup[pid] for pid in d['patch_id']])
            K.G.update(X=X,tree=tree,c=d['centre'],n=d['normal'],roof=d['kind']==1,data='gt',site=tile,pset=prior,original_index=original)
            gt=np.full(N,np.nan);status=np.full(N,9,np.int8);details={name:np.full(N,np.nan) for name in ['n_col','n_inner','runs','h','nx','ny','nz']}
            ii=np.flatnonzero(np.isfinite(d['normal']).all(1));chunks=[ii[a:a+200] for a in range(0,len(ii),200)];done=0
            with mp.get_context('fork').Pool(4) as pool:
                for rows in pool.imap_unordered(chunk,chunks):
                    for i,r in rows:
                        status[i]=r['status'];gt[i]=r.get('p',np.nan)
                        for name in details:details[name][i]=r.get(name,np.nan)
                    done+=len(rows)
                    if done%5000<200:print('GT_ALS',tile,done,len(ii),'seconds',time.monotonic()-started,flush=True)
            K.G.clear();del X,tree
        cc=cells(d,gt,status)
        savez(dest,patch_id=d['patch_id'],gt_p=gt,gt_status=status,cell=cc,old_cell=old['cell'],**details)
        dump(dest.with_suffix('.json'),dict(at=now(),tile=tile,prior=prior,cores=N,valid_truth=int((status==0).sum()),
            cell_counts={str(k):int((cc==k).sum()) for k in np.unique(cc)},seconds=time.monotonic()-started,
            input_sha256=sha(p),output_sha256=sha(dest),evaluation_only=True,scientific_verdict=None))
        print('GT_DONE',tile,prior,N,time.monotonic()-started,flush=True)

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else None)
