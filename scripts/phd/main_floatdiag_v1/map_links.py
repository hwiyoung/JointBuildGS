"""Recover exact displayed map rectangle bounds from the unchanged plot recipe."""
import json
import numpy as np
import matplotlib.pyplot as plt
from common import *
import build_visuals as B
from recount import load_eval

def capture(fig,key,meta,**kw):
    fig.canvas.draw();renderer=fig.canvas.get_renderer();box=fig.get_tightbbox(renderer)
    left,bottom,width,height=box.bounds;pad=.1
    left-=pad;bottom-=pad;width+=2*pad;height+=2*pad;rectangles=[]
    for ax in fig.axes:
        for c in meta['cases']:
            b=c['bbox'];lo=ax.transData.transform(b[:2])/fig.dpi;hi=ax.transData.transform(b[2:])/fig.dpi
            rectangles.append(dict(case=c['id'],x=(lo[0]-left)/width,y=1-(hi[1]-bottom)/height,
                w=(hi[0]-lo[0])/width,h=(hi[1]-lo[1])/height))
    save(DOC/'보기'/('mapareas_'+meta['site']+'.json'),dict(site=meta['site'],rectangles=rectangles,scientific_verdict=None))
    plt.close(fig);return key
B.save_figure=capture
for site in SITES:
    e,_=load_eval(site,'ALS');cases=json.loads((CFG/f'geometry_{site}_ALS.json').read_text())['cases'];B.map_site(site,e,cases)
