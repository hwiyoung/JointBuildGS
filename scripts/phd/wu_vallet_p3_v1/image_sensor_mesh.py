"""Freeze real P3 camera/pixel sensor topology using existing COLMAP depth.

This is a current-image preprocessing component, not full Wu-Vallet reproduction.
ALS rays, source judgment and evaluation references are not used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
import numpy as np
from src.phd.wu_vallet_p3_v1.sensor_mesh import image_depth_to_sensor_mesh, ImageMeshConfig


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,data): Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def main(config_path,output):
    cfg=json.loads(Path(config_path).read_text()); output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();write(output/'STARTED.json',{'scientific_verdict':None})
    try:
        vp=Path(cfg['common_root'])/'views.json'
        views=json.loads(vp.read_text())['views']
        candidates=([v for v in views if v['role']=='decision'] if cfg.get('scan_decision_views')
                    else [next(v for v in views if v['image_id']==cfg['image_id'])])
        if any(v['role']!='decision' for v in candidates): raise ValueError('Only frozen decision views permitted')
        audit=[]; selected=None; candidate_hashes={}
        for row in candidates:
            spec=row['maps']['depth'];path=Path(spec['path']);actual_hash=sha(path);candidate_hashes[str(path)]=actual_hash
            if actual_hash!=spec['sha256'] or (not cfg.get('scan_decision_views') and actual_hash!=cfg['depth_sha256']): raise ValueError('Depth hash mismatch')
            width,height,channels=spec['width'],spec['height'],spec['channels']
            if channels!=1: raise ValueError('Expected scalar camera-Z depth')
            with path.open('rb') as f:
                f.seek(spec['header_bytes']);depth=np.fromfile(f,dtype=np.float32).reshape((width,height,channels),order='F').transpose(1,0,2)[...,0].copy()
            if depth.shape!=(height,width): raise ValueError('Depth dimension mismatch')
            K=np.array(spec['K']);R=np.array(row['R']);t=np.array(row['t'])
            yy,xx=np.mgrid[:height,:width]
            rays=np.stack((xx,yy,np.ones_like(xx)),axis=-1)@np.linalg.inv(K).T
            world=(rays*depth[...,None]-t)@R
            valid=np.isfinite(depth)&(depth>0);inside=valid.copy()
            for i,key in enumerate(('x','y','z')): inside&=(world[...,i]>=cfg['domain'][key][0])&(world[...,i]<cfg['domain'][key][1])
            cropped=np.where(inside,depth,0.)
            result=image_depth_to_sensor_mesh(cropped,K,R,t,ImageMeshConfig(**cfg['algorithm']),image_id=str(row['image_id']))
            mesh=result['mesh'];eligible=len(mesh.triangles)>=cfg.get('minimum_faces',1)
            audit.append(dict(image_id=row['image_id'],hash_rank=row['hash_rank'],positive_depth_pixels=int(valid.sum()),prism_depth_pixels=int(inside.sum()),vertices=len(mesh.vertices),triangles=len(mesh.triangles),eligible=eligible))
            if selected is None and eligible: selected=(row,spec,path,depth,inside,valid,result)
        write(output/'coverage_audit.json',{'views':audit,'selection_rule':cfg['selection_rule'],'scientific_verdict':None})
        if selected is None: raise ValueError('No eligible sensor mesh in declared decision views')
        row,spec,path,depth,inside,valid,result=selected;mesh=result['mesh']
        np.savez_compressed(output/'image_sensor_mesh.npz',vertices=mesh.vertices,triangles=mesh.triangles,
            optical_origins=mesh.optical_origins,native_rows=mesh.native_rows,pixel_uv=result['pixel_uv'],
            image_id=np.full(len(mesh.vertices),row['image_id'],np.int32))
        np.save(output/'prism_pixel_mask.npy',inside)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(1,2,figsize=(11,4))
        ax[0].imshow(np.where(inside,depth,np.nan),cmap='viridis');ax[0].set_title(f"Camera {row['image_id']}: native camera-Z depth in P3")
        step=max(1,len(mesh.triangles)//3000)
        for face in mesh.triangles[::step]:
            p=mesh.vertices[face][:,[0,1]];p=np.vstack((p,p[:1]));ax[1].plot(p[:,0],p[:,1],color='#267c9d',linewidth=.25)
        ax[1].set(xlabel='Scene X (m)',ylabel='Scene Y (m)',title='Pixel adjacency sensor mesh (display subset)');ax[1].set_aspect('equal')
        fig.tight_layout();fig.savefig(output/'image_sensor_mesh.png',dpi=150);plt.close(fig)
        write(output/'config.json',cfg)
        receipt={'status':'IMAGE_SENSOR_MESH_COMPONENT_COMPLETE','task_id':cfg['task_id'],'scientific_verdict':None,
            'image_id':row['image_id'],'vertices':len(mesh.vertices),'triangles':len(mesh.triangles),
            'valid_depth_pixels':int(valid.sum()),'prism_depth_pixels':int(inside.sum()),'diagnostics':result['diagnostics'],
            'input_hashes':{str(vp):sha(vp),**candidate_hashes,str(config_path):sha(config_path)},
            'source_hashes':{str(Path(__file__)):sha(__file__), 'src/phd/wu_vallet_p3_v1/sensor_mesh.py':sha('src/phd/wu_vallet_p3_v1/sensor_mesh.py')},
            'reproduction_scope':result['reproduction_scope'],'native_Wu_Vallet_reproduction':False,'PSMNet_reproduced':False,
            'als_sensor_mesh_available':False,'source_decision_executed':False,'reference_accessed':False,
            'working_crs':'EPSG:25832','coordinates':'SCENE_LOCAL_XYZ; already local camera solution; no new shift',
            'git_head':os.environ.get('JBGS_SOURCE_GIT_HEAD'),'image_id_runtime':os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
            'elapsed_seconds':time.monotonic()-started,
            'outputs':{p.name:sha(p) for p in output.iterdir() if p.is_file()}}
        write(output/'receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('status','vertices','triangles')}),flush=True)
    except Exception as e:
        write(output/'FAILED.json',{'error':repr(e),'traceback':traceback.format_exc(),'scientific_verdict':None});raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.config,a.output)
