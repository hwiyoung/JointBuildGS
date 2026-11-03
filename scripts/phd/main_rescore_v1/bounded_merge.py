"""Disk-backed equivalent of streamed_tsdf.merge, with the same vertex ordering."""
import sys,gc,mmap
from common import *
sys.path.insert(0,'/repo')
from src.phd import streamed_tsdf as T
CHUNK=1_000_000
def release(a):
 if isinstance(a,np.memmap):
  a.flush();a._mmap.madvise(mmap.MADV_DONTNEED)
def merge(wd,out_ply,out_json):
 start=time.monotonic();W=Path(wd);lay=json.loads((W/'plan/layout.json').read_text());meta=json.loads((W/'inputs/meta.json').read_text());tj=[json.loads((W/f"tiles/tile{t['k']}.json").read_text()) for t in lay['tiles']];nv=sum(t['kept']['vertices'] for t in tj);nt=sum(t['kept']['triangles'] for t in tj);cache=W/'bounded_merge';cache.mkdir(exist_ok=True)
 def arr(name,dtype,shape):return np.memmap(cache/(name+'.bin'),dtype=dtype,mode='w+',shape=shape)
 V=arr('vertices','f8',(nv,3));C=arr('colors','f8',(nv,3));F=arr('faces','i8',(nt,3));G=arr('gcode','i8',(nt,));E=arr('edge','i1',(nt,3));VC=arr('vcode','i8',(nv,));TV=arr('tile','i4',(nv,));oc=T.enc(np.fromfile(W/'order/ord_onepiece.i32',np.int32).reshape(-1,3).astype(np.int64));srt=np.argsort(oc);ranks=[];lens=[];voff=foff=0
 for tile in lay['tiles']:
  with np.load(W/f"tiles/tile{tile['k']}.npz") as z:
   bc=T.enc(z['keys'].astype(np.int64));pos=np.clip(np.searchsorted(oc[srt],bc),0,len(oc)-1);assert (oc[srt][pos]==bc).all();ranks.append(srt[pos]);lens.append(z['lens'].astype(np.int64));vv=z['V'];ff=z['F'];n,m=len(vv),len(ff);V[voff:voff+n]=vv;C[voff:voff+n]=z['C'] if 'C' in z else 0;F[foff:foff+m]=ff.astype(np.int64)+voff;G[foff:foff+m]=z['gcode'];E[foff:foff+m]=z['e'];VC[voff:voff+n]=z['vcode'];TV[voff:voff+n]=tile['k'];voff+=n;foff+=m;del vv,ff
  for a in [V,C,F,G,E,VC,TV]:release(a)
  print('MERGE_LOAD_TILE',tile['k'],flush=True)
 assert (voff,foff)==(nv,nt);rank=np.concatenate(ranks);ln=np.concatenate(lens);assert len(np.unique(rank))==len(rank);st=np.r_[0,np.cumsum(ln)[:-1]];order=np.argsort(rank,kind='stable');ss,ll=st[order],ln[order];FO=arr('ordered_faces','i8',(nt,3));GO=arr('ordered_gcode','i8',(nt,));EO=arr('ordered_edges','i1',(nt,3));b=out=0
 while b<len(ll):
  end=b+1;count=int(ll[b])
  while end<len(ll) and count+ll[end]<=CHUNK:count+=int(ll[end]);end+=1
  lengths=ll[b:end];perm=np.repeat(ss[b:end]-np.r_[0,np.cumsum(lengths)[:-1]],lengths)+np.arange(count);FO[out:out+count]=F[perm];GO[out:out+count]=G[perm];EO[out:out+count]=E[perm];out+=count;b=end
 for a in [F,G,E,FO,GO,EO]:release(a)
 rep=arr('representative','i8',(nv,))
 for b in range(0,nv,CHUNK):rep[b:b+CHUNK]=np.arange(b,min(nv,b+CHUNK))
 known=np.flatnonzero(VC>=0);unique,first,inv=np.unique(VC[known],return_index=True,return_inverse=True);rep[known]=known[first][inv];vinfo=dict(vertices_without_edge=int(nv-len(known)),corners_unsettled=int((EO<0).sum()),copies_merged_by_edge=int(len(known)-len(first)),copies_with_other_coordinates=0,copies_with_other_colours=0);del unique,first,inv
 for b in range(0,len(known),CHUNK):
  ix=known[b:b+CHUNK];ri=rep[ix];vinfo['copies_with_other_coordinates']+=int((V[ri]!=V[ix]).any(1).sum());vinfo['copies_with_other_colours']+=int((C[ri]!=C[ix]).any(1).sum())
 assert vinfo['copies_with_other_coordinates']==vinfo['copies_with_other_colours']==0;del known;gc.collect();unk=np.flatnonzero(VC<0);merged=left=0
 if len(unk):
  key=np.asarray(V).view(np.dtype((np.void,24))).ravel()
  for v in unk:
   same=np.flatnonzero((key==key[v])&(TV!=TV[v]))
   if len(same) and all((TV[same]==t).sum()==1 for t in np.unique(TV[same])):rep[v]=rep[same].min() if rep[same].min()<v else v;merged+=1
   elif len(same):left+=1
 vinfo.update(vertex_identity='global edge'+('' if not len(unk) else ' (unsettled vertices: exact coordinates in other tiles)'),unsettled_merged_by_coordinates=merged,unsettled_left_apart=left)
 for b in range(0,nt,CHUNK):FO[b:b+CHUNK]=rep[FO[b:b+CHUNK]]
 for a in [V,C,rep,FO,VC,TV]:release(a)
 clean=vinfo['vertices_without_edge']==vinfo['corners_unsettled']==0;made=np.zeros(nv,bool);new_order=arr('new_order','i8',(nv,));used=b=0
 while b<nt:
  end=min(nt,b+CHUNK)
  if clean:
   while end<nt and GO[end]==GO[end-1]:end+=1
   codes=GO[b:end];groups=np.r_[0,np.cumsum(codes[1:]!=codes[:-1])];keys=np.repeat(groups,3)*16+EO[b:end].ravel().astype(np.int64);vs=FO[b:end].ravel()[np.argsort(keys,kind='stable')]
  else:vs=np.asarray(FO[b:end]).ravel()
  u,first=np.unique(vs,return_index=True);keep=~made[u];new=u[keep][np.argsort(first[keep],kind='stable')];made[new]=True;new_order[used:used+len(new)]=new;used+=len(new);b=end
 del made;vinfo['vertex_order']="Open3D's numbering (first cube in triangle order, edge-number order inside a cube)" if clean else 'first use in the triangle order (fallback: some corners unsettled)';newid=arr('new_id','i8',(nv,))
 for b in range(0,used,CHUNK):newid[new_order[b:min(b+CHUNK,used)]]=np.arange(b,min(b+CHUNK,used))
 for a in [FO,GO,EO,new_order,newid]:release(a)
 header=f'ply\nformat binary_little_endian 1.0\ncomment Created by Open3D\nelement vertex {used}\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face {nt}\nproperty list uchar uint vertex_indices\nend_header\n';out_ply=Path(out_ply);out_ply.parent.mkdir(parents=True,exist_ok=True)
 with out_ply.open('wb') as f:
  f.write(header.encode('ascii'))
  for b in range(0,used,CHUNK):
   ix=new_order[b:min(b+CHUNK,used)];data=np.empty(len(ix),dtype=[('xyz','<f8',(3,)),('rgb','u1',(3,))]);data['xyz']=V[ix];data['rgb']=np.floor(np.clip(C[ix],0,1)*255+.5).astype('u1');f.write(data.tobytes())
  for b in range(0,nt,CHUNK):
   ff=FO[b:b+CHUNK];data=np.empty(len(ff),dtype=[('n','u1'),('indices','<u4',(3,))]);data['n']=3;data['indices']=newid[ff].astype('<u4');f.write(data.tobytes())
 result=dict(site=meta['site'],result=meta['result'],prior_scene=meta['prior_scene'],source='streamed_tsdf.merge with disk-backed arrays and chunked identical permutation/first-use ordering',source_sha256=sha(__file__),inherited_source_sha256=sha(Path(T.__file__)),depth_dir=meta['depth_dir'],box=meta['box'],tsdf=dict(voxel_m=T.VOXEL,sdf_trunc_m=T.TRUNC,depth_trunc_m=T.DTRUNC,views=meta['views'],vertices=used,triangles=nt),tiled=dict(layout=f"{lay['nx']}x{lay['ny']}",L_m=T.L,M_m=T.M,EPS_m=T.EPS,vertices=vinfo,triangle_order='one-piece (simulated unordered_map iteration order)'),seconds=dict(prep=meta['seconds'],tiles=sum(t['seconds']['all'] for t in tj),merge=time.monotonic()-start),merge_peak_host_gb=T.rss_peak_gb(),merge_cgroup_peak_gb=T.cg_peak_gb(),mesh_sha256=sha(out_ply),scientific_verdict=None);dump(out_json,result);print('BOUNDED_MERGE_COMPLETE',nt,used,flush=True);return result
if __name__=='__main__':
 cfg();start=time.monotonic();wd,out_ply,out_json=map(Path,sys.argv[1:4]);mode=sys.argv[4] if len(sys.argv)>4 else 'final'
 if mode=='coarse':T.VOXEL=.1;T.TRUNC=.5;T.L=T.VOXEL*16;T.M=2*T.L
 result=merge(wd,out_ply,out_json);timing(result['result']+'_'+mode+'_merge',start,implementation='bounded_merge')
