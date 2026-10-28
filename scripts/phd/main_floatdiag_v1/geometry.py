"""Exact source-mesh crops, compact GLBs, and CPU ray-cast renders. No training."""
import argparse
import gc
import json
import struct
from pathlib import Path
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from PIL import Image
from common import *
from recount import load_eval

def rgb(text):
    return np.array([int(text[i:i+2],16) for i in (1,3,5)],np.uint8)

def write_points(path, xyz, colours=None):
    cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz))
    if colours is not None:cloud.colors=o3d.utility.Vector3dVector(np.asarray(colours)/255)
    assert o3d.io.write_point_cloud(str(path),cloud,write_ascii=False)

def glb(path, vertices, faces, face_colours=None, vertex_colours=None):
    # Duplicate face corners only for categorical face colours: no interpolation
    # across a GT/missing-data boundary. The source PLY remains unreduced.
    if face_colours is not None:
        v=vertices[faces].reshape(-1,3).astype('<f4')
        f=np.arange(len(v),dtype='<u4').reshape(-1,3)
        c=np.repeat(face_colours,3,axis=0)
    else:
        v=np.asarray(vertices,dtype='<f4');f=np.asarray(faces,dtype='<u4');c=np.asarray(vertex_colours,np.uint8)
    c=np.c_[c,np.full(len(c),255,np.uint8)].astype(np.uint8)
    arrays=[v.tobytes(),c.tobytes(),f.tobytes()];blob=b'';views=[]
    for arr in arrays:
        views.append(dict(buffer=0,byteOffset=len(blob),byteLength=len(arr)))
        blob+=arr+b'\0'*((-len(arr))%4)
    doc=dict(asset=dict(version='2.0',generator=TASK),buffers=[dict(byteLength=len(blob))],bufferViews=views,
        accessors=[dict(bufferView=0,componentType=5126,count=len(v),type='VEC3',min=v.min(0).tolist(),max=v.max(0).tolist()),
            dict(bufferView=1,componentType=5121,normalized=True,count=len(c),type='VEC4'),
            dict(bufferView=2,componentType=5125,count=f.size,type='SCALAR')],
        materials=[dict(doubleSided=True,pbrMetallicRoughness=dict(metallicFactor=0.,roughnessFactor=1.))],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0,COLOR_0=1),indices=2,material=0)])],
        nodes=[dict(mesh=0)],scenes=[dict(nodes=[0])],scene=0)
    raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4)
    data=struct.pack('<III',0x46546c67,2,12+8+len(raw)+8+len(blob))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(blob),0x004e4942)+blob
    assert len(data)<config()['delivery']['max_glb_bytes']
    path.write_bytes(data)

def reference(site):
    path=S1/'defs'/site/'gt_classes.npz'
    with np.load(path) as q:
        points=[q['xyz_gt_points'][q['use_gt_points']]]
        if 'xyz_gt_primary' in q.files:points.append(q['xyz_gt_primary'][q['use_gt_primary']])
        xyz=np.concatenate(points).astype(np.float64)
    return xyz,path

def gt_grid(xyz,origin,cell=.25):
    ij=np.floor((xyz[:,:2]-origin)/cell).astype(int)
    if not len(ij):return np.full((1,1),np.nan)
    size=ij.max(0)+1;out=np.full((size[1],size[0]),-np.inf)
    np.maximum.at(out,(ij[:,1],ij[:,0]),xyz[:,2])
    out[~np.isfinite(out)]=np.nan
    return out

def grid_values(xy,grid,origin,cell=.25):
    ij=np.floor((xy-origin)/cell).astype(int)
    valid=(ij[:,0]>=0)&(ij[:,1]>=0)&(ij[:,0]<grid.shape[1])&(ij[:,1]<grid.shape[0])
    out=np.full(len(xy),np.nan)
    out[valid]=grid[ij[valid,1],ij[valid,0]]
    return out

def face_colours(mesh,grid,origin,tree,tau):
    v=np.asarray(mesh.vertices);f=np.asarray(mesh.triangles);centres=v[f].mean(1)
    gz=grid_values(centres[:,:2],grid,origin)
    distance,idx=tree.query(centres[:,:2],workers=2)
    # Tau comes from the nearest existing patch in this same horizontal cell.
    ptau=tau[idx];known=np.isfinite(gz)&(distance<=np.sqrt(2)*.25)
    delta=centres[:,2]-gz;cfg=config()['colours']['mesh']
    colours=np.tile(rgb(cfg['no_gt']),(len(f),1))
    colours[known]=rgb(cfg['other'])
    colours[known&(np.abs(delta)<=ptau)]=rgb(cfg['within_tau'])
    colours[known&(delta>ptau)]=rgb(cfg['floating'])
    return colours,dict(faces=len(f),gt_known_faces=int(known.sum()),red_faces=int((known&(delta>ptau)).sum()))

