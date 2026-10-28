"""Bounded script syntax, source GLB compatibility, and camera projection checks."""
import ast
import json
from pathlib import Path
import numpy as np
import trimesh
from common import *

root=Path('/repo/scripts/phd/main_floatdiag_v1');checked=[]
for p in sorted(root.glob('*.py')):
    compile(p.read_text(),str(p),'exec');checked.append(p.name)
glbs=[]
for p in sorted((DOC/'보기/3d').glob('*.glb')):
    scene=trimesh.load(str(p),force='scene',process=False)
    n=sum(len(m.faces) for m in scene.geometry.values());assert 0<n<150000
    assert p.stat().st_size<4000000
    for m in scene.geometry.values():assert np.isfinite(m.vertices).all()
    glbs.append(dict(path=str(p),faces=n,bytes=p.stat().st_size,sha256=sha(p)))
camera_checks=[]
for p in sorted(CFG.glob('geometry_*.json')):
    for case in json.loads(p.read_text())['cases']:
        for cam in case['cameras']:
            eye=np.array(cam['eye']);target=np.array(cam['target']);r=np.array(cam['right']);u=np.array(cam['up']);d=np.array(cam['direction'])
            matrix=np.array([r,-u,-d]);assert np.allclose(matrix@matrix.T,np.eye(3))
            assert np.isclose(np.linalg.det(matrix),1)
            c=matrix@(target-eye);assert np.allclose(c[:2],0,atol=1e-6) and c[2]>0
            camera_checks.append(dict(case=case['id'],azimuth=cam['azimuth_deg'],elevation=cam['elevation_deg'],status='PASS'))
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--tag',default='02');args=ap.parse_args()
save(DOC/'provenance'/('code_asset_check_'+args.tag+'.json'),dict(at=now(),python_syntax=checked,glbs=glbs,camera_checks=camera_checks,
    status='PASS',scope='currently existing files only; not a completion claim',scientific_verdict=None))
print('syntax',len(checked),'GLBs',len(glbs),'camera checks',len(camera_checks),'PASS')
