"""Cropped original prior surfaces and MVS vertices in each locked case frame."""
import argparse
import json
import numpy as np
import open3d as o3d
from common import *
from geometry import write_points

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    cases=json.loads((CFG/f'geometry_{a.site}_{a.prior}.json').read_text())['cases']
    pp=S1/'defs'/a.site/f'prior_{a.prior}.npz'
    with np.load(pp) as p:
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(p['V'].astype(float)),o3d.utility.Vector3iVector(p['F'].astype(np.int32)))
    for c in cases:
        q=mesh.crop(o3d.geometry.AxisAlignedBoundingBox(np.array(c['crop_min']),np.array(c['crop_max'])))
        q.translate(-np.array(c['translation']));dest=OUT/'3d'/c['id'];q.paint_uniform_color([.91,.64,.24])
        assert o3d.io.write_triangle_mesh(str(dest/'prior.ply'),q)
    del mesh
    mp=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/mvs'/a.site/'mesh_mvs_a.ply'
    mesh=o3d.io.read_triangle_mesh(str(mp));xyz=np.asarray(mesh.vertices)
    for c in cases:
        m=((xyz>=c['crop_min'])&(xyz<=c['crop_max'])).all(1);points=xyz[m];dest=OUT/'3d'/c['id']
        # MVS points are the original scored MVS surface vertices, not invented samples.
        colours=np.tile([74,126,199],(len(points),1));write_points(dest/'mvs.ply',points-c['translation'],colours)
        save(dest/'reference_sources.json',dict(prior_source=str(pp),prior_sha256=sha(pp),mvs_source=str(mp),mvs_sha256=sha(mp),
            mvs_points=len(points),mvs_role='original MVS mesh vertices',scientific_verdict=None))
    print('reference geometry',a.site,'PASS')

if __name__=='__main__':main()
