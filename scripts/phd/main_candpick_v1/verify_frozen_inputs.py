"""Rehash all bound training photos, scene inputs, and implementation at finish."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from input_audit import sha
from result_io import save


def main():
    config = json.loads(Path('/config/candpick_v1.json').read_text())
    inventory = json.loads(Path('/docs/render_inputs_v1.json').read_text())
    checked = {}
    def check(path, digest):
        path = str(path)
        if path not in checked: checked[path] = sha(path)
        assert checked[path] == digest, path
    for unit, data in config['units'].items():
        for item in data['bindings']: check(item['path'], item['sha256'])
        for row in inventory['units'][unit]['training_views']:
            check(row['source']['path'], row['source']['sha256'])
    for rel, digest in config['implementation_sha256'].items(): check(Path('/repo') / rel, digest)
    check('/config/places_v1.json', config['places_config_sha256'])
    check('/config/candpick_v1.json', json.loads(Path('/config/candpick_v1.lock.json').read_text())['sha256'])
    report = dict(status='PASS', at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        checked_files=len(checked), unique_photo_files=inventory['unique_photo_files'],
        sha256=checked, scientific_verdict=None)
    save(Path('/docs/final_input_verification.json'), report)
    print('PASS', len(checked), 'files; all bound photos, derived scene inputs, implementation and configs unchanged')


if __name__ == '__main__': main()
