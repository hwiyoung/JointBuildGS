import json,shutil
import numpy as np
from preflight import C,D,O,Path,dump,sha,now
P=O/'r1/photo_benchmark';S=Path(__file__).parent

def main():
    before={};fields={}
    with np.load(P/'scores_cpu.npz') as a,np.load(P/'scores_cuda.npz') as b:
        for name in ['curves','best_score','texture','texture_by_view']:
            x=a[name];y=b[name];valid=np.isfinite(x)&np.isfinite(y);diff=np.where(valid,abs(x-y),-1);ix=np.unravel_index(np.argmax(diff),diff.shape)
            fields[name]=dict(max_absolute_difference=float(diff[ix]),index=list(map(int,ix)),cpu=float(x[ix]),gpu=float(y[ix]),
                finite_masks_equal=bool(np.array_equal(np.isfinite(x),np.isfinite(y))),quantiles=np.quantile(diff[valid],[.5,.9,.99,1]).tolist())
            if name=='curves':
                k,i,j,h=ix;fields[name].update(texture_cpu=float(a['texture'][k,i,j]),texture_gpu=float(b['texture'][k,i,j]),best_score_cpu=float(a['best_score'][k,i,j]),best_score_gpu=float(b['best_score'][k,i,j]))
    dest=P/'revisions/r0';assert not dest.exists();dest.mkdir(parents=True)
    for name in ['scores_cpu.npz','scores_cuda.npz','timing_cpu.json','timing_cuda.json']:
        p=P/name;before[name]=sha(p);shutil.copy2(p,dest/name)
    for name in ['photo_score.cpu.lock.json','photo_score.cuda.lock.json']:
        shutil.copy2(C/name,dest/name)
    shutil.copy2(S/'photo_score.py',dest/'photo_score.py')
    result=dict(at=now(),status='FAIL_CPU_GPU_PHOTO_PARITY_R0',fields=fields,before_sha256=before,
        required_score_tolerance=2e-5,required_texture_tolerance=2e-4,
        hypothesis='float32 image interpolation/grid and accumulation can amplify CPU/GPU arithmetic differences in low-variance patches; verify by float64 rerun, not by relaxing tolerance',
        scientific_verdict=None)
    dump(dest/'parity_diagnosis.json',result);dump(D/'tables/photo_precision_r0_issue.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
