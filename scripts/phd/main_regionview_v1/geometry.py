"""Immutable LoD2 polygon identities and geometric, XY-only ALS association."""
import numpy as np
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from shapely.affinity import translate
from matplotlib.path import Path as MPath
from common import *

def newell(p):
    q=np.roll(p,-1,axis=0)
    n=np.sum(np.cross(p,q),axis=0);length=np.linalg.norm(n)
    if length<1e-10:raise ValueError('degenerate original LoD2 face')
    return n/length

def inside(poly,xy):
    out=np.zeros(len(xy),bool)
    for g in getattr(poly,'geoms',[poly]):
        if g.geom_type!='Polygon':continue
        v=MPath(np.asarray(g.exterior.coords)).contains_points(xy,radius=1e-9)
        for h in g.interiors:v&=~MPath(np.asarray(h.coords)).contains_points(xy,radius=-1e-9)
        out|=v
    return out

def plan_distance(poly,xy):
    """Distance to the closed projected polygon, including interior holes."""
    distance=np.full(len(xy),np.inf)
    for g in getattr(poly,'geoms',[poly]):
        if g.geom_type!='Polygon':continue
        for r in [g.exterior,*g.interiors]:
            pts=np.asarray(r.coords)
            for a,b in zip(pts[:-1],pts[1:]):
                v=b-a;t=np.clip((xy-a)@v/max(v@v,1e-30),0,1)
                distance=np.minimum(distance,np.linalg.norm(xy-a-t[:,None]*v,axis=1))
    distance[inside(poly,xy)]=0
    return distance

class Catalog:
    def __init__(self,ledger):
        self.ledger=ledger
        self.frame=ledger.json(REPO/'configs/phd/main_prep_measure_v1/prep_v5.json')['frame']
        # Original CityGML polygons, same parser/IDs used by the inherited patch stores.
        survey=PH/'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1/s1/lod2_buildings.json'
        self.buildings={b['id']:b for b in ledger.json(survey,sealed=True)}
        aliases={}
        for b in ledger.json(W/'inputs/lod2_context_buildings.json',sealed=True):
            if b['id'] not in self.buildings:self.buildings[b['id']]=b
            original=self.buildings[b['id']]
            for typ in ['roof','wall','ground']:
                byid={p['id']:p for p in original['surfaces'][typ]}
                for p in b['surfaces'][typ]:
                    canonical=p['id'].removesuffix('_poly')
                    if canonical in byid:
                        old=byid[canonical]
                        assert old['ext']==p['ext'] and old['holes']==p['holes'],'polygon alias geometry differs'
                        aliases[p['id']]=canonical
                    elif p['id'] not in byid:
                        original['surfaces'][typ].append(p)
        self.faces={};self.by_building={}
        shift=np.asarray(self.frame['world_shift_xyz_m']);zb=self.frame['z_bridge_als_lod2_m']
        for bid,b in self.buildings.items():
            ground=unary_union([Polygon(np.asarray(p['ext'])[:,:2]-shift[:2],
                [np.asarray(h)[:,:2]-shift[:2] for h in p['holes'] if len(h)>=4]).buffer(0) for p in b['surfaces']['ground']])
            rows=[]
            for typ in ('roof','wall'):
                for p in b['surfaces'][typ]:
                    ext=np.asarray(p['ext'],float)-shift+[0,0,zb]
                    holes=[np.asarray(h,float)-shift+[0,0,zb] for h in p['holes'] if len(h)>=4]
                    if len(ext)<4:continue
                    n=newell(ext)
                    e1=ext[1]-ext[0];e1/=np.linalg.norm(e1);e2=np.cross(n,e1)
                    origin=ext[0];project=lambda q:np.column_stack([(q-origin)@e1,(q-origin)@e2])
                    planar=Polygon(project(ext),[project(h) for h in holes]).buffer(0)
                    centre=ext[:-1].mean(0)
                    if typ=='wall':
                        nh=n[:2]/max(np.linalg.norm(n[:2]),1e-12)
                        outside=ground.covers(Point(centre[:2]+.25*nh));inward=ground.covers(Point(centre[:2]-.25*nh))
                        if outside and not inward:n=-n
                    elif n[2]<0:n=-n
                    direction=['동','북','서','남'][int(np.floor((np.degrees(np.arctan2(n[1],n[0]))+45)%360/90))]
                    rows.append(dict(gml=p['id'],building=bid,type=typ,kind=1 if typ=='roof' else 2,normal=n,
                        ext=ext,holes=holes,area=float(planar.area),centre=centre,direction=direction,
                        poly=Polygon(ext[:,:2],[h[:,:2] for h in holes]).buffer(0),ground=ground))
            roofs=sorted([r for r in rows if r['type']=='roof'],key=lambda r:(-r['area'],r['gml']))
            for i,r in enumerate(roofs,1):r['name']=f'지붕 {i}';r['number']=i
            for direct in ['남','동','북','서']:
                walls=sorted([r for r in rows if r['type']=='wall' and r['direction']==direct],key=lambda r:(r['centre'][0],r['centre'][1],r['centre'][2],r['gml']))
                for i,r in enumerate(walls,1):r['name']='벽 '+direct+(f' {i}' if len(walls)>1 else '');r['number']=i
            for r in rows:
                if r['gml'] in self.faces:assert self.faces[r['gml']]['building']==bid
                self.faces[r['gml']]=r
            self.by_building[bid]=rows
        self.aliases=aliases

    def context(self,site=None,tile=None,sealed=False):
        if site:
            meshdir=DR/'s02_box'/site
            sr=S0/'s61/box'/site/'LoD2/summary.json'
        else:
            meshdir=W/'holdout/internal/prior_tiles'/tile
            sr=W/'holdout/internal/registration'/tile/'LoD2/summary.json'
        tab=self.ledger.json(meshdir/'lod2_surfaces.json',sealed=sealed)['surfaces']
        delta=np.array(self.ledger.json(sr,sealed=sealed)['registration']['shift_applied'])
        out={}
        for row in tab:
            r=self.faces[self.aliases.get(row['gml'],row['gml'])]
            assert r['building']==row['building']
            out[int(row['ext'])]=dict(r,ext=r['ext']+delta,holes=[h+delta for h in r['holes']],centre=r['centre']+delta,
                poly=Polygon((r['ext']+delta)[:,:2],[(h+delta)[:,:2] for h in r['holes']]).buffer(0),
                ground=translate(r['ground'],xoff=delta[0],yoff=delta[1]),source_ext=row['ext'])
        return out

