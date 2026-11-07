"""Only the two requested c3 checks; status is looked up from stored rows."""
from add10_common import *
from matplotlib.path import Path as PolygonPath

def main():
 c=case('c3');row,lab=data(c);job=next(j for j in camera_jobs('c3') if j['id']=='a_closeup');cam=job['camera'];W,H=cam['output_size_px'];xx,yy=np.meshgrid(np.arange(W)+.5,np.arange(H)+.5);pixel=np.c_[xx.ravel(),yy.ravel()];ref=loadz(F10/'c3_a_closeup_refrow.npz')['row_id'];along,across=strip_coord(row['xyz']);central=(along>=23.2)&(along<=24.7)&(abs(across)<=.5)
 s=selected(c)['section'];a=np.array(s['start']);dr=(np.array(s['end'])-a)/s['length_m'];side=np.array([-dr[1],dr[0]]);z=float(np.median(row['xyz'][central,2]));poly=np.array([np.r_[a+ss*dr+tt*side,z] for ss,tt in [(23.2,-.5),(24.7,-.5),(24.7,.5),(23.2,.5)]]);px,_=project(poly,cam);roi=PolygonPath(px).contains_points(pixel).reshape(H,W)
 colors={k:np.array(list(bytes.fromhex(v[1:])),dtype='u1') for k,v in {'in':'#2EAA5A','far':'#D83730','none':'#3A3A3A'}.items()};checks=[]
 for m in ['mvs','FINALTRAIN_30000']:
  stem='c3_a_closeup_'+m;idx=loadz(F10/(stem+'_row.npz'))['row_id'];hit=np.asarray(Image.open(F10/(stem+'_hit.png')))>0;shade=np.asarray(Image.open(F10/(stem+'_shade.png'))).astype(float)/255;saved=loadz(stored_scores(c)[m],['row_s'])['row_s'];states=status(saved,row['row_tau_m']);kind=np.full((H,W),'background',dtype='<U16');kind[hit&(idx<0)]='unmapped_mesh';good=hit&(idx>=0);kind[good]=states[idx[good]];ghost=(~hit)&(ref>=0);kind[ghost]=states[ref[ghost]]
  im=np.full((H,W,3),255,'u1');im[hit&(idx<0)]=np.rint(220*shade[hit&(idx<0),None]).astype('u1')
  for k,color in colors.items():
   mask=good&(kind==k);im[mask]=np.rint(color*shade[mask,None]).astype('u1');mask=ghost&(kind==k);im[mask]=color
  p=F10/(stem+'_check.png');Image.fromarray(im).save(p,icc_profile=ICC,dpi=(300,300));savez(W10/(stem+'_composite_states.npz'),state=kind,central_projected_mask=roi)
  n=int(roi.sum());ct={k:int((roi&(kind==k)).sum()) for k in ['in','far','none','unmapped_mesh','background']};colored=sum(ct[k] for k in ['in','far','none']);rid=np.where(hit,idx,ref);valid=rid>=0;by_row=np.zeros((H,W),bool);by_row[valid]=central[rid[valid]]
  r=dict(method=m,central_region_pixels=n,central_counts=ct,percent_all_region={k:100*v/n for k,v in ct.items()},percent_status_pixels={k:100*ct[k]/colored if colored else None for k in ['in','far','none']},central_reference_row_selected_pixels=int(by_row.sum()),central_reference_row_status_counts={k:int((by_row&(kind==k)).sum()) for k in ['in','far','none']},central_roi_local_xyz=poly.tolist(),central_roi_px=px.tolist(),central_roi_definition='s23.2..24.7m, transverse +-0.5m, projected at median reference height; all pixel centers in polygon',composition=dict(colors={k:'#'+bytes(v).hex().upper() for k,v in colors.items()},unmapped_mesh_base='#DCDCDC',background='#FFFFFF',formula='saved row status base RGB multiplied by exported uint8 shade/255 on hit pixels; no mesh uses front reference disc status without shade'),photo_background=False,line_drawn=False,text_in_figure=False,size_px=[W,H])
  checks.append(r);dump(p.with_suffix('.json'),record(r,[F10/(stem+'_row.npz'),F10/(stem+'_hit.png'),F10/(stem+'_shade.png'),F10/'c3_a_closeup_refrow.npz',stored_scores(c)[m]]));print('ADD10_CHECK',m,ct,flush=True)
 dump(T10/'c3_middle_composite_pixels.json',record(dict(checks=checks)))
 fractions=[];polys=A10['window_polygons_base_photo_px'];masks={k:PolygonPath(v).contains_points(pixel).reshape(H,W) for k,v in polys.items()};masks['all_glazing']=np.logical_or.reduce(list(masks.values()))
 for name,mask in masks.items():
  n=int(mask.sum());r=dict(region=name,roi_pixels=n)
  for m in ['prior','mvs','FINALTRAIN_30000']:
   hit=np.asarray(Image.open(F10/('c3_a_closeup_'+m+'_hit.png')))>0;r[m+'_hit_pixels']=int((hit&mask).sum());r[m+'_hit_pct']=100*r[m+'_hit_pixels']/n
  fractions.append(r)
 dump(T10/'c3_window_mesh_pixels.json',record(dict(rows=fractions,roi_definition='same fixed inner glazing pixel polygons as numerical raw/reference density diagnostic',camera=cam)))

if __name__=='__main__':main()
