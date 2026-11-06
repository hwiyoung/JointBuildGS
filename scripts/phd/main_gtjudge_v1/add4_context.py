"""User-requested building context and visible roof annotations; no score changes."""
from add4_common import *
from preservation import cameras
from add4_figures import camera_projection

def main(key,choice=None):
 c=case(key);rec=getcase(c);row=loadz(root_of(c)/'rows.npz');refpath=O/'reference'/c['site']/'dense.npz';ref=loadz(refpath);s=rec['section'];cam=cameras(c['site'])
 # The existing section XY is immutable. Drape its presentation annotation on original roof points.
 line=loadz(AW/'cases'/f"{c['id']}.npz")['line_xyz'].copy();roof=(~ref['wall'])&(abs(ref['normal'][:,2])>=.35);rp=ref['xyz'][roof];tree=cKDTree(rp[:,:2]);dd,ii=tree.query(line[:,:2],k=16,workers=2)
 near=dd<=.15;z=np.where(near,rp[ii,2],-np.inf).max(1);fallback=~near.any(1);z[fallback]=rp[ii[fallback,0],2]
 supported=dd[:,0]<=.35;line[supported,2]=z[supported];line[:,2]+=.03
 # Keep the whole existing case rectangle for c1, and add context around the short c2/c3 strips.
 box=np.array(rec['box_corners_uv']);extra=0 if key=='c1' else 8;lo=box.min(0)-extra;hi=box.max(0)+extra
 uv=xyuv(rp);inside=((uv>=lo)&(uv<=hi)).all(1);context=rp[inside];context=context[::max(1,len(context)//10000)]
 context=np.vstack([context,line]);aspect=1.25 if key=='c1' else .8
 gravity=PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json';up=np.array(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up)
 mp=meshpath(c,'mvs');V,F=read_surface(mp);sc=MeshScene(V,F);candidates=[];center=np.median(context,axis=0);direction=np.array(s['end'])-s['start'];direction/=np.linalg.norm(direction)
 for j,name in enumerate(cam.names):
  uv,dep,guard=cam.project(context,j)
  if not guard.all():continue
  low,high=uv.min(0),uv.max(0);mid=(low+high)/2;span=(high-low)*1.12;w=max(span[0],span[1]*aspect);h=w/aspect
  crop=[mid[0]-w/2,mid[1]-h/2,mid[0]+w/2,mid[1]+h/2]
  fits=crop[0]>=0 and crop[1]>=0 and crop[2]<=cam.w and crop[3]<=cam.h
  if not fits:continue
  d=line-cam.centres[j];rng=np.linalg.norm(d,axis=1);d/=rng[:,None];depth=sc.cast(np.broadcast_to(cam.centres[j],d.shape),d);visible=np.isfinite(depth)&(depth>=rng-.25)
  v=cam.centres[j]-line.mean(0);el=float(np.degrees(np.arcsin(np.clip(v@up/np.linalg.norm(v),-1,1))));perp=float(np.degrees(np.arcsin(np.clip(abs(v[:2]@direction)/np.linalg.norm(v[:2]),0,1))))
  candidates.append(dict(j=j,name=name,crop_xyxy_px=list(map(float,crop)),native_crop_size_px=[float(w),float(h)],elevation_deg=el,azimuth_deg=float(np.degrees(np.arctan2(-v[0],-v[1]))%360),perpendicular_error_deg=perp,visible_fraction=float(visible.mean()),unknown_fraction=float((~np.isfinite(depth)).mean()),context_aspect=aspect))
 del sc,V,F;gc.collect()
 # Readability revision: full context first, roof sight unobstructed, then angle and spatial resolution.
 candidates.sort(key=lambda v:(-round(v['visible_fraction'],1),max(35-v['elevation_deg'],0,v['elevation_deg']-80),abs(v['elevation_deg']-60),v['perpendicular_error_deg']))
 folder=AW/'context_candidates';folder.mkdir(exist_ok=True);dump(folder/f"{c['id']}.json",dict(candidates=candidates,line_xyz=line.tolist(),height_supported=supported.tolist(),context_bounds_uv=[lo.tolist(),hi.tolist()],sources=[proof(refpath),proof(mp)],scientific_verdict=None))
 if choice is not None:
  chosen=next(v for v in candidates if v['name']==choice);j=chosen['j'];camera=dict(rec['camera']);camera.update(chosen);camera.update(output_size_px=[1600,round(1600/aspect)],selection_fallback=True,angle_definition='camera_centre_to_section_centre_frozen_gravity',crop_policy='whole_case_context_user_revision',eligible_candidates=len(candidates),line_inside=True,inside_fraction=1.,centered_portrait_fits=None,crop_fits_source=True,selection_rule='user authorized wider building context and higher sight angle for visible roof; manually reviewed candidates')
  archive=PH.parent/'p0-audit/data/raw/uav/Images.zip'
  with zipfile.ZipFile(archive) as zz:data=zz.read(cam.members[j]);zi=zz.getinfo(cam.members[j])
  original=AW/'sources'/Path(cam.members[j]).name
  if not original.exists():original.write_bytes(data)
  im=Image.open(io.BytesIO(data));exif=im.getexif();ex=exif.get_ifd(34665) if 34665 in exif else {};camera.update(image_original=str(original),image_member=cam.members[j],image_sha256=hashlib.sha256(data).hexdigest(),crc32=zi.CRC,captured_at=ex.get(36867,exif.get(306)),R=cam.R[j].tolist(),t=cam.t[j].tolist(),centre=cam.centres[j].tolist(),photo_resampling='bicubic, full context; native dimensions recorded')
  rec.update(camera=camera,annotation_line_xyz=line.tolist(),line_altitude_rule='original dense reference roof point height at each fixed XY; +0.03m annotation offset; unsupported samples retain inherited plane',annotation_roof_support=supported.tolist(),annotation_reference=proof(refpath),context_revision='user requested whole building and roof legibility')
  dump(AW/'cases'/f"{c['id']}.json",rec);zold=loadz(AW/'cases'/f"{c['id']}.npz");zold['line_xyz']=line;savez(AW/'cases'/f"{c['id']}.npz",**zold);print('CONTEXT_CHOSEN',c['id'],chosen,flush=True);return
 sheet=Image.new('RGB',(1800,3*510),'white');draw=ImageDraw.Draw(sheet)
 for rank,v in enumerate(candidates[:12]):
  j=v['j']
  with zipfile.ZipFile(PH.parent/'p0-audit/data/raw/uav/Images.zip') as zz:data=zz.read(cam.members[j])
  W,H=440,round(440/aspect);H=min(H,470);W=round(H*aspect);im=Image.open(io.BytesIO(data)).convert('RGB').transform((W,H),Image.Transform.EXTENT,v['crop_xyxy_px'],Image.Resampling.BICUBIC)
  qcam=dict(parameters=cam.p.tolist(),R=cam.R[j].tolist(),t=cam.t[j].tolist(),crop_xyxy_px=v['crop_xyxy_px'],output_size_px=[W,H]);q,_=camera_projection(line,qcam);draw_section(im,q)
  x=(rank%4)*450;y=(rank//4)*510;sheet.paste(im,(x,y+30));draw.text((x+3,y+2),f"{rank} {v['name']} el {v['elevation_deg']:.0f} vis {v['visible_fraction']:.2f}",fill='black')
 sheet.save(folder/f"{c['id']}.png");print('CONTEXT_CANDIDATES',c['id'],len(candidates),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
