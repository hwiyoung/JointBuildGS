"""Small inspection copies; publication files remain unchanged."""
from common import *
from PIL import Image
import sys
dest=O/'validation/previews';dest.mkdir(parents=True,exist_ok=True)
for name in sys.argv[1:]:
 p=D/'figures'/name
 with Image.open(p) as im:
  im.thumbnail((2100,1600),Image.Resampling.LANCZOS);im.save(dest/p.name)
