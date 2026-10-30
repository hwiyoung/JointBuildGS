"""Verify result ZIP integrity and recompute every completed outcome row."""
import argparse
import hashlib
import json
import zipfile
from validate_results import validate


def verify(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, 'ZIP CRC failure'
        manifest = json.loads(z.read('MANIFEST.json'))
        names = z.namelist(); assert len(names) == len(set(names))
        assert set(names) == set(manifest['files']) | {'MANIFEST.json'}
        for name, entry in manifest['files'].items():
            data = z.read(name)
            assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], name
        report = validate(z.read)
        assert report['completed_arms'] == 24 and report['outcome_rows'] == 432
        report.update(zip_crc='PASS', member_sha256='PASS', members=len(names))
        return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('zip'); args = p.parse_args()
    print(json.dumps(verify(args.zip)))
