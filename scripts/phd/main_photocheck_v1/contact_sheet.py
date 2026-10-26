"""Local visual QA overview; original 300 dpi figures remain untouched."""
from PIL import Image,ImageOps,ImageDraw
from common import *
def main():
    for prior in ['LoD2','ALS']:
        fs=sorted((D/'figures/projection').glob(f'*_{prior}_*.png'));canvas=Image.new('RGB',(1800,500*((len(fs)+2)//3)),'white')
        for i,f in enumerate(fs):
            im=Image.open(f);im.thumbnail((600,480));canvas.paste(im,((i%3)*600,(i//3)*500))
            ImageDraw.Draw(canvas).text(((i%3)*600+4,(i//3)*500+482),f.stem,fill='black')
        canvas.save(O/'tmp'/f'projection_{prior}.jpg')
if __name__=='__main__':main()
