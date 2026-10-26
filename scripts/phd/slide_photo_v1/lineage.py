"""Input byte identities and dependency versions, no scientific outcome reads."""
import platform,subprocess,importlib.metadata
from common import *
def main():
    sources=[W/'inputs/tiles.json',W/'mvs/full/sparse/images.bin',W/'mvs/full/sparse/cameras.bin',W/'mvs/full/depth_manifest.json',G.DENSE/'triangulated/images.bin',G.DENSE/'triangulated/cameras.bin',S1/'v3/align/common_shift.json']
    for t in load(W/'inputs/tiles.json'):
        sources.append(W/'inputs/points'/t['id']/'uls.bin')
        sources.extend(W/'patch_values'/f'{t["id"]}__{prior}__R1.5.npz' for prior in ['ALS','LoD2'])
    sources.extend([REPO/'scripts/phd/main_regionfig_v1/common.py',REPO/'scripts/phd/main_photofig_v1/pf_geo.py',REPO/'scripts/phd/main_uncert_v1/u_core.py'])
    rows=[]
    for p in sources:
        rows.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)));print('HASH',p.name,flush=True)
    versions={p:importlib.metadata.version(p) for p in ['numpy','scipy','matplotlib','Pillow','plyfile']}
    dump(DOC/'input_lineage.json',dict(at=now(),scientific_verdict=None,base_commit=(PAY/'base_commit.txt').read_text().strip(),docker_image_id=(PAY/'image_id.txt').read_text().strip(),python=platform.python_version(),versions=versions,inputs=rows,depth_source='Input-only depth_manifest.json pins each geometric depth; raw photo member hashes are in figure JSON',geometry_allowlist=GEOMETRY_KEYS,no_holdout_paths=all('/holdout/' not in str(p) for p in sources)))
if __name__=='__main__':main()
