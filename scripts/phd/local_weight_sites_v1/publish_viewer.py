"""Publish a fresh local viewer directory; never replace an existing publication."""
import argparse
import hashlib
import json
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(attempt, application, server_data, name, base_url):
    assert name and all(c.isalnum() or c in '_-' for c in name)
    receipt = json.loads((attempt / 'build_receipt.json').read_text())
    assert receipt['status'] == 'PASS_VIEWER_DATA_AND_NATIVE_GEOMETRY'
    original = attempt / 'site'
    for filename, digest in receipt['files'].items():
        assert sha(original / filename) == digest, filename
    release = attempt / 'releases' / name
    release.parent.mkdir(exist_ok=True)
    assert not release.exists()
    destination = server_data / name
    assert not destination.exists(), 'Existing publication is protected'
    shutil.copytree(original, release)
    for filename in ['index.html', 'viewer.js', 'style.css']:
        shutil.copyfile(application / filename, release / filename)
    files = {str(p.relative_to(release)): sha(p) for p in release.rglob('*') if p.is_file()}
    staging = server_data / ('.' + name + '_staging')
    assert not staging.exists()
    shutil.copytree(release, staging)
    for filename, digest in files.items():
        assert sha(staging / filename) == digest
    staging.rename(destination)
    base = base_url.rstrip('/') + '/data/' + name + '/'

    def verify(item):
        filename, digest = item
        with urllib.request.urlopen(base + filename, timeout=30) as response:
            actual = hashlib.sha256(response.read()).hexdigest()
            assert response.status == 200 and actual == digest, filename
        return filename

    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(verify, files.items()))
    result = dict(status='PASS_LOCAL_VIEWER_PUBLICATION', scientific_verdict=None,
        url=base + 'index.html', build_receipt_sha256=sha(attempt / 'build_receipt.json'),
        application_sha256={filename:sha(application / filename) for filename in ['index.html','viewer.js','style.css']},
        publication_directory=str(destination), files=files, http_sha256_verified_count=len(verified),
        script_sha256=sha(__file__), source_results_changed=False)
    (attempt / (name + '_publication.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:result[k] for k in ['status','url','http_sha256_verified_count']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', type=Path, required=True)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--server-data', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8913')
    args = parser.parse_args()
    main(args.attempt, args.application, args.server_data, args.name, args.base_url)
