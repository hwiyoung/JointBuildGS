"""Freeze exact existing sections, local components and training camera choices."""
from add4_common import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from preservation import cameras

def main(key):
    c=case(key);out=AW/'cases'/f"{c['id']}.json"
    if out.exists() and json.loads(out.read_text()).get('camera',{}).get('angle_definition')=='camera_centre_to_section_centre_frozen_gravity':return
    root=root_of(c);row=loadz(root/'rows.npz');cells=loadz(root/'stage1_cells.npz');P=row['xyz']
    source=R/c['section_source'];meta=json.loads(source.read_text())
    s=dict(meta['rows'][c['section_index']] if 'section_index' in c else meta['section'])
    s['half_width']=.5;s['length_m']=float(np.linalg.norm(np.asarray(s['end'])-s['start']))
    m=cells['case_id']==c['case_id'];feature_path=None
    if 'feature' in c:
        feature_path=root/'preservation_features.npz';f=loadz(feature_path);m &= f[c['feature']]
    ids=np.flatnonzero(m);points,inv,counts=np.unique(P[ids],axis=0,return_inverse=True,return_counts=True)
    pairs=cKDTree(points).query_pairs(.6,output_type='ndarray');graph=coo_matrix((np.ones(len(pairs),'u1'),(pairs[:,0],pairs[:,1])),shape=(len(points),len(points)))
    n,labels=connected_components(graph,directed=False);sizes=np.bincount(labels,weights=counts)
    if 'feature' in c:k=int(np.argmax(sizes))
    else:
        a,b=np.asarray(s['start']),np.asarray(s['end']);d=(b-a)/np.linalg.norm(b-a);v=points[:,:2]-a;t=np.clip(v@d,0,s['length_m']);dist=np.linalg.norm(v-t[:,None]*d,axis=1)
        hits=np.bincount(labels[dist<=.5],weights=counts[dist<=.5],minlength=n)
        k=int(np.argmax(hits)) if hits.max()>0 else int(labels[np.argmin(dist)])
    selected=ids[labels[inv]==k];part=P[selected];q=xyuv(part);lo=q.min(0)-3;hi=q.max(0)+3
    band=section_mask(P,s)
    anchor=s.get('anchor_xyz');z=float(anchor[2]) if anchor else float(np.median(P[band,2]))
    ends=np.c_[np.asarray([s['start'],s['end']]),[z,z]];line=ends[0]+np.linspace(0,1,257)[:,None]*(ends[1]-ends[0])
    cam=cameras(c['site']);direction=(ends[1,:2]-ends[0,:2])/s['length_m'];center=ends.mean(0);candidates=[]
    gravity=PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json'
    up=np.array(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up)
    for j,name in enumerate(cam.names):
        uv,depth,guard=cam.project(line,j);inside=guard&(uv[:,0]>=0)&(uv[:,0]<cam.w)&(uv[:,1]>=0)&(uv[:,1]<cam.h)
        v=cam.centres[j]-center;fwd=cam.R[j,2];el=float(np.degrees(np.arcsin(np.clip(v@up/np.linalg.norm(v),-1,1))));az=float(np.degrees(np.arctan2(-v[0],-v[1]))%360)
        perp=float(np.degrees(np.arcsin(np.clip(abs(v[:2]@direction)/max(np.linalg.norm(v[:2]),1e-10),0,1))))
        mid=(uv.min(0)+uv.max(0))/2;span=(uv.max(0)-uv.min(0))*1.25;cw=max(span[0],span[1]*.8);ch=cw/.8
        centered=bool(mid[0]-cw/2>=0 and mid[0]+cw/2<=cam.w and mid[1]-ch/2>=0 and mid[1]+ch/2<=cam.h)
        elevgap=max(30-el,0,el-60);candidates.append(dict(j=j,name=name,elevation_deg=el,azimuth_deg=az,perpendicular_error_deg=perp,elevation_violation_deg=elevgap,line_inside=bool(inside.all()),inside_fraction=float(inside.mean()),centered_portrait_fits=centered,optical_axis_elevation_deg=float(np.degrees(np.arcsin(np.clip(-fwd@up,-1,1))))))
    valid=[v for v in candidates if v['line_inside'] and v['elevation_violation_deg']==0 and v['centered_portrait_fits']]
    chosen=min(valid,key=lambda v:(v['perpendicular_error_deg'],v['name'])) if valid else min(candidates,key=lambda v:(not v['line_inside'],not v['centered_portrait_fits'],1-v['inside_fraction'],v['elevation_violation_deg'],v['perpendicular_error_deg'],v['name']))
    j=chosen['j'];uv,_,_=cam.project(line,j);mid=(uv.min(0)+uv.max(0))/2;span=(uv.max(0)-uv.min(0))*1.25
    # Tight portrait field centred on the line, with a 25% margin.
    w=max(span[0],span[1]*.8);h=w/.8
    fits=bool(w<=cam.w and h<=cam.h)
    crop=[float(mid[0]-w/2),float(mid[1]-h/2),float(mid[0]+w/2),float(mid[1]+h/2)]
    archive=PH.parent/'p0-audit/data/raw/uav/Images.zip'
    with zipfile.ZipFile(archive) as zz:data=zz.read(cam.members[j]);zi=zz.getinfo(cam.members[j])
    original=AW/'sources'/Path(cam.members[j]).name;original.parent.mkdir(exist_ok=True)
    if not original.exists():original.write_bytes(data)
    image=Image.open(io.BytesIO(data));exif=image.getexif();ex=exif.get_ifd(34665) if 34665 in exif else {};captured=ex.get(36867,exif.get(306))
    # Retain the full exact distorted camera, not the reduced training pinhole camera.
    camera=dict(**chosen,angle_definition='camera_centre_to_section_centre_frozen_gravity',crop_policy='tight_line_1p25',selection_fallback=not bool(valid),eligible_candidates=len(valid),total_training_candidates=len(candidates),
        image_original=str(original),image_member=cam.members[j],image_sha256=hashlib.sha256(data).hexdigest(),archive=str(archive),crc32=zi.CRC,
        captured_at=captured,capture_time_timezone=None,calibration_model='FULL_OPENCV',parameters=cam.p.tolist(),R=cam.R[j].tolist(),t=cam.t[j].tolist(),centre=cam.centres[j].tolist(),source_size_px=[cam.w,cam.h],crop_xyxy_px=crop,crop_fits_source=fits,native_crop_size_px=[w,h],photo_resampling='bicubic to 1600x2000; native crop size disclosed',output_size_px=[1600,2000])
    sources=[source,root/'rows.npz',root/'stage1_cells.npz',BOXFILE,original,gravity]
    if feature_path:sources.append(feature_path)
    rec=dict(case=c,section=s,section_source=proof(source),section_reused=True,component_n_gt=len(selected),component_connectivity_m=.6,
        component_rule='largest feature component' if 'feature' in c else 'component with most target-case rows intersecting inherited 1m band',
        box_corners_uv=rect(lo,hi).tolist(),box_corners_xy=uvxy(rect(lo,hi)).tolist(),box_padding_m=3,
        line_xyz=ends.tolist(),line_altitude_rule='inherited anchor z or median reference height in 1m strip; annotation only',camera=camera,
        case_basis=json.loads((O/'targets_gt'/f"{c['site']}__{c['prior']}.json").read_text())['case_basis'],
        sources=[proof(p) for p in sources],scientific_verdict=None)
    assert rec['case_basis']=='normal_line'
    dump(out,rec);dump(AW/'cameras'/f"{c['id']}.json",dict(selected=camera,candidates=candidates,scientific_verdict=None))
    savez(AW/'cases'/f"{c['id']}.npz",component_row_ids=selected,line_xyz=line)
    print('ADD4_PREPARED',c['id'],chosen['name'],len(selected),flush=True)
if __name__=='__main__':main(sys.argv[1])
