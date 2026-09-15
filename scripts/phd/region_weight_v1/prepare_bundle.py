"""Bind accepted all-view annotations, source, exact anchors, and viewer config."""
import json
import hashlib
from pathlib import Path
import shutil
import time
import numpy as np
from prepare_source import prepare


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    return h.hexdigest()


def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False)


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    out=Path('/output');repo=Path('/repo');spec=json.loads((repo/'configs/phd/region_weight_v1/experiment_v1.json').read_text())
    parent=json.loads(Path('/parent_config.json').read_text())
    if sha('/parent_config.json')!=spec['parent_config_sha256']:raise ValueError('Parent config changed')
    shutil.copytree(repo/'scripts/phd/region_weight_v1',out/'scripts')
    (out/'parent_scripts').mkdir();(out/'legacy_scripts').mkdir()
    for name in ('run_phase.py','finalize.py'):shutil.copyfile(repo/'scripts/phd/geogs_mvs_pgsr_v1'/name,out/'parent_scripts'/name)
    shutil.copyfile(repo/'scripts/phd/geogs_p1p2p3_v1/parse_extraction.py',out/'legacy_scripts/parse_extraction.py')
    shutil.copyfile(repo/'scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py',out/'scripts/export_geometry.py')
    (out/'implementation').mkdir()
    shutil.copyfile(repo/'src/phd/region_weight_v1/loss.py',out/'implementation/loss.py')
    shutil.copyfile(repo/'src/phd/p1_single_view_weight_v1/loss.py',out/'implementation/core_loss.py')
    shutil.copyfile(repo/'scripts/phd/p1_single_view_weight_v1/prepare_source.py',out/'implementation/base_preparer.py')
    shutil.copyfile(repo/'tests/phd/test_region_weight_v1.py',out/'implementation/test_region_weight_v1.py')
    spec.update(created_unix=time.time(),repository_head=Path('/repository_head.txt').read_text().strip())
    write(out/'config.json',spec)
    source=prepare('/parent_source',out/'source',repo)
    summaries=[]
    for region in spec['regions']:
        folder=out/region;folder.mkdir();(folder/'mask').mkdir()
        annotation=Path('/annotations_'+region)
        if sha(annotation/'receipt.json')!=spec['annotation_receipts'][region]:raise ValueError('Accepted annotation differs')
        receipt=json.loads((annotation/'receipt.json').read_text());cfg=receipt['config']
        binding_path=Path('/mvs_'+region+'/bindings.json')
        if sha(binding_path)!=cfg['binding_sha256']:raise ValueError('MVS binding changed')
        binding=json.loads(binding_path.read_text()); ledger={r['path']:r['sha256'] for r in receipt['outputs']}; masks=[]
        for row,view in zip(receipt['views'],binding['train'],strict=True):
            if row['name']!=view['name']:raise ValueError('Mask camera order differs')
            rel=row['folder']+'/rgb_masks.npz'; original=annotation/rel
            if sha(original)!=ledger[rel]:raise ValueError('Mask source changed')
            with np.load(original,allow_pickle=False) as arrays:
                labels=arrays['region_id'];valid=arrays['valid'];used=np.isin(labels,[1,2,3])
                if valid.dtype!=np.bool_ or np.any(used&~valid):raise ValueError('Invalid support')
                r1=int((labels==1).sum());use=int(used.sum())
            name=f'{row["train_index"]:03d}.npz';shutil.copyfile(original,folder/'mask'/name)
            masks.append(dict(camera=Path(row['name']).stem,path=name,sha256=ledger[rel],r1_pixels=r1,used_pixels=use))
        write(folder/'mask/manifest.json',dict(schema='JBGS_REGION_MASK_MANIFEST_v1',region=region,
            binding_sha256=cfg['binding_sha256'],annotation_receipt_sha256=spec['annotation_receipts'][region],
            annotation_config_sha256=receipt['config_sha256'],views=masks,scientific_verdict=None))
        anchor=parent['anchors'][region]
        if sha('/anchor_'+region+'/checkpoint.pth')!=anchor['sha256']:raise ValueError('Anchor changed')
        regional=dict(spec,region=region,binding_sha256=cfg['binding_sha256'],anchor_sha256=anchor['sha256'],
            anchor_relative=anchor['relative'],mask_sha256=sha(folder/'mask/manifest.json'),
            training_rgb_views=len(masks),training_depth_views=len(masks),
            resource_gpu=0 if region=='P2' else 1)
        write(folder/'config.json',regional)
        extraction=json.loads(Path('/extraction_'+region+'.json').read_text())['realized_extraction']
        expected={k:extraction[k] for k in ('mesh_res','num_cluster','voxel_size_m','sdf_trunc_m','depth_trunc_m')}
        roi=cfg['evaluation_roi'];context=cfg['training_context']
        viewer=dict(task_id=spec['task_id'],region=region,scientific_verdict=None,
            config_sha256=sha(folder/'config.json'),mask_sha256=regional['mask_sha256'],anchor_sha256=anchor['sha256'],
            url_prefix='/data/p2p3_weights_v1/'+region+'/',point_cap=200000,
            depth_range_m=spec['viewer_depth_ranges_m'][region],expected_extraction=expected,
            views=[dict(id='source_'+str(s['train_index']),split='train',name=s['name']) for s in cfg['manual_sources']],
            regions=[dict(id=region,label=region+' · 기존 평가 범위',bounds=dict(min=[roi[k][0] for k in 'xyz'],max=[roi[k][1] for k in 'xyz'])),
                     dict(id=region+'_context',label=region+' · 주변 포함 범위',bounds=dict(min=[context[k][0] for k in 'xyz'],max=[context[k][1] for k in 'xyz']))])
        write(folder/'viewer_config.json',viewer)
        summaries.append(dict(region=region,config_sha256=sha(folder/'config.json'),mask_sha256=regional['mask_sha256'],train_views=len(masks)))
    write(out/'preparation.json',dict(status='PASS_FROZEN_BUNDLE',scientific_verdict=None,
        source_provenance_sha256=sha(out/'source/region_weight_source_provenance.json'),regions=summaries,
        script_hashes={str(p.relative_to(out)):sha(p) for sub in ('scripts','parent_scripts','legacy_scripts','implementation') for p in sorted((out/sub).rglob('*')) if p.is_file()}))
    print(json.dumps(summaries),flush=True)


if __name__=='__main__':main()