def associate(d,prior,faces,missing_policy):
    n=len(d['area']);assignment=np.full(n,'',dtype='<U120');status=np.full(n,'unassigned',dtype='<U60')
    building=np.asarray(d['building'],dtype='<U96').copy();dist=np.full(n,np.nan);ties=np.zeros(n,bool)
    if prior=='LoD2':
        for ext in np.unique(d['surf']):
            mask=d['surf']==ext
            if int(ext) not in faces:status[mask]='original_face_missing';continue
            f=faces[int(ext)];assert np.all(building[mask]==f['building'])
            assignment[mask]=f['gml'];status[mask]='original_face_id';dist[mask]=0
    else:
        roofs=[f for f in faces.values() if f['type']=='roof' and not f['poly'].is_empty]
        # Direct user clarification: unique GroundSurface plan containment first;
        # if outside all plans, exactly one plan within 1 m. Never use height.
        missing=building==''
        if missing.any() and missing_policy=='unique_plan_building':
            owners=np.flatnonzero(missing);candidate=np.full(len(owners),'',dtype='<U96');count=np.zeros(len(owners),int)
            near_candidate=candidate.copy();near_count=count.copy()
            for bid in sorted({f['building'] for f in roofs}):
                ground=next(f['ground'] for f in roofs if f['building']==bid)
                dd=plan_distance(ground,d['centre'][owners,:2]);contained=dd<=1e-10;near=dd<=1+1e-10
                count+=contained;candidate[contained]=bid;near_count+=near;near_candidate[near]=bid
            good=count==1;fallback=(count==0)&(near_count==1)
            building[owners[good]]=candidate[good];building[owners[fallback]]=near_candidate[fallback]
            status[owners[(count==0)&(near_count==0)]]='no_building_plan_within_1m'
            status[owners[(count>1)|((count==0)&(near_count>1))]]='ambiguous_building'
            status[owners[good|fallback]]='unique_plan_building'
        else:status[missing]='building_id_missing'
        for bid in np.unique(building[building!='']):
            ids=np.flatnonzero(building==bid);best=np.full(len(ids),np.inf);which=np.full(len(ids),'',dtype='<U120');nt=np.zeros(len(ids),int)
            for f in sorted([f for f in roofs if f['building']==bid],key=lambda f:f['gml']):
                dd=plan_distance(f['poly'],d['centre'][ids,:2]);better=dd<best-1e-10;equal=np.isclose(dd,best,atol=1e-10,rtol=0)
                nt[equal]+=1;nt[better]=1;which[better]=f['gml'];best[better]=dd[better]
            valid=best<=1+1e-10
            assignment[ids[valid]]=which[valid];dist[ids]=best;ties[ids]=nt>1
            original=status[ids].copy();status[ids[valid]]='same_building_nearest_roof'
            status[ids[valid&(original=='unique_plan_building')]]='unique_plan_building_then_roof'
            status[ids[~valid]]='no_same_building_roof_within_1m'
    return dict(face=assignment,assigned_building=building,association_status=status,face_distance_m=dist,face_tie=ties)