def camera(case,azimuth,elevation,width=720,height=600):
    az,el=np.deg2rad([azimuth,elevation]);direction=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0.]);up=np.cross(direction,right)
    extent=case['radius']*2.2;target=np.array(case['translation']);eye=target+2.5*case['radius']*direction
    return dict(azimuth_deg=azimuth,elevation_deg=elevation,width=width,height=height,
        eye=eye.tolist(),target=target.tolist(),right=right.tolist(),up=up.tolist(),direction=direction.tolist(),extent=extent,
        projection='perspective',fov_x_deg=45.)

def render_context(mesh,colours):
    scene=o3d.t.geometry.RaycastingScene(nthreads=8)
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    mesh.compute_triangle_normals();norm=np.asarray(mesh.triangle_normals)
    light=np.array([.3,-.4,.85]);light/=np.linalg.norm(light)
    shade=.65+.35*np.abs(norm@light)
    return scene,np.clip(colours*shade[:,None],0,255).astype(np.uint8)

def render(mesh,colours,cam,points=None,context=None):
    W,H=cam['width'],cam['height'];right=np.array(cam['right']);up=np.array(cam['up']);di=np.array(cam['direction']);eye=np.array(cam['eye'])
    focal=W/(2*np.tan(np.deg2rad(cam['fov_x_deg'])/2))
    u=(np.arange(W)-(W-1)/2)/focal;vv=-(np.arange(H)-(H-1)/2)/focal
    xx,yy=np.meshgrid(u,vv)
    directions=-di+xx[...,None]*right+yy[...,None]*up
    rays=np.concatenate((np.broadcast_to(eye,directions.shape),directions),axis=-1).astype(np.float32)
    scene,shaded=render_context(mesh,colours) if context is None else context
    hit=scene.cast_rays(o3d.core.Tensor(rays));depth=hit['t_hit'].numpy();ids=hit['primitive_ids'].numpy();good=np.isfinite(depth)
    image=np.full((H,W,3),248,np.uint8)
    image[good]=shaded[ids[good]]
    if points is not None and len(points):
        delta=points-eye;d=-(delta@di)
        px=np.rint((delta@right)/np.maximum(d,1e-8)*focal+(W-1)/2).astype(int)
        py=np.rint(-(delta@up)/np.maximum(d,1e-8)*focal+(H-1)/2).astype(int)
        valid=(px>=0)&(px<W)&(py>=0)&(py<H)&(d>0)
        idx=np.flatnonzero(valid);idx=idx[d[idx]<=depth[py[idx],px[idx]]+.05]
        image[py[idx],px[idx]]=[35,35,35]
    return image

