"""CPU previews for choosing a readable roof view, without outcome statistics."""
from add6_render import *

make_camera()
c=case('c3');p=W6/'c3_camera.json';record=json.loads(p.read_text());V,F=read_surface(meshpath(c,'mvs'));scene=MeshScene(V,F);sheet=Image.new('RGB',(1200,1125),'white')
for i,item in enumerate(record['candidates']):
 cam=dict(item['camera']);cam['output_size_px']=[300,375];rr,di=rays(cam,0,375);hit=scene.sc.cast_rays(scene.o3d.core.Tensor(rr));depth=hit['t_hit'].numpy();good=np.isfinite(depth);n=hit['primitive_normals'].numpy();light=.35+.65*abs((n*di/np.linalg.norm(di,axis=1)[:,None]).sum(1));rgb=np.full((len(depth),3),255,'u1');rgb[good]=np.rint(207*light[good,None]).astype('u1');im=Image.fromarray(rgb.reshape(375,300,3));a=annotation(c,cam,scene);draw_section(im,a['line_polyline_px']);sheet.paste(im,((i%4)*300,(i//4)*375))
out=W6/'verification/c3_camera_candidates.png';sheet.save(out);print(out,flush=True)
