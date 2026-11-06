"""Presentation addendum 9: unchanged rows, scores and geometry; isolated outputs."""
from add6_common import *
from PIL import ImageEnhance
A9=json.loads((C/'addendum9.json').read_text());assert sha(C/'addendum9.json')==json.loads((C/'addendum9.lock.json').read_text())['config_sha256']
W9=O/'addendum9';F9=D/'figures/addendum9';T9=D/'tables/addendum9'
for p in [W9,F9,T9]:p.mkdir(parents=True,exist_ok=True)

def proof(p):
 p=Path(p);q=W9/'hashes'/(hashlib.sha256(str(p).encode()).hexdigest()+'.json');st=stamp(p);old=json.loads(q.read_text()) if q.exists() else {}
 if old.get('stat')!=st:old=dict(path=str(p),sha256=sha(p),stat=st);dump(q,old)
 return {k:old[k] for k in ['path','sha256']}

def record(name,meta,sources=()):
 return dict(at=now(),scientific_verdict=None,crs='EPSG:25832',local_world_shift=SHIFT.tolist(),config_sha256=sha(C/'addendum9.json'),sources=[proof(p) for p in dict.fromkeys(map(str,sources))],runtime=dict(image=os.environ.get('GTJUDGE_IMAGE'),source_commit=os.environ.get('GTJUDGE_COMMIT'),python=sys.version,numpy=np.__version__),**meta)

def save9(im,name,meta,sources=()):
 p=F9/(name+'.png');im.convert('RGB').save(p,icc_profile=ICC,dpi=(300,300));dump(p.with_suffix('.json'),record(name,dict(size_px=list(im.size),text_in_figure=False,line_drawn=False,box_drawn=False,color_space='sRGB',**meta),sources));return p

def csv9(name,rows):
 p=T9/(name+'.csv');fields=list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
 return p

def data(c):
 root=root_of(c);return loadz(root/'rows.npz'),loadz(root/'stage1_cells.npz')['case_id']

def scorepath(c,m):return (AW/'keep_scores'/f"{c['site']}__{c['prior']}" if m=='always_keep_mesh' else root_of(c)/'distances')/(m+'.npz')

def scores(c,ms):return {m:loadz(scorepath(c,m),['row_s'])['row_s'] for m in ms}

def line9(key):
 if key=='c3_edge':return json.loads((W9/'edge_selected.json').read_text())
 c=case(key)
 if key=='c2':
  d=json.loads((D/'figures/addendum7/c2_hip_section_data.json').read_text());a=np.array(d['line']['A_local_xyz']);b=np.array(d['line']['Aprime_local_xyz']);s=dict(start=a[:2].tolist(),end=b[:2].tolist(),length_m=float(np.linalg.norm(b[:2]-a[:2])),half_width=.5);ann=np.array(getcase(c)['annotation_line_xyz'])
 else:
  d=selected(c);s=dict(d['section']);ann=np.array(d['annotation_xyz'])
  if key=='c3':
   a=np.array(s['start']);dr=(np.array(s['end'])-a)/s['length_m'];a,b=a+22.6*dr,a+25.6*dr;s=dict(start=a.tolist(),end=b.tolist(),length_m=3.,half_width=.5)
   row,lab=data(c);take=section_mask(row['xyz'],s)&(lab==2);z=float(np.median(row['xyz'][take,2]));ann=np.c_[np.linspace(a,b,257),np.full(257,z)]
 return dict(section=s,annotation_xyz=ann.tolist(),case=c['id'])

def box9(c,s,half=3):
 row,lab=data(c);P=row['xyz'];mask=section_mask(P,s)&(lab==c['case_id']);z=float(np.median(P[mask,2]));a=np.array(s['start']);b=np.array(s['end']);dr=(b-a)/s['length_m'];side=np.array([-dr[1],dr[0]]);xy=np.array([a-2*dr-half*side,b+2*dr-half*side,b+2*dr+half*side,a-2*dr+half*side]);return np.c_[xy,np.full(4,z)]

def circles(im,px,groups,colors,order,radius=3,alpha=.6):
 layer=Image.new('RGBA',im.size);draw=ImageDraw.Draw(layer)
 for k in order:
  for x,y in px[groups==k]:
   if -radius<=x<im.width+radius and -radius<=y<im.height+radius:draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(*bytes.fromhex(colors[str(k)][1:]),round(alpha*255)))
 return Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB')