def freeze_geometry(site,prior):
    cfg=config();cases=[x for x in json.loads((CFG/f'cases_{prior}.json').read_text())['cases'] if x['site']==site]
    gt,gtpath=reference(site);e,_=load_eval(site,prior)
    existing=CFG/f'geometry_{site}_{prior}.json'
    if existing.exists():
        old=json.loads(existing.read_text())
        assert old['source_sha256']==sha(CFG/f'cases_{prior}.json')
        return old['cases'],gt,e
    for case in cases:
        b=np.array(case['bbox']);lo=b[:2]-3;hi=b[2:]+3
        selected=gt[((gt[:,:2]>=lo)&(gt[:,:2]<=hi)).all(1)]
        assert len(selected),'GT absent: do not invent crop height'
        low=np.r_[lo,selected[:,2].min()-2];high=np.r_[hi,selected[:,2].max()+8]
        case.update(crop_min=low.tolist(),crop_max=high.tolist(),translation=((low+high)/2).tolist(),radius=float(np.linalg.norm(high-low)/2))
        case['cameras']=[camera(case,a,b) for a,b in zip(cfg['cameras']['azimuth_deg'],cfg['cameras']['elevation_deg'])]
        dest=OUT/'3d'/case['id'];dest.mkdir(parents=True,exist_ok=True)
        # Keep all reference points for all calculations; thinning applies only to the PLY display.
        stride=max(1,int(np.ceil(len(selected)/cfg['delivery']['max_reference_points'])))
        write_points(dest/'gt.ply',selected[::stride]-case['translation'])
        save(dest/'coordinate.json',dict(case=case,crs='EPSG:25832',global_origin_m=cfg['local_origin_m'],
            removed_local_translation=case['translation'],up='+z',gt_source=str(gtpath),gt_sha256=sha(gtpath),
            display_gt_stride=stride,gt_full_count=len(selected),display_gt_count=len(selected[::stride]),scientific_verdict=None))
    save(CFG/f'geometry_{site}_{prior}.json',dict(frozen_at=now(),cases=cases,source_sha256=sha(CFG/f'cases_{prior}.json'),
        method='Open3D CPU raycast, fixed perspective cameras shared with Gaussian renderer, face normal illumination; source crop keeps triangles with all vertices inside bounding box',scientific_verdict=None))
    return cases,gt,e

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',choices=SITES,required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    assert json.loads((DOC/'provenance'/f'appendix_C_{a.prior}.json').read_text())['status']=='PASS'
    cases,gt,e=freeze_geometry(a.site,a.prior)
    origin=np.minimum(gt[:,:2].min(0),e['centre'][:,:2].min(0))-.25;grid=gt_grid(gt,origin)
    tree=cKDTree(e['centre'][:,:2]);tau=e['tau']
    web=DOC/'보기/3d';web.mkdir(parents=True,exist_ok=True)
    for result in [f'{p}_{a.prior}_s0' for p in ['nojudge','lt_dyngt','lt_dynnow']]:
        path,receipt=mesh_path(a.site,result,a.prior);digest=sha(path)
        assert digest==receipt['mesh_sha256'],'source mesh differs from patch_z receipt'
        print('read exact scored mesh',a.site,result,flush=True)
        full=o3d.io.read_triangle_mesh(str(path));assert len(full.triangles)
        for case in cases:
            tag=case['id'];dest=OUT/'3d'/tag;imgs=DOC/'3d'/tag/result;imgs.mkdir(parents=True,exist_ok=True)
            if (dest/(result+'.json')).exists():
                done=json.loads((dest/(result+'.json')).read_text())
                assert done['source_mesh_sha256']==digest
                print('reuse completed case',tag,result,flush=True)
                continue
            mesh=full.crop(o3d.geometry.AxisAlignedBoundingBox(np.array(case['crop_min']),np.array(case['crop_max'])))
            assert len(mesh.triangles)>0
            col,colour_stats=face_colours(mesh,grid,origin,tree,tau)
            local=o3d.geometry.TriangleMesh(mesh);local.translate(-np.array(case['translation']))
            assert o3d.io.write_triangle_mesh(str(dest/(result+'.ply')),local)
            small=mesh.simplify_quadric_decimation(20000) if len(mesh.triangles)>20000 else o3d.geometry.TriangleMesh(mesh)
            # Disconnected TSDF fragments can prevent quadric decimation from
            # reaching its target. Cluster only this web derivative, retaining
            # the full crop and using the full mesh for every static capture.
            web_voxel=None
            for voxel in [.025,.05,.1,.2,.4]:
                if len(small.triangles)<=22000:break
                small=mesh.simplify_vertex_clustering(voxel)
                small=small.simplify_quadric_decimation(20000)
                web_voxel=voxel
            assert len(small.triangles)<=22000,'web simplification budget unmet'
            sc,scstats=face_colours(small,grid,origin,tree,tau)
            verts=np.asarray(small.vertices)-case['translation'];faces=np.asarray(small.triangles)
            assert small.has_vertex_colors(),'source TSDF colour missing'
            glb(web/f'{tag}__{result}__colour.glb',verts,faces,vertex_colours=np.clip(np.asarray(small.vertex_colors)*255,0,255).astype(np.uint8))
            glb(web/f'{tag}__{result}__float.glb',verts,faces,face_colours=sc)
            for flavour in ['colour','float']:
                p=web/f'{tag}__{result}__{flavour}.glb'
                (dest/p.name).write_bytes(p.read_bytes())
            pts=gt[((gt>=case['crop_min'])&(gt<=case['crop_max'])).all(1)]
            stride=max(1,int(np.ceil(len(pts)/30000)));pts=pts[::stride]
            context=render_context(mesh,col)
            for i,cam in enumerate(case['cameras']):
                Image.fromarray(render(mesh,col,cam,context=context)).save(imgs/f'view_{i}.png')
                Image.fromarray(render(mesh,col,cam,pts,context=context)).save(imgs/f'view_{i}_gt.png')
            for i in range(36):
                cam=camera(case,i*10,20,width=360,height=300)
                Image.fromarray(render(mesh,col,cam,context=context)).save(imgs/f'orbit_{i:02}.png')
            save(dest/(result+'.json'),dict(at=now(),case=tag,result=result,source_mesh=str(path),source_mesh_sha256=digest,
                patch_z_receipt=receipt['patch_z_sha256'],crop_vertices=len(mesh.vertices),crop_faces=len(mesh.triangles),
                glb_vertices=len(small.vertices),glb_faces=len(small.triangles),web_clustering_voxel_m=web_voxel,colour_stats=colour_stats,glb_colour_stats=scstats,
                camera_config=str(CFG/f'geometry_{a.site}_{a.prior}.json'),camera_config_sha256=sha(CFG/f'geometry_{a.site}_{a.prior}.json'),
                reference_height_rule='highest raw GT point in each 0.25m XY cell; missing stays light grey; tau from nearest same-cell patch',
                scientific_verdict=None))
            print(tag,result,'crop and captures PASS',len(mesh.triangles),flush=True)
            del mesh,local,small,context;gc.collect()
        del full;gc.collect()
    save(DOC/'provenance'/f'geometry_{a.site}_{a.prior}_PASS.json',dict(at=now(),cases=[c['id'] for c in cases],source_hashes_verified=True,scientific_verdict=None))

if __name__=='__main__':main()
