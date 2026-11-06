"""Inspection sheets live outside deliverable figure directories."""
from add6_common import *

def main():
 sheet=Image.new('RGB',(1200,1600),'white')
 for i,c in enumerate(AC['cases']):
  im=Image.open(F6/f"{c['id']}_section_check.png");im.thumbnail((590,790),Image.Resampling.LANCZOS);sheet.paste(im,((i%2)*600+(600-im.width)//2,(i//2)*800+(800-im.height)//2))
 out=W6/'verification';out.mkdir(exist_ok=True);sheet.save(out/'section_review.png',icc_profile=ICC)
 maps=Image.new('RGB',(1600,400),'white')
 for i,c in enumerate(AC['cases']):
  p,z,bounds=ortho(c['site']);im=orthocrop(z,bounds);line=pixels(xyuv(selected(c)['annotation_xyz']),bounds,im.size);draw_section(im,line);im.thumbnail((390,390),Image.Resampling.LANCZOS);maps.paste(im,(i*400+(400-im.width)//2,(400-im.height)//2))
 maps.save(out/'selection_map_review.png',icc_profile=ICC)
 sheet=Image.new('RGB',(1600,1600),'white')
 for i,c in enumerate(AC['cases']):
  first=c['id']+('_top_crop_noline_v2' if i==2 else '_top_crop_noline');prior=c['id']+('_wrong_dist_v2' if i==2 else '_oblique_noline' if i==3 else '_wrong_dist_noline')
  for j,name in enumerate([first,prior,c['id']+'_result_dist_FINALTRAIN_30000',c['id']+'_section_check']):
   p=F6/(name+'.png')
   if not p.exists():continue
   im=Image.open(p);im.thumbnail((390,390),Image.Resampling.LANCZOS);sheet.paste(im,(j*400+(400-im.width)//2,i*400+(400-im.height)//2))
 sheet.save(out/'panel_review.png',icc_profile=ICC);print(str(out),flush=True)
if __name__=='__main__':main()
