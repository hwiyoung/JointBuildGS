"""Text-free presentation panels from fixed input geometry and stored scores."""
from add4_common import *
from normal_line import values
from preservation import cameras
import cv2

def tops(key):
    c=case(key);rec=getcase(c);root=root_of(c);P=loadz(root/'rows.npz',['xyz'])['xyz'];lab=loadz(root/'stage1_cells.npz',['case_id'])['case_id']
    palette=dict(AC['case_colors']);paint_order=None;extra_sources=[]
    if (C/'addendum5.json').exists():
        override=json.loads((C/'addendum5.json').read_text());assert sha(C/'addendum5.json')==json.loads((C/'addendum5.lock.json').read_text())['config_sha256']
        palette=override['case_colors'];paint_order=override['paint_order_case_ids'];extra_sources=[C/'addendum5.json',C/'addendum5.lock.json']
    path,z,extent=ortho(c['site']);box=np.array(rec['box_corners_uv']);crop=aspect_bounds(box.min(0),box.max(0),1.25);uv=xyuv(P)
    for name,bounds in [('top',extent),('top_crop',crop)]:
        im=orthocrop(z,bounds);px=pixels(uv,bounds,im.size);radius=.125*im.width/(bounds[1]-bounds[0]);overlay=Image.new('RGBA',im.size);draw=ImageDraw.Draw(overlay)
        inside=(px[:,0]>=-radius)&(px[:,0]<im.width+radius)&(px[:,1]>=-radius)&(px[:,1]<im.height+radius)
        counts={str(k):int((inside&(lab==int(k))).sum()) for k in AC['case_colors']}
        ordered=np.flatnonzero(inside)[np.argsort(P[inside,2],kind='stable')]
        if paint_order is not None:ordered=np.concatenate([ordered[lab[ordered]==k] for k in paint_order])
        for i in ordered:
            col=palette.get(str(lab[i]))
            if col is None:continue
            rgb=tuple(bytes.fromhex(col[1:]));alpha=round(255*(.35 if lab[i]==0 else .55));x,y=px[i]
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(*rgb,alpha))
        im=Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB');pm=section_pixels(rec,bounds,im.size)
        draw_section(im,np.linspace(pm['A_px'],pm['Aprime_px'],257))
        savepng(im,AF/f"{c['id']}_{name}.png",dict(case=c['id'],panel=name,case_basis='stage1 normal_line',case_point_counts=counts,point_diameter_m=.25,point_alpha={'0':.35,'other':.55},case_colors=palette,paint_order_case_ids=paint_order,overlap_rule='class order first; higher-z last within a class' if paint_order is not None else 'higher-z circle takes foreground alpha',**pm),[path,root/'rows.npz',root/'stage1_cells.npz',AW/'cases'/f"{c['id']}.json"]+extra_sources)
    print('ADD4_TOPS',c['id'],flush=True)

