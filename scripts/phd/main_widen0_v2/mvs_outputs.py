"""Record byte identities of the completed training-only geometric depth inputs."""
import json
from analysis_common import O,save_table
from preflight import sha,dump

def main():
    root=O/'mvs/full';receipt=json.loads((root/'colmap_receipt.json').read_text())
    assert receipt['exit_code']==0
    split=json.loads((O/'image_split.json').read_text());train=set(split['train'])
    files={p.name.removesuffix('.geometric.bin'):p for p in (root/'stereo/depth_maps').glob('*.geometric.bin')}
    assert not (set(files)&set(split['evaluation']))
    assert set(files)<=train, 'unexpected geometric depth images'
    rows=[]
    for name in split['train']:
        p=files.get(name)
        rows.append(dict(image=name,source=str(p) if p else None,exists=p is not None,
            bytes=p.stat().st_size if p else None,sha256=sha(p) if p else None))
    missing=sorted(train-set(files))
    save_table('새_MVS_깊이파일',rows,role='generated input identities; no patch outcomes',
        expected_training_images=len(train),depth_maps=len(files),missing=missing,
        evaluation_depth_maps=0,colmap_receipt=receipt)
    dump(root/'depth_manifest.json',dict(files=rows,missing=missing,scientific_verdict=None))
    dump(O/'gates/mvs_outputs.json',dict(status='PASS' if not missing else 'PARTIAL',
        expected=len(train),depth_maps=len(files),missing=missing,training_only=True,
        manifest_sha256=sha(root/'depth_manifest.json'),scientific_verdict=None))
    print('geometric depth identities recorded',len(files),'missing',len(missing))

if __name__=='__main__':main()
