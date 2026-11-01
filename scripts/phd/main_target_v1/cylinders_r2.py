"""Reuse exact saved H10/H5 queries; recompute only failed faces with the locked repair."""
import sys, subprocess
import numpy as np
from common import *
from cylinder_runtime import run


def repair(points,d,stats,ridx,hidx,root,binary):
    bad=(stats[:,0]<4)&(stats[:,6]>=4)
    if bad.any():
        f=root.with_suffix('.repair.bin')
        run(points,d['centre'][bad],d['normal'][bad],f,binary)
        a=np.memmap(f,dtype='<f8',mode='r',shape=(int(bad.sum()),3,10,7))
        updated=np.array(a[np.arange(bad.sum()),hidx[bad],ridx[bad]])
        assert np.array_equal(updated[:,6],stats[bad,6]),'raw column changed'
        stats[bad]=updated
    return stats,bad


def main():
    cfg,lock=locked_r2();mode=sys.argv[1]
    binary=OUT/'r2/cylinders';src=Path(__file__).with_name('cylinders_r2.cpp')
    assert sha(src)==cfg['cylinder']['fallback']['source_sha256']
    if not binary.exists():
        subprocess.run(['g++','-O3','-std=c++17',str(src),'-o',str(binary)],check=True)
    if mode=='experiment':
        for site in cfg['sites']+cfg['deferred_sites']:
            source=(OUT/'b173_uncert_r1' if site=='B173_b0' else UN)
            for prior in cfg['priors']:
                key=f'{site}_{prior}';root=OUT/'r2/stage0/cylinders'/key;root.parent.mkdir(parents=True,exist_ok=True)
                dest=root.with_suffix('.selected.npz')
                if dest.exists():continue
                with np.load(OUT/'stage0_r1/inputs'/f'{key}.npz') as z:d={k:z[k] for k in ['centre','normal','kind']}
                old=OUT/'stage0_r1/cylinders'/key
                with np.load(old.with_suffix('.selected.npz')) as z:ridx=z['radius_index'];unavailable=z['unavailable_radius']
                hidx=np.where(d['kind']==1,2,0)
                a=np.memmap(old.with_suffix('.bin'),dtype='<f8',mode='r',shape=(len(ridx),3,10,7))
                stats=np.array(a[np.arange(len(ridx)),hidx,ridx]);before=stats.copy()
                stats,bad=repair(source/'points'/site/'mvs_a_xyz.npy',d,stats,ridx,hidx,root,binary)
                stats[unavailable]=np.nan;stats[unavailable,0]=-1
                np.savez_compressed(dest,stats=stats,before_repair=before,repair_attempted=bad,radius_index=ridx,unavailable_radius=unavailable)
                dump(dest.with_suffix('.json'),dict(at=stamp(),config_sha256=lock['config_sha256'],sha256=sha(dest),repair_attempts=int(bad.sum()),scientific_verdict=None))
                print('EXPERIMENT_REPAIRED',key,int(bad.sum()),flush=True)
    else:
        sealed=mode=='holdout';jn=JN/'holdout' if sealed else JN
        output=OUT/('holdout/r2/core_stats' if sealed else 'r2/stage0/core_stats');output.mkdir(parents=True,exist_ok=True)
        for receipt in sorted((jn/'cylinders').glob('*.complete.json')):
            tile=receipt.name.split('.')[0];rec=json.loads(receipt.read_text())
            sources=[];pieces=[];statsall=[];radii=[];lengths=[]
            total=sum(p['count'] for p in rec['parts'])
            a=np.memmap(jn/'cylinders'/f'{tile}.bin',dtype='<f8',mode='r',shape=(total,3,10,7))
            for part in rec['parts']:
                name=Path(part['file']).name;f=jn/'core_points'/name
                if (output/name).exists():continue
                with np.load(f) as z:d={k:z[k] for k in ['patch_id','centre','normal','kind']}
                assert len(d['kind'])==part['count']
                prior=f.stem.split('__')[1];chosen=cfg['inherited_radius'][prior]
                ridx=np.array([chosen[str(int(k))]['radius_index'] for k in d['kind']]);hidx=np.where(d['kind']==1,2,0)
                stats=np.array(a[part['start']+np.arange(part['count']),hidx,ridx])
                sources.append((name,len(ridx)));pieces.append(d);statsall.append(stats);radii.append(ridx);lengths.append(hidx)
            if not sources:continue
            d={k:np.concatenate([p[k] for p in pieces]) for k in pieces[0]}
            stats=np.concatenate(statsall);before=stats.copy();ridx=np.concatenate(radii);hidx=np.concatenate(lengths)
            source=json.loads((jn/'cylinders'/f'{tile}.json').read_text())['command'][1]
            stats,bad=repair(Path(source),d,stats,ridx,hidx,output/tile,binary)
            start=0
            for name,count in sources:
                sl=slice(start,start+count);dest=output/name
                np.savez_compressed(dest,patch_id=d['patch_id'][sl],stats=stats[sl],before_repair=before[sl],repair_attempted=bad[sl])
                start+=count
            print('CORE_REPAIRED',mode,tile,len(stats),int(bad.sum()),flush=True)
        dump(output/'complete.json',dict(at=stamp(),status='COMPLETE',config_sha256=lock['config_sha256'],scientific_verdict=None))


if __name__=='__main__':main()
