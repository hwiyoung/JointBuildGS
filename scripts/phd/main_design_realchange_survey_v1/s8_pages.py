"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 8: stack figure rows into report pages (PIL only). scientific_verdict: null."""
import sys
from PIL import Image
src=sys.argv[1]; dst=sys.argv[2]; names=sys.argv[3].split(','); W=int(sys.argv[4]) if len(sys.argv)>4 else 1700
ims=[Image.open('%s/%s.png'%(src,n)).convert('RGB') for n in names]
ims=[im.resize((W,int(im.height*W/im.width))) for im in ims]
H=sum(im.height for im in ims); out=Image.new('RGB',(W,H),'white'); y=0
for im in ims: out.paste(im,(0,y)); y+=im.height
out.save(dst)
