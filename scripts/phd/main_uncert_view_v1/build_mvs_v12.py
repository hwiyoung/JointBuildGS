"""Add actual MVS display points; never recompute or modify scientific values."""
import gc
import os
import shutil
import sys
from scipy.spatial import cKDTree
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *
from build_data import encode, js

WEB = OUT / 'web_mvs_v1_2'


def attach(xyz, z, version, k):
    c, normal, offset = z['centre'], z['normal'], z[f'mvs_{version}_o']
    ids = np.flatnonzero(np.isfinite(offset))
    centres = c[ids] + offset[ids, None] * normal[ids]
    tree = cKDTree(centres)
    result = np.full(len(xyz), -1, np.int32)
    for start in range(0, len(xyz), 25000):
        q = xyz[start:start+25000].astype(np.float64)
        distances, neighbours = tree.query(q, k=min(k, len(ids)), distance_upper_bound=np.hypot(.5, 1.)+1e-7, workers=8)
        good = neighbours < len(ids)
        patch = ids[np.minimum(neighbours, len(ids)-1)]
        delta = q[:, None, :] - c[patch]
        t = np.sum(delta * normal[patch], axis=2)
        lateral2 = np.maximum(0, np.sum(delta*delta, axis=2) - t*t)
        good &= (lateral2 <= .5**2+1e-10) & (np.abs(t-offset[patch]) <= 1.+1e-10)
        cost = np.where(good, distances, np.inf)
        nearest = np.min(cost, axis=1)
        chosen = np.min(np.where(good & (cost == nearest[:, None]), patch, len(c)), axis=1)
        result[start:start+len(q)] = np.where(chosen < len(c), chosen, -1)
    # Independently check every emitted association against the original column/slab.
    keep = result >= 0
    p = result[keep]
    delta = xyz[keep].astype(np.float64) - c[p]
    t = np.sum(delta*normal[p], axis=1)
    lateral = np.linalg.norm(delta-t[:, None]*normal[p], axis=1)
    assert np.all(lateral <= .5+1e-6)
    assert np.all(np.abs(t-offset[p]) <= 1.+1e-6)
    return result, dict(mapped_points=int(keep.sum()), covered_patches=int(len(np.unique(p))),
        total_patches=len(c), max_lateral_m=float(lateral.max()),
        max_slab_distance_m=float(np.abs(t-offset[p]).max()))


def main():
    cfgpath = CFG / 'mvs_display_v1_2.json'
    config = load(cfgpath)
    assert not WEB.exists(), 'Preserve an existing candidate release'
    WEB.mkdir()
    for path in (OUT / 'web_v1_1').iterdir():
        if path.is_dir():
            shutil.copytree(path, WEB/path.name, copy_function=os.link)
        else:
            shutil.copy2(path, WEB/path.name)
    manifest = json.loads((WEB/'manifest.js').read_text().split('=', 1)[1].rstrip(';\n'))
    manifest['mvs_display_v1_2'] = config
    manifest['mvs_display_v1_2_sha256'] = sha(cfgpath)
    dump(CFG/'mvs_display_v1_2.lock.json', dict(made=now(), sha256=sha(cfgpath), scientific_verdict=None))
    rows = []
    for site in U.SITES:
        per_prior = {prior: pv(site, prior, 1.) for prior in U.PRIORS}
        for version in 'ab':
            source = SRC/'points'/site/f'mvs_{version}_xyz.npy'
            original = np.load(source, mmap_mode='r')
            count = min(len(original), config['max_points_per_site_version'])
            xyz = np.array(original[:count], copy=True)
            assert xyz.dtype == np.float32
            assert xyz.tobytes() == original[:count].tobytes()
            maps, stats = {}, {}
            for prior, z in per_prior.items():
                mapping, stats[prior] = attach(xyz, z, version, config['mapping']['candidate_count'])
                maps[prior] = encode(mapping)
            filename = f'mvs_geometry/{site}_{version}.js'
            packet = dict(site=site, version=version, n=count, xyz=encode(xyz), mapping=maps,
                source_indices='0..n-1 in original random-key order', stats=stats, scientific_verdict=None)
            js(WEB/filename, 'UNCERT_MVS_GEOMETRY', packet)
            row = dict(site=site, version=version, source=str(source.relative_to(SRC)),
                source_points=len(original), displayed_points=count, source_sha256=sha(source),
                xyz_sha256=hashlib.sha256(xyz.tobytes()).hexdigest(),
                file=filename, bytes=(WEB/filename).stat().st_size, file_sha256=sha(WEB/filename), stats=stats)
            rows.append(row)
            print(json.dumps(row), flush=True)
            del original, xyz, maps, packet
            gc.collect()
    manifest['mvs_geometry'] = rows
    js(WEB/'manifest.js', 'UNCERT_MANIFEST', manifest)
    receipt = dict(task_id=config['task_id'], made=now(), commit=os.environ.get('VIEW_COMMIT'),
        image=os.environ.get('VIEW_IMAGE'), config_sha256=sha(cfgpath), rows=rows,
        added_bytes=sum(r['bytes'] for r in rows), scientific_values_changed=False, scientific_verdict=None)
    dump(DOC/'tables_v1_2/mvs_geometry.json', receipt)
    progress(f'v1.2 MVS 실제 점군 표시 자료 생성: 원본 XYZ 정밀도 유지, 지역·판마다 최대 {count:,}점 표시. 원래 패치 값 연결만 수행. 모든 연결의 안쪽 원·면 띠 조건 확인. 원본 수치 및 보정·희소화 정의 변경 없음.')


if __name__ == '__main__':
    main()