def sections(key):
    c=case(key);rec=getcase(c);s=rec['section'];root=root_of(c);row=loadz(root/'rows.npz');take=section_mask(row['xyz'],s);pts=section_points(row['xyz'],s)
    methods=c['methods'];segments={};paths={};zs=[pts[:,1]];cache=AW/'sections'/c['id'];cache.mkdir(parents=True,exist_ok=True)
    for m in methods+(['judgment_mesh'] if c['id'].startswith('c4') else []):
        p=meshpath(c,m);paths[m]=p;cp=cache/f'{m}.npz'
        if cp.exists():seg=loadz(cp)['segments']
        else:
            V,F=read_surface(p);seg=section_segments(V,F,s);savez(cp,segments=seg);del V,F;gc.collect()
        # Clip every intersection to the requested segment endpoints.
        for j in range(2):
            outside=(seg[:,j,0]<0)|(seg[:,j,0]>s['length_m'])
            if outside.any():
                x=np.clip(seg[outside,j,0],0,s['length_m']);other=1-j;a=seg[outside,j].copy();b=seg[outside,other].copy();t=(x-a[:,0])/(b[:,0]-a[:,0]);seg[outside,j]=a+t[:,None]*(b-a)
        segments[m]=seg
        if len(seg):zs.append(seg[:,:,1].ravel())
    lo=min(float(z.min()) for z in zs if len(z));hi=max(float(z.max()) for z in zs if len(z));pad=max(.1,(hi-lo)*.05);bounds=[0,s['length_m'],lo-pad,hi+pad]
    metadata=[];panels=[]
    for rank,m in enumerate(methods):
        distfile=root/'distances'/f'{m}.npz';dist=loadz(distfile,['row_s'])['row_s'][take];v=values(dist,row['row_tau_m'][take]);color=np.where(~np.isfinite(dist),2,np.where(abs(dist)<=row['row_tau_m'][take],0,1))
        W,H=1200,120;scale=3;im=Image.new('RGBA',(W*scale,H*scale));draw=ImageDraw.Draw(im)
        def proj(q):
            q=np.asarray(q);return np.stack([q[...,0]/s['length_m']*W,(bounds[3]-q[...,1])/(bounds[3]-bounds[2])*H],-1)*scale
        def line(segs,col,dashed=False):
            for edge in proj(segs):
                if dashed:
                    length=np.linalg.norm(edge[1]-edge[0]);n=max(1,int(np.ceil(length/(4*scale))))
                    for k in range(0,n,2):draw.line([tuple(edge[0]+(edge[1]-edge[0])*k/n),tuple(edge[0]+(edge[1]-edge[0])*min(k+1,n)/n)],fill=col,width=scale)
                else:draw.line([tuple(x) for x in edge],fill=col,width=round(scale*1.6))
        line(segments[m],AC['method_colors'][m])
        if c['id'].startswith('c4') and m in ['FINALTRAIN_30000','A1']:line(segments['judgment_mesh'],AC['method_colors']['judgment_mesh'],True)
        for p,k in zip(proj(pts),color):
            rr=1.0*scale;draw.ellipse([p[0]-rr,p[1]-rr,p[0]+rr,p[1]+rr],fill=AC['gt_colors'][int(k)])
        bar=None
        if rank==0:
            x,y=24*scale,18*scale;lx=2/s['length_m']*W*scale;ly=1/(bounds[3]-bounds[2])*H*scale
            draw.line([(x,y),(x+lx,y)],fill='#16263D',width=2*scale);draw.line([(x,y),(x,y+ly)],fill='#16263D',width=2*scale)
            bar=dict(horizontal_m=2,vertical_m=1,horizontal_px=lx/scale,vertical_px=ly/scale,origin_px=[x/scale,y/scale])
        im=im.resize((W,H),Image.Resampling.LANCZOS);panels.append(im)
        annot_y=(bounds[3]-rec['line_xyz'][0][2])/(bounds[3]-bounds[2])*H
        meta=dict(case=c['id'],method=m,section=s,axis_bounds= bounds,vertical_exaggeration=(H/(bounds[3]-bounds[2]))/(W/s['length_m']),
            A_px=[0,annot_y],Aprime_px=[W,annot_y],box_corners_px=[[0,0],[W,0],[W,H],[0,H]],horizontal_end_meaning='A at x=0; Aprime at x=1200; Y is the annotation plane altitude',
            metric_population='reference rows inside this 1m-wide section strip only; not the whole scene',n_gt=len(pts),completeness_pct=v['within_pct'],far_hit_pct=v['far_hit_pct'],no_surface_pct=v['no_surface_pct'],scale_bar=bar,
            target_overlay='judgment_mesh' if c['id'].startswith('c4') and m in ['FINALTRAIN_30000','A1'] else None)
        src=[paths[m],distfile,root/'rows.npz',AW/'cases'/f"{c['id']}.json"]
        if meta['target_overlay']:src.append(paths['judgment_mesh'])
        savepng(im,AF/c['id']/f'section_{m}.png',meta,src);metadata.append(meta)
    combined=Image.new('RGBA',(1200,120*len(panels)))
    for k,im in enumerate(panels):combined.paste(im,(0,120*k))
    savepng(combined,AF/f"{c['id']}_section.png",dict(case=c['id'],rows=metadata,axis_bounds=bounds,A_px=metadata[0]['A_px'],Aprime_px=metadata[0]['Aprime_px'],box_corners_px=[[0,0],[1200,0],[1200,combined.height],[0,combined.height]]),[AF/c['id']/f'section_{m}.png' for m in methods]+[AF/c['id']/f'section_{m}.json' for m in methods])
    dump(cache/'summary.json',dict(rows=metadata,scientific_verdict=None));print('ADD4_SECTIONS',c['id'],len(pts),next(v['completeness_pct'] for v in metadata if v['method']=='FINALTRAIN_30000'),flush=True)

