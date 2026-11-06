"""One visual inspection sheet, excluded from the requested delivery archives."""
from add4_common import *
canvas=Image.new('RGB',(1800,1280),'white')
for row,c in enumerate(AC['cases']):
    for col,tag in enumerate(['top_crop','oblique','wrong_gray','wrong_dist','truth_gray','section']):
        p=AF/f"{c['id']}_{tag}.png";im=Image.open(p).convert('RGBA');im.thumbnail((296,316),Image.Resampling.LANCZOS)
        x=col*300+(300-im.width)//2;y=row*320+(320-im.height)//2;canvas.paste(im,(x,y),im)
p=AW/'verification/presentation_preview.png';p.parent.mkdir(exist_ok=True);canvas.save(p,icc_profile=ICC)
print(str(p),flush=True)
