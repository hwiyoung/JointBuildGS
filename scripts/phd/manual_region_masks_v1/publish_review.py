"""Publish verified, input-only region review assets to the existing local viewer."""
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    out=Path('/output')
    published=[]
    for region in ('P2','P3'):
        review=Path('/'+region)
        check=json.loads((review/'validation.json').read_text())
        assert check['status']=='PASS_EXPORTED_ARRAYS_AND_HASHES'
        manifest=json.loads((review/'result/review.json').read_text())
        assert manifest['status']=='PASS_NATIVE_SOURCE_REVIEW'
        assert manifest['annotations_receipt_sha256']==check['receipt_sha256']
        for item in manifest['outputs']:
            assert sha(review/'result'/item['path'])==item['sha256'],item['path']
        shutil.copytree(review/'result',out/region)
        shutil.copyfile(review/'validation.json',out/region/'validation.json')
        published.append(dict(region=region,views=len(manifest['views']),sources=manifest['sources'],
                              review_sha256=sha(review/'result/review.json'),validation=check))
    (out/'publication.json').write_text(json.dumps(dict(status='PASS_PUBLISHED_INPUT_ANNOTATIONS',scientific_verdict=None,
        training_executed=False,regions=published,outputs=[dict(path=str(p.relative_to(out)),sha256=sha(p)) for p in sorted(out.rglob('*')) if p.is_file()]),ensure_ascii=False,indent=2))
    print(json.dumps({'status':'PASS_PUBLISHED_INPUT_ANNOTATIONS','regions':[x['region'] for x in published]},ensure_ascii=False))


if __name__=='__main__': main()