def camera_projection(P,camera):
    Q=np.asarray(P)@np.asarray(camera['R']).T+camera['t'];p=camera['parameters'];fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=p;x=Q[:,0]/Q[:,2];y=Q[:,1]/Q[:,2];r=x*x+y*y
    radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
    uv=np.c_[fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx,fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy]
    crop=camera['crop_xyxy_px'];W,H=camera['output_size_px'];uv=(uv-np.array(crop[:2]))/np.array([crop[2]-crop[0],crop[3]-crop[1]])*[W,H]
    return uv,Q[:,2]

def photos(key):
    c=case(key);rec=getcase(c);cam=rec['camera'];line=loadz(AW/'cases'/f"{c['id']}.npz")['line_xyz'];uv,_=camera_projection(line,cam)
    p=meshpath(c,'mvs');V,F=read_surface(p);sc=MeshScene(V,F);origin=np.asarray(cam['centre']);directions=line-origin;ranges=np.linalg.norm(directions,axis=1);directions/=ranges[:,None]
    depth=sc.cast(np.broadcast_to(origin,directions.shape),directions);visible=~np.isfinite(depth)|(depth>=ranges-.15)
    del sc,V,F;gc.collect()
    im=Image.open(cam['image_original']).convert('RGB').transform(tuple(cam['output_size_px']),Image.Transform.EXTENT,cam['crop_xyxy_px'],Image.Resampling.BICUBIC)
    draw_section(im,uv,visible[:-1]&visible[1:]);corners=np.c_[np.asarray(rec['box_corners_xy']),np.full(4,rec['line_xyz'][0][2])];bp,_=camera_projection(corners,cam)
    meta=dict(case=c['id'],camera=cam,A_px=uv[0].tolist(),Aprime_px=uv[-1].tolist(),box_corners_px=bp.tolist(),line_polyline_px=uv.tolist(),line_visibility=visible.tolist(),occlusion_rule='existing MVS mesh ray hit at least 0.15m in front of annotation; no hit means visibility unknown, drawn solid',unknown_visibility_count=int((~np.isfinite(depth)).sum()))
    savepng(im,AF/f"{c['id']}_oblique.png",meta,[cam['image_original'],AW/'cases'/f"{c['id']}.json",p]);dump(AW/'cameras'/f"{c['id']}_projection.json",meta)
    print('ADD4_PHOTO',c['id'],cam['name'],flush=True)

def sites():
    for site in SITES:
        p,z,bounds=ortho(site);im=orthocrop(z,bounds);cases=[case(x['id']) for x in AC['cases'] if x['site']==site]
        savepng(im,AF/f'site_{SHORT[site]}.png',dict(site=site,bounds_uv=bounds,cases={c['id']:section_pixels(getcase(c),bounds,im.size) for c in cases}),[p,BOXFILE]+[AW/'cases'/f"{c['id']}.json" for c in cases])
    p,z,bounds=ortho('overview');im=orthocrop(z,bounds,2400);draw=ImageDraw.Draw(im);boxes={}
    for site in SITES:
        b=BOXES[BIDS[site]];q=rect([b['eval_u'][0],b['eval_v'][0]],[b['eval_u'][1],b['eval_v'][1]]);px=pixels(q,bounds,im.size);draw.line([tuple(x) for x in np.vstack([px,px[:1]])],fill='white',width=round(im.width*.004));boxes[site]=px.tolist()
    start=[.05*im.width,.94*im.height];length=50*im.width/(bounds[1]-bounds[0]);draw.line([tuple(start),(start[0]+length,start[1])],fill='#16263D',width=10);draw.line([tuple(start),(start[0]+length,start[1])],fill='white',width=4)
    savepng(im,AF/'campus.png',dict(bounds_uv=bounds,experiment_box_corners_px=boxes,scale_bar=dict(length_m=50,length_px=length,start_px=start),A_px=None,Aprime_px=None,box_corners_px=boxes),[p,BOXFILE])
    print('ADD4_SITES_DONE',flush=True)

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='sites':sites()
    else:globals()[mode](sys.argv[2])
