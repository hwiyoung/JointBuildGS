"""Same A/A-prime and one-metre band, four states; no new section selection."""
from common import *
from PIL import Image,ImageDraw,ImageCms
from shapely.geometry import shape
from render import color
ICC=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
def clean(x):
 if isinstance(x,np.ndarray):return clean(x.tolist())
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 if isinstance(x,float) and not np.isfinite(x):return None
 return x
def main():
 c=cfg();old=json.loads(Path(c['sources']['section']).read_text());line=old['line'];a=np.array(line['A_local_xyz'][:2]);d=np.array(line['direction_unit_xy']);length=line['length_m']
 def band(P):
  q=P[:,:2]-a;s=q@d;off=abs(q[:,0]*d[1]-q[:,1]*d[0]);return s,(s>=0)&(s<=length)&(off<=.5)
 data=dict(line=line,strip_half_width_m=.5,coordinate_frame=c['coordinates'],source_section_sha256=sha(c['sources']['section']),scientific_verdict=None,states={})
 mvs=loadz(O/'work/mvs_building.npz')['xyz'];s,mask=band(mvs);data['mvs_points']=dict(s=s[mask],z=mvs[mask,2]);data['reference_points']=old['gt_points'];data['prior_sections']=old['surfaces']['prior'];data['mvs_mesh_sections']=old['surfaces']['mvs']
 t=loadz(c['sources']['target']);groups=loadz(O/'work/patch_groups.npz')['group'];s,mask=band(t['target']);mask&=np.isfinite(t['target']).all(1)&t['surface_exists'];data['targets']=dict(patch_index=np.flatnonzero(mask),s=s[mask],xyz=t['target'][mask],sigma=t['sigma'][mask],normal=t['normal'][mask],lower_xyz=t['target'][mask]-1.96*t['sigma'][mask,None]*t['normal'][mask],upper_xyz=t['target'][mask]+1.96*t['sigma'][mask,None]*t['normal'][mask],judge_region=t['judge_region'][mask],group33=groups[mask])
 W=1800;pad=55;plotw=W-2*pad;ploth=1300;gap=45;H=4*(ploth+2*pad)+3*gap;im=Image.new('RGB',(W,H),'#FCFCFA');panels=[]
 for j,it in enumerate(c['iterations']):
  g=loadz(O/'gaussians'/f'{it}.npz');s,mask=band(g['xyz']);keys=['opacity','origin','target_tag','judgment','group33','current_patch','init_id','target_xyz','target_sigma','normal_offset'];state={k:g[k][mask] for k in keys};state.update(s=s[mask],z=g['xyz'][mask,2],xyz=g['xyz'][mask]);data['states'][str(it)]=state
  tile=Image.new('RGB',(plotw,ploth),'#FCFCFA');draw=ImageDraw.Draw(tile);zmin,zmax=c['scope']['z_min'],c['scope']['z_max']
  def xy(s,z):return (float(s)/length*(plotw-1),(zmax-float(z))/(zmax-zmin)*(ploth-1))
  # Exact prior plane intersections, MVS points and reference points are unchanged.
  for poly in data['prior_sections']:
   if len(poly)>=2:draw.line([xy(*p) for p in poly],fill='#D85A30',width=2)
  for ss,zz in zip(data['mvs_points']['s'],data['mvs_points']['z']):
   x,y=xy(ss,zz);draw.ellipse([x-1,y-1,x+1,y+1],fill='#1D9E75')
  for p in data['reference_points']:
   x,y=xy(p['s'],p['z']);draw.ellipse([x-1,y-1,x+1,y+1],fill='#303030')
  for ss,lower,upper in zip(data['targets']['s'],data['targets']['lower_xyz'],data['targets']['upper_xyz']):draw.line([xy(ss,lower[2]),xy(ss,upper[2])],fill='#CEC9BC',width=1)
  for i in np.argsort(state['opacity'],kind='stable'):
   reg=state['judgment'][i];col=c['rendering']['colors'].get(str(reg),'#B4B2A9');col='#C2378A' if state['group33'][i]==1 else col;x,y=xy(state['s'][i],state['z'][i]);draw.ellipse([x-2,y-2,x+2,y+2],fill=col)
  y=pad+j*(ploth+2*pad+gap);im.paste(tile,(pad,y));drawall=ImageDraw.Draw(im);bl=2*plotw/length;drawall.line([(pad,y+ploth+25),(pad+bl,y+ploth+25)],fill='#333333',width=5)
  panels.append(dict(iteration=it,plot_bounds_px=[pad,y,pad+plotw,y+ploth],s_bounds_m=[0,length],z_bounds_m=[zmin,zmax],scale_bar_m=2,scale_bar_length_px=bl,vertical_exaggeration=(ploth/(zmax-zmin))/(plotw/length),gaussians=int(mask.sum()),gaussian_alpha_display='opaque position markers for checking; actual alpha preserved in JSON'))
 data['check_panels']=panels;dump(O/'figures/proc_section_data.json',clean(data));im.save(O/'figures/proc_section_check.png',icc_profile=ICC,dpi=(300,300));dump(O/'figures/proc_section_check.json',dict(panels=panels,text_in_figure=False,color_space='sRGB',size_px=list(im.size),source_sha256=sha(O/'figures/proc_section_data.json'),scientific_verdict=None))
 # Cell values are counts by fixed diagnostic lineage group, never resampled labels.
 bounds=shape(c['scope']['buffered_footprint']).bounds;res=.25;lo=np.floor(np.array(bounds[:2])/res)*res;hi=np.ceil(np.array(bounds[2:])/res)*res;nx,ny=np.ceil((hi-lo)/res).astype(int)
 for it in [0,30000]:
  g=loadz(O/'gaussians'/f'{it}.npz');take=~g['wall'];xy=g['xyz'][take,:2];idx=np.floor((xy-lo)/res).astype(int);groups=g['group33'][take];counts=np.zeros((ny,nx,3),'i4');np.add.at(counts,(idx[:,1],idx[:,0],groups),1);rgb=np.full((ny,nx,3),[252,252,250],dtype='u1');rgb[counts.sum(2)>0]=[180,178,169];rgb[counts[:,:,2]>0]=[216,90,48];rgb[counts[:,:,1]>0]=[194,55,138];tile=Image.fromarray(rgb[::-1]);width=1800;tile=tile.resize((width,round(width*ny/nx)),Image.Resampling.NEAREST);draw=ImageDraw.Draw(tile);px=5/(nx*res)*width;draw.line([(40,tile.height-40),(40+px,tile.height-40)],fill='#333333',width=6);path=O/'figures'/f'proc_top_{it}.png';tile.save(path,icc_profile=ICC,dpi=(300,300));savez(O/'figures'/f'proc_top_{it}.npz',counts=counts,origin_xy=lo,resolution_m=np.asarray(res,dtype='f4'))
  dump(path.with_suffix('.json'),dict(iteration=it,resolution_m=res,shape_y_x=[int(ny),int(nx)],origin_xy=lo.tolist(),channel_groups=['other','wrong','correction_control'],cell_value='number of roof Gaussian centres per lineage group; wrong takes paint precedence if mixed',y_axis='NPZ increasing north; PNG reversed rows',scale_bar=dict(m=5,length_px=px),gaussians=int(take.sum()),size_px=list(tile.size),text_in_figure=False,color_space='sRGB',source_sha256=sha(O/'gaussians'/f'{it}.npz'),scientific_verdict=None))
 print('SECTIONS_AND_MAPS_DONE',flush=True)
if __name__=='__main__':main()
