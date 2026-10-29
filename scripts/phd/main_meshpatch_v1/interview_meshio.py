"""Bounded exact triangle selection from binary PLY; no mesh simplification."""
import numpy as np
from pathlib import Path

DT={'float':'<f4','float32':'<f4','double':'<f8','float64':'<f8','uchar':'u1','uint8':'u1',
    'char':'i1','int8':'i1','int':'<i4','int32':'<i4','uint':'<u4','uint32':'<u4','short':'<i2','ushort':'<u2'}

def mapped(path):
    with Path(path).open('rb') as f:
        assert f.readline().strip()==b'ply'
        elements=[];cur=None
        while True:
            line=f.readline().decode('ascii').strip();bits=line.split()
            if line=='end_header':break
            if bits[:1]==['format']:assert bits[1]=='binary_little_endian'
            if bits[:1]==['element']:
                cur=dict(name=bits[1],count=int(bits[2]),props=[]);elements.append(cur)
            if bits[:1]==['property']:cur['props'].append(bits[1:])
        offset=f.tell()
    assert [x['name'] for x in elements][:2]==['vertex','face']
    v,face=elements[:2];assert all(p[0]!='list' for p in v['props'])
    vd=np.dtype([(p[1],DT[p[0]]) for p in v['props']]);verts=np.memmap(path,mode='r',offset=offset,dtype=vd,shape=(v['count'],))
    assert len(face['props'])==1 and face['props'][0][0]=='list'
    p=face['props'][0];fd=np.dtype([('count',DT[p[1]]),('indices',DT[p[2]],(3,))])
    faces=np.memmap(path,mode='r',offset=offset+v['count']*vd.itemsize,dtype=fd,shape=(face['count'],))
    return verts,faces

def crop(path,low,high,intersect=False):
    import open3d as o3d
    v,f=mapped(path);low=np.asarray(low);high=np.asarray(high);selected=[]
    for st in range(0,len(f),200000):
        chunk=f[st:st+200000];assert np.all(chunk['count']==3),'non-triangle source PLY'
        ids=chunk['indices'];xyz=np.stack([v[k][ids] for k in ['x','y','z']],axis=-1)
        m=((xyz.max(1)>=low)&(xyz.min(1)<=high)).all(1) if intersect else ((xyz>=low)&(xyz<=high)).all(axis=(1,2))
        if m.any():selected.append(np.asarray(ids[m],np.int64))
    mesh=o3d.geometry.TriangleMesh()
    if not selected:return mesh
    faces=np.concatenate(selected);ids,inv=np.unique(faces,return_inverse=True)
    xyz=np.stack([v[k][ids] for k in ['x','y','z']],axis=-1).astype(float)
    mesh.vertices=o3d.utility.Vector3dVector(xyz);mesh.triangles=o3d.utility.Vector3iVector(inv.reshape(-1,3))
    return mesh
