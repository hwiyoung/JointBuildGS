"""Publish input byte pins and software versions, with no sealed point or outcome values."""
from common import *
def main():
    pre=load(O/'input_preflight.json');files=set(Path(x) for x in pre['sources']);files.add(RAW/'raw/uav/Images.zip')
    for sealed in [False,True]:
        for f in (paths(sealed)/'geometry').glob('*__*.json'):
            r=load(f);files.add(W/('holdout/patch_values' if sealed else 'patch_values')/f'{r["tile"]}__{r["prior"]}__R1.5.npz')
    for t in load(W/'inputs/tiles.json'):
        for prior in ['LoD2','ALS']:
            files.add(W/'holdout/internal/prior_tiles'/t['id']/('lod2_mesh.npz' if prior=='LoD2' else 'als_mesh.npz'))
            files.add(W/'holdout/internal/registration'/t['id']/prior/'summary.json')
    records=[]
    for f in sorted(files):
        records.append(dict(file=str(f),bytes=f.stat().st_size,sha256=sha(f)))
    result=dict(at=now(),task_id='PHD-MAIN-PHOTOCHECK-v1',train_images=pre['train_images'],max_pose_difference=pre['max_pose_difference'],image_size=[pre['width'],pre['height']],camera_model='FULL_OPENCV',versions=pre['versions'],docker_image=pre['environment']['image'],inputs=records,source_policy='Inputs were mounted read-only for every project process. Hashes identify the bytes used and preserved at handover; no sealed point values or judgments are included.',scientific_verdict=None)
    dump(O/'input_hashes.json',result);dump(D/'provenance/inputs.json',result)
    names=sorted(load(W/'image_split.json')['train']);dump(D/'provenance/training_images.json',dict(images=names,indexing='zero based; selected_images indexes this list',scientific_verdict=None))
    print('input hashes recorded',len(records))
if __name__=='__main__':main()
