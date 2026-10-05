"""Validate staged surface-only packets, then atomically publish display metadata."""
import argparse
import json
import os
from pathlib import Path
import shutil

from build import sha, read, atomic, write


def buffers(value):
    if isinstance(value, dict):
        if 'url' in value and 'sha256' in value:
            yield value
        else:
            for item in value.values():
                yield from buffers(item)
    elif isinstance(value, list):
        for item in value:
            yield from buffers(item)


def signature(candidate):
    return [(x['sha256'], x['bytes'], x.get('shape'), x.get('dtype'))
            for name in ('mesh', 'points') for x in buffers(candidate.get(name))]


def validate(stage, live):
    staged, current = read(stage / 'manifest.json'), read(live / 'manifest.json')
    if staged.get('errors') or staged.get('scientific_verdict') is not None:
        raise ValueError('Staged export must have no errors and no scientific verdict')
    counts = {'unchanged_candidates': 0, 'available_surfaces': 0, 'pending_surfaces': 0, 'verified_buffers': 0}
    if [r['id'] for r in staged['regions']] != [r['id'] for r in current['regions']]:
        raise ValueError('Region membership changed')
    for region, previous in zip(staged['regions'], current['regions']):
        old = {c['id']: c for c in previous['candidates']}
        if set(old) != {c['id'] for c in region['candidates']}:
            raise ValueError('Candidate membership changed')
        for c in region['candidates']:
            if c['group'] != 'mvs_geogs':
                if c['status'] != old[c['id']]['status'] or signature(c) != signature(old[c['id']]):
                    raise ValueError('Unrequested panel geometry/color change: ' + region['id'] + '/' + c['id'])
                counts['unchanged_candidates'] += 1
            else:
                if c.get('representation_policy') != 'surface_only':
                    raise ValueError('Missing surface-only policy')
                if c['status'] == 'available':
                    if not c.get('mesh') or c['source']['identity']['kind'] != 'completed_native_rgb_tsdf512':
                        raise ValueError('Available MVS GeoGS must be an extracted surface')
                    counts['available_surfaces'] += 1
                elif c['status'] == 'pending' and not c.get('mesh') and not c.get('points'):
                    counts['pending_surfaces'] += 1
                else:
                    raise ValueError('Unexpected MVS GeoGS state')
            for name in ('mesh', 'points'):
                for b in buffers(c.get(name)):
                    if not b['url'].startswith('/data/cache/'):
                        raise ValueError('Unexpected display buffer URL')
                    path = (stage / b['url'].removeprefix('/data/')).resolve(strict=True)
                    path.relative_to(stage.resolve())
                    if path.stat().st_size != b['bytes'] or sha(path) != b['sha256']:
                        raise ValueError('Staged buffer bytes do not match metadata')
                    counts['verified_buffers'] += 1
    if counts['available_surfaces'] + counts['pending_surfaces'] != 12:
        raise ValueError('Expected twelve MVS conditions')
    return {'status': 'PASS_SURFACE_ONLY_DISPLAY_UPDATE', 'scientific_verdict': None,
            'manifest_sha256': sha(stage / 'manifest.json'), **counts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', type=Path, required=True)
    p.add_argument('--live', type=Path, required=True)
    p.add_argument('--publish', action='store_true')
    p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    if a.restore:
        for name in ('manifest.json', 'builder_status.json'):
            saved = a.stage.parent / ('previous_' + name)
            if saved.exists():
                atomic(a.live / name, read(saved))
        return
    receipt = validate(a.stage, a.live)
    if a.publish:
        update = a.stage.parent
        for name in ('manifest.json', 'builder_status.json'):
            shutil.copyfile(a.live / name, update / ('previous_' + name))
        for directory in sorted((a.stage / 'cache').iterdir()):
            destination = a.live / 'cache' / directory.name
            if destination.exists():
                raise ValueError('Refusing to replace an immutable cache directory')
            os.rename(directory, destination)
        for snapshot in sorted((a.stage / 'snapshots').iterdir()):
            write(a.live / 'snapshots' / snapshot.name, read(snapshot))
        atomic(a.live / 'manifest.json', read(a.stage / 'manifest.json'))
        atomic(a.live / 'builder_status.json', read(a.stage / 'builder_status.json'))
        write(update / 'publication_receipt.json', receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
