"""Exact r7 patch arrays/maps; baseline SfM provenance and unchanged cylinder exclusion."""
import shutil,subprocess,sys
import numpy as np
from plyfile import PlyData
from common import *
def load(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}
def main():
    cfg=json.loads((CFG/'target_v1.r8.json').read_text());lock=json.loads((CFG/'target_v1.r8.lock.json').read_text())
    assert sha(CFG/'target_v1.r8.json')==lock['config_sha256']
    c2,_=locked_r2();site='B173nb_b10'
    for prior in sys.argv[1:] or ['ALS','LoD2']:
        stem=f'{site}_{prior}';old=OUT/'r7/stage1'/stem;root=OUT/'r8/stage1'/stem;root.mkdir(parents=True,exist_ok=True)
        assert not (root/'seed_receipt.json').exists()
        source=S0/'fork_inputs/s61'/site/f'scene_{prior}/sparse/0'
        baseline=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/f'nojudge_{prior}_s0/model/input.ply'
        ply=source/'points3D.ply';assert sha(ply)==sha(baseline),'Baseline source bytes changed'
        v=PlyData.read(str(ply))['vertex'];xyz=np.c_[v['x'],v['y'],v['z']].astype('f4')
        rgb=np.c_[v['red'],v['green'],v['blue']].astype('f4')/255.
        origin=np.load(source/'origin.npy');assert len(origin)==len(xyz) and set(np.unique(origin))<=set([0,1])
        ids=np.flatnonzero(origin==0);positions=xyz[ids];np.save(root/'sfm_original_xyz.npy',positions)
        d=load(OUT/'stage0_r1/inputs'/f'{stem}.npz')
        radius=np.array([c2['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan for k in d['kind']])
        cores=root/'cylinders.bin';np.c_[d['centre'],d['normal'],np.where(d['kind']==1,10.,5.),radius].astype('<f8').tofile(cores)
        assert sha(cores)==sha(OUT/'r2/background'/site/prior/'cylinders.bin')
        binary=root/'exclude_cylinders';cpp=Path(__file__).with_name('exclude_cylinders_r2.cpp')
        subprocess.run(['g++','-O3','-std=c++17',str(cpp),'-o',str(binary)],check=True)
        with (root/'sfm_original_xyz.npy').open('rb') as f:
            version=np.lib.format.read_magic(f);np.lib.format._read_array_header(f,version);offset=f.tell()
        subprocess.run([str(binary),str(root/'sfm_original_xyz.npy'),str(offset),str(len(ids)),str(cores),str(len(radius)),str(root/'excluded.bin')],check=True)
        excluded=np.fromfile(root/'excluded.bin',dtype=np.uint8).astype(bool);kept=ids[~excluded];nb=len(kept)
        s=load(old/'seeds.npz');patch=s['origin']==1;count=int(patch.sum());assert np.array_equal(s['original_xyz'],xyz)
        index=json.loads((old/'maps/index.json').read_text());bg_sigma=float(np.hypot(index['background_u_median'],.0275))
        n=np.zeros((nb,3),'f4');n[:,2]=1;q=np.zeros((nb,4),'f4');q[:,0]=1
        extra=dict(xyz=xyz[kept],target=xyz[kept],normal=n,sigma=np.full(nb,bg_sigma,'f4'),quaternion=q,
            origin=np.zeros(nb,'i1'),region=np.full(nb,4,'i1'),patch=np.full(nb,-1,'i8'),uncertainty_replaced=np.ones(nb,bool))
        result={k:np.concatenate([s[k][patch],v.astype(s[k].dtype)],axis=0) for k,v in extra.items()}
        result.update(original_xyz=s['original_xyz'],keep_original=s['keep_original'],background_rgb=rgb[kept],background_original=kept)
        for k in extra:assert result[k][:count].tobytes()==s[k][patch].tobytes(),k
        np.savez_compressed(root/'seeds.npz',**result)
        shutil.copyfile(OUT/'r7/targets'/f'{stem}.npz',OUT/'r8/targets'/f'{stem}.npz')
        rec=dict(at=stamp(),site=site,prior=prior,config_sha256=lock['config_sha256'],seeds_sha256=sha(root/'seeds.npz'),
            baseline_ply_sha256=sha(baseline),source_ply_sha256=sha(ply),origin_sha256=sha(source/'origin.npy'),
            raw_combined=len(xyz),baseline_prior_removed=int((origin==1).sum()),sfm_candidates=len(ids),cylinder_excluded=int(excluded.sum()),background_kept=nb,prior_kept=count,
            background_source='baseline combined points3D.ply origin==0; exact input.ply bytes verified',
            extra_thinning=False,patch_seed_arrays_byte_identical=True,r7_background_kept=int((~patch).sum()),
            target_sha256=sha(OUT/'r8/targets'/f'{stem}.npz'),exclusion_code_sha256=sha(cpp),cylinders_sha256=sha(cores),
            background_sigma='same-unit/prior target-map substituted sigma; free-background diagnostic only',
            initial_rotation='retained baseline Gaussian random rotation by original source index; diagnostic normal updated from this rotation',scientific_verdict=None)
        dump(root/'seed_receipt.json',rec)
        maps=root/'maps';maps.mkdir(exist_ok=True);newindex=dict(index,at=stamp(),config_sha256=lock['config_sha256'],parent_index_sha256=sha(old/'maps/index.json'),background_weight=1.,views={})
        for j,(name,meta) in enumerate(index['views'].items()):
            p=old/'maps'/meta['file'];assert sha(p)==meta['sha256'];m=load(p);valid=(m['owner']<0)&np.isfinite(m['depth'])&(m['depth']>0)&(m['weight']>0)
            m['weight'][valid]=1.;dest=maps/meta['file'];np.savez_compressed(dest,**m)
            newindex['views'][name]=dict(meta,sha256=sha(dest),parent_sha256=sha(p))
            if (j+1)%40==0:print('R8_MAPS',prior,j+1,flush=True)
        dump(maps/'index.json',newindex);print('R8_INPUTS',prior,rec,flush=True)
if __name__=='__main__':main()
